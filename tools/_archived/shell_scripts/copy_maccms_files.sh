#!/bin/bash
set +e
PSW=$(head -1 /mnt/e/项目/psw)
D="/mnt/e/ffffff-JIANCAI/2026FIC团体赛/case/server/maccms_files"
mkdir -p "$D"

run_sudo() { echo "$PSW" | sudo -S bash -c "$1" 2>&1; }

echo "复制关键文件到 $D"

run_sudo "cp /mnt/server_root/var/www/html/maccms10/application/extra/maccms.php '$D/maccms_extra.php'"
run_sudo "cp /mnt/server_root/var/www/html/maccms10/application/database.php '$D/database.php'"
run_sudo "cp /mnt/server_root/var/www/html/maccms10/application/extra/domain.php '$D/domain.php' 2>/dev/null"
run_sudo "cp /mnt/server_root/etc/nginx/sites-available/default '$D/nginx_default.conf'"
run_sudo "cp /mnt/server_root/var/www/html/maccms10/application/admin/config.php '$D/admin_config.php' 2>/dev/null"
run_sudo "cp /mnt/server_root/var/www/html/maccms10/application/route.php '$D/route.php'"
run_sudo "cp /mnt/server_root/var/www/html/maccms10/index.php '$D/index.php'"
run_sudo "cp /mnt/server_root/var/www/html/maccms10/api.php '$D/api.php'"
run_sudo "cp /mnt/server_root/var/www/html/maccms10/user.php '$D/user.php'"
run_sudo "cp /mnt/server_root/var/www/html/maccms10/install.php '$D/install.php'"
run_sudo "cp /mnt/server_root/var/www/html/maccms10/.gitignore '$D/maccms.gitignore' 2>/dev/null"
run_sudo "cp /mnt/server_root/var/www/html/maccms10/template/YMYS002/application/extra/maccms.php '$D/template_YMYS002_maccms.php' 2>/dev/null"
run_sudo "cp /mnt/server_root/var/www/html/maccms10/template/YMYS002/application/extra/maccms.php.bak '$D/template_YMYS002_maccms.php.bak' 2>/dev/null"

echo "" 
echo "=== /aa/ 目录 (root 拥有, 可能后台入口) ==="
run_sudo "ls -la /mnt/server_root/var/www/html/maccms10/aa/"
echo ""
echo "=== aa/ 内 PHP 文件 ==="
run_sudo "find /mnt/server_root/var/www/html/maccms10/aa -type f 2>/dev/null"

echo ""
echo "权限调整..."
run_sudo "chmod -R 644 '$D'/*.php '$D'/*.conf 2>/dev/null"
run_sudo "chown -R $(id -u hjsssr):$(id -g hjsssr) '$D'/*"

echo ""
echo "已复制到 $D:"
ls -la "$D"
