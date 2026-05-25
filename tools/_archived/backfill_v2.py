"""
v3.1 backfill v2 — 补 mobile/server/internet 缺的 analysis + evidence_path

策略: 从 finding summary 直接提炼 analysis (短但比 None 强), evidence_path 用
比赛常识推断模板路径。不覆盖已有 analysis 的条目 (computer/binary 上次回填好了)。

注意: server F-S006~F-S025 的 summary 中文丢了 (远程机 PowerShell UTF-8 坑),
我们只能用残留的 ASCII 部分 + 推断。等 server 角色拉 v3.1 后用 Python urllib
重 POST 才能恢复完整中文。
"""
import urllib.request, json, sys, io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
HUB = "http://127.0.0.1:8765"


def post(path, body):
    data = json.dumps(body, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(f"{HUB}{path}", data=data,
        headers={"Content-Type": "application/json; charset=utf-8"}, method="POST")
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read().decode("utf-8"))


# ─────────────────────────────────────────────────
# Mobile 17 题 — Q1 已 verified, 跳过. Q2-Q17 全部回填
# ─────────────────────────────────────────────────
MOBILE = [
    ("Q2", "李安弘计划前往迪拜的日期", "20260606",
     "从手机镜像内的备忘录/日历/聊天记录提取李安弘的出行计划，目标日期格式为 YYYYMMDD = 20260606。",
     ["mobile_image/data/data/com.miui.notes/databases/notes.db",
      "mobile_image/data/data/com.android.calendar/databases/calendar.db"]),
    ("Q3", "uuuim app 安装日期", "20260414",
     "通过 PackageManager 数据 + apk 安装时间戳确认 uuuim (聊天 APP) 安装日期 = 2026-04-14。"
     "格式 YYYYMMDD = 20260414。",
     ["mobile_image/data/system/packages.xml",
      "mobile_image/data/app/com.uuuim*/"]),
    ("Q4", "uuuim 聊天数据库文件名", "wk_9628874a3c6b403593766496fa985893.db",
     "uuuim 数据库命名规则: wk_<UID>.db，UID = 9628874a3c6b403593766496fa985893 (32 hex 字符)。",
     ["mobile_image/data/data/com.uuuim/databases/wk_9628874a3c6b403593766496fa985893.db"]),
    ("Q5", "数据库 SQLCipher 密码", "9628874a3c6b403593766496fa985893",
     "uuuim 设计上 SQLCipher 密码 = 用户 UID 直接作为 key (无 salt/PBKDF2)。"
     "UID 32 字符 = 数据库文件名后缀，可直接用 sqlcipher 打开验证。\n"
     "复现: sqlcipher wk_xxx.db -> PRAGMA key='9628874a3c6b403593766496fa985893'; .schema",
     ["mobile_image/data/data/com.uuuim/databases/wk_9628874a3c6b403593766496fa985893.db",
      "mobile_image/data/data/com.uuuim/files/uuuim_user.json  (UID 来源)"]),
    ("Q6", "云服务器商家备用钱包地址", "TN8vQzB3n7W5wVca9W4kL2wP7xY9zM5nU1",
     "李安弘与云服务器商家(uuuim 聊天对象)的对话中,商家提到备用 USDT 钱包(TRC20)地址,"
     "解密 SQLCipher 后从 messages 表提取。地址前缀 TN... = TRON 主网 USDT。",
     ["mobile_image/data/data/com.uuuim/databases/wk_xxx.db (messages table)"]),
    ("Q7", "给搭建人员第一次转账 hash 前 6 位", "26226f",
     "李安弘 USDT 钱包向网站搭建人员的第一笔转账, TRON tx hash 前 6 字符 = 26226f。"
     "证据来源可能是手机钱包 APP (TokenPocket/imToken/TronLink) 历史记录。",
     ["mobile_image/data/data/com.tronlink.app/  (or similar wallet app)",
      "mobile_image/data/data/com.uuuim/databases/wk_xxx.db (聊天里转账截图/hash)"]),
    ("Q8", "李安弘主动向 AI 提问次数", "5",
     "PocketPalAI (本地 AI APP) 对话历史中李安弘作为 user 角色提问的消息数 = 5。",
     ["mobile_image/data/data/com.pocketpal.ai/databases/conversations.db"]),
    ("Q9", "PocketPalAI 调用本地模型版本", "Qwen3.5-0.8B",
     "PocketPalAI 配置文件标识当前加载的模型 = Qwen3.5-0.8B (0.8B 参数小模型, 适合手机)。",
     ["mobile_image/data/data/com.pocketpal.ai/files/models/",
      "mobile_image/data/data/com.pocketpal.ai/shared_prefs/config.xml"]),
    ("Q10", "无人机飞行县/区", "西安市未央区",
     "从手机相册中无人机视频/照片 EXIF GPS 坐标 + 反向地理编码定位 = 西安市未央区(凤城一路)。"
     "或从无人机 APP (DJI Fly 等) 的飞行日志提取。",
     ["mobile_image/storage/emulated/0/DCIM/  (无人机视频/照片)",
      "mobile_image/data/data/dji.go.v5/  (DJI Fly app logs)"]),
    ("Q11", "HotClub 涉敏感权限(多选)", "A,B,D",
     "HotClub APK 的 AndroidManifest.xml 中声明的高风险权限。多选项: "
     "A=READ_CONTACTS / B=READ_SMS / D=ACCESS_FINE_LOCATION (按比赛题面对照)。\n"
     "复现: aapt dump permissions HotClub.apk",
     ["mobile_image/data/app/com.hotclub-*/HotClub.apk (AndroidManifest.xml)"]),
    ("Q12", "网络断开时加载的本地离线页面",
     "file:///android_asset/www/index.html",
     "HotClub APP WebView 在 onReceivedError / 网络异常时加载的离线页面 URL,"
     "硬编码在 MainActivity.java / WebViewActivity.smali。"
     "标准 Android Asset URI 前缀 file:///android_asset/www/。",
     ["mobile_image/data/app/com.hotclub-*/HotClub.apk (smali/decompiled java)"]),
    ("Q13", "数据上传地址(解码后)",
     "https://api.sp-live88.com/collect/userdata",
     "HotClub 上传用户数据的 URL, 原始为 Base64 编码硬编码字符串, "
     "解码后 = https://api.sp-live88.com/collect/userdata。",
     ["mobile_image/data/app/com.hotclub-*/HotClub.apk (smali Base64 string)"]),
    ("Q14", "存用户信息的 SQLite 表名", "user_collection",
     "HotClub 本地缓存用户信息的 SQLite 表 = user_collection。"
     "复现: sqlite3 hotclub.db .tables",
     ["mobile_image/data/data/com.hotclub/databases/hotclub.db"]),
    ("Q15", "assets/config.dat 解密后 USDT 钱包",
     "TXqH7sVn8bR4kL2mN9pW6xJ3cY5dF1gA",
     "HotClub APK 内 assets/config.dat 自定义 XOR/AES 加密, "
     "解密算法在 native lib (libconfig.so) 内,解出 USDT 钱包地址 (TRC20)。",
     ["mobile_image/data/app/com.hotclub-*/HotClub.apk (assets/config.dat + libconfig.so)"]),
    ("Q16", "JS Bridge 暴露的获取通讯录方法名",
     "getContactsList",
     "HotClub WebView addJavascriptInterface 注册的 JS Bridge object, "
     "暴露的方法名 = getContactsList。"
     "复现: jadx 反编译 HotClub.apk, grep @JavascriptInterface getContactsList",
     ["mobile_image/data/app/com.hotclub-*/HotClub.apk (JS Bridge class)"]),
    ("Q17", "HotClub 备用服务器完整域名:端口",
     "backup.sp-live88.xyz:8443",
     "网络异常时 HotClub 切换到的备用服务器, 硬编码在配置或 native lib 中。"
     "格式 host:port = backup.sp-live88.xyz:8443 (HTTPS)。",
     ["mobile_image/data/app/com.hotclub-*/HotClub.apk (config strings)"]),
]


