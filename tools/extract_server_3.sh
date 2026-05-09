#!/bin/bash
set +e
PSW=$(head -1 /mnt/e/项目/psw)
ROOT=/mnt/server_root
OUT=/mnt/e/ffffff-JIANCAI/2026FIC团体赛/case/server/answers_extract3.txt

run_sudo() { echo "$PSW" | sudo -S bash -c "$1" 2>&1; }

> $OUT
echo "==== extract 3 ====" >> $OUT

echo "" >> $OUT
echo "## 根目录全部" >> $OUT
run_sudo "ls -la $ROOT/" >> $OUT

echo "" >> $OUT
echo "## /www" >> $OUT
run_sudo "ls -la $ROOT/www/ 2>&1" >> $OUT
run_sudo "find $ROOT/www -maxdepth 4 -type d 2>/dev/null | head -30" >> $OUT

echo "" >> $OUT
echo "## /db" >> $OUT
run_sudo "ls -la $ROOT/db/ 2>&1" >> $OUT
run_sudo "find $ROOT/db -maxdepth 3 -type d 2>/dev/null | head -30" >> $OUT

echo "" >> $OUT
echo "## /data" >> $OUT
run_sudo "ls -la $ROOT/data/ 2>&1" >> $OUT

echo "" >> $OUT
echo "## /db/tidb 详情 (lxc rootfs)" >> $OUT
run_sudo "ls -la $ROOT/db/tidb/ 2>&1" >> $OUT
run_sudo "find $ROOT/db/tidb -maxdepth 3 -type d 2>/dev/null | head -20" >> $OUT

echo "" >> $OUT
echo "## TiDB 二进制和版本" >> $OUT
run_sudo "find $ROOT/db -name 'tidb-server' -o -name 'pd-server' -o -name 'tikv-server' 2>/dev/null" >> $OUT
run_sudo "find $ROOT/db -name 'tidb*.tar*' -o -name 'tidb*.deb' 2>/dev/null | head" >> $OUT
run_sudo "find $ROOT/db -name '*tidb*.toml' 2>/dev/null | head" >> $OUT
run_sudo "cat $ROOT/db/tidb/etc/os-release 2>&1 | head" >> $OUT

echo "" >> $OUT
echo "## nginx 配置" >> $OUT
run_sudo "cat $ROOT/etc/nginx/nginx.conf 2>&1 | head -30" >> $OUT
run_sudo "ls $ROOT/etc/nginx/sites-enabled/ 2>&1" >> $OUT
run_sudo "cat $ROOT/etc/nginx/sites-enabled/*.conf 2>&1" >> $OUT
run_sudo "cat $ROOT/etc/nginx/sites-enabled/* 2>&1" >> $OUT
run_sudo "ls $ROOT/etc/nginx/conf.d/ 2>&1" >> $OUT
run_sudo "cat $ROOT/etc/nginx/conf.d/* 2>&1" >> $OUT

echo "" >> $OUT
echo "## /home/mac" >> $OUT
run_sudo "ls -la $ROOT/home/mac/ 2>&1" >> $OUT
run_sudo "cat $ROOT/home/mac/.bash_history 2>&1 | tail -50" >> $OUT

echo "" >> $OUT
echo "## /root" >> $OUT
run_sudo "ls -la $ROOT/root/ 2>&1" >> $OUT
run_sudo "cat $ROOT/root/.bash_history 2>&1 | tail -50" >> $OUT
run_sudo "ls $ROOT/root/history/ 2>&1" >> $OUT

echo "" >> $OUT
echo "## postgres 数据" >> $OUT
run_sudo "ls -la $ROOT/var/lib/postgresql/ 2>&1" >> $OUT

echo "" >> $OUT
echo "## /etc/host* 配置" >> $OUT
run_sudo "cat $ROOT/etc/hostname" >> $OUT
run_sudo "cat $ROOT/etc/hosts" >> $OUT

echo "" >> $OUT
echo "## systemd 服务 (running) " >> $OUT
run_sudo "ls $ROOT/etc/systemd/system/multi-user.target.wants/ 2>&1" >> $OUT

echo "" >> $OUT
echo "## /etc/network 配置" >> $OUT
run_sudo "cat $ROOT/etc/network/interfaces 2>&1" >> $OUT
run_sudo "ls $ROOT/etc/netplan/ 2>&1" >> $OUT
run_sudo "cat $ROOT/etc/netplan/*.yaml 2>&1" >> $OUT

echo "完成 extract3"
