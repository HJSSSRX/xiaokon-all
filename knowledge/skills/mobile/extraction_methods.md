---
tags: [mobile, android, ios, extraction, adb_backup, vendor_backup, itunes_backup,
  root, bootloader, magisk, dd, jtag, chip_off, edl, checkm8, methodology, exam_prep,
  mobile_forensics]
tools: [adb, fastboot, abe, magisk, dd, qemu-nbd, mtkclient, edl, plutil]
category: mobile_forensics
difficulty: medium
source: kb_seed_2026-05-08
verified: false
related: [adb_filesystem_cheatsheet.md, fundamentals_cheatsheet.md, device_basic_info.md,
  app_data_analysis.md, 2022_changancup_mobile_exe_apk.md]
---

# 手机数据提取方法 — 五大类全景

> **核心心法**：
> - **完整度**：物理 > 逻辑 > 备份 > 选择性
> - **侵入性**：物理 > 提权 > 备份 > ADB shell
> - **黄金原则**：能用低侵入拿到答案就别上高侵入
> - **现实**：现代 IM/支付 `allowBackup=false`，多数实战一上来就要 root

## 0. 五级方法对比

```
┌──────────────────────────────────────────────────────────┐
│  侵入性 ↑                                                  │
│                                                            │
│  5. 物理提取  → JTAG / Chip-off / ISP / EDL       完整度↑│
│  4. 逻辑镜像  → root + dd 分区镜像                        │
│  3. 提权提取  → BL 解锁 + Magisk + 拷数据                 │
│  2. 备份提取  → 厂商克隆 / 自备份 / iTunes Backup         │
│  1. ADB 备份  → adb backup（受 allowBackup 限制）         │
└──────────────────────────────────────────────────────────┘
```

| 方法 | 完整度 | 侵入性 | 法律 | 适用 |
|---|---|---|---|---|
| ADB backup | ★ | 几乎无 | 无 | 普通 app（受 allowBackup） |
| 厂商备份 / 克隆 | ★★ | 无 | 无 | 联系人/短信/通话/相册 |
| 提权 (解 BL + Magisk) | ★★★★ | **改引导** | 写报告 | 大多数实战 |
| 逻辑镜像 (dd 分区) | ★★★★ | 改引导 | 同上 | 完整 user data |
| 物理 (JTAG/Chip-off) | ★★★★★ | **破坏性** | 必报告 | 砖机/锁机 |

---

## 1. Level 1 — ADB 备份

### 1.1 命令
```bash
adb backup -f wechat.ab -noapk com.tencent.mm
adb backup -all -shared -system -f full.ab
adb backup -apk -obb -f games.ab com.example.game
```

### 1.2 .ab 文件解码
```bash
# .ab = 24 字节 header + zlib 压缩的 tar
dd if=wechat.ab bs=24 skip=1 | zlib-flate -uncompress > wechat.tar
tar -xf wechat.tar
# 或 abe.jar
java -jar abe.jar unpack wechat.ab wechat.tar
```

### 1.3 致命缺点 ⚠️

```xml
<application android:allowBackup="false" ...>
```

Android 6+ 起，主流 IM/支付/银行 app 几乎全部 `allowBackup="false"`：
- 微信、QQ、支付宝、各银行 → 备份出来空
- ADB backup 仅对老 app / 不在意的 app 有效

### 1.4 适用
- 应急少量数据
- 自研 / 小众 app（已知 allowBackup=true）

---

## 2. Level 2 — 厂商备份 / 克隆

### 2.1 手机自带备份

| 厂商 | 工具 | 路径 / 格式 |
|---|---|---|
| **小米 / Redmi** | 系统"备份"app + Mi PC Suite | `/sdcard/MIUI/backup/AllBackup/` `*.bak` (zip) |
| **华为 / 荣耀** | HiSuite | `*.bak` + key 文件，加密 |
| **OPPO / 一加** | OPPO Clone Phone / Switch | 私有 zip |
| **vivo** | EasyShare / vivo 互传 | 私有 zip |
| **三星** | Smart Switch | `*.bak` + 配套 |
| **苹果** | iTunes Backup / iCloud Backup | `Manifest.db` + 文件 hash 树 |

### 2.2 PC 端备份（取证大金矿）

不在嫌疑手机但在嫌疑人 **PC** 上的备份：

