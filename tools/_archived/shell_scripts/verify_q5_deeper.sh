#!/bin/bash
set +e
PSW=$(head -1 /mnt/e/项目/psw)
ROOT=/mnt/server_root
OUT=/mnt/e/ffffff-JIANCAI/2026FIC团体赛/case/server/q5_deeper.txt

run_sudo() { echo "$PSW" | sudo -S bash -c "$1" 2>&1; }

> $OUT
echo "==== Q5 后台入口深度验证 ====" >> $OUT

echo "" >> $OUT
echo "## 1. 各 .php 入口请求统计 ##" >> $OUT
for ph in admin admin1 admin_login admin\.php admin1\.php index\.php user\.php api\.php install\.php login\.php; do
  cnt=$(run_sudo "zgrep -h \"$ph\" $ROOT/var/log/nginx/access.log* 2>/dev/null | wc -l")
  printf "%-30s : %s\n" "$ph" "$cnt" >> $OUT
done

echo "" >> $OUT
echo "## 2. admin1.php 实际请求 (5 条) ##" >> $OUT
run_sudo "zgrep -hE 'admin1\.php' $ROOT/var/log/nginx/access.log* 2>/dev/null | head -5" >> $OUT

echo "" >> $OUT
echo "## 3. user.php/admin/ 实际请求 (5 条) ##" >> $OUT
run_sudo "zgrep -hE 'user\.php/admin/' $ROOT/var/log/nginx/access.log* 2>/dev/null | head -5" >> $OUT

echo "" >> $OUT
echo "## 4. POST 请求统计 (登录通常是 POST) ##" >> $OUT
echo "--- POST 到 admin1.php ---" >> $OUT
run_sudo "zgrep -hE 'POST [^ ]*admin1' $ROOT/var/log/nginx/access.log* 2>/dev/null | head -3" >> $OUT
echo "--- POST 到 user.php/admin ---" >> $OUT
run_sudo "zgrep -hE 'POST [^ ]*user\.php/admin' $ROOT/var/log/nginx/access.log* 2>/dev/null | head -3" >> $OUT
echo "--- POST 到 login ---" >> $OUT
run_sudo "zgrep -hE 'POST [^ ]*[Ll]ogin' $ROOT/var/log/nginx/access.log* 2>/dev/null | head -5" >> $OUT

echo "" >> $OUT
echo "## 5. 哪个是初始登录入口? 看 referer ##" >> $OUT
run_sudo "zgrep -h 'POST.*login' $ROOT/var/log/nginx/access.log* 2>/dev/null | head -5" >> $OUT

echo "" >> $OUT
echo "## 6. 用户访问的第一个 admin 页面 ##" >> $OUT
run_sudo "zgrep -hE '/(admin|admin1|user)\.php/admin' $ROOT/var/log/nginx/access.log.4.gz 2>/dev/null | head -5" >> $OUT

echo "" >> $OUT
echo "## 7. error.log 查看 admin1 ##" >> $OUT
run_sudo "zgrep -hE 'admin1|admin\.php' $ROOT/var/log/nginx/error.log* 2>/dev/null | head -5" >> $OUT

echo "" >> $OUT
echo "## 8. maccms 是否有 user.php 入口绑定 admin module? ##" >> $OUT
run_sudo "cat $ROOT/var/www/html/maccms10/user.php" >> $OUT

echo ""
echo "完成"
