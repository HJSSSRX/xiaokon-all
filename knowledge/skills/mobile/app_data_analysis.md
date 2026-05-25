---
tags: [mobile, android, ios, app_forensics, browser_history, search_history, im, payment,
  knowledgec, usagestats, input_method, methodology, mobile_forensics]
tools: [sqlite3, plutil, aapt, strings, grep, python]
category: mobile_forensics
difficulty: medium
source: kb_seed_2026-05-07
verified: false
related: [device_basic_info.md, uninstalled_app_recovery.md, geolocation_forensics.md,
  timestamps_reference.md, apk_permission_analysis.md, anti_forensics_and_misleading.md]
---

# 手机 App 通用分析 — 浏览/搜索/包名/行为足迹

> **核心心法**：
> - **元层（meta）**：app 是什么 — 包名、版本、安装时间、签名、权限
> - **行为层（behavior）**：app 干了什么 — 浏览、搜索、聊天、买卖
>
> 元层快（看 `packages.xml` 即可），行为层慢（每 app 数据库结构不同）。
> **不要只从主屏图标找 app**，要从 `packages.xml` 列**完整安装清单**，再按嫌疑类别逐个挖。漏一个 app 可能漏一条证据链。

## 0. 元层：所有 app 一览

### Android：完整 app 清单
```bash
# ⚠️ packages.xml 中 ft / it 是 HEX 字符串
python3 << 'EOF'
import xml.etree.ElementTree as ET, datetime as dt
for pkg in ET.parse('/data/system/packages.xml').findall('package'):
    ft = int(pkg.get('ft','0'),16)/1000   # 首次安装 ms
    it = int(pkg.get('it','0'),16)/1000   # 上次更新 ms
    print(dt.datetime.utcfromtimestamp(ft).isoformat(),
          pkg.get('installer','sideload'), pkg.get('name'))
EOF
```

| 字段 | 含义 |
|---|---|
| `name` | 包名 |
| `codePath` | APK 路径 |
| `ft` (hex) | 首次安装时间 ms |
| `it` (hex) | 上次更新 ms |
| `installer` | 安装来源（`com.android.vending`=Play / `null`=sideload / 应用宝等） |
| `userId` | UID（Linux 用户隔离） |
| `<perms>` | 已声明权限 |

**用户可见 vs 系统隐藏**：仅有 `LAUNCHER` intent 的 app 桌面才显示。

### iOS：app 清单

| 来源 | 作用 |
|---|---|
| `/private/var/mobile/Containers/Bundle/Application/{UUID}/{App}.app/` | 主体 |
| `/private/var/mobile/Containers/Data/Application/{UUID}/` | 沙箱数据 |
| `/private/var/installd/Library/MobileInstallation/LastLaunchServicesMap.plist` | 包名 → 沙箱 UUID 映射（关键） |
| `/private/var/db/MobileContainerManager/containers.db` | 容器关系 |
| 各 `.app/Info.plist` | bundle id、版本、最低 iOS、权限说明 |

```bash
plutil -p LastLaunchServicesMap.plist | grep -E "BundleID|Path"
plutil -p {App}.app/Info.plist | grep -iE "CFBundleIdentifier|CFBundleVersion|MinimumOSVersion"
```

⚠️ iOS 沙箱 UUID 每次重装变，必须用 `LastLaunchServicesMap.plist` 锁当前映射。

---

## 1. 行为层：八大数据类型 × 路径速查

### 1.1 浏览器历史 ★★★

| 浏览器 | Android | iOS |
|---|---|---|
| **Chrome** | `com.android.chrome/app_chrome/Default/History` | `com.google.chrome.ios/.../Chrome/Default/History` |
| **Edge** | `com.microsoft.emmx/app_chrome/Default/History` | 同 Chrome 结构 |
| **Firefox** | `org.mozilla.firefox/files/places.sqlite` | 同 |
| **Samsung Browser** | `com.sec.android.app.sbrowser/databases/SBrowser.db` | — |
| **小米浏览器** | `com.android.browser/databases/browser2.db` | — |
| **UC** | `com.UCMobile/databases/Browser.db` | `com.ucweb...` |
| **QQ 浏览器** | `com.tencent.mtt/databases/` | — |
| **Safari** | — | `Library/Safari/History.db` |
| **微信内嵌浏览器** | 不留独立 history，但 cache 留 URL |