| 路径 | 内容 |
|---|---|
| Win: `%APPDATA%\Apple Computer\MobileSync\Backup\{UDID}\` | iTunes Backup |
| macOS: `~/Library/Application Support/MobileSync/Backup/{UDID}/` | iTunes Backup |
| Win: `%USERPROFILE%\Documents\Mi PC Suite\` | 小米 |
| `C:\Users\X\Documents\HiSuite\backup\` | 华为 |
| `C:\Users\X\Documents\Smart Switch\` | 三星 |
| Win: `%PROGRAMDATA%\Apple\Lockdown\` | iTunes 配对证书（即使没备份也能再连原机） |

**iTunes Backup 加密**：
- `Manifest.plist` `IsEncrypted=true`
- 密码爆破 Hashcat：mode 14700 (≤10.10) / 14800 (10.11+)
- 工具：`iphone-backup-decrypter` / `iLEAPP` / Cellebrite / Magnet AXIOM

### 2.3 手机克隆 / 搬家

走 WiFi P2P 直传，**不经云**：

| 工具 | 包名 | 落地目录 |
|---|---|---|
| 小米搬家 | `com.miui.huanji` | `/sdcard/MIUI/huanji/` |
| OPPO Clone Phone | `com.coloros.backuprestore` | `/sdcard/Backup/` |
| vivo 互传 | `com.vivo.easyshare` | `/sdcard/EasyShare/` |
| 华为手机克隆 | `com.hicloud.android.clone` | `/sdcard/Huawei/Backup/` |
| 一加 OnePlus Switch | 同 OPPO | — |
| 茄子快传 / SHAREit | 第三方 | `/sdcard/SHAREit/` |

⚠️ 搬家数据**留痕**：嫌疑人删了原机，新机的搬家落地目录可能还有！

### 2.4 适用与限制

✅ 不需 root，合法、低侵入
✅ 联系人、通话、短信、相册、便签、闹钟齐全
❌ 第三方 app 受 `allowBackup` 限制
❌ 微信/QQ 数据库**不在备份内**

---

## 3. Level 3 — 提权（root）

实战最常用。**绕过 `allowBackup` 限制**的唯一办法。

### 3.1 标准流程（Android）

```
1. 解锁 Bootloader (BL)
   - 厂商账号申请解锁码 / fastboot oem unlock
   - ⚠️ 多数厂商解 BL 会清空 user data → 必须先 Level 1/2 抓快照
2. 刷入 patched boot.img (Magisk)
   - boot.img 来自原版 ROM，Magisk 给 ramdisk 打 patch
3. 进系统，Magisk app 授 root
4. adb shell → su → 拷数据
```

### 3.2 已 root 设备的提取

```bash
adb shell
su

# 全 /data tar
tar --exclude=/data/dalvik-cache -cf /sdcard/data.tar /data
# 或分开
tar -cf /sdcard/data_data.tar    /data/data
tar -cf /sdcard/data_user.tar    /data/user
tar -cf /sdcard/data_misc.tar    /data/misc
tar -cf /sdcard/data_system.tar  /data/system

exit; exit
adb pull /sdcard/data.tar
```

### 3.3 致命陷阱 ⚠️

| 陷阱 | 影响 |
|---|---|
| **解 BL 清 user data** | 解锁瞬间数据全没！必须确认机型政策 |
| **dm-verity / AVB** | 改 boot 启动失败，要 `disable-verity` |
| **三星 Knox 永久烧 efuse** | 解 BL 物理破坏，证据状态变化 |
| **SafetyNet / Play Integrity** | root 后银行/支付 app 不能用（取证不在乎） |
| **FBE 加密** | root 也救不了 BFU，必须 AFU |
| **Magisk hide / Zygisk** | 反取证：嫌疑人开了隐藏 root |

### 3.4 已知漏洞利用（无需 BL 解锁）

旧机型走漏洞拿临时 root：
- **MTK BROM 漏洞**（联发科多数旧机）→ `mtkclient`
- **Qualcomm EDL 9008 mode** → firehose 协议 dump
- **Kirin (海思) USB Loader**
- 各类 1day CVE（如老 Pixel CVE-2020-0041）

⚠️ "**逻辑提取边界**"——不解 BL 也能 dump，**法律上更干净**。

### 3.5 iOS 越狱

| 设备 / iOS | 方法 |
|---|---|
| iPhone 5s - X (A7-A11) | **checkm8** BootROM 永久越狱（unc0ver / palera1n） |
| A12+ (XS 起) | 仅软件越狱，更新即失，新机滞后 1-2 年 |
| 商业 | GrayKey / Cellebrite Premium / Elcomsoft iOS Forensic Toolkit |

---

## 4. Level 4 — 逻辑镜像（root 后 dd）

### 4.1 命令
```bash
adb shell
su
ls -la /dev/block/by-name/

