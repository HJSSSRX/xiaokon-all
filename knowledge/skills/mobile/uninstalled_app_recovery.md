---
tags: [mobile, android, ios, uninstalled, deleted_app, app_recovery, packages_xml,
  usagestats, knowledgec, recent_images, carving, mobile_forensics]
tools: [aleapp, ileapp, sleuthkit, foremost, photorec, strings, grep, sqlite3, aapt,
  androguard, plaso]
category: mobile_forensics
difficulty: medium
source: kb_seed_2026-05-07
verified: false
---

# 已删除 App 的痕迹挖掘

> **核心心法**：App 卸载只删了"入口"，痕迹分布在 N 个层面。普通用户点删图标根本删不掉痕迹。要真"擦干净"必须 `pm uninstall -k` + 清缓存 + factory reset + 多次写入覆盖物理扇区。

## 0. 先确认卸载形态

| 形态 | 残留多少 |
|---|---|
| **图标长按删除** | 几乎全留（packages-backup、usagestats、缩略图、缓存、媒体索引、APK 安装包都在） |
| **设置→应用→卸载** | 比上面少一点（cache 通常被清），但元数据全留 |
| **`pm uninstall -k`** | **保留数据卸载**，`/data/data/{pkg}/` 整个目录都还在 ★★★ 立刻 grep 这条 |
| **`pm uninstall`** + 清缓存** | data 目录清，但系统级元数据 + SD 卡数据全留 |
| **Factory reset** | userdata 分区被 trim/wipe，但 flash GC 未完成期间仍可能 carving |
| **多次写入覆盖** | 物理层都没了，只能靠流量/云端/其他设备 |

---

## 1. Android 九层残留排查清单

### 第 1 层：包管理器历史 ★★★（最不容易被清）

| 文件 | 内容 |
|---|---|
| `/data/system/packages.xml` | 当前已装 |
| `/data/system/packages-backup.xml` | **上一次状态备份，含已卸载 app 的最后一次记录** |
| `/data/system/packages.list` | 包名 + uid |
| `/data/system/users/0/package-restrictions.xml` | 禁用/隐藏 app 列表，含 stopped/disabled |
| `/data/system/uiderrors.txt` | 进程崩溃 |
| `/data/system/appops.xml` | **权限使用记录，卸载后仍保留** |
| `/data/system/usagestats/0/daily/`, `weekly/`, `monthly/`, `yearly/` | **每天用了多久，卸载后保留** |

```bash
grep -hoE 'name="[^"]+"' /data/system/packages*.xml | sort -u | head
grep -E "<package " /data/system/packages-backup.xml
# usagestats 是 XML/protobuf 二进制，用 strings 暴力扫
strings /data/system/usagestats/0/daily/* | grep -i "{包名特征}"
# 或用：https://github.com/p4n74/usagestats-parser
```

### 第 2 层：APK 安装包残留 ★★★

| 路径 | 说明 |
|---|---|
| `/data/app/{pkg}-{N}/base.apk` | 卸载通常删除 |
| `/data/app/vmdl*.tmp` | 安装临时文件，时常忘清 |
| `/data/local/tmp/*.apk` | adb push 装的常留 |
| `Download/`, `tencent/MicroMsg/Download/`, `Android/data/{im_pkg}/files/Download/` | **从聊天/浏览器下的安装包，卸载与否都不删** |
| `Pictures/Screenshots/` | 安装/使用过程截屏，文件名常含包名 |

```bash
find {extract} -iname "*.apk" 2>/dev/null
aapt dump badging unknown.apk | head -5
# 或 androguard
python -c "from androguard.misc import APK; a=APK('x.apk'); print(a.get_package(), a.get_app_name())"
```

### 第 3 层：日志类 ★★★（嫌疑人最难清理）

| 路径 | 内容 |
|---|---|
| `/data/log/`, `/data/misc/logd/` | logcat 持久化（仅部分 ROM 开 persist.log） |
| `/data/system/dropbox/` | 系统异常 + ANR + tombstone |
| `/data/tombstones/` | native crash, 含进程名 = 包名 |
| `/data/anr/` | ANR trace, 含进程名 |
| `/data/system_ce/0/recent_tasks/` | 最近任务列表，卸载后可能仍有 |
| `/data/system_ce/0/recent_images/` | **★ 最近任务缩略图，强证据，能直接看到 app UI ★** |

`recent_images/` 是大杀器：即使 app 卸载、缓存清空，最近任务缩略图（PNG）还在，能直接看到 app UI 截图。

```bash
ls -la /data/system_ce/0/recent_images/
file /data/system_ce/0/recent_images/*.png
```