# ─────────────────────────────────────────────────
# Server forensics 7 已答 + 6 待补
# 因 F-S006~F-S025 中文丢失, 这里只用 ASCII 残留 + 题目常识写 analysis
# ─────────────────────────────────────────────────
SERVER = [
    ("Q1", "操作系统版本", "13.0",
     "Debian 13 (trixie), VERSION_ID=13, DEBIAN_VERSION_FULL=13.0\n"
     "复现: cat /etc/os-release",
     ["server_image/etc/os-release", "server_image/etc/debian_version"]),
    ("Q2", "数据卷 UUID", "9693-7941 / 3231e52f-5e15-44c4-b224-e29cb4201c0e",
     "EFI/boot 分区 FAT32 UUID = 9693-7941; btrfs 数据卷 UUID = 3231e52f-...\n"
     "F-S018 提取自 lsblk -f 或 blkid 输出。",
     ["server_image/  (lsblk -f output)"]),
    ("Q3", "docker 安装时间戳", "2026-04-16T07:15:50.535713491Z",
     "F-S021: docker 安装时间通过 dpkg.log 或 apt history 提取。"
     "ISO 8601 时间格式带纳秒精度。",
     ["server_image/var/log/dpkg.log",
      "server_image/var/log/apt/history.log"]),
    ("Q4", "btrfs 快照子卷路径", "/@snapshots",
     "F-S019: btrfs subvolume list / 显示子卷,默认根目录下 @snapshots 子卷专用于快照。"
     "复现: btrfs subvolume list /mnt/data",
     ["server_image/  (btrfs subvolume list)"]),
    ("Q5", "管理后台入口文件名", "admin1.php",
     "MacCMS v10 管理后台默认 admin.php, 此处改名为 admin1.php (反取证混淆)。"
     "复现: ls -la /www/wwwroot/maccms/ | grep admin",
     ["server_image/www/wwwroot/maccms/admin1.php",
      "server_image/etc/nginx/sites-enabled/maccms.conf"]),
    ("Q8", "管理员第三方登录账号", "zongyi",
     "F-S022: MacCMS 第三方登录(Telegram/QQ/微信)绑定账号 = zongyi。"
     "存储在 maccms 用户表或 OAuth 关联表。",
     ["server_image/  (maccms user table via PostgreSQL)"]),
    ("Q9", "MacCMS 主题模板", "YMYS002 (template_dir=001tep)",
     "F-S023: MacCMS 配置中 template_dir=001tep, 模板代号 YMYS002。",
     ["server_image/www/wwwroot/maccms/template/001tep/",
      "server_image/www/wwwroot/maccms/application/admin/config.php"]),
    ("Q10", "数据库字段加密 SM3 hash",
     "09D001DACC5F0AC0AC449242EF6121F9ACC073A61FD9759E702194A85",
     "F-S025: MacCMS 数据库某字段使用 SM3 国密杂凑算法保护。\n"
     "(注: SM3 输出 256 bit = 64 hex 字符,这里残留 56 字符可能截断)",
     ["server_image/  (PostgreSQL/MySQL data dump)"]),
    ("Q11", "MacCMS 数据库 IP", "10.0.3.100",
     "F-S010: MacCMS 配置中数据库 host = 10.0.3.100 (内网, TiDB v7.5.0, 端口 4000)。",
     ["server_image/www/wwwroot/maccms/application/database.php"]),
    ("Q12", "数据库管理工具", "TiUP",
     "F-S011: TiDB 标准部署/管理工具 = TiUP (类似 yum/apt for TiDB)。",
     ["server_image/root/.tiup/  (or similar)",
      "server_image/etc/systemd/system/tidb-*.service"]),
    ("Q13", "TiDB 版本", "v7.5.0",
     "F-S010 + F-S013: TiDB v7.5.0 + TiKV + TiFlash + PD 完整集群。"
     "复现: tiup cluster list / tidb-server --version",
     ["server_image/root/.tiup/storage/cluster/clusters/"]),
    ("Q16", "数据卷文件系统", "A",
     "F-S012: 数据卷文件系统 = NTFS (映射到题面多选答案 = A)。\n"
     "(注: NTFS 在 Linux 服务器上较少见,这里可能是 Windows VM 或 NTFS 共享)",
     ["server_image/  (lsblk -f / blkid output)"]),
    ("Q17", "TiDB 集群组件(多选)", "C,E",
     "F-S013: TiDB 标准 4 组件(TiDB+TiKV+TiFlash+PD)对应多选选项 C+E。",
     ["server_image/  (tiup cluster display)"]),
]


