#!/bin/bash
set +e
PSW=$(head -1 /mnt/e/项目/psw)
VHD=/mnt/e/ffffff-JIANCAI/2026FIC团体赛/case/binary/vc_rc4_decrypted.vhd
OUT=/mnt/e/ffffff-JIANCAI/2026FIC团体赛/case/binary/vhd_extracted

run_sudo() { echo "$PSW" | sudo -S bash -c "$1" 2>&1; }

mkdir -p "$OUT"

echo "=== 1. VHD 文件 magic ==="
run_sudo "xxd $VHD | head -3"
echo ""
echo "VHD footer (last 512 bytes):"
run_sudo "tail -c 512 $VHD | xxd | head -10"

echo ""
echo "=== 2. 用 file 看类型 ==="
file $VHD

echo ""
echo "=== 3. 7z 列出内容 ==="
7z l $VHD 2>&1 | head -30

echo ""
echo "=== 4. 尝试 qemu-nbd 挂载 (replace if avail) ==="
if which qemu-nbd >/dev/null 2>&1; then
  run_sudo "modprobe nbd max_part=8 2>&1"
  run_sudo "qemu-nbd --read-only -c /dev/nbd0 $VHD 2>&1"
  sleep 2
  run_sudo "fdisk -l /dev/nbd0 2>&1 | head -10"
  run_sudo "mkdir -p /mnt/vhd_decrypted"
  run_sudo "mount -o ro /dev/nbd0 /mnt/vhd_decrypted 2>&1 || mount -o ro /dev/nbd0p1 /mnt/vhd_decrypted 2>&1"
  run_sudo "ls -la /mnt/vhd_decrypted/" 2>&1 | head -30
fi

echo ""
echo "=== 5. 替代: dd VHD 数据部分 (skip 511*0 padding) ==="
echo "VHD 是 fixed format, 数据从 offset 0 开始, footer 在末尾 512 bytes"
echo "试 dd 取数据部分 + 用 fdisk/parted 看分区"
DATA_SIZE=$((10486272 - 512))
run_sudo "dd if=$VHD of=$OUT/vhd_data.bin bs=1 count=$DATA_SIZE 2>&1 | tail -3"
ls -la "$OUT/vhd_data.bin" 2>/dev/null

echo ""
echo "=== 6. file vhd_data.bin ==="
file "$OUT/vhd_data.bin" 2>/dev/null

echo ""
echo "=== 7. 用 fls (sleuthkit) 列出 NTFS 文件 ==="
run_sudo "fls -r $VHD 2>&1 | head -30"
run_sudo "fls -r -o 0 $VHD 2>&1 | head -30"

echo ""
echo "=== 8. strings (找文件名/保险柜编号) ==="
strings $VHD | grep -E "(保险|safe|password|README|note|txt)" | head -20

echo ""
echo "完成"
