---
tags: [mobile, android, adb, filesystem, partitions, fbe, fde, erofs, f2fs, selinux,
  exam_prep, methodology, mobile_forensics]
tools: [adb, fastboot, dd, tar]
category: mobile_forensics
difficulty: foundational
source: kb_seed_2026-05-08
verified: false
related: [fundamentals_cheatsheet.md, device_basic_info.md, app_data_analysis.md,
  uninstalled_app_recovery.md]
---

# ADB 命令 / Android 文件系统速查

> **核心心法**：
> - **ADB 不是工具，是协议**。3 种连接（USB / `adb tcpip` / Android 11+ Wireless `adb pair`）；3 种权限（shell / root / 系统签名）
> - **Android 文件系统 = 多分区拼起来的逻辑根**。`/`、`/system`、`/data`、`/sdcard` 看起来都是普通目录，背后对应不同物理分区 + 不同挂载选项
> - 题目常考"哪些只读、哪些是用户数据、IMEI 在哪、`/sdcard` 是不是真 SD 卡"

## 0. 速查总图

```
逻辑路径              物理分区           挂载         典型用途
/                     system_root        ro          根
/system               system             ro EROFS    AOSP / 厂商系统
/vendor               vendor             ro          HAL / 驱动
/product /odm         同名               ro          ODM / 定制
/data                 userdata           rw F2FS+FBE ★ 用户数据主战场
/sdcard ──soft link→ /data/media/0       rw          内置存储（不是真 SD）
/storage/XXXX-XXXX    外置 microSD       rw exFAT    真 SD 卡
/cache                cache              rw          旧版才有
/metadata             metadata           rw          FBE 元数据
/persist (不挂常规)   persist            ro          IMEI/MAC 出厂校准
/proc /sys /dev       内核虚拟           —          内核接口
```

⚠️ **`/sdcard` 是软链到 `/data/media/0`，不是真 SD 卡**。真 SD 在 `/storage/XXXX-XXXX`。

---

## 1. ADB 必背命令

### 1.1 连接 / 状态

```bash
adb devices                         # 列设备
adb devices -l                      # 含型号
adb get-state                       # device / offline / unauthorized

# WiFi 调试（旧式，需先 USB）
adb tcpip 5555
adb connect 192.168.1.100:5555

# Android 11+ 无线调试（设置 → 开发者选项 → 无线调试，输入配对码）
adb pair 192.168.1.100:41234
adb connect 192.168.1.100:41234

# 多设备指定
adb -s SERIAL shell
```

| 状态 | 含义 |
|---|---|
| `device` | 正常 |
| `offline` | 不响应 |
| `unauthorized` | 设备未点"允许 USB 调试" |
| `no permissions` | Linux udev 规则没装 |

### 1.2 文件传输

```bash
adb push local.txt /sdcard/         # 推
adb pull /sdcard/DCIM ./            # 拉
adb pull -p /data/...               # -p 显示进度
```

### 1.3 应用管理

```bash
adb install app.apk                 # 装
adb install -r app.apk              # 重装保留数据
adb install -d app.apk              # 允许降级
adb install -g app.apk              # 全权限默认 grant
adb install-multiple base.apk split_*.apk

adb uninstall com.x.y               # 卸
adb uninstall -k com.x.y            # 卸但保留 data/cache

adb shell pm list packages          # 列所有
adb shell pm list packages -3       # 仅第三方
adb shell pm list packages -s       # 仅系统
adb shell pm list packages -u       # 含已卸载
adb shell pm list packages -f       # 显示 APK 路径
adb shell pm list packages -i       # 显示 installer
adb shell pm path com.x.y
adb shell pm dump com.x.y           # 详细（权限、Activity）

adb shell am start -n com.x/.MainActivity
adb shell am start -a android.intent.action.VIEW -d "https://x.com"
adb shell am force-stop com.x.y
adb shell am kill com.x.y
```

### 1.4 Shell / 调试

