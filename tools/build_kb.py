"""
从 questions_meta.yaml + answers_official.yaml + Hub answers + 博客 wp 摘录
一键生成 52 道题的知识库骨架 yaml。

后续手动补充: solution_steps, lessons, common_mistakes 等深度字段。
"""
import json
import urllib.request
from pathlib import Path
import yaml
import re

HUB = "http://127.0.0.1:8765"
SHARED = Path(r"E:\ffffff-JIANCAI\2026FIC团体赛\case\shared")
KB = SHARED / "knowledge_base"
PROBLEMS = KB / "problems" / "fic2026_initial"

CATS = {
    "computer_forensics": ("computer", "C"),
    "mobile_forensics": ("mobile", "M"),
    "server_forensics": ("server", "S"),
    "internet_forensics": ("internet", "I"),
    "binary_forensics": ("binary", "B"),
}

# 从博客 wp 抽取的官方答案 (手工整理)
WP_OFFICIAL = {
    "computer": {
        "Q1": {"answer": "23.1", "method": "系统信息 / cat /etc/os-release"},
        "Q2": {"answer": "hf13338261292@outlook.com", "method": "搜邮件中关键词 'token'"},
        "Q3": {"answer": "13612817854", "method": "火眼仿真 → 语音记事本 → 黄金换现金联系方式"},
        "Q4": {
            "answer": "https://drive.google.com/file/d/1z3aRS-lkaJYKm7Cp1XjtUmVPsOEVW2fV/view?usp=sharing",
            "method": "搜推广设计图 → .enc + decrypt.html + public.txt → RSA Fermat 分解 → 解密 → 扫二维码",
        },
        "Q5": {"answer": "9527", "method": "VPN 软件设置查代理端口"},
        "Q6": {"answer": "OpenRouter", "method": "UOSAI 设置 → 模型类型 (问 provider 不是 model_id)"},
        "Q7": {"answer": "(UOSAI db 中真实 apikey)", "method": "搜 UOS 配置文件 → llm 表的 apikey 字段"},
        "Q8": {
            "answer": "beijixin996@tutanota.com",
            "method": "VC 解密(密码=mobile笔记 9ed2@99y8.com.cn) → IDA 反汇编 get_token_linux → main.main 中小端序 hex 转 UTF-8",
        },
        "Q9": {
            "answer": "997546",
            "method": "VC 解密 → 看到加密 mp4 → 反汇编 main.a 发现 stco 表每个 chunk_offset += 1337 → 减 1337 解密 → 打开 mp4 看密码",
        },
        "Q10": {
            "answer": "583985",
            "method": "搜'保险箱' → /root/文档/zhongyao 加密 Excel → tool 目录加密脚本 (((x+100)^85)*1000+((y+100)^85)) → 反算 x,y",
        },
    },
    "mobile": {
        "Q1": {"answer": "RedmiNote7Pro", "method": "火眼直读手机型号"},
        "Q2": {"answer": "20260606", "method": "小米 Note → todo.db → 计划记录"},
        "Q3": {"answer": "20260414", "method": "APP 分析锁定 uuutalk → 安装时间"},
        "Q4": {"answer": "wk_9628874a3c6b403593766496fa985893.db", "method": "uuutalk 加密 db 文件名"},
        "Q5": {"answer": "9628874a3c6b403593766496fa985893", "method": "SQLCipher 密码 = 文件名去 wk_ 前缀"},
        "Q6": {"answer": "TN8vQzB3n7W5wVca9W4kL2wP7xY9zM5nU1", "method": "解密聊天 db → message_seq=30 (大日云服务器)"},
        "Q7": {"answer": "26226f", "method": "聊天截图 9054354934843.png → 交易 hash 前 6 位 (官方/平台版本)"},
        "Q8": {"answer": "5", "method": "PocketPal AI db → message 表 role='user' 计数"},
        "Q9": {"answer": "Qwen3.5-0.8B", "method": "PocketPalAI 文件夹 model 子目录 (博客作者拼写有误 Qwem3.5)"},
        "Q10": {
            "answer": "米脂县",
            "method": "DJI FlightRecord *.txt → pydjirecord 库解析 → 经纬度 (37.7966, 110.3707) → 反查米脂县",
        },
        "Q11": {"answer": "A,B,D", "method": "AndroidManifest.xml 看 permissions"},
        "Q12": {"answer": "file:///android_asset/www/index.html", "method": "MainActivity onCreate WebView 离线加载分支"},
        "Q13": {
            "answer": "Base64",
            "method": "敏感字段 aHR0cHM6Ly9hcGku... → Base64 解码 → URL (题目只问编码方式)",
        },
        "Q14": {"answer": "user_collection", "method": "全文搜 'CREATE TABLE' 找到 user_collection"},
        "Q15": {"answer": "TXqH7sVn8bR4kL2mN9pW6xJ3cY5dF1gA", "method": "config.dat 解密 → JSON sponsors[2].wallet"},
        "Q16": {"answer": "getContactsList", "method": "AppNative 暴露的 JS 接口"},
        "Q17": {"answer": "backup.sp-live88.xyz:8443", "method": "失败回退逻辑 → 备用域名+端口"},
    },
    "server": {
        "Q1": {"answer": "13", "method": "cat /etc/os-release → Debian 13"},
        "Q2": {"answer": "3231e52f-5e15-44c4-b224-e29cb4201c0e", "method": "cat /etc/fstab → 根分区 btrfs UUID"},
        "Q3": {"answer": "2026-04-16T07:15:50.535713491Z", "method": "docker images --format + docker inspect"},
        "Q4": {"answer": "/root/history", "method": "btrfs subvolume list / + show 看 snapshot 标记"},
        "Q5": {"answer": "user.php", "method": "nginx 配置 + maccms10 ENTRANCE='admin' 判定改名后入口"},
        "Q6": {"answer": "icp1919810", "method": "/var/www/html/maccms10/application/extra/maccms.php"},
        "Q7": {"answer": "www.2026fic.forensix", "method": "同上 maccms.php"},
        "Q8": {"answer": "sipaanshe", "method": "mysql 连数据库 → mac_type 表 type_id=3 → type_en 字段"},
        "Q9": {"answer": "info.ini", "method": "maccms.php 模板目录配置 001tep → info.ini (问应用文件不是源 zip)"},
        "Q10": {
            "answer": "e73407468e6f52af54c7b14632eeeb9be25b05106d06c4c3085fc843c223793f",
            "method": "openssl dgst -sm3 /etc/nginx/sites-enabled/default (伪静态规则在 nginx 配置)",
        },
        "Q11": {"answer": "10.0.3.100", "method": "database.php host=mytidb + /etc/hosts 查 IP"},
        "Q12": {"answer": "lxc", "method": "/var/lib/lxc/mytidb/config 确认 (不是 docker)"},
        "Q13": {"answer": "v7.5.0", "method": "lxc-attach mytidb → tidb --version 或 SQL select tidb_version()"},
        "Q14": {"answer": "2026/4/15", "method": "SQL DATE_FORMAT(FROM_UNIXTIME(user_reg_time), '%Y/%c/%e')"},
        "Q15": {
            "answer": "51.43.21.163",
            "method": "SELECT inet_ntoa(user_last_login_ip) FROM mac_user WHERE user_name LIKE 'Ma Hui Mei'",
        },
        "Q16": {"answer": "A,C", "method": "lsblk -f 看完整文件系统 (ntfs+xfs 都没用)"},
        "Q17": {"answer": "A,C,D", "method": "dpkg -l + systemctl 看 mariadb-server 仅客户端 → mysql+tidb+postgresql"},
    },
    "internet": {
        "Q1": {"answer": "@FIC_2026", "method": "服务器 maccms 配置中的 TG 链接 (注意带 @)"},
        "Q2": {
            "answer": "7b3fdd9d464ce48e7f20cd45f918c9a6.jpg",
            "method": "lxc-attach mytidb → SQL mac_vod 表的 vod_pic 字段",
        },
        "Q3": {"answer": "blemish-junior-unengaged.ngrok-free.dev", "method": "ngrok http 80 看动态分配域名"},
    },
    "binary": {
        "Q1": {"answer": "764789dd9c095d74b6b258cf0f7568b2", "method": "U盘 SampleVC.exe → certutil/md5sum"},
        "Q2": {"answer": "2026-04-17", "method": "DIE 看 PE 编译时间戳"},
        "Q3": {
            "answer": "PleaseRunAsAdmin",
            "method": "IDA → sub_140002200 看到 AES-128 + 异或层 → key=0x0123456789ABCDEF + ct=afb977ac... → 解密+反异或",
        },
        "Q4": {"answer": ".vhd", "method": "IDA sub_140001CF0 看到拼接 .vhd 后缀"},
        "Q5": {
            "answer": "186948.09",
            "method": "RC4 解 vc → vc.vhd → 挂载 NTFS → openpyxl 计算收款地址总额 70 条",
        },
    },
}