dd if=/dev/block/by-name/userdata of=/sdcard/userdata.img bs=4M
dd if=/dev/block/by-name/system   of=/sdcard/system.img   bs=4M
dd if=/dev/block/by-name/persist  of=/sdcard/persist.img  bs=4M
dd if=/dev/block/by-name/modemst1 of=/sdcard/modem.img    bs=4M

# 或写到 PC（不占设备空间）
adb shell "su -c 'dd if=/dev/block/by-name/userdata bs=4M'" > userdata.img
```

### 4.2 镜像分析
```bash
file userdata.img

# F2FS（旗舰常用）
sudo mount -t f2fs -o ro,loop userdata.img /mnt/

# ext4
sudo mount -t ext4 -o ro,loop userdata.img /mnt/

# EROFS
erofsfuse system.img /mnt/

# 商业：FTK Imager / X-Ways / Magnet AXIOM
```

### 4.3 加密镜像问题

dd 出来的 userdata **是密文**！需要：
- **AFU 状态下提取**，密钥在内核内存 → LiME 抠或 dm-crypt 调用
- **导出 keymaster keys** → `/data/misc/vold/`
- 商业工具能直接处理

未解密的 userdata ≈ 一坨随机数据，价值有限。

### 4.4 模拟器镜像（无加密）

```bash
# 夜神 Nox: .vmdk
qemu-nbd --connect=/dev/nbd0 -f vmdk Nox-disk2.vmdk
mount /dev/nbd0p4 /mnt/

# 雷电 / MEmu: 同 vmdk
# Genymotion: .vbox + .vdi
# BlueStacks: .vhd / .bstk
```

详见 `@knowledge/solved/2022_changancup_mobile_exe_apk.md` 长安杯实战。

---

## 5. Level 5 — 物理提取

### 5.1 JTAG / SWD
- 主板调试接口直读 NAND，不经 OS
- 适用：砖机、屏坏、密码忘
- 工具：RIFF Box / EasyJTAG / MEDUSA Pro
- 缺点：找触点难，部分机型 JTAG 已禁

### 5.2 ISP（In-System Programming）
- 直焊到 eMMC/UFS 数据脚
- 比 JTAG 普适（JTAG 被禁也能 ISP）

### 5.3 Chip-off（拆芯片）
- **破坏性**：加热拆 NAND/eMMC/UFS → 编程器读 raw → 软件还原 FTL → 文件系统
- 适用：JTAG/ISP 都不行的硬骨头 + 法律允许破坏

### 5.4 EDL / BROM 厂商模式
- **Qualcomm EDL 9008**：firehose protocol dump
- **MTK BROM**：mtkclient
- **Kirin USB Loader**

⚠️ **加密机型物理提取拿到的也是密文**，需配合密钥提取。Android 14+ 物理价值大幅缩水。

---

## 6. 决策树

```
"要从手机提取数据"
   │
   ├─ Step 1: 设备状态？
   │     ├ 锁机 + 不知密码     → Level 5（漏洞 / 物理）
   │     ├ 已解锁 (AFU)        → Level 3/4
   │     ├ 关机 / BFU          → 先尝试开机解锁
   │     └ 砖机                → Level 5
   │
   ├─ Step 2: 法律 / 时间约束？
   │     ├ 紧急 + 法庭无要求    → Level 3
   │     ├ 需保留原状           → 优先 Level 1/2
   │     └ 可破坏               → Level 5
   │
   ├─ Step 3: 数据要全还是部分？
   │     ├ 几个 app             → Level 1/2 试
   │     ├ 微信/QQ/支付         → Level 3 (allowBackup 拦截)
   │     ├ 完整 user data       → Level 4
   │     └ 整盘 raw             → Level 5
   │
   ├─ Step 4: 机型？
   │     ├ 老 MTK/高通 → 漏洞绕 BL
   │     ├ 新 OPPO/vivo → 锁严，多走商业
   │     └ iPhone A11- → checkm8
   │
   └─ Step 5: 漏数据？补救
         PC 上找备份 / 云端账户司法协助 / 路由器流量
```

---

## 7. 命令速查

```bash
# Level 1: ADB backup
adb backup -all -shared -system -f full.ab
java -jar abe.jar unpack full.ab full.tar
tar -xf full.tar

# Level 2: 厂商备份扫描（Win PC）
where /R C:\Users *.bak 2>nul | findstr /i "huanji backup hisuite mobilesync"
plutil -p {UDID}/Manifest.plist

