#!/bin/bash
set +e
PSW=$(head -1 /mnt/e/项目/psw)
ZFS=/mnt/server_root/media/zfs
OUT_DIR=/mnt/e/ffffff-JIANCAI/2026FIC团体赛/case/server/zfs_strings

run_sudo() { echo "$PSW" | sudo -S bash -c "$1" 2>&1; }

run_sudo "mkdir -p $OUT_DIR"
run_sudo "chown -R hjsssr:hjsssr $OUT_DIR"

echo "=== 1. 全文 strings (10GB, 慢) → file ==="
echo "[预计 1-3 分钟]..."
run_sudo "strings -a -n 8 $ZFS > $OUT_DIR/all.strings.txt"
echo "完成. 大小:"
ls -la $OUT_DIR/all.strings.txt

echo ""
echo "=== 2. 提取 mac_user 表相关 ==="
grep -E "(mac_user|mahuimei|马慧美|ma hui mei)" $OUT_DIR/all.strings.txt | head -50 > $OUT_DIR/q_user.txt
wc -l $OUT_DIR/q_user.txt
head -10 $OUT_DIR/q_user.txt

echo ""
echo "=== 3. 提取 mac_user_login / mac_ulog (登录IP) ==="
grep -E "(mac_user_login|mac_ulog|user_id.*ip|last_login)" $OUT_DIR/all.strings.txt | head -50 > $OUT_DIR/q_login.txt
wc -l $OUT_DIR/q_login.txt
head -10 $OUT_DIR/q_login.txt

echo ""
echo "=== 4. 提取 mac_type (视频分类) ==="
grep -E "(mac_type|type_en|type_pid|国产|guochan)" $OUT_DIR/all.strings.txt | head -30 > $OUT_DIR/q_type.txt
wc -l $OUT_DIR/q_type.txt
head -10 $OUT_DIR/q_type.txt

echo ""
echo "=== 5. 提取 TiDB 版本字符串 ==="
grep -hE "(tidb-server|TiDB Server.*Version|Release Version|^v[0-9]+\.[0-9]+\.[0-9]+|tikv-server|pd-server|github.com/pingcap)" $OUT_DIR/all.strings.txt | sort -u | head -30 > $OUT_DIR/q_tidb_version.txt
wc -l $OUT_DIR/q_tidb_version.txt
head -20 $OUT_DIR/q_tidb_version.txt

echo ""
echo "=== 6. 提取 IP 地址 (192.168.x / 10.0.x) ==="
grep -hoE "[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+" $OUT_DIR/all.strings.txt | sort -u | head -50 > $OUT_DIR/q_ips.txt
wc -l $OUT_DIR/q_ips.txt

echo ""
echo "=== 7. 注册时间相关 (date/timestamp) ==="
grep -hE "(reg_time|register|2026-04-1[0-9]|2026/04/1[0-9])" $OUT_DIR/all.strings.txt | sort -u | head -50 > $OUT_DIR/q_reg.txt
wc -l $OUT_DIR/q_reg.txt
head -10 $OUT_DIR/q_reg.txt

echo "全部完成. 输出文件:"
ls -la $OUT_DIR/
