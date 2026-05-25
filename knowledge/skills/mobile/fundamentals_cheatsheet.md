---
tags: [mobile, fundamentals, theory, imei, meid, iccid, imsi, msisdn, faraday, bfu,
  afu, ram, rom, flash, baseband, exam_prep, mobile_forensics]
tools: []
category: mobile_forensics
difficulty: foundational
source: kb_seed_2026-05-08
verified: false
related: [device_basic_info.md, app_data_analysis.md, timestamps_reference.md, geolocation_forensics.md]
---

# 手机取证基础理论速查（考前 10 分钟扫一遍）

> 这页面不教操作，专治**选择题 / 简答题**：4 大标识符差异、信号屏蔽 SOP、RAM/ROM/Flash 区分、BFU/AFU、Android/iOS 对比。
>
> **一句话破题**：处置 → 屏蔽袋 + 持续供电 + 保持 AFU；标识符 → 看 §1 一图记牢。

## 0. 一图记牢

```
┌─────────────────────────────────────────────────────────┐
│  设备硬件层  ──  IMEI / MEID    （烙在基带，跟着手机走）  │
│  SIM 卡层    ──  ICCID          （印在 SIM 卡上）        │
│  用户身份层  ──  IMSI           （存在 SIM 卡里，跟着用户）│
│  电话号码层  ──  MSISDN         （运营商分配的号码）      │
└─────────────────────────────────────────────────────────┘

ICCID    →  哪张 SIM 卡（实体卡序列号）
IMSI     →  这张 SIM 卡是谁的（用户身份）
MSISDN   →  打这张卡用什么号码（电话号）
IMEI     →  哪台手机（硬件）
MEID     →  CDMA 时代的 IMEI

SIM 换手机：IMEI 变，IMSI/ICCID 不变
手机换 SIM：IMEI 不变，IMSI/ICCID/MSISDN 都变
```

---

## 1. 四大移动标识符

### 1.1 IMEI

| 项 | 内容 |
|---|---|
| 含义 | 国际移动设备识别码 — 标识**手机硬件** |
| 长度 | **15 位十进制** |
| 结构 | TAC(8) + SNR(6) + CD(1)<br>TAC=型号分配码，SNR=厂商序列，CD=Luhn 校验位 |
| 适用网络 | GSM / WCDMA / LTE / 5G NR |
| 存储 | 基带芯片 EFS 分区，烧录写入；软件不可改 |
| 查看 | `*#06#`（任意手机通用） |
| **IMEISV** | 16 位，多 1 位软件版本号 |
| **双卡手机** | 两个 IMEI（IMEI1 / IMEI2） |

### 1.2 MEID

| 项 | 内容 |
|---|---|
| 含义 | 移动设备识别码 — **CDMA 网络**用 |
| 长度 | **14 位十六进制**（也可表 18 位十进制） |
| 适用 | CDMA / CDMA2000（中国电信老网、Verizon、Sprint） |
| 关系 | MEID 是 ESN(11 位) 的扩展；现代手机同时有 IMEI 和 MEID |

⚠️ 国内 2G/3G CDMA 已退网，电信现在 4G/5G 用 IMEI；老题/卡贴可能考 MEID。

### 1.3 ICCID

| 项 | 内容 |
|---|---|
| 含义 | **SIM 卡**唯一序列号 — 印在卡上 |
| 长度 | **19-20 位十进制** |
| 结构 | 89 + CC(2) + IIN(1-3) + 卡号 + Luhn(1)<br>89=通信行业前缀；CC=86 中国；IIN=00 移动 / 06 联通 / 03 电信 |
| 适用 | 一切蜂窝制式 + eSIM |
| 存储 | SIM 卡 EF_ICCID |
| 查看 | Android `*#*#4636#*#*`、iOS 设置→关于；卡背面肉眼可见 |

### 1.4 IMSI

| 项 | 内容 |
|---|---|
| 含义 | **用户**身份标识（鉴权用） |
| 长度 | **不超过 15 位十进制** |
| 结构 | MCC(3) + MNC(2-3) + MSIN<br>MCC 460=中国 |
| 存储 | SIM 卡 EF_IMSI |
| 隐私性 | 比 ICCID 更敏感；攻击：IMSI Catcher（伪基站） |
| 查看 | 老 Android `*#*#4636#*#*`，新版本对 app 隐藏 |

