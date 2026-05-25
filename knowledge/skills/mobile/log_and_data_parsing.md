---
tags: [mobile, android, logcat, dropbox, anr, tombstones, sqlite, sqlcipher, realm,
  leveldb, mmkv, protobuf, plist, manual_parsing, data_format, methodology, exam_prep,
  mobile_forensics]
tools: [adb, logcat, sqlite3, undark, plyvel, blackboxprotobuf, plutil, frida, axmlprinter,
  realm_studio, xxd, strings]
category: mobile_forensics
difficulty: hard
source: kb_seed_2026-05-08
verified: false
related: [apk_crypto_analysis.md, app_data_analysis.md, uninstalled_app_recovery.md,
  pattern_wechat_db_decrypt.md, timestamps_reference.md]
---

# 安卓日志 + 应用数据结构 + 手工解析 + 加解密

> **核心心法**：app 数据 = 容器格式 + 业务结构 + 可选加密。三层都要会拆：
> 1. **容器**：SQLite / Realm / LevelDB / MMKV / Protobuf / plist / SharedPrefs / 自定义二进制
> 2. **业务结构**：字段名混淆、值再编码（Base64 / 自定义 TLV）
> 3. **加密**：SQLCipher 整库 / 字段级 AES / XOR / 字符串混淆函数
>
> **日志是行为时间线的脚手架**：logcat / dropbox / anr / tombstones 联合还原"那个瞬间发生了什么"。是反取证识别的关键。

## 0. Android 日志体系

### 0.1 五大日志缓冲区

```bash
adb logcat -b main -b system -b crash -b events -b kernel
```

| Buffer | 内容 |
|---|---|
| **main** | app `Log.d/i/w/e()` 普通日志（默认） |
| **system** | 系统服务（ActivityManager / PackageManager） |
| **crash** | 崩溃日志（Java 异常、ANR） |
| **events** | 二进制事件日志（`/system/etc/event-log-tags` 解码） |
| **kernel** | dmesg |
| **radio** | 基带日志（仅厂商 ROM） |

### 0.2 优先级

```
V(Verbose) < D(Debug) < I(Info) < W(Warn) < E(Error) < F(Fatal) < S(Silent)
```

```bash
adb logcat *:E
adb logcat ActivityManager:I *:S
adb logcat -v threadtime           # 含 PID/TID
adb logcat -d                      # dump 一次
adb logcat -G 16M                  # 设缓冲大小
```

### 0.3 持久化日志路径（取证主战场）

```
/data/anr/                  ★ ANR 完整堆栈
   traces.txt, anr_*.txt

/data/tombstones/           ★ native crash
   tombstone_00 .. tombstone_09 (循环覆盖)

/data/system/dropbox/       ★ DropBoxManager 长期日志（gz 压缩）
   data_app_anr@*.txt.gz
   data_app_crash@*.txt.gz
   system_app_wtf@*.txt.gz
   SYSTEM_AUDIT@*.txt.gz
   SYSTEM_BOOT@*.txt.gz
   SYSTEM_LAST_KMSG@*.txt.gz   ⚠️ 上次重启前内核日志

/data/log/                  厂商日志
/data/vendor/log/           厂商
/cache/recovery/            recovery 模式日志

/proc/last_kmsg             上次重启前 dmesg
/sys/fs/pstore/console-ramoops-0   崩溃时内核日志（持久内存）
```

### 0.4 取证用法

| 题目 | 看哪 |
|---|---|
| 嫌疑人何时启动了某 app | events buffer + ActivityManager:I `START u0` |
| 某操作时刻 | logcat + PID（`dumpsys activity`） |
| 删除证据时是否崩过 | tombstones / dropbox crash |
| 系统是否异常重启（销毁证据） | last_kmsg / SYSTEM_BOOT |
| 敏感 API 调用 | grep `getDeviceId`, `getLocation` |
| 反取证（频繁 ANR / 强停） | dropbox 频次 |

```bash
adb shell logcat -d | grep -iE "getDeviceId|TelephonyManager|LocationManager|MediaRecorder"
ls /data/anr/ ; cat /data/anr/anr_*.txt | head -50
strings /data/tombstones/tombstone_00 | head -100
```