# Level 3: 提权后全拷
adb shell "su -c 'tar -cf - /data'"   > data.tar
adb shell "su -c 'tar -cf - /sdcard'" > sdcard.tar

# Level 4: 逻辑镜像
adb shell "su -c 'ls -la /dev/block/by-name/'"
adb shell "su -c 'dd if=/dev/block/by-name/userdata bs=4M'" > userdata.img
file userdata.img
sudo mount -t f2fs -o ro,loop userdata.img /mnt/

# Level 5: EDL（高通）
edl printgpt --memory=ufs

# 模拟器
qemu-nbd --connect=/dev/nbd0 -f vmdk Nox-disk2.vmdk
mount /dev/nbd0p4 /mnt/
```

---

## 8. 常见坑

- **`allowBackup="false"`** 让 ADB backup 几乎无用
- **解 BL = 清 user data**：操作前必须先 Level 1/2 抓快照
- **dm-verity / AVB** 让 patched boot 启动失败 → `disable-verity`
- **Knox efuse 永久烧** 改变机器物理状态，法律风险
- **FBE 加密**：BFU 拿到的 dd 镜像是密文
- **PC iTunes Backup 加密**：需密码 / Hashcat 爆破
- **iTunes Backup `Manifest.db`** 才是文件入口
- **多用户隔离**：`/data/user/0` 之外别忘 `/data/user/{N}`
- **WAL / SHM**：必须连 `.db-wal`、`.db-shm` 一起拉，否则丢最新数据
- **adb 普通 shell 读不到别 app `/data/data`**：必须 root
- **Magisk hide / Shamiko 隐藏 root**：嫌疑人反取证
- **EROFS/F2FS 挂载需新内核**（5.4+）
- **磁吸合盖**：旧手机磁铁触发锁屏 → BFU 风险
- **Find My / 远程擦除 30 秒到达**：必须屏蔽袋
- **物理 raw NAND 含 FTL 层**：先还原逻辑映射
- **报告必写**：用了哪一级、是否解 BL、是否改 boot、有无破坏

---

## 9. 实战提取证据链（报告样式）

```
1. 现场处置：屏蔽袋 + 充电
2. 状态确认：AFU / 已知锁屏密码
3. Level 1 ADB backup：抓老 app + 设置（无解锁）
4. Level 2 厂商备份：联系人/短信/通话/照片（无解锁）
5. 解 BL 前：cloud sync 关 + 飞行模式
6. 解 BL → patched boot.img → Magisk
7. Level 3：su 后 tar /data 完整拉取
8. Level 4：dd userdata + persist + modem 镜像（保留 raw）
9. 哈希记录：每个 .tar / .img SHA256
10. 报告：完整描述每步、操作时间、操作人、工具版本
```

---

## 10. 简答题套路

### "提取顺序原则"
**先低侵入后高侵入，先非破坏后破坏**。Level 1 → 2 → 3 → 4 → 5。但实战因 `allowBackup=false` 普及，Level 1/2 常拿不到关键 IM/支付，多直接进 Level 3。

### "解锁 Bootloader 取证风险"
1. 多数厂商解 BL 清 user data（必须先抓快照）
2. 三星 Knox 烧 efuse 物理破坏
3. dm-verity 校验失败启动不了
4. 改变设备状态，法庭质疑可能性
**结论**：解 BL 前必须做 Level 1/2 + 报告记录。

### "物理提取适用场景"
- 砖机 / 屏坏 / 密码忘
- JTAG/ISP/Chip-off/EDL 四种手段
- 现代加密机型物理拿到也是密文，价值缩水

### "iTunes Backup 取证步骤"
1. 找 PC 上 `MobileSync/Backup/{UDID}/`
2. 看 `Manifest.plist IsEncrypted`
3. 加密 → Hashcat 14700/14800 爆破
4. 解密后用 `Manifest.db` 索引解析所有文件
5. 工具：iLEAPP / iphone-backup-extractor / Magnet AXIOM

---

## 11. KB 联动

| 主题 | 跳哪 |
|---|---|
| ADB 命令详解 | `mobile/adb_filesystem_cheatsheet.md` |
| 屏蔽袋 / BFU/AFU | `mobile/fundamentals_cheatsheet.md` |
| 字段实际提取 | `mobile/device_basic_info.md` |
| App 数据库分析（提取后） | `mobile/app_data_analysis.md` |
| 模拟器实战 | `solved/2022_changancup_mobile_exe_apk.md` |
| 微信解密（提取后才用） | `solved/pattern_wechat_db_decrypt.md` |
| 已删 app 恢复 | `mobile/uninstalled_app_recovery.md` |