### 1.5 MSISDN

| 项 | 内容 |
|---|---|
| 含义 | 国际标准电话号码 |
| 结构 | CC + NDC + SN（中国：86 + 138 + 12345678） |
| 存储 | SIM 卡 EF_MSISDN（不一定写）+ 各 app 注册时填 |

### 1.6 中国 MCC / MNC 速记

| MCC | MNC | 运营商 |
|---|---|---|
| 460 | **00 / 02 / 04 / 07 / 08** | 中国移动 |
| 460 | **01 / 06 / 09** | 中国联通 |
| 460 | **03 / 05 / 11** | 中国电信 |
| 460 | 15 | 中国广电 |

---

## 2. 信号屏蔽 / 现场处置

### 2.1 为什么要屏蔽

设备一旦联网：
- **远程擦除**（Find My / 查找设备）瞬间清空数据
- 远程定位/追踪 → 嫌疑人销毁证据
- 锁机命令推送 → 无法解锁
- 自动 OTA → 改变系统状态
- 后台数据同步 → 改变内存/存储

### 2.2 屏蔽方法（从优到劣）

| 方法 | 优 | 缺 |
|---|---|---|
| **法拉第袋 / 屏蔽袋**（推荐） | 完全屏蔽，便携，不改设备状态 | 屏蔽中持续找信号**电池快速耗尽**，需配充电宝 |
| **法拉第柜 / 屏蔽箱** | 实验室级别 | 不便携 |
| **飞行模式** | 最简单 | 嫌疑人可远程关闭；蓝牙/WiFi 仍开 |
| 关 WiFi + 移动数据 | — | 同上，不防 SIM 主动连基站 |
| 拔 SIM / 取电池 | 彻底断蜂窝 | 现代手机电池不可拆；拔 SIM 可能触发 app 自毁 |
| 关机 | 最彻底 | 改变状态；开机要密码 / 触发 BFU |

### 2.3 现场标准 SOP

```
1. 立刻装入屏蔽袋（亮屏勿熄屏，保持 AFU）
2. 屏蔽袋中持续充电（屏蔽找信号耗电极快）
3. 拍照记录屏幕、SIM 卡槽、损伤
4. 运回实验室再脱袋
5. 实验室用法拉第柜 / 屏蔽房作业
```

### 2.4 BFU vs AFU（**最重要概念**）

| 状态 | 全称 | 含义 |
|---|---|---|
| **BFU** | Before First Unlock | 开机后未输过密码 — 文件系统**仍加密**，可读极少 |
| **AFU** | After First Unlock | 已输过密码 — 加密密钥在内存，**大部分 user data 可读** |

⚠️ **黄金原则**：缴获时若设备**已亮屏 / 已解锁** → **千万别关机**，保持 AFU 直到实验室。

---

## 3. RAM / ROM / Flash

| 概念 | 通俗叫法 | 真实含义 |
|---|---|---|
| **RAM** | "运行内存"（8GB 运存） | DRAM，**易失**，程序运行时用 |
| **ROM** | "机身存储"（256GB） | ⚠️ 商家口语错称，**实际是 NAND Flash**（可读写）。真正 ROM = mask ROM 已过时 |
| **eMMC** | embedded MultiMediaCard | 早期/中低端"ROM"标准，慢 |
| **UFS** | Universal Flash Storage | 现代旗舰主流（UFS 3.1/4.0），快 |
| **NVMe SSD** | — | iPhone 6s 起用 |
| **TF / microSD** | 外置卡 | 中低端 Android 还有，旗舰多取消 |
| **基带 NV / EFS** | — | 独立小分区，存 IMEI/校准/IMSI 等 |
| **SE (Secure Element)** | 安全芯片 | 指纹模板、支付密钥、Apple Secure Enclave |

### 3.1 取证含义对照

| 题目说法 | 实际意思 |
|---|---|
| "提取手机 ROM" | 提 NAND Flash 用户数据分区（`/data`） |
| "RAM 取证" | 内存取证 — Android LiME / Volatility，iOS 几乎做不到 |
| "提取系统镜像" | 通常 `system + data + cache` 多分区 dump |
| "TF 卡取证" | 单独拔卡 dd，按 FAT/exFAT 分析 |