### 第 4 层：媒体扫描索引 ★★

```
/data/data/com.android.providers.media/databases/external.db, internal.db
```

`files` 表保留所有曾被扫描的文件路径，**含已删除文件路径**。

```sql
SELECT _data, date_added, date_modified
FROM files
WHERE _data LIKE '%{包名片段}%'
ORDER BY date_added DESC;
```

例：能看到 `tencent/MicroMsg/{hash}/voice/.../{msg_id}.amr` → 说明微信用过、用了语音功能。

### 第 5 层：缩略图 / 缓存类 ★★

```
DCIM/.thumbnails/, Pictures/.thumbnails/
.thumbdata3-*, .thumbdata4--*
```

缩略图保留被删原图证据。原图删了 `.thumbdata*` 里仍有 JPEG 流可 carving：

```bash
foremost -t jpg -i .thumbdata4--1967290299
# 或 strings 检查路径
strings .thumbdata4--1967290299 | grep -iE "/(DCIM|Pictures|tencent)/"
```

### 第 6 层：账号 / 同步框架 ★★

```
/data/system_ce/0/accounts_ce.db
/data/system_de/0/accounts_de.db
/data/system/sync/
```

- 即使 app 卸载，**账号条目可能仍在**（`account_type` 字段是包名风格字符串，如 `com.tencent.mm.account`）
- 直接看出装过哪个邮箱客户端、IM、云盘

```sql
SELECT * FROM accounts;
SELECT name, type FROM accounts WHERE type LIKE '%{包名片段}%';
```

### 第 7 层：网络流量层 ★★★

卸载完全不影响这层。
- pcap 里：DNS 查询 → 域名 → app 反查（`mp.weixin.qq.com` ↔ 微信、`graph.facebook.com` ↔ FB 系）
- TLS SNI / 证书 CN
- 端口 + 通信模式（每 30s 心跳 1 字节 → IM 类）

如果案件有同时段流量包，就算手机端啥都没了也能证明用过。

### 第 8 层：其他 app 留下的间接痕迹 ★★

| 来源 | 留什么 |
|---|---|
| 输入法（搜狗/百度）`词库.db` | 输入过的 app 名、人名、关键词 |
| 系统剪贴板历史（部分 ROM） | app 内复制内容 |
| 浏览器历史 | 访问 app 官网/下载页/web 版 |
| 通话/短信 | 验证码短信发件人能反推 app（"XX 验证码 1234"） |
| 相册 EXIF / 截屏文件名 | `Screenshot_2026...com.tencent.mm.png` 含包名 |
| 文件管理器 thumbcache | 浏览过的文件预览 |

### 第 9 层：物理层（终极兜底） ★★★

卸载只是元数据级删除，物理扇区还在。

```bash
# Sleuthkit
fls -r -d {userdata.img}        # 列已删除
icat {img} {inode} > recovered

# 全类型 carving
foremost -i {userdata.img}
photorec {userdata.img}

# 暴力 strings 扫包名
strings -e l {userdata.img} | grep -aE "com\.[a-z]+\.[a-z]+" | sort -u | head -100

# 暴力扫特征字符串（聊天内容、用户名等）
strings -e l {userdata.img} | grep -i "{特征关键字}"
```

ext4 删除清 inode 但 data block 在被复用前完整保留几小时到几天。flash 的 wear leveling 让残留更久。

---

## 2. iOS 已删除 App 的痕迹

iOS 沙盒严、卸载更彻底，但仍有：

| 来源 | 内容 |
|---|---|
| `/private/var/mobile/Library/MobileInstallation/LastLaunchServicesMap.plist` | App 历史启动记录 |
| `/private/var/mobile/Library/Caches/com.apple.LaunchServices-*.csstore` | LaunchServices 缓存，**含已卸载 app 的 bundle ID** |
| `/private/var/mobile/Library/Application Support/com.apple.spotlight/` | Spotlight 索引 |
| `/private/var/mobile/Library/CoreDuet/Knowledge/knowledgeC.db` | **★ iOS 大杀器 ★** 每个 app 的使用时间、位置、屏幕亮起、Bundle ID（含已删除） |
| iCloud 备份 (`Manifest.db`) | 即使本机删了，云端可能还在 |
| Health DB `healthdb_secure.sqlite` | 步数/心率数据有时附带 app source |
| Notification Center | 最近通知含 bundle ID |
| `interactionC.db` | 与 app 的交互历史 |

iOS 排查首选三件套：**`knowledgeC.db` + `LaunchServices` plist + iCloud 备份对比**。

