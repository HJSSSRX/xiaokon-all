---
tags: [disk_forensics, e01, raw, mount, ewfmount, ftk_imager, file_system, computer_forensics]
tools: [ewfmount, ewfinfo, losetup, mount, file, sqlite3, find]
category: computer_forensics
difficulty: easy
source: fic2026
date: 2026-05-05
verified: true
---

# Title: 磁盘镜像挂载与分析 (E01/RAW)

## Problem
取证中需要挂载 E01/DD/RAW 等格式磁盘镜像进行文件系统分析。

## Solution Steps

1. 识别镜像格式
   ```bash
   file disk_image.E01
   ewfinfo disk_image.E01    # E01 详细信息
   ```

2. 挂载 E01 镜像
   ```bash
   # 方法1: ewfmount (Linux, 推荐)
   sudo mkdir /mnt/e01_mnt
   sudo ewfmount disk_image.E01 /mnt/e01_mnt
   # 产生 /mnt/e01_mnt/ewf1 虚拟设备

   # 再挂载文件系统
   sudo mount -o ro,loop /mnt/e01_mnt/ewf1 /mnt/disk/

   # 方法2: 转 raw 后挂载
   ewfexport disk_image.E01 -f raw -o disk_image.raw
   sudo losetup /dev/loop0 disk_image.raw
   sudo mount -o ro /dev/loop0 /mnt/disk/

   # 方法3: FTK Imager (Windows GUI)
   # 方法4: Arsenal Image Mounter (Windows, 推荐)
   ```

3. 处理多分区
   ```bash
   # 查看分区表
   sudo fdisk -l /mnt/e01_mnt/ewf1
   # 或
   mmls disk_image.raw

   # 按偏移量挂载特定分区
   sudo mount -o ro,loop,offset=$((512*2048)) /mnt/e01_mnt/ewf1 /mnt/part1/
   ```

4. 分析文件系统
   ```bash
   # 查找关键文件
   find /mnt/disk/ -name "*.db" -o -name "*.sqlite" 2>/dev/null
   find /mnt/disk/ -name "*mail*" -o -name "*Mail*" 2>/dev/null
   find /mnt/disk/ -name "*.xml" -o -name "*.json" -o -name "*.ini" 2>/dev/null

   # 查看系统信息
   cat /mnt/disk/etc/os-release
   cat /mnt/disk/etc/fstab
   ```

5. 卸载
   ```bash
   sudo umount /mnt/disk/
   sudo umount /mnt/e01_mnt/
   ```

## Key Takeaways
- 始终使用 `ro` (只读) 模式挂载，避免修改原始镜像
- E01 需先 ewfmount 产生虚拟设备，再 mount 文件系统（两步）
- 多分区镜像需要用 `mmls` 或 `fdisk` 查看分区偏移量
- Windows 上推荐 Arsenal Image Mounter，比 FTK Imager 更灵活
- btrfs/LVM 分区需要额外工具: `btrfs-progs`, `lvm2`