### 3.2 必考点

- **存储速度**：UFS > eMMC > microSD
- **数据擦除**：SSD/UFS 有 wear leveling + TRIM，**删了的可能立即被 GC 物理擦除**，比磁盘恢复难
- **加密**：Android 现代默认 **FBE**（File-Based Encryption），iOS 默认全盘 + per-file key
- **JTAG / Chip-off**：物理取证，对加固/砖机有效；现代加密机型拿到也是密文

---

## 4. 手机硬件

### 4.1 主要芯片

| 芯片 | 角色 |
|---|---|
| **AP** (Application Processor) | 主 CPU，跑 OS（骁龙 8 Gen3、A17 Pro） |
| **BP / Baseband** | 基带，**IMEI 在这里** |
| **PMIC** | 电源管理 |
| **SE / Secure Enclave** | 生物识别、密钥 |
| **NFC controller** | 近场通信 |
| **WiFi/BT combo** | 通常一颗（如 BCM4356） |

### 4.2 Android 典型分区

```
boot       → kernel + ramdisk
recovery   → 恢复模式
system     → 只读系统（OTA 之间不变）
vendor     → 厂商定制层
data       → 用户数据 ★★★ 取证主战场
cache      → 缓存
persist    → 出厂校准 + WiFi/BT MAC + IMEI 备份
modem/efs  → 基带数据
misc       → 启动状态标志
```

### 4.3 屏幕 / 锁

- **指纹 / Face ID**：模板存 SE，**云端无备份**；嫌疑人去世/拒不配合无法复现
- **PIN/Pattern/Password**：哈希存 `/data/system/locksettings.db`，可暴力破解（有冷却 / 多次失败擦除）
- **绘图密码 (Pattern)**：仅 Android，9 点连线，状态空间约 38 万，**最弱**

### 4.4 电池

- 现代旗舰**电池不可拆**
- 屏蔽袋里**温度过低**会快速掉电，注意保暖
- 电池循环次数（iOS 设置 → 电池可看，Android 厂商不一）

---

## 5. Android vs iOS 速记

| 维度 | Android | iOS |
|---|---|---|
| 内核 | Linux | XNU (Mach + BSD) |
| 文件系统 | ext4 / F2FS | APFS |
| 加密 | FBE / 旧 FDE | 全盘 + per-file |
| 包格式 | APK (zip) | IPA (zip) |
| 沙箱 | UID 隔离 | 容器（UUID 目录） |
| Root | 解锁 BL → Magisk | 越狱（checkm8 < A11 永久） |
| 备份 | adb backup（受限）/ 厂商工具 | iTunes / iCloud |
| 提取难度 | 中 | 高（A12+ 几乎无越狱） |

### 5.1 Android 版本 ↔ API ↔ 安全特性

| 版本 | API | 关键 |
|---|---|---|
| 6 | 23 | 运行时权限（必考） |
| 7 | 24 | Direct Boot |
| 8 | 26 | 后台限制 |
| 9 | 28 | FBE 强制 |
| 10 | 29 | Scoped Storage、MAC 随机化 |
| 11 | 30 | one-time perm、Scoped Storage 强制 |
| 12 | 31 | 蓝牙权限拆分 |
| 13 | 33 | `READ_MEDIA_*` 拆、通知权限 |
| 14 | 34 | 部分照片授权 |

### 5.2 iOS 越狱

| iOS / 机型 | 关键 |
|---|---|
| iOS 8 起 | 全盘加密默认开 |
| iPhone 5s - X (A7-A11) | **checkm8 BootROM 漏洞，永久可越狱** |
| A12+（XS 起） | 仅软件越狱，更新即失效，新机型常滞后 1-2 年 |

---

## 6. 常考选择题速记

