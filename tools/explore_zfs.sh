#!/bin/bash
set +e
PSW=$(head -1 /mnt/e/项目/psw)
ROOT=/mnt/server_root
OUT=/mnt/e/ffffff-JIANCAI/2026FIC团体赛/case/server/zfs_explore.txt

run_sudo() { echo "$PSW" | sudo -S bash -c "$1" 2>&1; }

> $OUT
echo "==== ZFS 探查 ====" >> $OUT

echo "" >> $OUT
echo "## 1. ZFS 工具是否可用 ##" >> $OUT
run_sudo "which zfs zpool 2>&1" >> $OUT

echo "" >> $OUT
echo "## 2. 现有池 (在 wsl host) ##" >> $OUT
run_sudo "zpool list 2>&1" >> $OUT
run_sudo "zfs list 2>&1" >> $OUT

echo "" >> $OUT
echo "## 3. 检材的 ZFS 配置 (在挂的 server 里) ##" >> $OUT
run_sudo "ls $ROOT/etc/zfs/" >> $OUT
run_sudo "cat $ROOT/etc/zfs/zpool.cache 2>/dev/null | xxd | head -3" >> $OUT

echo "" >> $OUT
echo "## 4. 服务器历史 zpool 命令 ##" >> $OUT
run_sudo "grep -E 'zpool|zfs|tank|datapool' $ROOT/root/.bash_history 2>/dev/null" >> $OUT

echo "" >> $OUT
echo "## 5. 尝试扫描挂载的 loop 设备里有没有 zfs 池签名 ##" >> $OUT
run_sudo "zpool import -d /dev/mapper -d /dev 2>&1" >> $OUT

echo "" >> $OUT
echo "## 6. 系统挂载历史 (mtab/dmesg)" >> $OUT
run_sudo "find $ROOT/var/log -name 'syslog*' -o -name 'kern.log*' -o -name 'messages*' 2>/dev/null | head -3" >> $OUT
run_sudo "for f in $ROOT/var/log/syslog $ROOT/var/log/kern.log; do
  echo === \$f ===
  zgrep -hE 'zfs|zpool|tidb|lxc' \$f 2>/dev/null | head -5
done" >> $OUT

echo "" >> $OUT
echo "## 7. /var/log/lxc/ ##" >> $OUT
run_sudo "find $ROOT/var/log/lxc -type f 2>/dev/null" >> $OUT
run_sudo "ls $ROOT/var/log/lxc/ 2>/dev/null" >> $OUT
run_sudo "tail -30 $ROOT/var/log/lxc/mytidb.log 2>/dev/null" >> $OUT

echo "" >> $OUT
echo "## 8. mtab 实际挂载快照 ##" >> $OUT
run_sudo "cat $ROOT/etc/mtab 2>/dev/null | head -20" >> $OUT
run_sudo "cat $ROOT/proc/mounts 2>/dev/null | head" >> $OUT

echo "" >> $OUT
echo "## 9. 看关机前 systemd-journal (可能保留挂载历史) ##" >> $OUT
run_sudo "ls $ROOT/var/log/journal/ 2>/dev/null" >> $OUT

echo ""
echo "完成"