def load_yaml(path: Path):
    if not path.exists():
        return {}
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def get_hub_answers():
    out = {}
    for cat in CATS:
        try:
            with urllib.request.urlopen(f"{HUB}/answers/{cat}", timeout=5) as r:
                out[cat] = {a["qid"]: a for a in json.loads(r.read())}
        except Exception:
            out[cat] = {}
    return out


def normalize(x):
    import unicodedata
    s = str(x or "").strip()
    s = unicodedata.normalize("NFKC", s)
    return "".join(s.split()).lower()


def detect_qtype(answer: str) -> str:
    a = str(answer or "")
    if re.match(r"^[A-Z](,[A-Z])*$", a) or re.match(r"^[A-Z]+$", a):
        return "multi_choice"
    if a.startswith(("http://", "https://", "file://")):
        return "url"
    if re.match(r"^[a-f0-9]{32}$", a):
        return "md5"
    if re.match(r"^[a-f0-9]{40}$", a):
        return "sha1"
    if re.match(r"^[a-f0-9]{64}$", a):
        return "sha256"
    if re.match(r"^\d+(\.\d+)?$", a):
        return "number"
    if re.match(r"^\d{4}[-/年]\d", a) or re.match(r"^\d{8}$", a):
        return "date"
    if re.match(r"^\d+\.\d+\.\d+\.\d+$", a):
        return "ip"
    if "@" in a and "." in a:
        return "email"
    return "text"