```sql
-- Chrome / Chromium 内核
SELECT datetime(last_visit_time/1000000-11644473600,'unixepoch') AS visited,
       url, title, visit_count
FROM urls ORDER BY last_visit_time DESC LIMIT 100;

SELECT datetime(visit_time/1000000-11644473600,'unixepoch'),
       u.url, u.title
FROM visits v JOIN urls u ON v.url=u.id
ORDER BY visit_time DESC LIMIT 100;

-- Safari (iOS Cocoa 秒)
SELECT datetime(visit_time+978307200,'unixepoch'),
       url, title
FROM history_visits v JOIN history_items i ON v.history_item=i.id
ORDER BY visit_time DESC LIMIT 100;

-- Firefox
SELECT datetime(last_visit_date/1000000,'unixepoch'),
       url, title, visit_count
FROM moz_places ORDER BY last_visit_date DESC LIMIT 100;
```

⚠️ Chrome WebKit µs 时间换算见 `@knowledge/skills/timestamps_reference.md`。

### 1.2 搜索关键词 ★★★

| 来源 | 路径 |
|---|---|
| Chrome 搜索框 | `Chrome/Default/History` `keyword_search_terms` 表 |
| Google 搜索 app | `com.google.android.googlequicksearchbox/databases/` |
| Sogou / Baidu 搜索 | 各自 `databases/search_history*` |
| **输入法词库** | 见 §1.7 |
| App 内搜索（淘宝/京东/微信公众号/知乎） | 各 app `databases/`，常表 `search_history`, `search_word` |

```sql
SELECT term FROM keyword_search_terms;
```

万能扫：
```bash
for db in $(find /data/data -name "*.db"); do
  t=$(sqlite3 "$db" "SELECT name FROM sqlite_master WHERE name LIKE '%search%' OR name LIKE '%history%'" 2>/dev/null)
  [ -n "$t" ] && echo "$db: $t"
done
```

### 1.3 即时通讯 ★★★

| App | Android | iOS | 加密 |
|---|---|---|---|
| **微信** | `com.tencent.mm/MicroMsg/{hash}/EnMicroMsg.db` | `AppDomain-com.tencent.xin/Documents/{hash}/DB/MM.sqlite` | Android: SQLCipher (IMEI+UIN); iOS: 明文 |
| **QQ** | `com.tencent.mobileqq/databases/{uin}.db` | 类似 | 部分加密 |
| **Telegram** | `org.telegram.messenger/files/cache4.db` | — | 字段加密 |
| **WhatsApp** | `com.whatsapp/databases/msgstore.db` | — | crypt14 加密备份 |
| **钉钉** | `com.alibaba.android.rimet/databases/` | — | 字段混淆 |
| **飞书 Lark** | `com.larksuite.suite/databases/` | — | — |
| **Signal** | `org.thoughtcrime.securesms/databases/signal.db` | — | SQLCipher |

详见 `@knowledge/solved/pattern_wechat_db_decrypt.md`。

### 1.4 支付 / 金融 / 订单 ★★★

| App | 关键 |
|---|---|
| **支付宝** | `com.eg.android.AlipayGphone/databases/`，`cashier.db`、`mywallet_*.db` |
| **微信支付** | 微信主库 `message` type=49 含转账/红包 |
| **银行 app** | 各 app `databases/`，账号常加密 |
| **京东 / 淘宝** | `databases/` 含订单 + 收货地址 |
| **美团 / 饿了么** | 订单含**精确地址**（GPS 高价值） |

### 1.5 多媒体 / 相册 / 视频 ★★

