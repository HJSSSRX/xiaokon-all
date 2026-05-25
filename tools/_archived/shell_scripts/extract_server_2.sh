#!/bin/bash
set +e
PSW=$(head -1 /mnt/e/项目/psw)
ROOT=/mnt/server_root
OUT=/mnt/e/ffffff-JIANCAI/2026FIC团体赛/case/server/answers_extract2.txt

run_sudo() { echo "$PSW" | sudo -S bash -c "$1" 2>&1; }

> $OUT
echo "==== sudo 探查 (wwwroot, lxc, etc) ====" >> $OUT

echo "" >> $OUT
echo "## /www/wwwroot/ (sudo) ##" >> $OUT
run_sudo "ls -la $ROOT/www/wwwroot/" >> $OUT

echo "" >> $OUT
echo "## /www/server/panel/vhost/nginx/ (sudo) ##" >> $OUT
run_sudo "ls -la $ROOT/www/server/panel/vhost/nginx/" >> $OUT

echo "" >> $OUT
echo "## nginx vhost 配置 (sudo) ##" >> $OUT
run_sudo "cat $ROOT/www/server/panel/vhost/nginx/*.conf 2>&1" >> $OUT

echo "" >> $OUT
echo "## /www/server/panel/vhost/rewrite/ (伪静态)" >> $OUT
run_sudo "ls -la $ROOT/www/server/panel/vhost/rewrite/" >> $OUT
run_sudo "ls -la $ROOT/www/server/panel/vhost/" >> $OUT

echo "" >> $OUT
echo "## var/lib/lxc/ (LXC 容器) ##" >> $OUT
run_sudo "ls -la $ROOT/var/lib/lxc/" >> $OUT

echo "" >> $OUT
echo "## var/lib/lxc/mytidb/" >> $OUT
run_sudo "ls -la $ROOT/var/lib/lxc/mytidb/" >> $OUT

echo "" >> $OUT
echo "## lxc 容器配置文件" >> $OUT
run_sudo "cat $ROOT/var/lib/lxc/mytidb/config 2>&1" >> $OUT

echo "" >> $OUT
echo "## TiDB 版本 (从 binary 或 logs)" >> $OUT
run_sudo "find $ROOT/var/lib/lxc/mytidb/rootfs -name 'tidb-server' -o -name 'pd-server' -o -name 'tikv-server' 2>/dev/null | head -5" >> $OUT
run_sudo "find $ROOT/var/lib/lxc/mytidb/rootfs/var/log/tidb -type f 2>/dev/null | head -5" >> $OUT

echo "" >> $OUT
echo "## 浏览器历史 / 邮件 (主用户)" >> $OUT
run_sudo "ls $ROOT/home/ 2>&1" >> $OUT
run_sudo "ls $ROOT/root/ 2>&1" >> $OUT

echo "" >> $OUT
echo "## /etc/sudoers / /etc/passwd 系统用户" >> $OUT
run_sudo "cat $ROOT/etc/passwd 2>&1 | grep -E '/home|root|admin|www|nginx|mysql|postgresql' " >> $OUT

echo "" >> $OUT
echo "## /etc/timeshift /var/lib/snapper / btrfs 子卷快照" >> $OUT
run_sudo "ls -la $ROOT/var/lib/timeshift 2>/dev/null" >> $OUT
run_sudo "ls -la $ROOT/var/lib/snapper/ 2>/dev/null" >> $OUT
run_sudo "btrfs subvolume list $ROOT 2>&1" >> $OUT
run_sudo "ls -la $ROOT/run/timeshift 2>/dev/null" >> $OUT
run_sudo "find $ROOT -maxdepth 3 -name 'snapshot*' 2>/dev/null" >> $OUT
run_sudo "find $ROOT -maxdepth 3 -name '@*' 2>/dev/null | head" >> $OUT

echo "" >> $OUT
echo "## 全局: 完整 btrfs subvolume list" >> $OUT
run_sudo "umount /mnt/btrfs 2>/dev/null; mount -o ro /dev/md0 /mnt/btrfs && btrfs subvolume list /mnt/btrfs && umount /mnt/btrfs" >> $OUT

echo "完成 extract2"
echo "见 $OUT"