```bash
adb shell                           # 进 shell
adb shell <cmd>                     # 直接跑

adb root                            # 提 root（仅 userdebug ROM）
adb unroot
adb remount                         # /system 改可写
adb disable-verity                  # 关 dm-verity（Magisk 前置）

adb reboot                          # 重启
adb reboot bootloader               # 进 fastboot
adb reboot recovery                 # 进 recovery

adb logcat                          # 日志
adb logcat -d                       # dump 一次
adb logcat -c                       # 清
adb logcat *:E                      # 仅 Error
adb logcat -s ActivityManager       # 仅某 tag

adb bugreport bugreport.zip         # 完整诊断包（取证神器）
```

### 1.5 端口转发 / 屏幕

```bash
adb forward tcp:8080 tcp:8080       # 主机 → 设备
adb reverse tcp:3000 tcp:3000       # 设备 → 主机

adb shell screencap -p /sdcard/s.png && adb pull /sdcard/s.png
adb shell screenrecord /sdcard/v.mp4

adb shell input tap 500 1000
adb shell input swipe 100 500 100 100
adb shell input keyevent KEYCODE_HOME
adb shell input text "hello"
```

### 1.6 取证常用一行

```bash
# 全量 dump（root 后）
adb shell "su -c 'tar -cf - /data'" > data.tar
# 单 app 全包
adb backup -f wechat.ab -noapk com.tencent.mm
dd if=wechat.ab bs=24 skip=1 | zlib-flate -uncompress > wechat.tar

# 设备信息一击
adb shell getprop                   # 所有 build.prop + persist props
adb shell getprop ro.product.model
adb shell dumpsys battery
adb shell dumpsys wifi
adb shell dumpsys telephony.registry
adb shell service call iphonesubinfo 1   # 拿 IMEI（老 ROM）
```

---

## 2. Android 主要分区

```
boot          → kernel + ramdisk（不挂载，启动用）
recovery      → 恢复模式
system        → /system     只读
system_ext    → /system_ext 只读（A/B 设备）
vendor        → /vendor     只读，HAL/驱动
product       → /product    只读，定制 app
odm           → /odm        只读，ODM 定制
vbmeta        → 启动校验元数据 (dm-verity)
userdata      → /data       ★ 用户数据
cache         → /cache      旧版有
metadata      → /metadata   FBE 加密元数据
persist       → 出厂校准 + WiFi/BT MAC + IMEI 备份
modem/efs     → 基带数据（IMEI 真身在这）
misc          → 启动状态标志
```

⚠️ **现代 Android 多份 build.prop**：`/system/`、`/vendor/`、`/product/`、`/odm/`、`/system_ext/`，多读才能拼齐设备信息。

---

## 3. `/data` 内部（取证核心）

```
/data/app/                   用户安装 APK
  com.x.y-1/base.apk
/data/app-private/           老版

/data/data/                  各 app 沙箱（= /data/user/0/）
  com.x.y/
    databases/               ★ SQLite
    shared_prefs/            ★ 配置/登录信息 (XML)
    files/                   app 自定义文件
    cache/                   临时缓存
    code_cache/              JIT/dex 缓存
    lib/                     so 链接

/data/user/0/                = /data/data/
/data/user/{N}/              ★ 其他用户/工作模式/双开（别只看 0）
/data/user_de/0/             Direct Boot（开机未解锁可读）

/data/system/                ★ 系统级
  packages.xml               ★★★ 已装 app 注册表
  packages.list
  users/0/runtime-permissions.xml
  users/userlist.xml
  locksettings.db            锁屏哈希
  netstats/                  流量统计

/data/system_ce/             credential encrypted（每用户）
  0/accounts_ce.db           ★ Google 账号
/data/system_de/             device encrypted

/data/misc/
  wifi/WifiConfigStore.xml   ★ WiFi 配置 + MAC + 密码
  bluedroid/bt_config.conf   ★ 蓝牙 MAC + 配对
  keychain/                  系统密钥
  vpn/                       VPN 配置

/data/media/0/               = /sdcard
  DCIM/  Download/  Pictures/
  Android/data/{pkg}/        ★ 各 app 外置缓存（图/语音常在这）
  Android/obb/{pkg}/         游戏资源包

/data/local/tmp/             调试用临时目录
/data/anr/                   ANR 堆栈
/data/tombstones/            native crash 堆栈
/data/log/                   厂商日志
```