| 类型 | 路径 |
|---|---|
| **系统相册（Android）** | `com.android.providers.media/databases/external.db` (`files`/`images`) + 各厂商 `gallery3d.db` |
| **系统相册（iOS）** | `Photos.sqlite` |
| **抖音 / 快手** | `databases/` + `cache/` 看过/点赞/关注 |
| **B 站** | `tv.danmaku.bili/databases/` |
| **小红书** | `com.xingin.xhs/databases/` |
| **YouTube** | `com.google.android.youtube/databases/yt_player.db` |

抖音类用户行为 → 行为画像金矿。

### 1.6 邮件 / 笔记 / 文档 ★★

| 类型 | 路径 |
|---|---|
| Gmail | `com.google.android.gm/databases/` 含原始正文 |
| 网易邮 | `com.netease.mail/databases/` |
| 备忘录 (iOS) | `Notes.sqlite`、`NoteStore.sqlite` |
| 印象笔记 | `com.evernote/databases/` |
| WPS / Office | `cn.wps.moffice_eng/databases/` 最近打开列表 |

### 1.7 输入法词库 ★★★（被忽略的金矿）

记录用户**亲手打过的所有词**（搜过的、姓名、地名、密码片段）：

| 输入法 | 路径 |
|---|---|
| 搜狗 | `com.sohu.inputmethod.sogou/files/usrdict/` |
| 百度 | `com.baidu.input/files/userdict/` |
| 讯飞 | `com.iflytek.inputmethod/files/` |
| 微软 SwiftKey | `com.touchtype.swiftkey/databases/` |
| Gboard | `com.google.android.inputmethod.latin/databases/` |
| 系统输入法（iOS） | `Library/Keyboard/dynamic-text.dat`（旧）、`com.apple.keyboard.plist` |

```bash
strings -n 4 /data/data/com.sohu.inputmethod.sogou/files/usrdict/* | head
strings -e l /data/data/.../usrdict/*  # GBK/UTF-16 时
strings /private/var/mobile/Library/Keyboard/dynamic-text.dat | head
```

### 1.8 剪贴板 / 通知 / 应用使用 ★★

| 类型 | 路径 |
|---|---|
| Android 剪贴板 | 第三方剪贴板 app；MIUI: `com.miui.contentextension/databases/` |
| iOS 剪贴板 | `pasteboardDB`（部分版本） |
| 通知历史 | Android 11+: `dumpsys notification --noredact`；iOS BiomeAgent |
| **UsageStats** | `/data/system/usagestats/{user}/` 每日/每周 app 使用 |
| **iOS knowledgeC.db** | `/private/var/mobile/Library/CoreDuet/Knowledge/knowledgeC.db` 行为流（app/锁屏/通知/充电/通话） |

```bash
ls /data/system/usagestats/0/   # daily/, weekly/, monthly/, yearly/

# iOS app 使用时长 Top
sqlite3 knowledgeC.db "
SELECT ZVALUE_STRING, SUM(ZEND_DATE-ZSTART_DATE)/60 AS minutes
FROM ZOBJECT WHERE ZSTREAM_NAME='/app/usage'
GROUP BY ZVALUE_STRING ORDER BY minutes DESC LIMIT 20"

# iOS 应用启动时间线
sqlite3 knowledgeC.db "
SELECT datetime(ZSTART_DATE+978307200,'unixepoch'),
       datetime(ZEND_DATE+978307200,'unixepoch'),
       ZVALUE_STRING
FROM ZOBJECT WHERE ZSTREAM_NAME='/app/usage'
ORDER BY ZSTART_DATE DESC LIMIT 100"
```

iOS `knowledgeC.db` 是行为分析金矿，能拼"用户那段时间在干嘛"完整时间线。

---

## 2. 通用挖掘技巧

### 2.1 全盘 grep 关键词
```bash
find /data/data -name "*.db" -exec grep -l "关键词" {} \;
```

