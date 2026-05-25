#!/bin/bash
set +e
PSW=$(head -1 /mnt/e/项目/psw)
ROOT=/mnt/server_root
OUT=/mnt/e/ffffff-JIANCAI/2026FIC团体赛/case/server/verify_suspicious.txt

run_sudo() { echo "$PSW" | sudo -S bash -c "$1" 2>&1; }

> $OUT
echo "==== 验证 3 个可疑答案 ====" >> $OUT

echo "" >> $OUT
echo "## Q5 验证: admin1.php 文件是否存在?" >> $OUT
run_sudo "ls -la $ROOT/var/www/html/maccms10/admin*.php 2>&1" >> $OUT
run_sudo "find $ROOT/var/www/html/maccms10 -maxdepth 2 -name 'admin*.php' -type f 2>/dev/null" >> $OUT
run_sudo "ls $ROOT/var/www/html/maccms10/ | grep -i admin" >> $OUT
run_sudo "ls $ROOT/var/www/html/maccms10/*.php" >> $OUT
echo "对比 nginx 配置 rewrite 规则 (有没有 admin1.php?)" >> $OUT
run_sudo "grep -E 'admin' $ROOT/etc/nginx/sites-available/default" >> $OUT

echo "" >> $OUT
echo "## Q12 验证: 数据库容器技术" >> $OUT
echo "检查 maccms.conf database hostname:" >> $OUT
run_sudo "grep -E 'hostname|host|server' $ROOT/var/www/html/maccms10/application/database.php" >> $OUT
echo "/etc/hosts mytidb 解析:" >> $OUT
run_sudo "grep mytidb $ROOT/etc/hosts" >> $OUT
echo "lxc 容器 mytidb 配置:" >> $OUT
run_sudo "cat $ROOT/var/lib/lxc/mytidb/config 2>&1" >> $OUT
echo "docker 容器列表 (从 /data/containers):" >> $OUT
run_sudo "ls $ROOT/data/containers/ 2>/dev/null" >> $OUT
echo "docker images:" >> $OUT
run_sudo "ls $ROOT/data/image/ 2>/dev/null" >> $OUT
run_sudo "find $ROOT/data/image -name 'config.json' 2>/dev/null | head -3" >> $OUT
echo "查 TiDB 在哪:" >> $OUT
run_sudo "find $ROOT -path '*lxc*tidb*' -prune -o -name 'tidb-server' -print 2>/dev/null | head" >> $OUT
echo "看 docker 容器配置 是否提到 tidb:" >> $OUT
run_sudo "grep -r 'tidb' $ROOT/data/containers/ 2>/dev/null | head -5" >> $OUT
run_sudo "ls $ROOT/data/containers/*/config.v2.json 2>/dev/null | head -3" >> $OUT
run_sudo "for f in $ROOT/data/containers/*/config.v2.json; do echo === \$f ===; head -c 500 \$f; echo; done 2>/dev/null" >> $OUT

echo "" >> $OUT
echo "## Q16 验证: 单选文件系统" >> $OUT
echo "题目 (从 questions_meta 看):" >> $OUT
echo "选项可能是 A.ntfs B.btrfs C.xfs D.LVM" >> $OUT
echo "实际看 fstab + mount + lsblk:" >> $OUT
run_sudo "cat $ROOT/etc/fstab | grep -v '^#' | grep -v '^$'" >> $OUT
run_sudo "lsblk -f 2>&1 | head -50" >> $OUT
echo "如果是单选 'XX 没用' 题, 那 A.ntfs 才对 (确实无 ntfs)" >> $OUT
echo "如果是单选 'XX 用了' 题, 那 B.btrfs 才对" >> $OUT
echo "查找题目原文:" >> $OUT
echo "(从 questions_meta.yaml)" >> $OUT

echo ""
echo "完成"
