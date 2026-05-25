---
tags: [fic2026, deepin, uos, android, xiaomi, clash, ngrok, sqlite, todo, vpn, computer_forensics]
tools: [cat, grep, find, sqlite3, r2]
category: mixed
difficulty: easy-medium
source: fic2026
date: 2026-05-05
verified: false
---

# Title: FIC2026 精选题解 (C01/C05/I03/M01/M02)

## C01 — 操作系统版本识别 (Deepin/UOS)

### Problem
分析计算机检材，操作系统版本号为？

### Solution
```bash
cat {mount}/etc/os-release        # PRETTY_NAME
cat {mount}/etc/deepin-version    # Version=20, Type=Professional
cat {mount}/etc/lsb-release       # DISTRIB_DESCRIPTION
```
**Answer**: `UnionTech OS Desktop 20 Pro`

**注意**: Deepin 是社区版，UOS 是商业版，底层相同。题目问操作系统版本应回答发行版名称，不是内核或底层 Debian 版本。

---

## C05 — VPN 代理端口 (Clash Verge)

### Problem
李安弘电脑 VPN 软件开放的代理端口为？

### Solution
```bash
find {mount}/root/.config -name '*.yaml' -path '*clash*'
grep -i 'port' {mount}/root/.config/clash-verge/verge.yaml
# → mixed-port: 7897
```
**Answer**: `7897`

**注意**: Clash 新版使用 `mixed-port` 替代分离的 `socks-port` 和 `port`，同时支持 SOCKS5+HTTP。

---

## I03 — ngrok 域名发现

### Problem
ngrok 提供的域名为？

### Solution
```bash
# 方法1: nginx 日志中搜索
grep 'ngrok' {mount}/var/log/nginx/access.log | head -5

# 方法2: nginx 配置中搜索
grep -rh 'ngrok' {mount}/etc/nginx/

# 方法3: Web 应用配置搜索
grep -rh 'ngrok\|domain' {mount}/var/www/*/config/
```
**Answer**: `blemish-junior-unengaged.ngrok-free.dev`

**注意**: ngrok 域名格式: `*.ngrok.io` 或 `*.ngrok-free.dev`。不要把 `127.0.0.1:4040` (管理界面) 当域名。

---

## M01 — 手机型号识别 (Android build fingerprint)

### Problem
分析手机检材，该手机型号为？

### Solution
```bash
# 读取 build fingerprint
cat {phone}/data/misc/recovery/ro.build.fingerprint
# → xiaomi/violet/violet:10/QKQ1.190915.002/...

# 映射 codename → 市售名
# violet = Redmi Note 7 Pro
# lavender = Redmi Note 7 (注意区分)

# 交叉验证
grep lastLoggedInFingerprint {phone}/data/system/users/0.xml
grep -rh fingerprint {phone}/data/user/0/com.xiaomi.account/
```
**Answer**: `Redmi Note 7 Pro`

**注意**: codename 是内部代号，题目问市售型号。三源交叉验证更可靠。

---

## M02 — 待办事项日期提取 (MIUI Notes)

### Problem
李安弘手机计划前往迪拜的日期是？

### Solution
```bash
# 定位数据库
find {phone}/data/user/0/com.miui.notes/databases/ -name '*.db'

# 搜索关键词 (注意中英文都试)
sqlite3 todo.db "SELECT plain_text FROM todo WHERE plain_text LIKE '%dubai%' OR plain_text LIKE '%迪拜%'"
# → 2026.06.06 乘坐飞机去 dubai

# 时间戳转换
sqlite3 todo.db "SELECT datetime(create_time/1000,'unixepoch','+8 hours'), plain_text FROM todo"
```
**Answer**: `2026.06.06`

**注意**: 
- Android 时间戳通常是毫秒级 Unix 时间，需 `/1000` 再转换
- 中国赛事时间一律转 CST (UTC+8): `'+8 hours'`
- 同时搜索中英文关键词

## Key Takeaways
- Linux 版本: `/etc/os-release` + `/etc/deepin-version` 交叉验证
- 代理配置: `~/.config/` 下搜索 `clash`/`v2ray` 等
- ngrok 域名: nginx 日志 Host header > nginx 配置 > Web 应用配置
- Android 设备识别: build fingerprint → codename → 型号映射表
- SQLite 取证: `.tables` → `.schema` → 关键词 LIKE 搜索