### 0.5 events buffer 解码

events 是二进制，标签表在 `/system/etc/event-log-tags`：

```
30001 am_finish_activity ...
30002 am_task_to_front ...
```

事件含 app 切换、Activity 生命周期、电池状态变化 → 还原"那段时间在做什么"。

---

## 1. 应用数据存储格式（八大类）

### 1.1 SQLite（最常见）

#### 文件结构
```
SQLite header (100 bytes)
├─ Magic: "SQLite format 3\0"
├─ Page size (offset 16, 2 bytes)
├─ DB encoding (UTF-8/16)
└─ ...

Pages (B-tree)
├─ Page 1: schema (sqlite_master)
└─ Free pages (delete 后留下)
```

#### WAL / SHM 必须一起拉
```
xxx.db        主库
xxx.db-wal    Write-Ahead Log（最新数据可能仅在这里！）
xxx.db-shm    共享内存索引
```
⚠️ **只拷 .db 不拷 -wal 是新手最大坑**。

#### 已删除恢复
```bash
undark -i database.db -o recovered.txt
pip install pysqlitedeletedrecords
```

#### SQLCipher 加密
- 微信、Signal、企业 IM 用
- 整库加密，看不到 magic header
- 解密见 `@knowledge/solved/pattern_wechat_db_decrypt.md`

```bash
xxd file.db | head -1
# SQLite: "SQLite format 3"
# SQLCipher: 看似随机字节
```

### 1.2 Realm（iOS 多用，Android 也有）

```
.realm 文件，二进制
```

| 路径 | App |
|---|---|
| iOS `~/Library/HomeKit/HomeKitDatabase.realm` | Apple Home |
| Android `databases/*.realm` | 部分 |

工具：Realm Studio (GUI)、`pip install realm`、转 SQL。
加密：AES-256，key 在 Keychain/Keystore。

### 1.3 LevelDB（涂鸦、Chrome IndexedDB、Discord）

Google key-value，**目录而非单文件**：

```
*.ldb / *.log / MANIFEST-* / CURRENT / LOCK
```

```python
import plyvel
db = plyvel.DB('/path/to/leveldb', create_if_missing=False)
for k, v in db: print(k, '=>', v)
```

### 1.4 MMKV（腾讯系，微信普及）

腾讯开源 key-value，比 SharedPrefs 快几十倍。微信、QQ 内部大量用。

```
mmkv 主文件 + .crc 校验
```

特点：
- 顺序追加 protobuf-like 编码
- **删除 = 标记，物理空间不释放（适合恢复）**
- 支持 AES-128 加密（微信用）

```python
# pymmkv 或 jadx 看 app 怎么读
# 微信用户配置、token、临时缓存都在 MMKV
```

### 1.5 Protobuf（Google）

无 schema 自描述：
```
field_number << 3 | wire_type | value
```

无 .proto 时反推：
```bash
protoc --decode_raw < message.bin

# Python
pip install blackboxprotobuf
python3 -c "
import blackboxprotobuf
data = open('msg.bin','rb').read()
msg, typedef = blackboxprotobuf.decode_message(data)
print(msg, typedef)
"
```

### 1.6 SharedPreferences XML

`/data/data/{pkg}/shared_prefs/*.xml`

```xml
<map>
    <string name="user_id">12345</string>
    <int name="last_login" value="1714998000"/>
    <boolean name="logged_in" value="true"/>
</map>
```

⚠️ 部分 ROM 是 **binary XML**，需 `aapt` / `axmlparser` 解。

### 1.7 plist（iOS 主战场）

```
- XML plist：纯文本，<?xml 开头
- Binary plist：bplist00 开头
```

```bash
plutil -p file.plist               # 显示
plutil -convert xml1 file.plist    # 二进制 → XML
plutil -convert binary1 file.plist # XML → 二进制
```

iOS 几乎所有偏好/缓存都是 plist。

### 1.8 自定义二进制（恶意 / 加固 app）

无规律 → 走逆向：
1. jadx 看 app 怎么读这文件 → 还原结构
2. 010 Editor 模板试探
3. `xxd` + `strings` 找 magic / 关键字
4. Frida hook `read()` / `decode()` 拿明文

