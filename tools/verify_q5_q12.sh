#!/bin/bash
set +e
PSW=$(head -1 /mnt/e/项目/psw)
ROOT=/mnt/server_root
OUT=/mnt/e/ffffff-JIANCAI/2026FIC团体赛/case/server/q5_q12_check.txt

run_sudo() { echo "$PSW" | sudo -S bash -c "$1" 2>&1; }

> $OUT
echo "==== Q5 admin1.php / Q12 docker 验证 ====" >> $OUT

echo "" >> $OUT
echo "## 1. nginx access.log 是否真有 admin1.php 请求? ##" >> $OUT
run_sudo "ls $ROOT/var/log/nginx/" >> $OUT
echo "--- access log admin1 ---" >> $OUT
run_sudo "zgrep -hE 'admin1|admin\.php|/admin/' $ROOT/var/log/nginx/access.log* 2>/dev/null | head -15" >> $OUT
echo "--- 统计 admin1.php 请求数 ---" >> $OUT
run_sudo "zgrep -hE 'admin1\.php' $ROOT/var/log/nginx/access.log* 2>/dev/null | wc -l" >> $OUT

echo "" >> $OUT
echo "## 2. Q12 docker 验证: /etc/docker/daemon.json ##" >> $OUT
run_sudo "cat $ROOT/etc/docker/daemon.json 2>/dev/null" >> $OUT

echo "" >> $OUT
echo "## 3. /data 是否真是 docker data-root? ##" >> $OUT
run_sudo "ls $ROOT/data/" >> $OUT
run_sudo "cat $ROOT/data/engine-id 2>/dev/null" >> $OUT
run_sudo "ls $ROOT/data/network/" >> $OUT
run_sudo "ls $ROOT/data/containers/" >> $OUT

echo "" >> $OUT
echo "## 4. mytidb 是怎么连的? docker 还是 lxc? ##" >> $OUT
echo "--- LXC 容器 ---" >> $OUT
run_sudo "ls $ROOT/var/lib/lxc/" >> $OUT
echo "--- docker container metadata 查 mytidb 名字 ---" >> $OUT
run_sudo "for f in $ROOT/data/containers/*/config.v2.json; do
  if grep -q 'mytidb' \"\$f\" 2>/dev/null; then
    echo MATCH: \$f
  fi
done" >> $OUT
run_sudo "for f in $ROOT/data/containers/*/config.v2.json; do
  echo === \$(basename \$(dirname \$f)) ===
  python3 -c \"import json; d=json.load(open('\$f')); print('Name:', d.get('Name','?')); print('Image:', d.get('Config',{}).get('Image','?')); print('Hostname:', d.get('Config',{}).get('Hostname','?'))\" 2>/dev/null
done" >> $OUT

echo "" >> $OUT
echo "## 5. /data/network/ ip 配置 (看 mytidb 哪个网络) ##" >> $OUT
run_sudo "find $ROOT/data/network -maxdepth 3 -type f 2>/dev/null | head" >> $OUT

echo "" >> $OUT
echo "## 6. lxcbr0 ip 配置 (10.0.3.x) ##" >> $OUT
run_sudo "cat $ROOT/etc/default/lxc-net 2>/dev/null" >> $OUT
run_sudo "cat $ROOT/etc/lxc/lxc-usernet 2>/dev/null" >> $OUT
run_sudo "cat $ROOT/etc/lxc/default.conf 2>/dev/null" >> $OUT

echo "" >> $OUT
echo "## 7. 决定性: mytidb (10.0.3.100) 由哪个容器系统提供? ##" >> $OUT
run_sudo "grep -lE '10\.0\.3\.100|mytidb' $ROOT/etc/docker/* 2>/dev/null" >> $OUT
run_sudo "grep -rE 'mytidb' $ROOT/etc/network /etc/hosts 2>/dev/null" >> $OUT
run_sudo "grep mytidb $ROOT/etc/hosts" >> $OUT

echo ""
echo "完成 Q5/Q12 验证"
