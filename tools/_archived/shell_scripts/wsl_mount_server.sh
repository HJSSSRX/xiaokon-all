#!/bin/bash
# WSL 挂 2026FIC 检材3 服务器 E01 + LVM + cryptsetup
# 用题目给的挂载密码: FIC-{e404d6e66586e9460c23755afab5a872bcf78ab4}
set -e

PSW=$(head -1 /mnt/e/项目/psw)
E01_DIR='/mnt/e/ffffff-JIANCAI/2026FIC团体赛/检材3-服务器'
E01_1="$E01_DIR/检材3-1.E01"
E01_2="$E01_DIR/检材3-2.E01"
MOUNT_PSW='FIC-{e404d6e66586e9460c23755afab5a872bcf78ab4}'

echo "=== Step 0: 检查现有挂载 ==="
mount | grep -E "(e1|e2|server_)" || echo "(无现有挂载)"
echo ""
echo "=== Step 1: 准备挂载点 ==="
echo "$PSW" | sudo -S mkdir -p /mnt/e1 /mnt/e2 /mnt/server_root /mnt/server_data

# 如果 /mnt/e1 不空 (已挂), skip; 否则挂
if ! mountpoint -q /mnt/e1; then
  echo "ewfmount E01-1 ..."
  echo "$PSW" | sudo -S ewfmount "$E01_1" /mnt/e1
fi
if ! mountpoint -q /mnt/e2; then
  echo "ewfmount E01-2 ..."
  echo "$PSW" | sudo -S ewfmount "$E01_2" /mnt/e2
fi

echo "=== Step 2: ewf1 文件 ==="
ls -la /mnt/e1/ /mnt/e2/

echo "=== Step 3: losetup -fP ==="
EXISTING=$(echo "$PSW" | sudo -S losetup -a | grep -E "ewf1" || true)
if [ -z "$EXISTING" ]; then
  echo "$PSW" | sudo -S losetup -fP /mnt/e1/ewf1
  echo "$PSW" | sudo -S losetup -fP /mnt/e2/ewf1
fi
echo "$PSW" | sudo -S losetup -a

echo "=== Step 4: lsblk 看分区 ==="
lsblk

echo "=== Step 5: pvscan + vgscan ==="
echo "$PSW" | sudo -S pvscan
echo "$PSW" | sudo -S vgscan
echo "$PSW" | sudo -S vgchange -ay
echo "$PSW" | sudo -S lvs

echo "=== Step 6: 列出所有 LV 路径 ==="
ls -la /dev/mapper/ /dev/*/  2>/dev/null | grep -v "^total" | head -50

echo "=== 完成 Step 1-6, 等下一步 cryptsetup ==="