def extract_keywords(question: str, category: str) -> list:
    """从题目中提取检索关键词"""
    # 去掉规则部分
    q = question.split("【")[0]
    # 去标点
    import re
    q = re.sub(r"[，。、？\?！,.\s]+", " ", q)
    words = [w for w in q.split() if len(w) >= 2 and "分析" not in w]
    # 加分类
    return list(dict.fromkeys(words))[:8]  # dedupe + top 8


def build_problem(category_long: str, qid: str) -> dict:
    cat_short, cat_letter = CATS[category_long]
    qmeta_q = QMETA.get(category_long, {}).get(qid, {})
    question = qmeta_q.get("question", "") if isinstance(qmeta_q, dict) else ""
    if isinstance(qmeta_q, str):
        question = qmeta_q
    
    wp = WP_OFFICIAL.get(cat_short, {}).get(qid, {})
    official = OFFICIAL_RAW.get(category_long, {}).get(qid)
    if isinstance(official, dict):
        off_ans = official.get("answer")
    else:
        off_ans = official
    
    # 优先用 wp 答案 (更详细), 次用 official.yaml
    final_answer = wp.get("answer") or off_ans
    
    our = HUB_ANS.get(category_long, {}).get(qid, {})
    our_ans = our.get("answer", "")
    
    # 比对
    if final_answer and our_ans:
        result = "correct" if normalize(our_ans) == normalize(final_answer) else "incorrect"
    elif our_ans:
        result = "unknown"
    else:
        result = "not_answered"
    
    qno = int(qid[1:])
    full_qid = f"FIC2026_INITIAL_{cat_letter}_Q{qno}"
    
    return {
        "qid": full_qid,
        "competition": "FIC",
        "year": 2026,
        "stage": "initial",
        "category": cat_short,
        "question_no": qno,
        "question": question,
        "question_type": detect_qtype(final_answer or ""),
        "expected_format": qmeta_q.get("expected_format", "") if isinstance(qmeta_q, dict) else "",
        "keywords": extract_keywords(question, cat_short),
        "official_answer": final_answer,
        "our_actual_answer": our_ans,
        "our_confidence": our.get("confidence", ""),
        "result": result,
        "verification_status": our.get("verification_status", ""),
        "method_summary": wp.get("method", ""),
        # 占位待手工补充
        "solution_steps": [],
        "tools": [],
        "script_snippets": [],
        "common_mistakes": [],
        "lessons": [],
        "related_techniques": [],
        "related_problems": [],
        "contributed_by": "main_designer",
        "contributed_at": "2026-05-09",
        "verified": bool(final_answer),
    }


# === 入口 ===
QMETA = load_yaml(SHARED / "questions_meta.yaml")
OFFICIAL_RAW = load_yaml(SHARED / "answers_official.yaml")
HUB_ANS = get_hub_answers()

index = {"problems": []}
for cat_long, (cat_short, cat_letter) in CATS.items():
    out_dir = PROBLEMS / cat_short
    out_dir.mkdir(parents=True, exist_ok=True)
    
    qids = sorted((QMETA.get(cat_long, {}) or {}).keys(), key=lambda x: int(x[1:]))
    for qid in qids:
        prob = build_problem(cat_long, qid)
        out_path = out_dir / f"{qid}.yaml"
        with out_path.open("w", encoding="utf-8") as f:
            yaml.safe_dump(prob, f, allow_unicode=True, sort_keys=False, width=100)
        index["problems"].append({
            "qid": prob["qid"],
            "category": cat_short,
            "question_no": prob["question_no"],
            "file": str(out_path.relative_to(KB)).replace("\\", "/"),
            "keywords": prob["keywords"],
            "result": prob["result"],
        })

# 全局索引
with (KB / "INDEX.yaml").open("w", encoding="utf-8") as f:
    yaml.safe_dump(index, f, allow_unicode=True, sort_keys=False, width=120)

# 统计
total = len(index["problems"])
correct = sum(1 for p in index["problems"] if p["result"] == "correct")
print(f"已生成 {total} 道题骨架")
print(f"录入位置: {KB}")
print(f"正确率(对照官方): {correct}/{total} = {correct/total*100:.0f}%")

# 错题清单
print("\n=== 错题清单 (优先补充 lessons) ===")
for p in index["problems"]:
    if p["result"] == "incorrect":
        print(f"  {p['qid']}")