---

## 2. 应用数据加密策略

### 2.1 SQLCipher 整库
- 微信（Android）、Signal、企业 IM
- 微信 key = `md5(IMEI + UIN)[:7]`
- 详见 `@knowledge/solved/pattern_wechat_db_decrypt.md`

### 2.2 字段级 AES（最常见）
- 某 SQLite 字段 = `Base64(AES_CBC_PKCS5(明文))`
- jadx 找加密类，key 在常量字符串 / SharedPrefs / native .so
- 详见 `@knowledge/skills/mobile/apk_crypto_analysis.md`

### 2.3 XOR 流加密（轻量）
多见游戏存档、缓存：
```python
# 单字节 XOR 爆破
data = open('cache.bin','rb').read()
for k in range(256):
    out = bytes(b ^ k for b in data)
    if b'http' in out or b'{' in out:
        print(k, out[:80])
```

### 2.4 Base64 / Hex 套壳（伪加密）
- 全 `[A-Za-z0-9+/=]` → Base64
- 全 hex 字符 → hex decode
- 可能多层套（B64(Hex(B64(...)))）

### 2.5 字符串解密函数（混淆）
```java
String real = StringUtils.a("xK9z...");
```

```javascript
// Frida 批量
var SU = Java.use("a.a.StringUtils");
SU.a.implementation = function(x) {
    var r = this.a(x);
    console.log("decrypt('"+x+"') = '"+r+"'");
    return r;
};
```

### 2.6 设备绑定密钥（最难）
- key = `f(IMEI, ANDROID_ID, UUID)` 派生
- 必须**原设备 + 原数据**才能解
- 跨设备搬数据库会"打不开"

### 2.7 服务器下发密钥
- 抓包 SSL Pinning bypass → API 响应里有 key
- Frida 通用 SSL Pinning Bypass 脚本

---

## 3. 手工解析示例

### 3.1 SQLite 已删手工恢复

```python
import struct
with open('user.db','rb') as f:
    data = f.read()

page_size = struct.unpack('>H', data[16:18])[0]
print(f"Page size: {page_size}")

for i in range(0, len(data), page_size):
    page = data[i:i+page_size]
    chunks = page.split(b'\x00')
    for c in chunks:
        if len(c) > 4 and all(32 <= b < 127 for b in c):
            print(c)
```

### 3.2 Protobuf 反推 schema

```python
import blackboxprotobuf
data = bytes.fromhex("0a05Hello1003")
msg, typedef = blackboxprotobuf.decode_message(data)
print(msg)         # {'1': b'Hello', '2': 3}
print(typedef)     # {'1': {'type':'bytes'}, '2': {'type':'int'}}
```

### 3.3 binary plist

```python
import plistlib
with open('Prefs.plist','rb') as f:
    obj = plistlib.load(f)
print(obj)
```

### 3.4 MMKV 简易解析

```python
# MMKV 文件 = total_size(4 bytes) + protobuf-like KV pairs
import struct
with open('mmkv.default','rb') as f:
    total = struct.unpack('<I', f.read(4))[0]
    body = f.read(total)
# body 是 (key_len, key, value_len, value) 重复
# 实战用 pymmkv 或 jadx 反推 app 读法
```

---

## 4. 决策树

```
"应用数据 / 日志题"
   │
   ├─ Step 1: 检材类型
   │     ├ logcat 文本    → §0
   │     ├ dropbox/anr/tombstones → §0.3
   │     ├ app 数据库     → §1 + §2
   │     └ 不知格式的二进制 → §1.8
   │
   ├─ Step 2: 识别容器
   │     SQLite / Realm / LevelDB 目录 / bplist00 / MMKV+CRC / Protobuf?
   │
   ├─ Step 3: 是否加密
   │     ├ SQLCipher (无 magic) → key 派生（微信式）
   │     ├ 字段级       → jadx 找算法
   │     ├ 全 Base64/Hex → 解码再判断
   │     ├ 字符串混淆   → Frida hook
   │     └ 设备绑定     → 必原机原数据
   │
   ├─ Step 4: 解析
   │     ├ 标准容器 → 工具
   │     ├ 自定义   → jadx 反推 + 010 Editor
   │     └ 删除恢复 → undark / WAL / strings
   │
   └─ Step 5: 时间线
         数据库时间戳 + logcat + dropbox 串完整故事
```

