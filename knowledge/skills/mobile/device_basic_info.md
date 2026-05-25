---
tags: [mobile, android, ios, device_info, imei, iccid, imsi, mac_address, build_prop,
  telephony, lockdown, itunes_backup, methodology, mobile_forensics]
tools: [sqlite3, plutil, grep, plistutil, exiftool]
category: mobile_forensics
difficulty: foundational
source: kb_seed_2026-05-07
verified: false
related: [quick_reference.md, iot_device_forensics.md, geolocation_forensics.md, anti_forensics_and_misleading.md,
  timestamps_reference.md]
---

# 手机设备基本信息提取速查

> **核心心法**：每个字段都有"权威源"和"备份源"。
> - **权威源**：系统从硬件直接读（IMEI 在基带，MAC 在 WiFi 芯片 EFS）
> - **备份源**：app/系统服务把它缓存到了文件里
>
> 取证镜像里**权威源不一定能直接读到**（基带分区不在常规提取），所以靠**备份源**反推。
> 一个字段往往在 5-10 处都有，**多源交叉验证 = 防伪造**。

## 0. 速查总图

| 字段 | Android 主源 | iOS 主源 |
|---|---|---|
| 设备型号 | `/system/build.prop` `ro.product.model` | `lockdownd ProductType` (如 `iPhone14,2`) |
| 系统版本 | `ro.build.version.release` / `.sdk` | `SystemVersion.plist ProductVersion` |
| 序列号 | `ro.serialno` | `lockdownd SerialNumber` |
| IMEI | `telephony.db.siminfo.imei` | `com.apple.commcenter.plist IMEI` |
| ICCID | `telephony.db.siminfo.icc_id` | `com.apple.commcenter.plist ICCID` |
| IMSI | `telephony.db.siminfo.imsi` | `commcenter.device_specific_nobackup.plist` |
| 本机号码 | `telephony.db.siminfo.number` | `com.apple.commcenter.plist PhoneNumber` |
| WiFi MAC | `WifiConfigStore.xml` `MacAddress` | `lockdownd WiFiAddress` |
| BT MAC | `bt_config.conf [Adapter] Address` | `lockdownd BluetoothAddress` |
| Android ID / UDID | settings.db `secure.android_id` | `lockdownd UniqueDeviceID` |
| 时区 | `persist.sys.timezone` | iOS 全 UTC，无对应 |

---

## 1. Android 关键字段

### 1.1 系统层（build.prop + settings.db）

```bash
# /system/build.prop（部分 ROM 还有 /vendor/、/odm/、/system_ext/）
cat /system/build.prop | grep -E "ro.product|ro.build|ro.serialno|persist.sys.timezone"
```

| 字段 | key |
|---|---|
| 型号 / 厂商 | `ro.product.model`, `ro.product.brand`, `ro.product.manufacturer`, `ro.product.device` |
| Android 版本 | `ro.build.version.release` (如 13), `ro.build.version.sdk` (如 33) |
| 构建指纹 | `ro.build.fingerprint` |
| 构建日期 | `ro.build.date`, `ro.build.date.utc` |
| CPU 架构 | `ro.product.cpu.abi`, `ro.product.cpu.abilist` |
| 序列号 | `ro.serialno`, `ro.boot.serialno` |
| 时区 | `persist.sys.timezone` |

```bash
# settings.db 三张表
DB=/data/data/com.android.providers.settings/databases/settings.db
sqlite3 $DB "SELECT name,value FROM secure WHERE name IN ('android_id','bluetooth_name','default_input_method')"
sqlite3 $DB "SELECT name,value FROM global WHERE name IN ('device_name','wifi_on','bluetooth_on','airplane_mode_on')"
sqlite3 $DB "SELECT name,value FROM system WHERE name LIKE '%locale%'"
```

### 1.2 IMEI / IMSI / SIM / 本机号码

⚠️ IMEI 是基带数据，常规提取抓不到原始，但系统多处缓存：