| 问 | 答 |
|---|---|
| IMEI 多少位？ | **15 位十进制** |
| ICCID 多少位？ | **19-20 位** |
| IMSI 多少位？ | **不超过 15 位** |
| MEID 多少位？ | **14 位十六进制** |
| 查 IMEI 通用命令？ | `*#06#` |
| IMSI 第一段是什么？ | **MCC（中国 460）** |
| 中国移动 MNC？ | **00/02/04/07/08** |
| 现代手机 ROM 实际是？ | **NAND Flash（UFS / eMMC）** |
| 屏蔽现场用？ | **法拉第袋** |
| 保持设备状态最佳？ | **屏蔽袋 + 持续供电** |
| BFU / AFU 谁能读数据？ | **AFU** |
| Android 加密默认是？ | **FBE** |
| IMEI 校验算法？ | **Luhn** |

---

## 7. 简答题套路（教科书答案）

### 7.1 "对在场可疑手机的处置"

```
1. 现场拍照 + 记录屏幕状态
2. 不按任何按键 / 不滑动（保持 AFU）
3. 装入屏蔽袋
4. 连接充电宝持续供电
5. 避免接触磁铁（旧手机磁吸合盖触发锁屏）
6. 运回实验室屏蔽柜内操作
7. 优先保持开机解锁状态（AFU），再考虑提取
```

### 7.2 "IMEI 与 IMSI 区别"

- **IMEI** 标识手机硬件，烧录在基带，15 位十进制
- **IMSI** 标识用户身份，存 SIM 卡，最长 15 位，结构 MCC+MNC+MSIN
- 换手机 IMEI 变，换 SIM IMSI 变；二者结合才能在网络中唯一确认"谁的什么手机"

### 7.3 "为什么要信号屏蔽"

防远程擦除、远程定位、锁机推送、OTA 升级、后台同步五大风险，最大化保留证据原始状态。

### 7.4 "ROM 容量是什么"

口语错称。手机宣传的"256GB ROM"实际是 **NAND Flash 存储**（UFS 或 eMMC），可读写，存系统 + 用户数据；真正的 ROM（mask ROM）只读，现代手机不用。

---

## 8. 决策树

```
"基础理论题"
   │
   ├─ 问标识符差异     → §0 一图记牢
   ├─ 问位数/结构      → §1 表格
   ├─ 问 SIM 卡相关    → ICCID / IMSI / MSISDN
   ├─ 问网络制式       → IMEI=GSM/LTE/5G, MEID=CDMA
   ├─ 问 MCC/MNC       → §1.6
   ├─ 问现场处置       → §2 SOP
   ├─ 问 BFU/AFU       → §2.4
   ├─ 问"ROM X GB"含义 → §3 NAND Flash
   ├─ 问加密差异       → §3.2 / §5
   ├─ 问 Android/iOS   → §5
   └─ 问"为何 IMEI 镜像里搜不到" → §4.1 基带独立芯片
```

---

## 9. 实验 / 命令对应

```bash
# 拨号查 IMEI
*#06#

# Android 老方法查 IMSI (AOSP)
*#*#4636#*#*

# Luhn 校验位计算（IMEI/ICCID 通用）
python3 -c "
def luhn(s):
    s=[int(c) for c in s][::-1]
    return (sum(s[::2]) + sum(sum(divmod(d*2,10)) for d in s[1::2])) % 10 == 0
print(luhn('358240051111110'))
"

# 实际从镜像提（详见 device_basic_info.md）
sqlite3 /data/data/com.android.providers.telephony/databases/telephony.db \
  "SELECT _id, icc_id, display_name, carrier_name, number, imsi, mcc, mnc FROM siminfo"

plutil -p /private/var/wireless/Library/Preferences/com.apple.commcenter.plist \
  | grep -iE "IMEI|MEID|ICCID|PhoneNumber"
```

---

## 10. KB 联动

| 主题 | 跳哪 |
|---|---|
| **实际从镜像提取这些字段** | `mobile/device_basic_info.md` |
| 时间戳格式 | `skills/timestamps_reference.md` |
| MAC 反查地理位置 | `mobile/geolocation_forensics.md` (§4) |
| App 数据分析 | `mobile/app_data_analysis.md` |
| APK 加解密/权限 | `mobile/apk_crypto_analysis.md` / `apk_permission_analysis.md` |
| 已删 app 恢复 | `mobile/uninstalled_app_recovery.md` |
| 反取证识别 | `mobile/anti_forensics_and_misleading.md` |
| IoT 设备 | `mobile/iot_device_forensics.md` |
| 虚拟货币 | `mobile/crypto_currency_forensics.md` |
