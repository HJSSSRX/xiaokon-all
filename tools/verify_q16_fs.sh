#!/bin/bash
# Q16: 以下哪个文件系统未被使用 (A.ntfs B.btrfs C.xfs D.LVM)
# btrfs 用了 (md0), LVM 用了 (vg root, vg volum)
# 候选未用: ntfs 或 xfs
set +e
PSW=$(head -1 /mnt/e/项目/psw)
ROOT=/mnt/server_root
OUT=/mnt/e/ffffff-JIANCAI/2026FIC团体赛/case/server/q16_fs_check.txt

run_sudo() { echo "$PSW" | sudo -S bash -c "$1" 2>&1; }

> $OUT
echo "==== Q16 文件系统未使用 验证 ====" >> $OUT

echo "" >> $OUT
echo "## mkfs 工具是否安装 ##" >> $OUT
run_sudo "ls $ROOT/sbin/mkfs* $ROOT/usr/sbin/mkfs* 2>/dev/null | sort -u" >> $OUT

echo "" >> $OUT
echo "## dpkg 包: xfsprogs / ntfs-3g / btrfs-progs / lvm2 ##" >> $OUT
for pkg in xfsprogs ntfs-3g ntfs-3g-dev btrfs-progs lvm2 zfsutils-linux; do
  echo "--- $pkg ---" >> $OUT
  run_sudo "grep -A1 \"^Package: $pkg\$\" $ROOT/var/lib/dpkg/status 2>/dev/null | head -3" >> $OUT
done

echo "" >> $OUT
echo "## 内核 fs 模块 (kernel /lib/modules/.../kernel/fs/) ##" >> $OUT
run_sudo "find $ROOT/usr/lib/modules -maxdepth 4 -name 'kernel' -type d 2>/dev/null | head -3" >> $OUT
run_sudo "ls $ROOT/usr/lib/modules/*/kernel/fs/ 2>/dev/null | head -30" >> $OUT
run_sudo "ls $ROOT/usr/lib/modules/*/kernel/fs/ntfs* $ROOT/usr/lib/modules/*/kernel/fs/xfs* 2>/dev/null" >> $OUT

echo "" >> $OUT
echo "## /proc/filesystems 当前支持 (从 mount 看) ##" >> $OUT
run_sudo "mount | awk '{print \$5}' | sort -u" >> $OUT

echo "" >> $OUT
echo "## /etc/mtab.fuselist / blkid 全部 ##" >> $OUT
run_sudo "blkid 2>/dev/null" >> $OUT

echo "" >> $OUT
echo "## fstab + mtab 引用的所有 fs 类型 ##" >> $OUT
run_sudo "grep -v '^#' $ROOT/etc/fstab 2>/dev/null | awk '{print \$3}' | sort -u" >> $OUT

echo "" >> $OUT
echo "## bash history 是否提到 mkfs / xfs / ntfs ##" >> $OUT
run_sudo "grep -E 'mkfs|xfs|ntfs|format' $ROOT/root/.bash_history $ROOT/home/mac/.bash_history 2>/dev/null" >> $OUT

echo "" >> $OUT
echo "## /tmp /var/log 是否提到挂载 ntfs/xfs ##" >> $OUT
run_sudo "grep -lE 'ntfs|xfs' $ROOT/var/log/dmesg* $ROOT/var/log/syslog* $ROOT/var/log/kern.log* 2>/dev/null | head -3" >> $OUT

echo "完成 Q16 验证"
