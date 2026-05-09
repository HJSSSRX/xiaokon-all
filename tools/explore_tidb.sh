#!/bin/bash
set +e
PSW=$(head -1 /mnt/e/项目/psw)
ROOT=/mnt/server_root
OUT=/mnt/e/ffffff-JIANCAI/2026FIC团体赛/case/server/tidb_explore.txt

run_sudo() { echo "$PSW" | sudo -S bash -c "$1" 2>&1; }

> $OUT
echo "==== TiDB LXC mytidb 探查 ====" >> $OUT

echo "" >> $OUT
echo "## 1. /db 目录全部 (lxc.rootfs.path = dir:/db/tidb) ##" >> $OUT
run_sudo "ls -la $ROOT/db/" >> $OUT
run_sudo "ls -la $ROOT/db/tidb/" >> $OUT

echo "" >> $OUT
echo "## 2. /db/tidb 子目录 (LXC ubuntu rootfs?) ##" >> $OUT
run_sudo "ls $ROOT/db/tidb/etc/" >> $OUT
run_sudo "cat $ROOT/db/tidb/etc/os-release 2>&1 | head -10" >> $OUT
run_sudo "cat $ROOT/db/tidb/etc/hostname 2>&1" >> $OUT

echo "" >> $OUT
echo "## 3. TiDB 二进制 (查版本 - Q13) ##" >> $OUT
run_sudo "find $ROOT/db -name 'tidb-server' -o -name 'pd-server' -o -name 'tikv-server' 2>/dev/null" >> $OUT
run_sudo "find $ROOT/db -name 'tiup*' 2>/dev/null" >> $OUT
run_sudo "find $ROOT/db -name 'tidb*' -type f 2>/dev/null | head -20" >> $OUT

echo "" >> $OUT
echo "## 4. TiDB 配置文件 ##" >> $OUT
run_sudo "find $ROOT/db -name '*.toml' 2>/dev/null | head" >> $OUT
run_sudo "find $ROOT/db -name 'config.toml' 2>/dev/null | head" >> $OUT

echo "" >> $OUT
echo "## 5. TiDB 数据目录 (mac2 数据库) ##" >> $OUT
run_sudo "find $ROOT/db -name 'mac2' -o -name 'mac_*' 2>/dev/null | head -10" >> $OUT
run_sudo "ls $ROOT/db/tidb/var/lib/ 2>&1" >> $OUT
run_sudo "ls $ROOT/db/tidb/data/ 2>&1" >> $OUT

echo "" >> $OUT
echo "## 6. tiup deploy (常见 TiDB 部署位置) ##" >> $OUT
run_sudo "find $ROOT/db -path '*deploy*' -type d 2>/dev/null | head -10" >> $OUT
run_sudo "find $ROOT/db -name '.tiup' -type d 2>/dev/null" >> $OUT

echo "" >> $OUT
echo "## 7. /root/.tiup 或 /home/.tiup ##" >> $OUT
run_sudo "ls $ROOT/db/tidb/root/ 2>&1" >> $OUT
run_sudo "ls $ROOT/db/tidb/root/.tiup/ 2>&1" >> $OUT
run_sudo "ls $ROOT/db/tidb/home/ 2>&1" >> $OUT

echo "" >> $OUT
echo "## 8. TiDB log files (启动日志带版本) ##" >> $OUT
run_sudo "find $ROOT/db -name '*.log' 2>/dev/null | head -10" >> $OUT
run_sudo "find $ROOT/db -name 'tidb*.log' 2>/dev/null" >> $OUT
run_sudo "find $ROOT/db -path '*tidb*log*' 2>/dev/null | head -10" >> $OUT

echo ""
echo "完成"