⚠️ **双开微信 / 工作 Profile 数据不在 `/data/data/`**，要在 `/data/user/{N}/` 找。

---

## 4. `/system` 内部

```
/system/build.prop           ★ 系统标识
/system/app/                 系统 app
/system/priv-app/            高权限系统 app
/system/framework/           Java 框架
/system/etc/                 配置
/system/bin/  /system/xbin/  可执行
/system/lib(64)/             so
/system/fonts/
```

---

## 5. 加密状态 → 路径影响

| 加密 | 影响 |
|---|---|
| **FBE** (File-Based Encryption) Android 7+ 默认 | 每文件单独密钥；BFU 时 `/data/user/0` 多数文件不可读，`/data/user_de/0` 可读 |
| **FDE** (Full-Disk) Android 5-6 | 整 userdata 一把锁 |
| **Direct Boot** | BFU 状态可访问 `_de` 目录的有限数据（来电、闹钟等） |

参见 `@knowledge/skills/mobile/fundamentals_cheatsheet.md:79-95` BFU/AFU。

---

## 6. 文件系统类型

| 分区 | 文件系统 |
|---|---|
| boot/recovery | 不挂载，原始镜像 |
| system / vendor / product / odm | **EROFS**（Android 11+ 默认）/ ext4（旧）/ squashfs |
| userdata | **F2FS**（旗舰常用）/ ext4 |
| cache / metadata / persist | ext4 |
| 外置 SD | exFAT (>32GB) / FAT32 (≤32GB) |
| OTG U 盘 | FAT32 / exFAT / NTFS |

⚠️ **EROFS 镜像 mount 需 kernel 5.4+**；取证可用 `unsquashfs` / `erofsfuse` 解。

---

## 7. SELinux / 权限

| 调用 | 能读 |
|---|---|
| `adb shell` 普通 | `/sdcard` 全读、自己 app 数据；**别的 app `/data/data/*`** 读不到 |
| `adb root` (userdebug ROM) | 全部 |
| `adb shell su` (Magisk 后) | 全部，需用户首次授权 |
| 系统 app（platform 签名） | 部分系统 API |

```bash
ls -Z /data/data/com.x.y/databases/
# u:object_r:app_data_file:s0:c123,c256
```

加固机型 SELinux 严格 → root shell 都不一定能读某些目录，要 `setenforce 0`（仅 userdebug 能改）。

---

## 8. 决策树

```
"ADB / 文件系统题"
   │
   ├─ 命令用法        → §1
   ├─ /sdcard 是真 SD？ → §0 不是
   ├─ 分区作用        → §2
   ├─ user data 在哪  → /data/data 或 /data/user/{N}
   ├─ IMEI 在哪       → modem/efs（基带），不在 /data
   ├─ WiFi 密码在哪   → /data/misc/wifi/WifiConfigStore.xml
   ├─ 蓝牙 MAC 在哪   → /data/misc/bluedroid/bt_config.conf
   ├─ 已装 app 列表   → /data/system/packages.xml
   ├─ 加密 vs BFU     → §5 + fundamentals_cheatsheet §2.4
   ├─ 双开/工作模式   → /data/user/{N}/
   └─ 文件系统类型    → §6 EROFS/F2FS
```

---

## 9. 命令速查（选择题常出）

| 命令 | 作用 |
|---|---|
| `adb devices` | 列设备 |
| `adb shell` | 进 shell |
| `adb pull/push` | 文件传输 |
| `adb install/uninstall` | 装卸 app |
| `adb root / unroot` | 切 root |
| `adb remount` | /system 可写 |
| `adb reboot bootloader/recovery` | 进特殊模式 |
| `adb logcat` | 看日志 |
| `adb bugreport` | 完整诊断 |
| `adb backup -f x.ab pkg` | 备份 app 数据 |
| `adb forward / reverse` | 端口转发 |
| `adb shell pm list packages` | 列已装 |
| `adb shell pm path pkg` | 看 APK 路径 |
| `adb shell dumpsys` | 系统服务状态 |
| `adb shell getprop` | 读 build.prop / persist props |
| `adb shell screencap / screenrecord` | 截图录屏 |
| `adb shell input tap/swipe/text` | 模拟操作 |
| `adb tcpip / connect / pair` | 无线调试 |

