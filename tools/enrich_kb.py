"""
批量补充 13 道错题的 solution_steps + common_mistakes + lessons + scripts + 关联技巧
+ 创建 9 张通用技巧卡
"""
from pathlib import Path
import yaml

KB = Path(r"E:\ffffff-JIANCAI\2026FIC团体赛\case\shared\knowledge_base")
PROBLEMS = KB / "problems" / "fic2026_initial"
TECHNIQUES = KB / "techniques"

# === 13 道错题深度补充 (C-Q4 已示范完成, 这里跳过) ===
WRONG_FIXES = {
    # ========== COMPUTER ==========
    ("computer", "Q6"): {
        "keywords": ["AI软件", "模型类型", "OpenRouter", "UOSAI", "provider"],
        "solution_steps": [
            "1. 桌面任务栏右下角 UOS AI 图标 → 主动确认这是 AI 软件",
            "2. 点击 UOS AI → 设置 → 模型管理",
            "3. 看到当前激活模型来自 OpenRouter (顶层 provider 名)",
            "4. 答 OpenRouter (问 provider 不是 model_id)",
        ],
        "tools": ["UOS AI 桌面客户端", "Linux 系统设置"],
        "script_snippets": [],
        "common_mistakes": [
            "❌ 答 model_id 如 `minimax/minimax-m2.5:free` (这是模型本身, 不是类型/provider)",
            "❌ 在配置文件里乱猜模型 ID, 没注意到题目的『类型』中文含义",
        ],
        "lessons": [
            "🎯 中文题『模型类型』= provider/category (OpenAI/OpenRouter/Anthropic), 不是 model_id",
            "🎯 AI 软件 GUI 设置里『模型类型』是顶层下拉框, model_id 是次级选择",
            "🎯 看到选项类提问优先取语义最大的层级",
        ],
        "related_techniques": ["llm_app_config_inspect"],
        "related_problems": ["FIC2026_INITIAL_C_Q7"],
    },
    ("computer", "Q7"): {
        "keywords": ["UOSAI", "apiKey", "配置数据库", "sqlite", "llm"],
        "solution_steps": [
            "1. UOS AI 设置 GUI 看到 apiKey 被打码, 拿不到完整值",
            "2. find / -iname '*UOSAI*' 或 find ~ -iname '*UOS*' 找配置目录",
            "3. 通常在 ~/.config/uos-ai/ 或 ~/.local/share/uos-ai/",
            "4. 大小降序看, 找到 sqlite db 文件",
            "5. sqlite3 <db> '.tables' 看到 llm 表",
            "6. SELECT * FROM llm; → 拿到 apikey 字段完整值",
        ],
        "tools": ["sqlite3 CLI", "find / locate"],
        "script_snippets": [
            {
                "lang": "bash",
                "purpose": "找 AI 软件配置 db",
                "code": "find ~ -iname '*UOS*' -size +10k 2>/dev/null | head -20\n# 或\nfind ~/.config ~/.local -name '*.db' -o -name '*.sqlite*' 2>/dev/null | xargs -I{} sh -c 'echo {}; sqlite3 {} \".tables\" 2>/dev/null'",
            },
        ],
        "common_mistakes": [
            "❌ 答『不存在/网页版无 apiKey』(漏看 GUI 仅打码, 配置文件里有原文)",
            "❌ 只看 GUI 不去翻配置 db",
        ],
        "lessons": [
            "🎯 GUI 打码 ≠ 不存在, 永远去翻底层 sqlite/json/yaml 配置",
            "🎯 Linux AI 软件配置 99% 在 ~/.config/<appname>/ 或 ~/.local/share/<appname>/",
            "🎯 sqlite db 里搜表名: llm/api_key/key/credential/auth/token",
        ],
        "related_techniques": ["llm_app_config_inspect"],
        "related_problems": ["FIC2026_INITIAL_C_Q6"],
    },
    ("computer", "Q8"): {
        "keywords": ["勒索软件", "VeraCrypt", "VC加密", "get_token_linux", "Go逆向", "tutanota"],
        "solution_steps": [
            "1. 火眼证据分析 → 跳出『需要 VeraCrypt 解密』提示, 注意分区编号 (这里是分区 3)",
            "2. 跨检材取密码: mobile 检材笔记里找 → 笔记本/隐写识别工具显示 `9ed2@99y8.com.cn`",
            "3. 把 PC 分区 3 扔 VeraCrypt → 输入密码 → 解密成功",
            "4. 解密后看到 5 个文件, 重点是 get_token_linux (Go 程序)",
            "5. IDA 9.x 打开 (低版本不支持 Go) → 跳到 main_main 函数",
            "6. 看到字符串常量 `*(_QWORD *)v4 = 0xAFE886AFE5A3A7E8LL; v5 = 0xBBB3E7BBB3E720B7LL;`",
            "7. 小端序 hex 拼接 + UTF-8 解码 → 得到 `解密请系系` (中文勒索信)",
            "8. 后续 qmemcpy 拷贝 `beijixin996@tutanota.com` 字面量 → 这就是邮箱答案",
        ],
        "tools": ["VeraCrypt", "IDA Pro 9.2+", "Python (small-endian decoder)"],
        "script_snippets": [
            {
                "lang": "python",
                "purpose": "小端序 hex 转 UTF-8",
                "code": "import struct\n# IDA 中 *(_QWORD *)v4 = 0xAFE886AFE5A3A7E8LL\n# 小端: 8 字节按小端转 bytes\nhex_vals = [0xAFE886AFE5A3A7E8, 0xBBB3E7BBB3E720B7]\ndata = b''.join(struct.pack('<Q', v) for v in hex_vals)\nprint(data.decode('utf-8'))",
            },
        ],
        "common_mistakes": [
            "❌ 没去 mobile 检材取 VC 密码 (以为密码本地, 实际跨检材联动)",
            "❌ 把 mobile 笔记的 SHA1 当作密码 (那是 binary 题用的, 是不同的密码)",
            "❌ Go 程序用 IDA 7.x 打开看不到清晰的 main 函数",
            "❌ 看到 hex 常量没意识到是字符串 (Go 字符串字面量编译时拆成 64-bit chunks)",
        ],
        "lessons": [
            "🎯 火眼提示『需要 VeraCrypt 解密』= 第一优先级, 立即跨检材找密码",
            "🎯 mobile 笔记里有 2 个不同的密码: 9ed2@99y8.com.cn (VC) + 16字符 ASCII (binary)",
            "🎯 Go 程序逆向必备 IDA 9.x + 知道 main_main 是真入口",
            "🎯 看到 0xAFE886AFE5A3A7E8 类常量 → 立即想小端 hex → UTF-8",
            "🎯 这种『藏邮箱』题目, 邮箱通常用 qmemcpy 字面量直接放, 而提示文字用 hex 常量隐藏",
        ],
        "related_techniques": ["veracrypt_manual_mount", "go_program_reversing", "le_hex_to_utf8"],
        "related_problems": ["FIC2026_INITIAL_C_Q9", "FIC2026_INITIAL_C_Q10"],
    },
    ("computer", "Q9"): {
        "keywords": ["保险柜编号", "MP4加密", "stco", "1337", "VC容器内文件"],
        "solution_steps": [
            "1. 接 Q8 思路, VC 解密后看到 .hidden + 2 个 mp4",
            "2. 直接打开 mp4 失败 (被 get_token_linux 加密过)",
            "3. IDA 跟进 main.a 函数 (mp4 加密逻辑)",
            "4. 关键代码: 找 mp4 中的 stco box (sample table chunk offsets) → 每个 4 字节 chunk_offset 加 1337",
            "5. 解密 = 减 1337, 写 Python 脚本批量改 stco 表",
            "6. 解密后 mp4 可正常播放, 视频内显示保险柜编号 `997546`",
        ],
        "tools": ["IDA Pro", "Python (struct)", "MP4 player (VLC)"],
        "script_snippets": [
            {
                "lang": "python",
                "purpose": "MP4 stco 解密 (减 1337)",
                "code": "import struct\nfrom pathlib import Path\n\nKEY = 0x539  # 1337\n\ndef decrypt(path: Path):\n    data = bytearray(path.read_bytes())\n    idx = data.find(b'stco')\n    if idx == -1:\n        return\n    entry_count = struct.unpack('>I', data[idx+8:idx+12])[0]\n    for i in range(entry_count):\n        pos = idx + 12 + i*4\n        old = struct.unpack('>I', data[pos:pos+4])[0]\n        if old >= KEY:\n            data[pos:pos+4] = struct.pack('>I', old - KEY)\n    path.with_name(path.stem + '_dec.mp4').write_bytes(data)",
            },
        ],
        "common_mistakes": [
            "❌ 没读 main.a, 不知道 stco 是被加密的位置",
            "❌ 改 stco 时忘了 big-endian (mp4 box 数据是大端)",
            "❌ 试图用通用 mp4 修复工具 (untrunc/MP4Box) → 不行, 因为 chunk_offset 全偏移了",
        ],
        "lessons": [
            "🎯 mp4 box 结构 stco = chunk_offset table, 是常见隐藏点 (改 offset 让播放失败但 metadata 还在)",
            "🎯 stco 加密常见模式: 每个 offset ± 固定值 (1337 / 4096 / 0x10000)",
            "🎯 mp4 box header (4字节大小 + 4字节类型) → 大端 unpack '>I'",
            "🎯 程序逆向中看 main.a / main.encrypt 类函数名, Go 习惯把功能拆到 a/b/c 单字母函数",
        ],
        "related_techniques": ["mp4_stco_encryption", "go_program_reversing"],
        "related_problems": ["FIC2026_INITIAL_C_Q8", "FIC2026_INITIAL_C_Q10"],
    },
    ("computer", "Q10"): {
        "keywords": ["保险柜密码", "Excel加密", "XOR", "如何加密excel", "tool目录"],
        "solution_steps": [
            "1. 火眼/Everything 搜『保险箱』『保险柜』, 找到 /root/文档/zhongyao/ 加密 Excel",
            "2. 直接打开失败 → Excel 是被自定义脚本加密的",
            "3. 看用户的 Chrome/Firefox 历史, 反复搜过『如何加密 excel』",
            "4. 在 ~/tool/ 或桌面 tool 目录找加密脚本",
            "5. 加密逻辑: `encoded = (((x + 100) ^ 85) * 1000) + ((y + 100) ^ 85)`",
            "6. 反算: `x = ((encoded // 1000) ^ 85) - 100; y = ((encoded % 1000) ^ 85) - 100`",
            "7. 跑脚本解密 Excel 全部单元格 → 得到密码 `583985`",
        ],
        "tools": ["Python", "openpyxl"],
        "script_snippets": [
            {
                "lang": "python",
                "purpose": "Excel XOR-加 解密",
                "code": "def decrypt(encoded: int) -> tuple[int, int]:\n    x = ((encoded // 1000) ^ 85) - 100\n    y = ((encoded % 1000) ^ 85) - 100\n    return x, y\n\nfrom openpyxl import load_workbook\nwb = load_workbook('encrypted.xlsx')\nws = wb.active\nfor row in ws.iter_rows():\n    for cell in row:\n        if isinstance(cell.value, int):\n            x, y = decrypt(cell.value)\n            print(cell.coordinate, x, y)",
            },
        ],
        "common_mistakes": [
            "❌ 试图用 john/excel-密码暴破 (不是 Excel 标准加密, 是自定义脚本)",
            "❌ 没去看用户搜索历史, 错过『如何加密 excel』关键线索",
            "❌ 没去 tool 目录找加密脚本",
        ],
        "lessons": [
            "🎯 用户的浏览器搜索历史是金矿: 搜过的关键词 = 他们做过的事",
            "🎯 自定义加密脚本通常和加密文件在同/邻目录, 反算很简单",
            "🎯 看到 `(x ^ K) * N + (y ^ K)` 这种结构 = 把两个值 pack 进一个数 + XOR 混淆",
            "🎯 Excel 被加密时先确认是『标准加密』还是『单元格内容编码』(后者用脚本反算)",
        ],
        "related_techniques": ["excel_xor_decrypt", "browser_history_mining"],
        "related_problems": ["FIC2026_INITIAL_C_Q8", "FIC2026_INITIAL_C_Q9"],
    },
    # ========== MOBILE ==========
    ("mobile", "Q10"): {
        "keywords": ["DJI", "FlightRecord", "无人机", "飞行轨迹", "经纬度", "米脂县", "pydjirecord"],
        "solution_steps": [
            "1. 火眼/Everything 搜 'DJI' / 'FlightRecord' / '.txt' 在 DJI fly app 数据目录",
            "2. 找到 DJI/FlightRecord/*.txt (DJI 加密二进制日志, 文本扩展名误导)",
            "3. pip install pydjirecord",
            "4. Python: from pydjirecord import DJILog; log = DJILog.from_bytes(data)",
            "5. log.version >= 13 时需要 DJI API key (官方申请) 解密 frames",
            "6. 提取 frame.osd.latitude / longitude → 得到 (37.7966, 110.3707)",
            "7. 反查行政区 (百度地图 API / GeoNames) → 米脂县 (陕西榆林)",
        ],
        "tools": ["pydjirecord (pip)", "百度地图 API / 高德地图反查行政区"],
        "script_snippets": [
            {
                "lang": "python",
                "purpose": "DJI 日志解析",
                "code": "from pydjirecord import DJILog\nimport os\n\ndata = open('FlightRecord_xxx.txt', 'rb').read()\nlog = DJILog.from_bytes(data)\nprint(f'version={log.version}')\n\napi_key = os.environ.get('DJI_API_KEY')\nif log.version >= 13 and not api_key:\n    print('需要 DJI API key')\nelse:\n    keychains = log.fetch_keychains(api_key) if log.version >= 13 else None\n    for f in log.frames(keychains):\n        if f.osd and f.osd.latitude:\n            print(f.osd.latitude, f.osd.longitude)\n            break",
            },
        ],
        "common_mistakes": [
            "❌ 看到 .txt 扩展名以为是文本 → 直接 cat 看到乱码",
            "❌ 答省/市/区, 题目要『县』 → 中国行政区严格 县/区/市辖区",
            "❌ 用了已知 lat/lon 但反查工具不准 (用百度/高德 API 严格)",
        ],
        "lessons": [
            "🎯 DJI FlightRecord 是加密二进制即使后缀 .txt",
            "🎯 pydjirecord 在 v13+ 需要 DJI API key, header/details 不需要",
            "🎯 中国行政区精度: 省 > 市 > 县/区, 题目用『县』就严格答县级 (e.g. 米脂县, 不是榆林市)",
            "🎯 lat 37.7966, lon 110.3707 落在陕西榆林米脂县",
        ],
        "related_techniques": ["dji_flightrecord_parse", "gis_reverse_lookup"],
        "related_problems": [],
    },
    # ========== SERVER ==========
    ("server", "Q8"): {
        "keywords": ["maccms", "mac_type", "type_en", "拼音", "视频分类"],
        "solution_steps": [
            "1. 网页前台看不到拼音 → 进数据库",
            "2. cat /var/www/html/maccms10/application/database.php 拿连接信息",
            "3. mysql -h <host> -u <user> -p<pwd> <db>",
            "4. SELECT * FROM mac_type WHERE type_id = 3;",
            "5. 字段 type_en (英文/拼音 slug) = sipaanshe",
            "6. 题目要『视频的拼音』 = type_en 字段值",
        ],
        "tools": ["mysql client"],
        "script_snippets": [
            {
                "lang": "sql",
                "purpose": "查 maccms 分类拼音",
                "code": "SELECT type_id, type_name, type_en\nFROM mac_type\nWHERE type_id = 3;",
            },
        ],
        "common_mistakes": [
            "❌ 答 type_name 的拼音转换 (e.g. guochan/sipai)",
            "❌ 没意识到 maccms 有专门的 type_en 字段",
        ],
        "lessons": [
            "🎯 maccms 表设计: type_name=中文, type_en=英文/拼音 slug, type_pinyin 不存在",
            "🎯 看到『拼音』『英文』『slug』 → 优先查 type_en 字段",
            "🎯 题目说『分类3』 = type_id = 3, 不是数组索引",
        ],
        "related_techniques": ["maccms_internals"],
        "related_problems": ["FIC2026_INITIAL_S_Q7", "FIC2026_INITIAL_S_Q14"],
    },
    ("server", "Q9"): {
        "keywords": ["maccms", "前端模板", "info.ini", "001tep", "源文件"],
        "solution_steps": [
            "1. cat /var/www/html/maccms10/application/extra/maccms.php",
            "2. 看到 template => '001tep' 类配置",
            "3. ls /var/www/html/maccms10/template/001tep/",
            "4. 看到 info.ini = 模板配置文件 (含模板名/作者/版本)",
            "5. 答 info.ini (问『被使用的源文件』, 是当前应用的配置)",
            "6. 不要答 zip 包名 (e.g. YMYS002-8x8x.zip) — 那是上传时的源, 不是『被使用的』",
        ],
        "tools": ["bash (cat/ls)"],
        "script_snippets": [],
        "common_mistakes": [
            "❌ 答 zip 包名 (上传打包源)",
            "❌ 答 .html 模板文件 (具体页面不是配置)",
            "❌ 没注意到题目里『被使用的』这 3 字 (强调当前生效的, 不是历史)",
        ],
        "lessons": [
            "🎯 maccms 模板结构: template/<name>/info.ini (元信息) + html/*.html (具体模板)",
            "🎯 题目『模板源文件』≠ 模板源代码包 (.zip), 而是模板的配置文件 info.ini",
            "🎯 中文题『被使用的 X』强调当前激活, 排除已上传未启用的",
        ],
        "related_techniques": ["maccms_internals"],
        "related_problems": ["FIC2026_INITIAL_S_Q7"],
    },
    ("server", "Q10"): {
        "keywords": ["伪静态", "nginx", "sm3", "rewrite", "default"],
        "solution_steps": [
            "1. 题目『伪静态规则配置文件』 → 落在 nginx 站点配置 (rewrite 规则)",
            "2. cat /etc/nginx/sites-available/default 或 sites-enabled/default",
            "3. 确认含 location ~* / rewrite ... 等典型 URL 重写规则",
            "4. openssl dgst -sm3 /etc/nginx/sites-enabled/default",
            "5. 得到 e73407468e6f52af54c7b14632eeeb9be25b05106d06c4c3085fc843c223793f",
        ],
        "tools": ["openssl (dgst -sm3)"],
        "script_snippets": [
            {
                "lang": "bash",
                "purpose": "SM3 哈希",
                "code": "openssl dgst -sm3 /etc/nginx/sites-enabled/default\n# 或\ngmssl sm3 /etc/nginx/sites-enabled/default",
            },
        ],
        "common_mistakes": [
            "❌ 算了 maccms.conf 或 maccms.php 的 SM3 (那不是伪静态)",
            "❌ 算了 nginx.conf (主配置, 不是站点伪静态)",
            "❌ 用 sha256 不是 sm3",
        ],
        "lessons": [
            "🎯 伪静态规则 (URL rewrite) 永远在 web server 站点配置, 不在 PHP 应用内",
            "🎯 nginx 路径: sites-available/<site> → 软链 sites-enabled/<site>",
            "🎯 SM3 = 国密哈希 = openssl dgst -sm3 (要 openssl ≥ 1.1.1, 否则用 gmssl)",
            "🎯 看『xx 规则配置文件 sm3 值』分两步: 先确认正确文件 → 再算哈希",
        ],
        "related_techniques": ["sm3_hash", "nginx_rewrite_inspection"],
        "related_problems": [],
    },
    ("server", "Q15"): {
        "keywords": ["最后登录", "ip", "mac_user", "user_last_login_ip", "inet_ntoa", "TiDB"],
        "solution_steps": [
            "1. 进 maccms 数据库 (3306 端口主库, 不是 4000 备份)",
            "2. DESCRIBE mac_user; → 注意 user_last_login_ip 是 int unsigned (4字节整数)",
            "3. 直接 SELECT user_last_login_ip → 输出整数 e.g. 859467171",
            "4. 必须用 inet_ntoa() 转为 IPv4 字符串",
            "5. SQL: SELECT inet_ntoa(user_last_login_ip) FROM mac_user WHERE user_name LIKE 'Ma Hui Mei';",
            "6. 得到 51.43.21.163",
        ],
        "tools": ["mysql / TiDB client"],
        "script_snippets": [
            {
                "lang": "sql",
                "purpose": "查最后登录 IP",
                "code": "SELECT user_name, inet_ntoa(user_last_login_ip) AS last_ip\nFROM mac_user\nWHERE user_name LIKE 'Ma Hui Mei';",
            },
        ],
        "common_mistakes": [
            "❌ 直接 cat /var/log/nginx/access.log 推断 (那只是访问日志, 不是用户表)",
            "❌ 答 192.168.226.1 / 内网 IP (可能是日志里的, 不是 mac_user 表的)",
            "❌ SELECT user_last_login_ip 看到整数没转 IP",
            "❌ 用 user_name = 'Ma Hui Mei' 严格相等 (有空格/大小写, 用 LIKE 更稳)",
        ],
        "lessons": [
            "🎯 maccms / Discuz / WordPress 都把 IPv4 存为 int unsigned (省 12 字节)",
            "🎯 SQL 转 IP: MySQL `inet_ntoa()`, MariaDB 同, PostgreSQL 用 `text(inet '...')`, Python `socket.inet_ntoa(struct.pack('!I', n))`",
            "🎯 中文姓名在英文系统里通常是拼音 (Ma Hui Mei), 用 LIKE '%Ma%Hui%Mei%' 更鲁棒",
            "🎯 看到字段名带 _ip, 数据是整数 → 立刻 inet_ntoa()",
        ],
        "related_techniques": ["inet_ntoa_conversion", "maccms_internals"],
        "related_problems": ["FIC2026_INITIAL_S_Q14"],
    },
    ("server", "Q16"): {
        "keywords": ["文件系统", "未使用", "lsblk", "ntfs", "xfs", "btrfs", "lvm", "多选"],
        "solution_steps": [
            "1. lsblk -f (看完整文件系统类型列, 不是只看挂载点)",
            "2. 对照选项 A.ntfs B.btrfs C.xfs D.lvm",
            "3. btrfs (根分区) ✓ 用了",
            "4. lvm (data/root vg) ✓ 用了",
            "5. ntfs ✗ 没出现",
            "6. xfs ✗ 没出现",
            "7. 答 A,C (注意是多选)",
        ],
        "tools": ["lsblk -f", "blkid", "df -T"],
        "script_snippets": [
            {
                "lang": "bash",
                "purpose": "穷举文件系统",
                "code": "lsblk -f\necho '---'\nblkid\necho '---'\ndf -T | tail -n +2 | awk '{print $2}' | sort -u",
            },
        ],
        "common_mistakes": [
            "❌ 单选答 A 漏 C (题目是多选, 必须穷举)",
            "❌ 只看 mount/df, 漏了未挂载的设备",
        ],
        "lessons": [
            "🎯 多选题第一原则: 穷举所有候选, 用 3 种工具交叉验证 (lsblk-f / blkid / df-T)",
            "🎯 lsblk -f 显示所有块设备的 FSTYPE 列, 包括 lvm 子卷",
            "🎯 LVM 不是文件系统但题目把它列入, 说明题目把『存储栈层』都算文件系统",
        ],
        "related_techniques": ["multichoice_enumeration"],
        "related_problems": ["FIC2026_INITIAL_S_Q17"],
    },
    ("server", "Q17"): {
        "keywords": ["数据库服务", "mysql", "tidb", "postgresql", "mariadb", "多选"],
        "solution_steps": [
            "1. 选项 A.mysql B.GuessDB C.tidb D.postgresql E.mariadb",
            "2. dpkg -l | grep -iE 'mysql|tidb|postgres|mariadb|guess'",
            "3. 看 mariadb 只有 client 没有 server",
            "4. systemctl status mysql / postgresql / tidb",
            "5. ss -tlnp 看监听端口确认运行状态",
            "6. mysql ✓ (3306), tidb ✓ (4000), postgresql ✓",
            "7. mariadb ✗ (只装了 client), GuessDB ✗ (虚构)",
            "8. 答 A,C,D",
        ],
        "tools": ["dpkg -l", "systemctl", "ss -tlnp"],
        "script_snippets": [
            {
                "lang": "bash",
                "purpose": "穷举数据库服务",
                "code": "dpkg -l | grep -iE 'mysql|tidb|postgres|mariadb|sqlite|redis|mongo'\necho '---'\nfor svc in mysql mariadb postgresql tidb; do\n    systemctl is-active $svc 2>/dev/null\ndone\necho '---'\nss -tlnp 2>/dev/null | grep -E ':(3306|3307|4000|5432|6379|27017)'",
            },
        ],
        "common_mistakes": [
            "❌ 答 C,D 漏 mysql (mysql 也在跑, 容器外的)",
            "❌ 答 A,C,D,E 加上 mariadb (只装 client 不算『安装数据库服务』)",
            "❌ 看到 GuessDB 不知道是虚构选项",
        ],
        "lessons": [
            "🎯 多选『数据库服务』判定标准: 装了 server 包 + 服务能启动 (不只看 client)",
            "🎯 dpkg -l 看包名后缀: -server (服务) vs -client (客户端) vs -common (公共)",
            "🎯 ss -tlnp 看监听端口验证: 3306=mysql, 3307=mariadb, 4000=tidb, 5432=postgresql",
            "🎯 选项里的『虚构项』(GuessDB) 是常见干扰, 排除即可",
        ],
        "related_techniques": ["multichoice_enumeration", "linux_service_inventory"],
        "related_problems": ["FIC2026_INITIAL_S_Q16"],
    },
    # ========== INTERNET ==========
    ("internet", "Q1"): {
        "keywords": ["卡密", "群组ID", "TG", "Telegram", "@前缀"],
        "solution_steps": [
            "1. 来源: server maccms.php 主配置文件中, 看到 t.me/FIC_2026 链接",
            "2. Telegram 群组 ID 平台规则: 必须带 @ 前缀",
            "3. 答 @FIC_2026 (不是 FIC_2026, 不是 t.me/FIC_2026)",
        ],
        "tools": ["grep", "对官方 platform_confirmed 答案抓格式"],
        "script_snippets": [],
        "common_mistakes": [
            "❌ 答 FIC_2026 缺 @ 前缀",
            "❌ 答完整 URL t.me/FIC_2026 (太长不符合 ID 格式)",
            "❌ 答 https://t.me/FIC_2026 (是链接不是 ID)",
        ],
        "lessons": [
            "🎯 Telegram/QQ/微信 群组 ID 平台规则: TG 带 @, QQ 不带, 微信用 wxid_",
            "🎯 看到题目『群组 ID』 → 第一反应去『关注』平台格式潜规则",
            "🎯 早期收集 platform_confirmed 答案样本, 建格式字典: ID/日期/URL/多选/路径",
        ],
        "related_techniques": ["platform_format_dictionary"],
        "related_problems": [],
    },
    ("internet", "Q2"): {
        "keywords": ["备份数据库", "视频图片", "mac_vod", "lxc-attach", "TiDB"],
        "solution_steps": [
            "1. 题目说『备份数据库』 = 服务器 4000 端口的 TiDB (Q13 已确认)",
            "2. 不要在 /etc/mysql 找 — 那是主库",
            "3. lxc-ls -f 看到 mytidb 容器",
            "4. lxc-attach -n mytidb -- bash → 进容器",
            "5. 容器内 mysql -h 127.0.0.1 -P 4000 -u root <db>",
            "6. SHOW TABLES → 看到 mac_vod 表",
            "7. SELECT vod_pic FROM mac_vod LIMIT 5;",
            "8. 找出 .jpg 文件名 = 7b3fdd9d464ce48e7f20cd45f918c9a6.jpg",
        ],
        "tools": ["lxc-attach", "mysql client (TiDB 兼容)"],
        "script_snippets": [
            {
                "lang": "bash",
                "purpose": "进 TiDB 容器查 mac_vod",
                "code": "lxc-attach -n mytidb -- mysql -h 127.0.0.1 -P 4000 -u root \\\n    -e 'SELECT vod_id, vod_name, vod_pic FROM <db>.mac_vod LIMIT 10;'",
            },
        ],
        "common_mistakes": [
            "❌ 在主库 (3306) 查 mac_vod (主库的不是『备份』)",
            "❌ 没意识到 maccms 的图片字段叫 vod_pic 不是 vod_img",
            "❌ 容器外 ping 不到 mytidb (lxc 网络隔离, 必须 lxc-attach 进去)",
        ],
        "lessons": [
            "🎯 备份数据库的访问路径: 找运行的容器/服务 → lxc-attach 进 → 内部连接",
            "🎯 maccms 表 mac_vod 字段: vod_id (主键), vod_name (片名), vod_pic (封面 URL/文件名)",
            "🎯 区分『主库』和『备份库』: 不同端口 (3306 vs 4000) / 不同容器 (host vs lxc)",
            "🎯 lxc-attach -n <容器> -- <命令> 一行执行",
        ],
        "related_techniques": ["lxc_attach", "maccms_internals"],
        "related_problems": ["FIC2026_INITIAL_S_Q11", "FIC2026_INITIAL_S_Q13"],
    },
}


def load_yaml(path: Path) -> dict:
    if not path.exists():
        return {}
    with path.open(encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def save_yaml(path: Path, data: dict):
    with path.open("w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, allow_unicode=True, sort_keys=False, width=100)


# === 应用补充 ===
print("=== 补充 13 道错题 ===")
filled = 0
for (cat, qid), patch in WRONG_FIXES.items():
    p = PROBLEMS / cat / f"{qid}.yaml"
    if not p.exists():
        print(f"  ⚠ {cat}/{qid}.yaml 不存在")
        continue
    data = load_yaml(p)
    # 合并 patch (覆盖式)
    data.update(patch)
    save_yaml(p, data)
    filled += 1
    print(f"  ✓ {cat}/{qid}.yaml")

print(f"\n共补充 {filled} 道")