```sql
-- knowledgeC.db
SELECT ZOBJECT.ZSTREAM_NAME,
       ZOBJECT.ZVALUE_STRING,
       datetime(ZOBJECT.ZSTART_DATE + 978307200, 'unixepoch') AS start_time,
       datetime(ZOBJECT.ZEND_DATE   + 978307200, 'unixepoch') AS end_time
FROM ZOBJECT
WHERE ZSTREAM_NAME IN ('/app/usage', '/app/inFocus', '/app/install')
ORDER BY ZSTART_DATE DESC
LIMIT 200;
```

---

## 3. 决策树（拿到 "app 已删" 案件）

```
确认 app 真的被卸载？
   │
   ├─ 跑 ALEAPP / iLEAPP 全自动报告
   │   └ 看 "Installed Apps" / "App Usage" 模块（含历史）
   │
   ├─ 第 1 层 packages-backup.xml + usagestats + appops
   │   └ 找到包名 + 版本 + 使用时长 → 锁定身份
   │
   ├─ 第 3 层 recent_images + tombstones + dropbox
   │   └ 截图直接复原 app UI
   │
   ├─ 第 4 层 media provider files 表
   │   └ 文件路径含包名 → 用过哪些功能
   │
   ├─ 第 7 层 流量包
   │   └ DNS / SNI 反查
   │
   ├─ 第 8 层 间接痕迹（输入法词库、截图名、短信）
   │
   └─ 兜底：第 9 层 strings / carving 物理层
```

---

## 4. 实用命令速查

```bash
# 一行扫整个手机镜像找包名残留（按出现频率排）
strings -e l {userdata.img} | grep -aoE "com\.[a-z][a-z0-9_]+\.[a-z][a-z0-9_.]+" \
  | sort | uniq -c | sort -rn | head -100

# 列出所有 packages.xml/-backup.xml 里出现过的包名
grep -hoE 'name="[^"]+"' /data/system/packages*.xml | sort -u

# usagestats 文件粗看
for f in /data/system/usagestats/0/daily/*; do
  echo "=== $f ==="
  strings "$f" | grep -iE "{包名特征}"
done

# .thumbdata carve JPEG
foremost -t jpg -i DCIM/.thumbnails/.thumbdata4--1967290299

# APK 反查
aapt dump badging unknown.apk | head -5
python -c "from androguard.misc import APK; a=APK('x.apk'); print(a.get_package(), a.get_app_name(), a.get_main_activity())"

# 媒体库 SQL
sqlite3 external.db "SELECT _data, datetime(date_added,'unixepoch') FROM files WHERE _data LIKE '%mm%' ORDER BY date_added DESC LIMIT 50"

# 最近任务缩略图
ls -la /data/system_ce/0/recent_images/
# Windows 端转 PNG 看
magick mogrify -format png /data/system_ce/0/recent_images/*

# iOS knowledgeC.db
sqlite3 knowledgeC.db ".schema ZOBJECT"
```

---

## 5. 常见坑

- **Factory reset 之后**：userdata 被擦但 flash GC 未完成期间，物理 carving 仍可能找回片段
- **`pm uninstall -k`**：保留数据卸载，`/data/data/{pkg}/` 完整在！这条线索一定要先 check
- **存储卡 SD**：很多 app 把数据放 `/sdcard/Android/data/{pkg}/`，**Android 11+ 才会跟随卸载删除**，旧版本 SD 数据全留
- **微信/QQ/Telegram 等 IM 卸载**：聊天附件常留在 `tencent/MicroMsg/`、`tencent/MobileQQ/`、`Telegram/` 公共目录
- **不要漏 `Android/data/` 与 `Android/obb/`**：scoped storage 时代 app 数据移到这里
- **`recent_images/` 必扫** —— 一张缩略图能省 2 小时挖掘
- **第三方手机助手** (MIUI/EMUI/ColorOS)：自带"应用管理→已卸载"列表，看一眼省事
- **小米 / 华为云空间**：用户登录账号后云端自动同步，**云端可能保留卸载前完整数据**
- **iOS 必须解密备份**：未加密备份才能直接读 sqlite；加密备份要 GPU 爆破或从 Keychain 取

---

## 6. 串联到取证报告

最有说服力的"用过 X app"证据链：

```
1. packages-backup.xml 里出现包名 X        （元数据层）
2. usagestats/0/daily/* 显示日均使用 N 分钟  （行为层）
3. recent_images/ 里有 X 的 UI 截图         （视觉层）
4. media provider files 表含 X 路径文件     （文件层）
5. 流量包里有 X 的域名/SNI                  （网络层）
6. 物理 carving 出 X 数据库片段             （物理层）
```

任意 3 层互相印证 = 强证据；只有 1 层 = 可疑；6 层全有 = 铁证。