---

## 10. 概念辨析（选择题陷阱）

| A | B | 区别 |
|---|---|---|
| `/sdcard` | `/storage/XXXX-XXXX` | 内置存储软链 vs 真 SD 卡 |
| `/data/data/` | `/data/user/0/` | 等价（user 0），其他用户在 `/data/user/{N}/` |
| `/data/user/0/` | `/data/user_de/0/` | CE（解锁后）vs DE（开机即可读） |
| `/system` | `/data` | 系统只读 vs 用户可写 |
| `adb shell` | `adb root` | 普通 shell vs root（仅 userdebug） |
| `adb backup` | `tar /data` | 前者受 `allowBackup` 限制，后者 root 后无限制 |
| `pm list -3` | `-s` | 第三方 vs 系统 |
| `am start` | `am force-stop` | 启动 vs 杀死 |
| `getprop` | `setprop` | 读 vs 写（需 root） |
| FDE | FBE | 整盘 vs 文件级（Android 7+ 默认 FBE） |
| EROFS | ext4 | 只读压缩 vs 通用读写 |

---

## 11. 简答题套路

### 11.1 "ADB 工作原理"

ADB = Android Debug Bridge，三部分：
1. **客户端**（PC `adb` 命令）
2. **adb server**（PC 后台进程，5037 端口）
3. **adbd**（设备上守护，普通跑 shell 用户，root 模式跑 root）

通信走 USB（默认）或 TCP（5555）。`adb` → server → adbd → 设备 shell / 文件系统。

### 11.2 "Android 文件系统主要分区"

`boot / recovery / system / vendor / product / userdata / cache / persist / modem / metadata / misc`。
- 只读：`system / vendor / product / odm / system_ext`
- 可写：`userdata（即 /data）`
- 取证主战场：`/data` + `/sdcard（=/data/media/0）`

### 11.3 "用户数据保存在哪"

- **app 沙箱**：`/data/data/{pkg}/` 或 `/data/user/0/{pkg}/`，含 `databases/`、`shared_prefs/`、`files/`、`cache/`
- **用户媒体**：`/sdcard/`（实际 `/data/media/0/`）
- **app 外置缓存**：`/sdcard/Android/data/{pkg}/`
- **系统级**：`/data/system/`（packages.xml、locksettings.db）
- **网络配置**：`/data/misc/wifi/`、`/data/misc/bluedroid/`

### 11.4 "ADB 提取证据须注意"

1. 先开 USB 调试（设置 → 关于 → 连点 7 次版本号 → 开发者选项）
2. 设备需 AFU，否则 `/data/user/0` 加密读不到
3. 普通 `adb shell` 只能读 `/sdcard` 和自身 app；要读别人 app 数据需 root
4. `adb backup` 受 `allowBackup="false"` 限制（绝大多数 IM/支付 app 都关）
5. 务必 `adb pull` 数据库 + WAL（`-wal`、`-shm`）一起，避免丢最新数据

---

## 12. KB 联动

| 主题 | 跳哪 |
|---|---|
| 标识符理论（IMEI/IMSI/BFU/AFU） | `mobile/fundamentals_cheatsheet.md` |
| 字段实际提取 | `mobile/device_basic_info.md` |
| App 数据库分析 | `mobile/app_data_analysis.md` |
| APK 加解密/权限 | `mobile/apk_crypto_analysis.md` / `apk_permission_analysis.md` |
| 已删 app 残留路径 | `mobile/uninstalled_app_recovery.md` |
| 时间戳格式 | `skills/timestamps_reference.md` |
