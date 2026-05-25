#!/bin/bash
set +e
PSW=$(head -1 /mnt/e/项目/psw)
ROOT=/mnt/server_root
ZFS_DIR=/mnt/server_root/media
OUT=/mnt/e/ffffff-JIANCAI/2026FIC团体赛/case/server/zdb_objects.txt

run_sudo() { echo "$PSW" | sudo -S bash -c "$1" 2>&1; }

> $OUT
echo "==== zdb 深入 (列出 dataset 对象) ====" >> $OUT

echo "" >> $OUT
echo "## 1. zdb -e -d (列出 dataset) ##" >> $OUT
run_sudo "zdb -e -p $ZFS_DIR -d db" >> $OUT

echo "" >> $OUT
echo "## 2. zdb -e -d -d (Detail dataset 信息) ##" >> $OUT
run_sudo "zdb -e -p $ZFS_DIR -dd db" 2>&1 | head -100 >> $OUT

echo "" >> $OUT
echo "## 3. zdb -e -d db/tidb (tidb dataset 信息) ##" >> $OUT
run_sudo "zdb -e -p $ZFS_DIR -d db/tidb" >> $OUT

echo "" >> $OUT
echo "## 4. 用 strings 找 mac_ulog 表内容 (上下文) ##" >> $OUT
run_sudo "grep -B2 -A15 'mac_ulog' /mnt/e/ffffff-JIANCAI/2026FIC团体赛/case/server/zfs_strings/all.strings.txt | head -80" >> $OUT

echo "" >> $OUT
echo "## 5. 用 strings 找 user_name 数据 ##" >> $OUT
run_sudo "grep -E '(user_name|user_pwd|user_qq|user_email|user_phone|nick_name)' /mnt/e/ffffff-JIANCAI/2026FIC团体赛/case/server/zfs_strings/all.strings.txt | sort -u | head -30" >> $OUT

echo "" >> $OUT
echo "## 6. 找 hex 编码的中文 (UTF-8: 马=E9 A9 AC 慧=E6 85 A7 美=E7 BE 8E) ##" >> $OUT
echo "马 hex = e9 a9 ac" >> $OUT
echo "马慧美 hex = e9 a9 ac e6 85 a7 e7 be 8e" >> $OUT
run_sudo "xxd /mnt/server_root/media/zfs | grep -i 'e9 a9 ac e6 85 a7' | head -5" >> $OUT

echo "" >> $OUT
echo "## 7. 用 binwalk 找压缩块 (snappy/lz4) ##" >> $OUT
run_sudo "binwalk /mnt/server_root/media/zfs 2>&1 | head -20" >> $OUT

echo ""
echo "完成"
