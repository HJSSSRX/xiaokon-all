#!/bin/bash
set +e
PSW=$(head -1 /mnt/e/项目/psw)
ROOT=/mnt/server_root
OUT=/mnt/e/ffffff-JIANCAI/2026FIC团体赛/case/server/answers_extract4_maccms.txt

run_sudo() { echo "$PSW" | sudo -S bash -c "$1" 2>&1; }

> $OUT
echo "==== extract 4: maccms 探查 ====" >> $OUT

echo "" >> $OUT
echo "## /var/www/html 全部" >> $OUT
run_sudo "ls -la $ROOT/var/www/html/" >> $OUT

echo "" >> $OUT
echo "## maccms10 主目录" >> $OUT
run_sudo "ls -la $ROOT/var/www/html/maccms10/" >> $OUT

echo "" >> $OUT
echo "## 入口 PHP 文件 (Q5)" >> $OUT
run_sudo "ls $ROOT/var/www/html/maccms10/*.php 2>&1" >> $OUT
run_sudo "find $ROOT/var/www/html/maccms10 -maxdepth 2 -name '*.php' 2>&1 | head -20" >> $OUT

echo "" >> $OUT
echo "## maccms 配置 (database.php / config.php)" >> $OUT
run_sudo "find $ROOT/var/www/html/maccms10/application -name 'database.php' -o -name 'config.php' 2>/dev/null" >> $OUT
run_sudo "cat $ROOT/var/www/html/maccms10/application/database.php 2>&1" >> $OUT
run_sudo "cat $ROOT/var/www/html/maccms10/application/config.php 2>&1 | head -80" >> $OUT
run_sudo "cat $ROOT/var/www/html/maccms10/application/admin/config.php 2>&1 | head -50" >> $OUT
run_sudo "cat $ROOT/var/www/html/maccms10/application/extra/maccms.php 2>&1 | head -100" >> $OUT

echo "" >> $OUT
echo "## maccms admin 后台目录 (Q5)" >> $OUT
run_sudo "ls -la $ROOT/var/www/html/maccms10/application/admin/ 2>&1 | head -20" >> $OUT
run_sudo "find $ROOT/var/www/html/maccms10 -maxdepth 3 -type d -name '*admin*' 2>/dev/null" >> $OUT
run_sudo "find $ROOT/var/www/html/maccms10 -maxdepth 1 -name '*.php' 2>/dev/null" >> $OUT

echo "" >> $OUT
echo "## maccms 模板 (Q9)" >> $OUT
run_sudo "ls $ROOT/var/www/html/maccms10/template/ 2>&1" >> $OUT
run_sudo "find $ROOT/var/www/html/maccms10/template -maxdepth 3 -type f 2>/dev/null | head -30" >> $OUT

echo "" >> $OUT
echo "## maccms public/static 入口" >> $OUT
run_sudo "ls $ROOT/var/www/html/maccms10/public/ 2>&1" >> $OUT

echo "" >> $OUT
echo "## maccms .htaccess (伪静态 Q10)" >> $OUT
run_sudo "find $ROOT/var/www/html/maccms10 -name '.htaccess' 2>/dev/null" >> $OUT
run_sudo "cat $ROOT/var/www/html/maccms10/.htaccess 2>&1" >> $OUT
run_sudo "cat $ROOT/var/www/html/maccms10/public/.htaccess 2>&1" >> $OUT

echo "" >> $OUT
echo "## ICP 备案 (Q6) - 搜模板" >> $OUT
run_sudo "grep -rE 'ICP[备案]?[0-9]+|备案号' $ROOT/var/www/html/maccms10/template/ 2>/dev/null | head -10" >> $OUT
run_sudo "grep -rE 'ICP|icp' $ROOT/var/www/html/maccms10/template/ 2>/dev/null | head -10" >> $OUT

echo "" >> $OUT
echo "## 主域名 (Q7) - nginx 配置" >> $OUT
run_sudo "cat $ROOT/etc/nginx/conf.d/*.conf 2>&1" >> $OUT
run_sudo "find $ROOT/etc/nginx -name '*.conf' -exec grep -l 'server_name\|listen' {} \\; 2>/dev/null" >> $OUT
run_sudo "grep -rE 'server_name|root|fastcgi_pass' $ROOT/etc/nginx/ 2>/dev/null | head -20" >> $OUT
run_sudo "grep -rE 'site_name|MAC_HOST|web_url|domain' $ROOT/var/www/html/maccms10/application/ 2>/dev/null | head -10" >> $OUT

echo "" >> $OUT
echo "## maccms install.lock 安装时间" >> $OUT
run_sudo "ls -la $ROOT/var/www/html/maccms10/install.lock 2>&1" >> $OUT
run_sudo "ls -la $ROOT/var/www/html/maccms10/data/install.lock 2>&1" >> $OUT
run_sudo "ls -la $ROOT/var/www/html/maccms10/data/ 2>&1" >> $OUT

echo "" >> $OUT
echo "## maccms 路由配置" >> $OUT
run_sudo "cat $ROOT/var/www/html/maccms10/application/route.php 2>&1 | head -50" >> $OUT
run_sudo "cat $ROOT/var/www/html/maccms10/application/admin/route.php 2>&1 | head -30" >> $OUT
run_sudo "cat $ROOT/var/www/html/maccms10/route.php 2>&1 | head -30" >> $OUT

echo ""
echo "完成 extract4"
echo "见 $OUT"
