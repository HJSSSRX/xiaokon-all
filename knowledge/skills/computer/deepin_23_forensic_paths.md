---
tags: [technique, deepin, forensic_paths, disk_layout, dde_data, computer_forensics]
tools: [ewfmount, losetup, mount, mmls, find]
category: computer_forensics
difficulty: easy
source: fic2026
date: 2026-05-09
verified: true
---

# Title: Deepin 23.1 取证路径速查

## Disk Layout (A/B 双系统镜像)

```
E01 → ewfmount → raw (80GB)
  ├─ p1: Boot (ext4, 1.5GB) → /boot
  ├─ p2: (no fs, 8GB)       → 扩展分区元数据
  ├─ p3: Roota (ext4, 55GB) → rootfs (不可变系统)
  ├─ p4: (扩展分区)
  └─ p5: _dde_data (ext4, 16GB) → 用户数据 ★
```

## Mount Commands
```bash
ewfmount 检材.E01 /mnt/e01
losetup -f --show -P --read-only /mnt/e01/ewf1
mount -o ro,noload /dev/loop0p3 /mnt/pc_root   # 系统
mount -o ro,noload /dev/loop0p5 /mnt/pc_data   # 用户数据
```

## Key Paths (user=lha)

| 数据类型 | 路径 |
|---|---|
| 用户家目录 | `/mnt/pc_data/home/lha/` |
| 系统配置 | `/mnt/pc_root/etc/` |
| Wine 应用 | `~/.deepinwine/` |
| Chrome | `~/.config/google-chrome/` |
| Deepin 浏览器 | `~/.config/browser/` |
| Firefox | `~/.config/mozilla/` |
| Thunderbird | `~/.thunderbird/` |
| Foxmail (Wine) | `~/.deepinwine/Foxmail/` |
| WPS | `~/.config/Kingsoft/` |
| 搜狗输入法 | `~/.config/SogouPY/`, `~/.config/cpis/`, `~/.sogouinput/` |
| UOS AI | `~/.config/deepin/`, `~/.local/share/deepin/` |
| Clash Verge | `~/.config/clash-verge/` |
| VeraCrypt | `~/.config/VeraCrypt/` |
| Bob Wallet (HNS) | `~/.config/Bob/` |
| SSH | `~/.ssh/` |
| 向日葵 | `~/Sunlogin Files/` |
| 玲珑沙箱 | `~/.linglong/` |

## Quick Recon
```bash
# 用户概览
ls /mnt/pc_data/home/
# 最近文件
find /mnt/pc_data/home/lha -type f -mtime -7 2>/dev/null
# 所有 sqlite db
find /mnt/pc_data/home/lha -name "*.db" -o -name "*.sqlite" 2>/dev/null
# 所有配置文件
find /mnt/pc_data/home/lha/.config -name "*.json" -o -name "*.yaml" -o -name "*.xml" 2>/dev/null
# 加密文件
find /mnt/pc_data/home/lha -name "*.enc" -o -name "*.hc" -o -name "*.vc" 2>/dev/null
```

## Key Takeaways
- Deepin 23.1 数据在 p5 (`_dde_data`), 不在 p3 rootfs
- rootfs 上 `/home` 是空骨架, 真实数据在 `/mnt/data/home`
- Foxmail 跑在 Wine 里, 路径不是标准 Linux 邮件路径
- UOS AI 是系统组件, 不是第三方应用
- mount 必须加 `ro,noload` 避免 journal replay
