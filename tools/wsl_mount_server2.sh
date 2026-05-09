#!/bin/bash
# 假设 /mnt/e1 和 /mnt/e2 已经 ewfmount 挂载好了, 直接 losetup + LVM
set +e

PSW=$(head -1 /mnt/e/项目/psw)

run_sudo() { echo "$PSW" | sudo -S bash -c "$1" 2>&1; }

echo "=== Step 1: 验证 ewf1 文件存在 ==="
ls -la /mnt/e1/ewf1 /mnt/e2/ewf1
echo ""

echo "=== Step 2: 已存在的 loop devices ==="
run_sudo "losetup -a"
echo ""

echo "=== Step 3: losetup -fP (如未挂) ==="
EXISTING=$(run_sudo "losetup -a" | grep -E "ewf1" || true)
if [ -z "$EXISTING" ]; then
  echo "正在 losetup E01-1..."
  run_sudo "losetup -fP /mnt/e1/ewf1"
  echo "正在 losetup E01-2..."
  run_sudo "losetup -fP /mnt/e2/ewf1"
else
  echo "已存在: $EXISTING"
fi
echo "现在的 loop:"
run_sudo "losetup -a"
echo ""

echo "=== Step 4: lsblk ==="
lsblk
echo ""

echo "=== Step 5: pvscan ==="
run_sudo "pvscan"
echo ""

echo "=== Step 6: vgscan + vgchange ==="
run_sudo "vgscan"
run_sudo "vgchange -ay"
echo ""

echo "=== Step 7: lvs ==="
run_sudo "lvs"
echo ""

echo "=== Step 8: 列出所有 LV ==="
run_sudo "ls -la /dev/mapper/ /dev/volum/ /dev/root/ 2>/dev/null"
echo ""

echo "=== Step 9: blkid (查 UUID 和 fs type) ==="
run_sudo "blkid"
echo ""
echo "=== 完成 Step 1-9 ==="