### 2.2 每个 app "三件套"
```bash
APP=/data/data/com.example/
ls $APP/databases/                                # SQLite 数据
ls $APP/shared_prefs/                             # XML 配置（登录信息、token、user id）
cat $APP/shared_prefs/*.xml | grep -iE "user|account|phone|token|email"
ls $APP/files/  $APP/cache/                       # 文件 / 缓存
```

### 2.3 包名 → 中文名
```bash
aapt dump badging /data/app/com.xxx.yyy/base.apk | grep "application-label"
# 或在线 https://play.google.com/store/apps/details?id=com.xxx.yyy
```

### 2.4 跨 app 搜索表自动定位
```bash
for db in $(find /data/data -name "*.db" 2>/dev/null); do
  t=$(sqlite3 "$db" "SELECT name FROM sqlite_master WHERE name LIKE '%search%' OR name LIKE '%history%' OR name LIKE '%record%'" 2>/dev/null)
  [ -n "$t" ] && echo "$db: $t"
done
```

---

## 3. 决策树

```
"分析手机 app 的某类记录"
   │
   ├─ Step 1: 列完整 app 清单（packages.xml + iOS LastLaunchServicesMap）
   │     └ 按题目关键词过滤可疑 app
   │
   ├─ Step 2: 走标准三件套（databases / shared_prefs / files）
   │
   ├─ Step 3: 按数据类型走 §1 速查
   │     ├ 浏览 → urls/visits/history_items
   │     ├ 搜索 → keyword_search_terms / 输入法词库
   │     ├ 通讯 → 微信/QQ 解密
   │     ├ 支付 → 各支付 db
   │     ├ 多媒体 → external.db / Photos.sqlite
   │     ├ 邮件笔记 → Gmail / Notes
   │     └ 行为 → usagestats / knowledgeC.db
   │
   ├─ Step 4: 时间线对齐（→ timestamps_reference.md）
   │
   └─ Step 5: 跨源交叉
         浏览过 X → 搜索过 X → 输入法记 X → 微信聊过 X → 多源印证
```

---

## 4. 命令速查

```bash
# Android 完整 app 清单（hex 时间转换）
python3 -c "
import xml.etree.ElementTree as ET, datetime as dt
for pkg in ET.parse('/data/system/packages.xml').findall('package'):
    ft = int(pkg.get('ft','0'),16)/1000
    print(dt.datetime.utcfromtimestamp(ft).isoformat(),
          pkg.get('installer','sideload'), pkg.get('name'))
" | sort

# Chrome 浏览
sqlite3 Chrome/Default/History "
SELECT datetime(last_visit_time/1000000-11644473600,'unixepoch'),
       url, title FROM urls ORDER BY last_visit_time DESC LIMIT 50"

# Chrome 搜索词
sqlite3 Chrome/Default/History "SELECT term FROM keyword_search_terms"

# Safari
sqlite3 History.db "
SELECT datetime(visit_time+978307200,'unixepoch'), url, title
FROM history_visits v JOIN history_items i ON v.history_item=i.id
ORDER BY visit_time DESC LIMIT 50"

# 跨 app 搜索/历史表
for db in $(find /data/data -name "*.db" 2>/dev/null); do
  t=$(sqlite3 "$db" "SELECT name FROM sqlite_master WHERE name LIKE '%search%' OR name LIKE '%history%'" 2>/dev/null)
  [ -n "$t" ] && echo "$db: $t"
done

# iOS knowledgeC 行为流
sqlite3 knowledgeC.db "
SELECT ZVALUE_STRING, SUM(ZEND_DATE-ZSTART_DATE)/60 AS minutes
FROM ZOBJECT WHERE ZSTREAM_NAME='/app/usage'
GROUP BY ZVALUE_STRING ORDER BY minutes DESC LIMIT 20"

# 输入法词库
strings -n 4 /data/data/com.sohu.inputmethod.sogou/files/usrdict/* \
       /data/data/com.baidu.input/files/userdict/* 2>/dev/null \
  | sort -u | head -200

# 包名 → 中文名
for apk in /data/app/*/base.apk; do
  pkg=$(aapt dump badging "$apk" 2>/dev/null | grep "package:" | sed -E "s/.*name='([^']+)'.*/\1/")
  name=$(aapt dump badging "$apk" 2>/dev/null | grep "application-label:" | head -1 | sed -E "s/application-label:'([^']+)'/\1/")
  echo "$pkg | $name"
done

# UsageStats（XML/Protobuf）
ls /data/system/usagestats/0/daily/
# 用 Belkasoft / Magnet AXIOM 直接解析，或自己解 protobuf
```

