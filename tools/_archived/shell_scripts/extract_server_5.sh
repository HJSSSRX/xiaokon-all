#!/bin/bash
set +e
PSW=$(head -1 /mnt/e/项目/psw)
ROOT=/mnt/server_root
OUT=/mnt/e/ffffff-JIANCAI/2026FIC团体赛/case/server/answers_extract5.txt

run_sudo() { echo "$PSW" | sudo -S bash -c "$1" 2>&1; }

> $OUT

echo "=== maccms.php (site 全部配置) ===" >> $OUT
run_sudo "cat $ROOT/var/www/html/maccms10/application/extra/maccms.php 2>&1" >> $OUT

echo "" >> $OUT
echo "=== database.php (主数据库) ===" >> $OUT
run_sudo "cat $ROOT/var/www/html/maccms10/application/database.php 2>&1" >> $OUT

echo "" >> $OUT
echo "=== domain.php (域名配置) ===" >> $OUT
run_sudo "cat $ROOT/var/www/html/maccms10/application/extra/domain.php 2>&1" >> $OUT

echo "" >> $OUT
echo "=== nginx 完整 site default ===" >> $OUT
run_sudo "cat $ROOT/etc/nginx/sites-available/default 2>&1" >> $OUT

echo "" >> $OUT
echo "=== maccms10 根目录 (找入口 index/admin/api) ===" >> $OUT
run_sudo "ls -la $ROOT/var/www/html/maccms10/" >> $OUT

echo "" >> $OUT
echo "=== public/ ===" >> $OUT
run_sudo "ls -la $ROOT/var/www/html/maccms10/public/ 2>&1" >> $OUT

echo "" >> $OUT
echo "=== 全部 .php 入口 ===" >> $OUT
run_sudo "find $ROOT/var/www/html/maccms10 -maxdepth 2 -name '*.php' -type f" >> $OUT

echo "" >> $OUT
echo "=== application/extra 全部 ===" >> $OUT
run_sudo "ls $ROOT/var/www/html/maccms10/application/extra/" >> $OUT

echo "" >> $OUT
echo "=== install.lock / data ===" >> $OUT
run_sudo "find $ROOT/var/www/html/maccms10 -name 'install.lock' -o -name 'install.php' 2>/dev/null" >> $OUT
run_sudo "ls $ROOT/var/www/html/maccms10/runtime 2>&1 | head -20" >> $OUT

echo "" >> $OUT
echo "=== nginx 主配置 ===" >> $OUT
run_sudo "cat $ROOT/etc/nginx/nginx.conf | head -80" >> $OUT

echo "" >> $OUT
echo "=== nginx sites-enabled ===" >> $OUT
run_sudo "ls -la $ROOT/etc/nginx/sites-enabled/" >> $OUT

echo "" >> $OUT
echo "=== php-fpm 池 ===" >> $OUT
run_sudo "ls $ROOT/etc/php/8.4/fpm/pool.d/ 2>&1" >> $OUT

echo "" >> $OUT
echo "=== 关键: 有没有 admin 路径自定义? ===" >> $OUT
run_sudo "grep -rE 'admin|API_PATH|MAC_ADMIN_PATH' $ROOT/var/www/html/maccms10/application/extra/maccms.php 2>/dev/null | head -10" >> $OUT
run_sudo "grep -rE 'admin' $ROOT/var/www/html/maccms10/application/admin/config.php 2>/dev/null" >> $OUT

echo "完成 extract5"
