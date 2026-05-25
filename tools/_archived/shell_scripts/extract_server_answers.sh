#!/bin/bash
# 服务器取证: 系统性提取 Q1-Q17 答案
set +e
PSW=$(head -1 /mnt/e/项目/psw)
ROOT=/mnt/server_root
OUT=/mnt/e/ffffff-JIANCAI/2026FIC团体赛/case/server/answers_extract.txt

run_sudo() { echo "$PSW" | sudo -S bash -c "$1" 2>&1; }

echo "==============================================" > $OUT
echo "服务器取证答案提取 $(date)" >> $OUT
echo "==============================================" >> $OUT

echo "" >> $OUT
echo "## Q1 OS 版本 (参考 0.9)" >> $OUT
cat $ROOT/etc/os-release 2>&1 >> $OUT
echo "" >> $OUT
echo "/etc/debian_version: $(cat $ROOT/etc/debian_version 2>&1)" >> $OUT

echo "" >> $OUT
echo "## Q2 根分区 UUID (参考 a1b2-c3)" >> $OUT
echo "blkid /dev/md0:" >> $OUT
run_sudo "blkid /dev/md0" >> $OUT
echo "/etc/fstab UUID:" >> $OUT
grep -E "UUID|/" $ROOT/etc/fstab 2>&1 >> $OUT

echo "" >> $OUT
echo "## Q4 根分区快照路径 (参考 /abc/def)" >> $OUT
echo "btrfs subvolume list:" >> $OUT
run_sudo "btrfs subvolume list $ROOT" >> $OUT
echo "snapshots dir:" >> $OUT
ls $ROOT/.snapshots/ 2>&1 >> $OUT
ls $ROOT/var/lib/snapper/ 2>&1 >> $OUT
find $ROOT -type d -name ".snapshots" 2>/dev/null | head >> $OUT

echo "" >> $OUT
echo "## Q5 网站后台管理入口文件 (参考 123.txt, 应该是 *.php)" >> $OUT
echo "nginx vhost:" >> $OUT
ls $ROOT/etc/nginx/ 2>&1 | head -20 >> $OUT
ls $ROOT/www/ 2>&1 >> $OUT
ls $ROOT/www/server/ 2>&1 >> $OUT
ls $ROOT/www/server/panel/ 2>&1 >> $OUT
ls $ROOT/www/wwwroot/ 2>&1 >> $OUT
ls $ROOT/www/server/panel/vhost/nginx/ 2>&1 >> $OUT

echo "" >> $OUT
echo "## Q6 ICP 备案号 (参考 icp123)" >> $OUT
grep -rE "ICP[备案]*[0-9]+|备案号" $ROOT/www/wwwroot/ 2>/dev/null | head -10 >> $OUT
grep -rE "ICP|icp" $ROOT/www/wwwroot/*/template/ 2>/dev/null | head -5 >> $OUT

echo "" >> $OUT
echo "## Q7 主域名 (参考 abc.com)" >> $OUT
grep -h server_name $ROOT/www/server/panel/vhost/nginx/*.conf 2>/dev/null >> $OUT
ls $ROOT/www/wwwroot/ 2>&1 >> $OUT

echo "" >> $OUT
echo "## Q8 视频分类3拼音 (参考 abc)" >> $OUT
echo "(需要数据库查询, 后续处理)" >> $OUT

echo "" >> $OUT
echo "## Q9 前端模板源文件 (参考 abc.def)" >> $OUT
ls $ROOT/www/wwwroot/*/template/ 2>&1 >> $OUT
ls $ROOT/www/wwwroot/*/themes/ 2>&1 >> $OUT

echo "" >> $OUT
echo "## Q10 伪静态规则 SM3" >> $OUT
ls $ROOT/www/server/panel/vhost/rewrite/ 2>&1 >> $OUT
echo "(需要 SM3 后续计算)" >> $OUT

echo "" >> $OUT
echo "## Q12 数据库容器技术 (docker/podman/lxc)" >> $OUT
ls $ROOT/var/lib/docker 2>&1 | head -5 >> $OUT
ls $ROOT/var/lib/containers 2>&1 | head -5 >> $OUT
which docker podman lxc 2>/dev/null >> $OUT
ls $ROOT/usr/bin/ | grep -E "docker|podman|lxc" >> $OUT

echo "" >> $OUT
echo "## Q13 4000端口备份数据库版本 (参考 v1.1.1)" >> $OUT
echo "(可能是 TiDB v8.x.x, 在 docker container 中)" >> $OUT
ls $ROOT/var/lib/docker/image/ 2>/dev/null >> $OUT
find $ROOT -name "*tidb*" 2>/dev/null | head -10 >> $OUT

echo "" >> $OUT
echo "## Q15 注册用户最多日期 + Q14 马慧美登录IP (依赖数据库)" >> $OUT
echo "(需要查 docker container 内的 MySQL/postgresql 数据库)" >> $OUT

echo "" >> $OUT
echo "## Q16 单选 文件系统 (A.ntfs B.btrfs C.xfs D.Lvm)" >> $OUT
echo "已知: btrfs (md0=raid0+btrfs), LVM (vg root,volum)" >> $OUT
mount | grep -E "(ntfs|btrfs|xfs|ext4|lvm)" >> $OUT
cat $ROOT/etc/fstab 2>&1 | grep -v "^#" | grep -v "^$" >> $OUT

echo "" >> $OUT
echo "## Q17 多选 数据库 (A.mysql B.GuessDB C.tidb D.postgresql E.Mariadb)" >> $OUT
ls $ROOT/var/lib/postgresql 2>/dev/null >> $OUT
ls $ROOT/var/lib/mysql 2>/dev/null >> $OUT
ls $ROOT/var/lib/mariadb 2>/dev/null >> $OUT

echo "" >> $OUT
echo "## hostname / 系统信息" >> $OUT
cat $ROOT/etc/hostname >> $OUT
cat $ROOT/etc/timezone 2>/dev/null >> $OUT

echo "" >> $OUT
echo "## /www/wwwroot/ 全部站点" >> $OUT
ls -la $ROOT/www/wwwroot/ 2>&1 >> $OUT

echo ""
echo "提取完成, 见 $OUT"
echo ""
echo "=== 关键摘要 ==="
head -60 $OUT
echo "..."