| 字段 | 备份源（按可靠性） |
|---|---|
| **IMEI** | ① `telephony.db.siminfo`<br>② `/persist/` 厂商分区<br>③ logcat `getDeviceId()` 调用<br>④ Google `com.google.android.gms` 数据库<br>⑤ app 上报：微信 `EnMicroMsg.db.userinfo`、抖音、京东 |
| **IMSI** | ① `telephony.db.siminfo.imsi` ② 运营商 app 缓存 ③ logcat |
| **本机号码 (MSISDN)** | ① `telephony.db.siminfo.number`<br>② 微信/短信注册时填的<br>③ 联系人 "Me" 卡片 |
| **ICCID** | ① `telephony.db.siminfo.icc_id`（最权威）<br>② NFC SIM 工具数据 |
| **运营商 / SPN** | `siminfo.carrier_name`, `mcc`, `mnc`, `display_name` |
| **eSIM 配置** | `/data/data/com.android.phone/files/`、`euicc_*.db` |

```sql
SELECT _id, icc_id, sim_id, display_name, carrier_name,
       mcc, mnc, number, imsi
FROM siminfo;
```

### 1.3 MAC 地址（WiFi / Bluetooth）

⚠️ Android 10+ 默认对 app 隐藏真实 MAC（每 SSID 随机），系统层仍留真实：

| 类型 | 路径 |
|---|---|
| **WiFi MAC（真实）** | `/data/misc/wifi/factory.dat` 或 `/persist/wlan_mac.bin` |
| **WiFi MAC（缓存）** | `/data/misc/wifi/WifiConfigStore.xml` `<string name="MacAddress">` |
| **每 SSID 随机 MAC** | 同文件 `<string name="RandomizedMacAddress">` |
| **Bluetooth MAC** | `/data/misc/bluedroid/bt_config.conf` `[Adapter] Address` |
| **历史 BSSID** | `WifiConfigStore.xml` 中所有 `<string name="BSSID">` |
| **Bonded BT 设备** | `bt_config.conf` 内 `[XX:XX:..]` 段 |
| **WiFi 密码（明文）** | `WifiConfigStore.xml` `<string name="PreSharedKey">` |

```bash
grep -E "MacAddress|RandomizedMacAddress|SSID|BSSID|PreSharedKey" /data/misc/wifi/WifiConfigStore.xml
grep -E "^Address|^Name|^DevClass|LinkKey" /data/misc/bluedroid/bt_config.conf
sed -n '/^\[..:..:..:..:..:..\]/,/^$/p' /data/misc/bluedroid/bt_config.conf
```

### 1.4 硬件 / 用户

| 字段 | 来源 |
|---|---|
| 屏幕分辨率 | `ro.sf.lcd_density` 或 `dumpsys display` |
| 内存 | `/proc/meminfo` |
| CPU 详情 | `/proc/cpuinfo` |
| 存储分区 | `/proc/partitions`、`/etc/fstab` |
| 电池 | `/sys/class/power_supply/battery/`，`dumpsys battery` |
| 传感器 | `dumpsys sensorservice` |
| Google 账号 | `/data/system_ce/0/accounts_ce.db`（加密 keystore） |
| 锁屏哈希 | `/data/system/locksettings.db` + `gatekeeper.pattern.key`/`password.key` |
| 用户列表 | `/data/system/users/userlist.xml` |

---

## 2. iOS 关键字段

### 2.1 系统 plist

```bash
plutil -p /System/Library/CoreServices/SystemVersion.plist
plutil -p /private/var/preferences/SystemConfiguration/preferences.plist
```

| 字段 | 文件 / key |
|---|---|
| 设备型号 | lockdown plist `ProductType` (如 `iPhone14,2`) |
| iOS 版本 | `SystemVersion.plist ProductVersion`, `BuildVersion` |
| 设备名 | `com.apple.assistant.plist DeviceName` 或 `preferences.plist ComputerName` |
| 序列号 | lockdown `SerialNumber` |
| UDID | lockdown `UniqueDeviceID` |
| 激活时间 | `/private/var/root/Library/Lockdown/activation_records/wildcard_record.plist ActivationDate` |
| 首次设置时间 | `/private/var/db/.AppleSetupDone` 文件 mtime |

⚠️ iOS 提取必须**解密 backup**或越狱镜像才能拿到 `/private/var/mobile/`。Lockdown 配对在 PC 上的 iTunes Backup 是另一座金矿。

### 2.2 IMEI / ICCID / SIM

| 字段 | 路径 |
|---|---|
| **IMEI / IMEI2** | `/private/var/wireless/Library/Preferences/com.apple.commcenter.plist IMEI` |
| **MEID** | 同上 `MEID` |
| **ICCID** | `com.apple.commcenter.plist` 或 Carrier Bundle |
| **IMSI** | `com.apple.commcenter.device_specific_nobackup.plist` |
| **本机号码** | `com.apple.commcenter.plist PhoneNumber` 或 `AddressBook.sqlitedb` 我的卡片 |
| **运营商** | `com.apple.carrier.plist` |
| **eSIM** | `com.apple.commcenter.eSIM.plist`，多 profile |

