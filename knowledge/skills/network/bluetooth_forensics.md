---
tags: [network, pcap, capture, bluetooth, hci, btsnoop, ble, hid, network_forensics]
tools: [wireshark, tshark, capinfos, python]
category: network_forensics
difficulty: medium
source: kb_seed_2026-05-06
verified: false
---

# Bluetooth / HCI / btsnoop 流量取证速查

蓝牙取证题的抓包文件通常是 `.btsnoop`、`.pcap`、`.pcapng`，里面承载 HCI（Host Controller Interface）数据：HCI Command、HCI Event、ACL/SCO，再上层是 LE Advertising Report、L2CAP、ATT、SDP、RFCOMM、HID。

## 总体策略

蓝牙题的答案绝大多数藏在三类包里：

1. **HCI Command / Event** —— 设备改名、改地址、写广播数据
2. **LE Advertising Report** —— 广播包里的 device name、manufacturer data、TX power
3. **L2CAP / RFCOMM / SDP / ATT / HID** —— 业务层数据：远程命令注入、文件传输、GATT 读写

打开 Wireshark 第一步永远是：
- `Statistics → Protocol Hierarchy` 看分级
- `Statistics → Endpoints` / `Conversations` 列出所有 BD_ADDR
- `View → Time Display Format → UTC` 把时区切到 UTC（题目几乎都按 UTC 出题）

## 抓包接口名（很多题第一问的来源）

```powershell
# 列出 pcapng 中的接口
tshark -r capture.pcapng -D

# 文件元信息（包含 if_name / if_description / OS / 抓包工具）
capinfos capture.pcapng
```

常见接口名：
- Linux: `hci0`、`bluetooth-monitor`
- Android: `btsnoop_hci.log`
- Windows USBPcap: `\\.\USBPcap1` + USB 路径如 `DVI1-2.1`（设备 VID/接口）
- macOS: `PacketLogger`

## 关键 HCI Opcode 速查

| Opcode | 名称 | 用途 |
|---|---|---|
| 0x0c13 | Write Local Name | BR/EDR 改本地设备名 |
| 0x0c18 | Write Class of Device | 改设备类别（伪装耳机常用） |
| 0x0c1a | Write Scan Enable | 启用可发现 |
| 0x2005 | LE Set Random Address | BLE 改随机地址 |
| 0x2006 | LE Set Advertising Parameters | 设广播参数 |
| 0x2008 | LE Set Advertising Data | 设广播数据（含 device name、manufacturer data） |
| 0x2009 | LE Set Scan Response Data | 设扫描响应（也可放 device name） |
| 0x200a | LE Set Advertise Enable | 启用广播 |
| 0xfcXX | Vendor Specific | 厂商私有命令，部分用于改 BD_ADDR |

## 常用 tshark 过滤器

```powershell
# 所有 BR/EDR 改名事件（Write Local Name）
tshark -r cap.pcapng -Y "bthci_cmd.opcode == 0x0c13" `
  -T fields -e frame.number -e frame.time_utc -e bthci_cmd.device_name

# 所有 BLE 广播里的 device name
tshark -r cap.pcapng -Y "btcommon.eir_ad.entry.device_name" `
  -T fields -e frame.time_utc -e bthci_evt.bd_addr -e btcommon.eir_ad.entry.device_name

# 所有广播里的 manufacturer specific data
tshark -r cap.pcapng -Y "btcommon.eir_ad.entry.company_id" `
  -T fields -e bthci_evt.bd_addr -e btcommon.eir_ad.entry.company_id -e btcommon.eir_ad.entry.data

# 所有 LE Set Advertising Data 命令（设备主动设广播内容）
tshark -r cap.pcapng -Y "bthci_cmd.opcode == 0x2008" `
  -T fields -e frame.time_utc -e btcommon.eir_ad.entry.device_name -e btcommon.eir_ad.entry.data

# 所有 LE Set Random Address（地址变更）
tshark -r cap.pcapng -Y "bthci_cmd.opcode == 0x2005" `
  -T fields -e frame.time_utc -e bthci_cmd.le.random_address

# Bluetooth HID 报文（键鼠注入）
tshark -r cap.pcapng -Y "bthid" -T fields -e frame.time_utc -e bthid.data

# HOGP（BLE HID over GATT）
tshark -r cap.pcapng -Y "btatt.handle && btatt.opcode == 0x1b" `
  -T fields -e frame.time_utc -e btatt.handle -e btatt.value

# RFCOMM 流（串口/AT/OBEX 常走这里）
tshark -r cap.pcapng -Y "btrfcomm" -T fields -e frame.time_utc -e btrfcomm.channel -e data
```

## 时区与时间格式

- 题目要 UTC+0：用 `frame.time_utc` 字段，**不要**用 `frame.time`（带本地时区）
- 精度要毫秒：`tshark` 默认就是微秒，截到 `.123` 即可
- Wireshark GUI: `View → Time Display Format → UTC Date and Time of Day` + `… with seconds`

## 锁定"同一物理设备"的两个 BD_ADDR

设备可能改名也可能改地址。把"同一物理设备的两次现身"对应起来的特征：

1. **Manufacturer Specific Data 的厂商 ID + 数据载荷一致**（最强证据）
2. **Service UUID 列表完全一致**
3. **TX Power、Adv Interval、广播帧型号一致**
4. **改名/改址前后包之间的时间间隔很短**（毫秒级紧挨）

## Bluetooth HID 键码还原（题型 7-9 常用）

Bluetooth HID 报文头：
- `0xA1` = DATA 输入报文（设备 → 主机）
- `0xA2` = DATA 输出报文（主机 → 设备，注入键盘走这个）