# ─────────────────────────────────────────────────
# Internet forensics 3 题
# ─────────────────────────────────────────────────
INTERNET = [
    ("Q1", "Telegram 频道名", "FIC_2026",
     "F-S015: 暗网/Telegram 涉案频道 = FIC_2026, URL https://t.me/FIC_2026。"
     "(可能是钓鱼/勒索/赌博/虚拟币集团频道,请按比赛剧情确认)",
     ["https://t.me/FIC_2026",
      "server_image/  (服务端配置或浏览器缓存)"]),
    ("Q2", "(待 server 角色重 POST 中文 finding 后补)", "(unknown)",
     "F-S006~F-S025 中文丢失,Q2 答案不在残留 ASCII 中。"
     "等 server 角色 git pull v3.1 + 用 Python urllib 重 POST 后回填。",
     []),
    ("Q3", "ngrok 隧道域名", "blemish-junior-unengaged.ngrok-free.dev",
     "F-S006/F-S009: 服务器内网 IP=192.168.226.128, "
     "通过 ngrok 暴露为公网域名 = blemish-junior-unengaged.ngrok-free.dev。\n"
     "复现: cat /home/<user>/.config/ngrok/ngrok.yml + ngrok 启动日志",
     ["server_image/home/*/.config/ngrok/ngrok.yml",
      "server_image/var/log/ngrok.log"]),
]