---

## 5. 常见坑

- **packages.xml `ft`/`it` 是 hex**：`int(s,16)`，不是 `int(s)`
- **Chrome / Chromium 时间是 WebKit µs**：`/1e6 - 11644473600`
- **Safari 时间是 Cocoa 秒**：`+ 978307200`
- **微信 db 加密**：Android SQLCipher (md5(IMEI+UIN)[:7])，iOS 明文
- **WhatsApp 备份加密**：`.crypt14`，需要 key 文件
- **app 数据库 WAL 模式**：必须连同 `.db-wal`、`.db-shm` 一起 dump，否则丢最新数据
- **packages.xml 多版本路径**：Android 13+ 拆 `packages.xml` + `package_extra.xml`
- **iOS 沙箱 UUID 每次重装变**：用 `LastLaunchServicesMap.plist` 锁当前映射
- **输入法编码**：常 GBK / UTF-16，`strings -e l` 试 16-bit LE
- **app 内嵌浏览器历史**：微信公众号、抖音里点的链接 → 不在 Chrome history，在各 app 自己 cache
- **隐私模式**：浏览器无痕不写 history，但 cache + 通知历史 + DNS 缓存仍可能留
- **包名混淆**：少数恶意 app 用 `com.android.system` 之类伪装系统包，看签名识破
- **预装 vs 用户安装**：`/system/app/` vs `/data/app/`，`installer` 字段也能分
- **iOS knowledgeC.db 30 天滚动**：超期被清，尽早提取
- **多用户隔离**：Android 多账户/工作模式，`/data/user/{N}/com.xxx/`，别只看 user 0
- **iOS 应用使用 (Screen Time)**：`RMAdminStore-Local.sqlite`，比 knowledgeC 更长保留
- **微信收藏 / 朋友圈数据库分散**：除 `EnMicroMsg.db` 外还有 `FTS5IndexMicroMsg_*.db`、`favorite.db`

---

## 6. 实战证据链（行为画像）

```
1. packages.xml: 装了"某偷拍 app" 2026-05-01    （持有）
2. UsageStats: 每天晚上 22-24 点用 1 小时         （使用模式）
3. app databases/: 内含 800 张本地图              （证据本身）
4. 输入法词库: 出现"偷拍" "藏镜头"等词            （主观意图）
5. 浏览历史: 连续访问"偷拍论坛"                   （兴趣对照）
6. iOS knowledgeC: 该 app 与摄像头使用时段重合    （行为印证）
```

任意 4 项匹配 = 强证据；6 项全匹配 = 行为画像铁证。

---

## 7. KB 联动

| 场景 | 跳哪 |
|---|---|
| 设备身份字段（IMEI/MAC/序列号） | `mobile/device_basic_info.md` |
| 时间戳格式换算 | `skills/timestamps_reference.md` |
| App 已被卸载 | `mobile/uninstalled_app_recovery.md` |
| App 加解密 / 字段解密 | `mobile/apk_crypto_analysis.md` |
| App 权限分析 | `mobile/apk_permission_analysis.md` |
| 数据是否被伪造 | `mobile/anti_forensics_and_misleading.md` |
| 位置类 app（订单地址/订餐） | `mobile/geolocation_forensics.md` |
| IoT 类 app | `mobile/iot_device_forensics.md` |
| 微信解密详解 | `solved/pattern_wechat_db_decrypt.md` |