之后是 Report ID（1B，可能省略），紧接 8 字节键盘报文：
```
[modifier] [reserved] [key1] [key2] [key3] [key4] [key5] [key6]
```

USB HID Usage ID 表（部分常用）：

| Code | 键 | Code | 键 |
|---|---|---|---|
| 0x04..0x1d | a..z | 0x1e..0x27 | 1..9, 0 |
| 0x28 | Enter | 0x29 | Esc |
| 0x2a | Backspace | 0x2b | Tab |
| 0x2c | Space | 0x2d | - |
| 0x2e | = | 0x2f | [ |
| 0x30 | ] | 0x31 | \ |
| 0x33 | ; | 0x34 | ' |
| 0x36 | , | 0x37 | . |
| 0x38 | / |  |  |

Modifier byte 位定义：
- bit0 LCtrl, bit1 LShift, bit2 LAlt, bit3 LGUI
- bit4 RCtrl, bit5 RShift, bit6 RAlt, bit7 RGUI

Python 还原脚本骨架：

```python
import sys

KEYMAP = {
    **{i: chr(ord('a') + i - 4) for i in range(0x04, 0x1e)},
    0x1e: '1', 0x1f: '2', 0x20: '3', 0x21: '4', 0x22: '5',
    0x23: '6', 0x24: '7', 0x25: '8', 0x26: '9', 0x27: '0',
    0x28: '\n', 0x29: '<ESC>', 0x2a: '<BS>', 0x2b: '\t',
    0x2c: ' ', 0x2d: '-', 0x2e: '=', 0x2f: '[', 0x30: ']',
    0x31: '\\', 0x33: ';', 0x34: "'", 0x35: '`',
    0x36: ',', 0x37: '.', 0x38: '/',
}
SHIFT_MAP = {
    '1':'!','2':'@','3':'#','4':'$','5':'%','6':'^','7':'&','8':'*','9':'(','0':')',
    '-':'_','=':'+','[':'{',']':'}','\\':'|',';':':',"'":'"','`':'~',',':'<','.':'>','/':'?',
}

def decode_report(hex_bytes):
    # hex_bytes: 8 bytes keyboard report (modifier + reserved + 6 keys)
    if len(hex_bytes) < 8:
        return ''
    mod = hex_bytes[0]
    shift = bool(mod & 0x22)  # LShift | RShift
    out = []
    for code in hex_bytes[2:8]:
        if code == 0:
            continue
        ch = KEYMAP.get(code, f'<{code:02x}>')
        if shift and ch.isalpha():
            ch = ch.upper()
        elif shift and ch in SHIFT_MAP:
            ch = SHIFT_MAP[ch]
        out.append(ch)
    return ''.join(out)

# 用法：
# tshark -r cap.pcapng -Y "bthid" -T fields -e bthid.data > hid.txt
# 然后逐行解析（注意去重 —— 按键释放也会发空报文，要过滤连续相同帧）
```

去重要点：相同键持续按下时会重复发同一报文，**只在报文从"无键"转为"有键"或键码变化时**记录，否则会重复字符。

## 影子账户取证小贴士

Windows 影子账户特征：
- 账号名末尾带 `$`，`net user` 看不到
- 创建命令组合：
  ```
  net user hacker$ Passw0rd /add
  net localgroup administrators hacker$ /add
  ```
- 进一步隐藏：`reg add` 修改 `HKLM\SAM\SAM\Domains\Account\Users\Names\hacker$` 的 F 值复制 Administrator 的 SID

题目里 "影子账户" 几乎都来自键盘注入还原后的 `net user xxx$ yyy /add`。

## 题型对照表（流量分析-1 ~ 9 风格题）

| 题目特征 | 主要过滤器 / 字段 | 备注 |
|---|---|---|
| 抓包接口/设备 | `capinfos`, `tshark -D`, pcapng IDB | USBPcap 路径如 `DVIx-y.z` |
| 设备原始名 | `bthci_cmd.device_name`, `btcommon.eir_ad.entry.device_name`, `bthci_evt.remote_name` | 找 BD_ADDR 最早一次出现的 name |
| 改名/改址前后 MAC | opcode 0x2005 + manufacturer data 配对 | md5 用小写、注意冒号大写 |
| 首次改名时间 (UTC) | opcode 0x0c13 / 0x2008 + frame.time_utc | 切 UTC 显示 |
| 手机制造商数据 | `btcommon.eir_ad.entry.company_id` + data | OUI 区分手机 vs dongle |
| 真名 | 手机蓝牙名常含用户名 ("XXX 的 iPhone") |  |
| 命令条数 | bthid 报文还原后数 `\n` |  |
| 影子账户 账/密 | 还原命令里找 `net user $$ /add` |  |
| 最后一条命令 | 还原命令序列末条做 md5 | 注意完整原文含空格 |

## 推荐做题顺序

1. 接口/元信息题（最快，直接 `capinfos`）
2. 改名 / 改址 / 时间题作为一组：一把过滤跑出时间线
3. 手机 / 制造商 / 真名作为一组：锁定手机 BD_ADDR 后顺势答完
4. 键盘注入题最后做：先把整个命令文本还原出来再分别答

## 常见坑

- 时区：题目要 UTC+0，Wireshark 默认本地时区
- MAC 大小写：`md5` 是 32 位**小写**，但 MAC 字符串本身按题面格式（一般大写）
- HID 还原：Bluetooth HID 报文有 `0xA1/0xA2` 头；连续相同帧要去重
- 厂商私有改 BD_ADDR：常用 `OGF=0x3F` 的 vendor opcode，过滤 `bthci_cmd.opcode.ogf == 0x3f`
- BLE 公共/随机地址：`bthci_evt.bd_addr_type` 区分 public(0) / random(1)