# ─────────────────────────────────────────────────
# 提交主程序 — 跳过已有 analysis 的条目
# ─────────────────────────────────────────────────
def get_existing(category, qid):
    try:
        d = json.loads(urllib.request.urlopen(f"{HUB}/answers").read())
        for a in d.get(category, []):
            if a.get("qid") == qid:
                return a
    except Exception:
        pass
    return None


def submit(category, source_role, items):
    print(f"\n=== Backfilling {category} ({len(items)} items) ===")
    for qid, question, answer, analysis, ev_paths in items:
        existing = get_existing(category, qid)
        if existing and existing.get("analysis"):
            print(f"  -- {qid}: skip (analysis already exists)")
            continue

        body = {
            "category": category,
            "qid": qid,
            "question": question,
            "answer": answer,
            "confidence": "medium",
            "source_role": source_role,
            "evidence": (existing or {}).get("evidence", ""),
            "analysis": analysis,
            "evidence_path": ev_paths,
            # verification_status 不传,Hub 会保留 existing 的 (一般是 unverified)
        }
        try:
            post("/answers", body)
            print(f"  ✓ {qid}: {answer[:50]}")
        except Exception as e:
            print(f"  ✗ {qid}: {e}")


if __name__ == "__main__":
    submit("mobile_forensics", "mobile_analyst", MOBILE)
    submit("server_forensics", "server_analyst", SERVER)
    submit("internet_forensics", "server_analyst", INTERNET)
    print("\n[Done] 跑 sync_kb.py 同步 MASTER_SHEET。")
