#!/bin/bash
set +e
PSW=$(head -1 /mnt/e/项目/psw)
ROOT=/mnt/server_root
OUT=/mnt/e/ffffff-JIANCAI/2026FIC团体赛/case/server/q5_final.txt

run_sudo() { echo "$PSW" | sudo -S bash -c "$1" 2>&1; }

> $OUT
echo "==== Q5 最终判定 ====" >> $OUT

echo "" >> $OUT
echo "## 1. admin1.php 物理文件是否存在? ##" >> $OUT
run_sudo "find $ROOT/var/www/html/maccms10 -maxdepth 2 -name 'admin*.php' -type f -o -type l 2>/dev/null" >> $OUT
run_sudo "ls -la $ROOT/var/www/html/maccms10/admin*.php 2>&1" >> $OUT

echo "" >> $OUT
echo "## 2. admin1.php 请求的 HTTP 响应码统计 ##" >> $OUT
run_sudo "zgrep -hE 'admin1\.php' $ROOT/var/log/nginx/access.log* 2>/dev/null | awk '{print \$9}' | sort | uniq -c | sort -rn" >> $OUT

echo "" >> $OUT
echo "## 3. user.php/admin/ 请求的 HTTP 响应码统计 ##" >> $OUT
run_sudo "zgrep -hE 'user\.php/admin' $ROOT/var/log/nginx/access.log* 2>/dev/null | awk '{print \$9}' | sort | uniq -c | sort -rn" >> $OUT

echo "" >> $OUT
echo "## 4. user.php 直接请求 (主页 user.php) HTTP 响应统计 ##" >> $OUT
run_sudo "zgrep -hE '\"GET /user\.php ' $ROOT/var/log/nginx/access.log* 2>/dev/null | head -5" >> $OUT

echo "" >> $OUT
echo "## 5. admin1.php 第一次出现时间 (查 access.log 历史最早一条) ##" >> $OUT
run_sudo "zgrep -hE 'admin1\.php' $ROOT/var/log/nginx/access.log* 2>/dev/null | head -1" >> $OUT
run_sudo "zgrep -hE 'admin1\.php' $ROOT/var/log/nginx/access.log* 2>/dev/null | tail -1" >> $OUT

echo "" >> $OUT
echo "## 6. 第一次访问 admin1.php 的来源 referer (登录页?) ##" >> $OUT
run_sudo "zgrep -hE 'admin1\.php' $ROOT/var/log/nginx/access.log* 2>/dev/null | head -3 | awk -F'\"' '{print \$4}'" >> $OUT

echo "" >> $OUT
echo "## 7. nginx 是否有 admin1.php specific rewrite? ##" >> $OUT
run_sudo "grep -rE 'admin1' $ROOT/etc/nginx/ 2>/dev/null" >> $OUT
run_sudo "grep -rE 'admin1' $ROOT/var/www/html/maccms10/.htaccess 2>/dev/null" >> $OUT

echo "" >> $OUT
echo "## 8. application/admin/ 模块 是否提到 admin1.php? ##" >> $OUT
run_sudo "grep -rlE 'admin1\.php' $ROOT/var/www/html/maccms10/application/ 2>/dev/null | head -5" >> $OUT

echo ""
echo "## 9. 决定性: 看登录 POST 请求 ##" >> $OUT
echo "--- 任何 admin* login POST ---" >> $OUT
run_sudo "zgrep -hE 'POST .*(admin|admin1|user)\.php.*[Ll]ogin' $ROOT/var/log/nginx/access.log* 2>/dev/null | head -5" >> $OUT

echo "完成"
