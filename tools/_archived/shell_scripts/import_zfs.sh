#!/bin/bash
set +e
PSW=$(head -1 /mnt/e/项目/psw)
ROOT=/mnt/server_root
OUT=/mnt/e/ffffff-JIANCAI/2026FIC团体赛/case/server/zfs_import.txt

run_sudo() { echo "$PSW" | sudo -S bash -c "$1" 2>&1; }

> $OUT
echo "==== ZFS import 尝试 ====" >> $OUT

echo "" >> $OUT
echo "## 1. modprobe zfs (检查内核模块) ##" >> $OUT
run_sudo "modprobe zfs 2>&1" >> $OUT
run_sudo "lsmod | grep zfs" >> $OUT

echo "" >> $OUT
echo "## 2. zpool import 扫描 (用 /media/zfs 作为后端) ##" >> $OUT
run_sudo "zpool import -d $ROOT/media -N -o readonly=on db 2>&1" >> $OUT
echo "(尝试 readonly import)" >> $OUT

echo "" >> $OUT
echo "## 3. 如果 import 成功, 看 zpool 状态 ##" >> $OUT
run_sudo "zpool list" >> $OUT
run_sudo "zpool status db 2>&1" >> $OUT

echo "" >> $OUT
echo "## 4. zfs list (看 dataset) ##" >> $OUT
run_sudo "zfs list -r db 2>&1" >> $OUT

echo "" >> $OUT
echo "## 5. 挂载 db/tidb 到 /mnt/zfs_tidb ##" >> $OUT
run_sudo "mkdir -p /mnt/zfs_tidb"
run_sudo "zfs set mountpoint=/mnt/zfs_tidb db/tidb 2>&1 || true"
run_sudo "zfs mount -a 2>&1"
run_sudo "ls /mnt/zfs_tidb/" >> $OUT
run_sudo "ls -la /mnt/zfs_tidb/" >> $OUT

echo "" >> $OUT
echo "## 6. 直接 mount 默认挂载点 ##" >> $OUT
run_sudo "zfs mount db/tidb 2>&1" >> $OUT
run_sudo "mount | grep zfs" >> $OUT
run_sudo "ls /db/tidb 2>&1" >> $OUT

echo ""
echo "完成 zfs_import"