```bash
plutil -p com.apple.commcenter.plist | grep -iE "IMEI|MEID|ICCID|PhoneNumber|CarrierName"
```

### 2.3 MAC 地址

| 类型 | 路径 |
|---|---|
| **WiFi MAC** | `com.apple.wifi.plist` 或 lockdown `WiFiAddress` |
| **Bluetooth MAC** | lockdown `BluetoothAddress`，或 `com.apple.MobileBluetooth.devices.plist` |
| **以太网 MAC**（数据线） | lockdown `EthernetAddress` |
| **历史 BSSID** | `com.apple.wifi.plist List of known networks` |
| **AirDrop MAC** | `com.apple.sharingd.plist` |

### 2.4 Apple ID / iCloud

| 字段 | 路径 |
|---|---|
| Apple ID | `/private/var/mobile/Library/Accounts/Accounts3.sqlite` |
| iCloud 设备列表 | `/private/var/mobile/Library/Preferences/com.apple.icloud.fmip.plist` |
| Find My 状态 | 同上 |

---

## 3. PC 端反推（不打开手机）

锁机/无 root 时的备选：

| 来源 | 能拿到 |
|---|---|
| **iTunes Backup `Info.plist`** | iPhone 序列号、UDID、IMEI、MAC、电话号码、所有 plist |
| **iTunes 配对记录** Win: `%ProgramData%\Apple\Lockdown\` macOS: `/var/db/lockdown/` | 配对的所有 iPhone UDID + 证书 |
| **adb keys** PC: `~/.android/adbkey.pub` | 哪台 Android 信任过这台 PC |
| **Google Sync (Chrome)** | 登录账号、绑定设备列表 |
| **Samsung Smart Switch / Mi PC Suite** 备份 | 设备型号、IMEI |
| **路由器 ARP/DHCP** | MAC + 设备 hostname |

---

## 4. 决策树

```
"手机基本信息题：要 IMEI/MAC/ICCID/SDK/型号..."
   │
   ├─ Step 1: 看检材类型
   │     ├ 完整 ext4 镜像 → 走 §1 / §2 表
   │     ├ iTunes Backup → 走 §3 + Backup Info.plist
   │     └ 模拟器/碎片 → 看 build.prop + settings.db
   │
   ├─ Step 2: 主力源一击
   │     Android: build.prop + settings.db + telephony.db
   │              + bt_config.conf + WifiConfigStore.xml
   │     iOS:     SystemVersion.plist + com.apple.commcenter.plist
   │              + lockdown plist
   │
   ├─ Step 3: 多源交叉验证
   │     IMEI 在 ① telephony.db ② 微信 db ③ logcat 都查 → 一致才可信
   │     真实 MAC 在 ① bt_config.conf ② WifiConfigStore.xml ③ ARP 对照
   │
   └─ Step 4: 找不到时上 app 反查
         微信 EnMicroMsg.db / 抖音 / 京东 / 各种登录 app 都会上报
```

---

## 5. 命令速查

### Android
```bash
# 一击拿系统
cat /system/build.prop | grep -E "ro.product|ro.build|ro.serialno|persist.sys.timezone"
cat /vendor/build.prop 2>/dev/null | grep ro.product

# settings.db
DB=/data/data/com.android.providers.settings/databases/settings.db
sqlite3 $DB "SELECT name,value FROM global"  | grep -iE "device_name|bluetooth_name"
sqlite3 $DB "SELECT name,value FROM secure"  | grep -iE "android_id|bluetooth|wifi"
sqlite3 $DB "SELECT name,value FROM system"  | grep -iE "locale"

# SIM
sqlite3 /data/data/com.android.providers.telephony/databases/telephony.db \
  "SELECT _id, icc_id, display_name, carrier_name, number, imsi, mcc, mnc FROM siminfo"

# WiFi MAC + SSID + 密码
grep -E "MacAddress|RandomizedMacAddress|SSID|BSSID|PreSharedKey" \
  /data/misc/wifi/WifiConfigStore.xml

# Bluetooth
grep -E "^Address|^Name|^LinkKey" /data/misc/bluedroid/bt_config.conf

