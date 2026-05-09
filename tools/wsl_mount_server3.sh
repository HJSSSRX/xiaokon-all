#!/bin/bash
# 挂载已发现的 btrfs md0 (root-data + volum-root 组成的 mdadm RAID)
set +e

PSW=$(head -1 /mnt/e/项目/psw)
run_sudo() { echo "$PSW" | sudo -S bash -c "$1" 2>&1; }

echo "=== 当前 md 状态 ==="
run_sudo "cat /proc/mdstat"
echo ""
run_sudo "mdadm --detail /dev/md0 2>/dev/null"
echo ""

echo "=== 挂载 /dev/md0 (btrfs) 到 /mnt/server_root (ro) ==="
run_sudo "mkdir -p /mnt/server_root"
run_sudo "umount /mnt/server_root 2>/dev/null"
run_sudo "mount -o ro,noload,subvol=@ /dev/md0 /mnt/server_root 2>&1 || mount -o ro /dev/md0 /mnt/server_root 2>&1"
echo ""

echo "=== /mnt/server_root 内容 ==="
ls /mnt/server_root/ 2>&1
echo ""

echo "=== btrfs subvolume list ==="
run_sudo "btrfs subvolume list /mnt/server_root 2>&1"
echo ""

echo "=== /etc/os-release ==="
cat /mnt/server_root/etc/os-release 2>/dev/null
echo ""

echo "=== /etc/debian_version ==="
cat /mnt/server_root/etc/debian_version 2>/dev/null
echo ""

echo "=== /etc/fstab ==="
cat /mnt/server_root/etc/fstab 2>/dev/null
echo ""

echo "=== /etc/hostname ==="
cat /mnt/server_root/etc/hostname 2>/dev/null
echo ""

echo "=== /var/lib/mysql / postgresql / docker ==="
ls /mnt/server_root/var/lib/ 2>/dev/null | grep -E "(mysql|postgres|docker|tidb|mariadb|tikv|pd)" | head -20
echo ""

echo "=== docker images (ro) ==="
ls /mnt/server_root/var/lib/docker/image/ 2>/dev/null
echo ""

echo "=== www / nginx / httpd ==="
ls -la /mnt/server_root/www/ 2>/dev/null
ls -la /mnt/server_root/var/www/ 2>/dev/null
ls -la /mnt/server_root/etc/nginx/ 2>/dev/null
echo ""

echo "=== 完成 ==="