---

## 5. 命令速查

```bash
# 日志
adb logcat -d > full.log
adb logcat -b events -d > events.log
adb shell ls -la /data/anr/ /data/tombstones/ /data/system/dropbox/
zcat /data/system/dropbox/data_app_crash@*.txt.gz | head

# 容器识别
file *.db *.realm *.plist *.dat
xxd file.bin | head -3

# SQLite
sqlite3 db ".tables"
sqlite3 db ".schema"
sqlite3 db ".dump"
undark -i db -o recovered.txt
ls *.db*               # 必含 -wal -shm

# Realm
realm-studio file.realm

# LevelDB
python3 -c "import plyvel; db=plyvel.DB('dir'); [print(k,v) for k,v in db]"

# Protobuf
protoc --decode_raw < msg.bin
python3 -c "import blackboxprotobuf as b; print(b.decode_message(open('msg.bin','rb').read()))"

# plist
plutil -p Prefs.plist
plutil -convert xml1 Prefs.plist

# Binary XML (Android)
java -jar AXMLPrinter2.jar AndroidManifest.xml

# 单字节 XOR 爆破
python3 -c "
d=open('x.bin','rb').read()
for k in range(256):
    o=bytes(b^k for b in d)
    if b'http' in o or b'{' in o: print(k, o[:80])
"

# Frida hook 字符串解密
frida -U -f com.x.y -l hook_decrypt.js --no-pause
```

---

## 6. 常见坑

- **只拷 `.db` 不拷 `-wal`/`-shm`**：丢最新数据
- **logcat 默认 buffer 小（256KB）**：不调大很快滚没
- **events buffer 是二进制**：要 `event-log-tags` 解码
- **dropbox 是 gz 压缩**：要 `zcat`
- **tombstone 编号循环 0..9**：旧的会被覆盖
- **SQLCipher 看似 SQLite 但开头乱**：xxd 头一眼看出
- **MMKV 删除是逻辑标记**：物理仍在，**适合恢复**
- **LevelDB 是目录不是单文件**：拷整个目录
- **Realm 字段名混淆**：要 schema 才认得
- **Protobuf 字段名丢失**：反推只给数字编号
- **Binary plist vs XML plist**：开头 `bplist00` vs `<?xml`
- **某些 ROM SharedPrefs 是 binary XML**
- **设备绑定密钥**：迁出设备就解不了
- **`/data/log/` 厂商私有格式**
- **logcat 时间是手机本地时间**：与镜像其他时间戳对齐前注意时区
- **last_kmsg 仅一次重启**：再启被覆盖，必须立即取
- **app 反取证检测 logcat**：发现自己被监控就自毁

---

## 7. 实战证据链（行为时间线）

```
1. logcat events: 23:05 ActivityManager START com.bad.app
2. logcat main:  23:05 BadApp.onCreate called
3. SQLite db:    23:06 row 插入（msg='我已到达'）
4. dropbox crash:23:08 java.lang.SecurityException
5. tombstone:    23:08 native crash，pc 在 libcipher.so
6. last_kmsg:    23:09 系统重启
7. anr trace:    23:10 重启后 BadApp ANR

→ 完整还原"嫌疑人 23:05 启动 app，23:06 写消息，
   23:08 崩溃但留下数据，23:09 重启可能为销毁证据"
```

任意 4 项时间一致 = 强证据。

---

## 8. KB 联动

| 主题 | 跳哪 |
|---|---|
| APK 加解密详解 | `mobile/apk_crypto_analysis.md` |
| 微信 SQLCipher 解密 | `solved/pattern_wechat_db_decrypt.md` |
| 已删 app 数据库恢复 | `mobile/uninstalled_app_recovery.md` |
| App 路径速查 | `mobile/app_data_analysis.md` |
| 时间戳格式 | `skills/timestamps_reference.md` |
| 反取证识别 | `mobile/anti_forensics_and_misleading.md` |
| ADB 命令 | `mobile/adb_filesystem_cheatsheet.md` |