# 微信 IMEI / 用户信息
sqlite3 EnMicroMsg.db "SELECT * FROM userinfo WHERE id IN (4,6,42)"

# 已装 app + 安装时间
grep -oE 'name="[^"]+" .*ft="[^"]+"' /data/system/packages.xml | head -20
```

### iOS
```bash
# 系统版本
plutil -p /System/Library/CoreServices/SystemVersion.plist

# IMEI / SIM
plutil -p /private/var/wireless/Library/Preferences/com.apple.commcenter.plist \
  | grep -iE "IMEI|MEID|ICCID|PhoneNumber"

# 设备名
plutil -p /private/var/preferences/SystemConfiguration/preferences.plist \
  | grep -iE "ComputerName|HostName"

# WiFi 历史
plutil -p /private/var/preferences/SystemConfiguration/com.apple.wifi.plist | head -100

# 蓝牙配对
plutil -p /private/var/root/Library/Preferences/com.apple.MobileBluetooth.devices.plist
```

### iTunes Backup（PC 端）
```bash
# Backup 根目录的 Info.plist
plutil -p ~/Library/Application\ Support/MobileSync/Backup/{UDID}/Info.plist
# Windows: %APPDATA%\Apple Computer\MobileSync\Backup\{UDID}\Info.plist

# Manifest.db 是文件目录入口
sqlite3 Manifest.db "SELECT fileID, domain, relativePath FROM Files LIMIT 20"
```

---

## 6. 常见坑

- **build.prop 不止一个**：`/system/`、`/vendor/`、`/odm/`、`/system_ext/` 都要读
- **`ro.serialno` 厂商可能伪造**：与 `/persist/` 中真实 serial 对比
- **Android 10+ MAC 随机化**：app 看到的 MAC 不是真实 MAC，要从系统层拿
- **`siminfo` 字段名跨版本变**：`number` vs `phone_number`，`carrier_name` vs `display_name`
- **多 SIM 槽**：`siminfo` 多行，按 `sim_id` / `subscription_id` 区分
- **IMEI 在 Android 10+ 普通 app 拿不到**：但系统服务和 Carrier app 仍能读，备份源仍有
- **越狱前 vs 越狱后镜像差异**：未越狱只能从 backup
- **iOS Backup 加密**：要用密码爆破或在原设备关闭"加密备份"
- **Backup 不含的字段**：IMEI/MAC 在 `Info.plist` 有，但部分 plist 不入备份
- **`Manifest.db`**：iTunes Backup 所有文件名 + 域 + 哈希入口
- **Android ID 工厂重置后会变**：能识别"这台手机是否被重置过"
- **eSIM 时代 ICCID 多个**：每个 profile 一个，看 `siminfo` 多行 / iOS `eSIM.plist`
- **盗版 / Mod ROM 改 build.prop**：型号显示高端机但 `/proc/cpuinfo` 是低端，对比鉴别
- **`persist.sys.timezone` vs 拍照 EXIF 时区**不一致 = 改过时区，反取证信号
- **二手机交易**：上一任 IMEI 不变但 Android ID 变；微信 db 残留可能是上一任的

---

## 7. 实战证据链（设备身份）

```
1. build.prop: ro.product.model = "Mi 11"          （厂商显示）
2. /proc/cpuinfo: Snapdragon 888                    （硬件印证）
3. telephony.db: IMEI=86AA...                       （基带身份）
4. 微信 EnMicroMsg.db.userinfo: IMEI 一致           （app 上报印证）
5. WifiConfigStore.xml: MAC=B0:C5:...               （网络身份）
6. 路由器 ARP 历史: 同 MAC 出现                     （外部印证）
7. bt_config.conf: BT MAC=B0:C5:...+1               （蓝牙印证）
```

任意 4 项匹配 = 强证据；7 项全匹配 = 设备身份铁证。

---

## 8. KB 联动

| 场景 | 跳哪 |
|---|---|
| 已删 app 的 MAC/包名残留 | `mobile/uninstalled_app_recovery.md` |
| MAC 反查地理位置 | `mobile/geolocation_forensics.md` (§4 BSSID) |
| 蓝牙 MAC + 配对 | `network/bluetooth_forensics.md` |
| 时间戳/时区伪造识别 | `mobile/anti_forensics_and_misleading.md` + `skills/timestamps_reference.md` |
| IoT 设备（同样需要 MAC/型号） | `mobile/iot_device_forensics.md` |
