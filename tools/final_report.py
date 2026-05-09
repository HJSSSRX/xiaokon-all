"""
生成比赛最终成绩报告
- 从 Hub 拉取所有 category 的最终答案
- 对照 answers_official.yaml 里 platform_confirmed 的答案
- 生成清晰的成绩单 + 估分
"""
import json
import urllib.request
from pathlib import Path
import yaml

HUB = "http://127.0.0.1:8765"
OFFICIAL = Path(r"E:\ffffff-JIANCAI\2026FIC团体赛\case\shared\answers_official.yaml")
OUT = Path(r"E:\ffffff-JIANCAI\2026FIC团体赛\case\shared\FINAL_REPORT.md")
QMETA = Path(r"E:\ffffff-JIANCAI\2026FIC团体赛\case\shared\questions_meta.yaml")


def get_answers(category: str):
    url = f"{HUB}/answers/{category}"
    with urllib.request.urlopen(url, timeout=5) as r:
        return json.loads(r.read())


# 加载 official
official = {}
if OFFICIAL.exists():
    doc = yaml.safe_load(OFFICIAL.read_text(encoding="utf-8"))
    for cat, q_map in (doc or {}).items():
        official[cat] = {}
        for qid, qinfo in q_map.items():
            official[cat][qid] = qinfo.get("answer") if isinstance(qinfo, dict) else qinfo

# 加载 questions_meta (拿题目原文 + score)
qmeta = {}
if QMETA.exists():
    doc = yaml.safe_load(QMETA.read_text(encoding="utf-8"))
    for cat, q_list in (doc or {}).items():
        qmeta[cat] = {}
        if isinstance(q_list, dict):
            for qid, info in q_list.items():
                qmeta[cat][qid] = info
        elif isinstance(q_list, list):
            for info in q_list:
                qmeta[cat][info["qid"]] = info

# 角色映射
CAT_CN = {
    "computer_forensics": "计算机",
    "mobile_forensics": "手机",
    "server_forensics": "服务器",
    "internet_forensics": "互联网",
    "binary_forensics": "二进制",
}

# 总数矩阵
cats = ["computer_forensics", "mobile_forensics", "server_forensics", "internet_forensics", "binary_forensics"]

# 生成报告
lines = []
lines.append("# 2026FIC 团体赛最终成绩报告")
lines.append("")
lines.append("_生成时间: 2026-05-09 09:15 | 比赛截止: 11:00_")
lines.append("")
lines.append("## 总览")
lines.append("")
lines.append("| 分类 | 题目数 | 已答 | platform 确认 | 主观估计得分* |")
lines.append("|---|---|---|---|---|")

total_solved = 0
total_q = 0
total_platform = 0
total_est_score = 0
total_max_score = 0
cat_data = {}  # 临时存储每个类别

for cat in cats:
    try:
        answers = get_answers(cat)
    except Exception as e:
        print(f"fetch {cat} failed: {e}")
        continue
    
    by_qid = {a["qid"]: a for a in answers}
    total_in_cat = len(qmeta.get(cat, {}))
    if total_in_cat == 0:
        total_in_cat = len(by_qid)
    
    solved = len(by_qid)
    platform_ok = sum(1 for a in answers if a.get("verification_status") == "platform_confirmed")
    
    # 估分: platform_confirmed = 10 分 (稳拿), verified = 8 分 (高概率), 
    #       high confidence unverified = 5 分, medium/low = 3 分
    est = 0
    for a in answers:
        score = 10  # 每题 10 分
        status = a.get("verification_status", "unverified")
        conf = a.get("confidence", "medium")
        if status == "platform_confirmed":
            est += score
        elif status == "verified":
            est += score * 0.8
        elif conf == "high":
            est += score * 0.5
        elif conf == "medium":
            est += score * 0.3
        else:
            est += score * 0.1
    max_score = total_in_cat * 10
    total_est_score += est
    total_max_score += max_score
    total_solved += solved
    total_q += total_in_cat
    total_platform += platform_ok
    
    lines.append(f"| {CAT_CN[cat]} | {total_in_cat} | {solved} | {platform_ok} | {est:.0f}/{max_score} |")
    cat_data[cat] = (answers, total_in_cat)

lines.append(f"| **合计** | **{total_q}** | **{total_solved}** | **{total_platform}** | **{total_est_score:.0f}/{total_max_score}** |")
lines.append("")
lines.append("*估分规则：platform_confirmed=10, verified=8, high_conf_unverified=5, medium=3, low=1*")
lines.append("")

# 详细答案表 (每个类别)
for cat in cats:
    if cat not in cat_data:
        continue
    answers, total_in_cat = cat_data[cat]
    by_qid = {a["qid"]: a for a in answers}
    
    lines.append(f"## {CAT_CN[cat]} ({cat})")
    lines.append("")
    lines.append("| QID | 题目 | 最终答案 | 信心 | 状态 | 验证 |")
    lines.append("|---|---|---|---|---|---|")
    
    qids = sorted(by_qid.keys(), key=lambda x: int(x[1:]))
    for qid in qids:
        a = by_qid[qid]
        question = qmeta.get(cat, {}).get(qid, {}).get("question", "")
        # 截短题目
        qtext = question[:50] + ("..." if len(question) > 50 else "")
        answer = str(a.get("answer", ""))
        if len(answer) > 60:
            answer = answer[:60] + "..."
        conf = a.get("confidence", "?")
        status = a.get("verification_status", "unverified")
        off = official.get(cat, {}).get(qid)
        
        match = ""
        if off is not None:
            if str(off) == str(a.get("answer", "")):
                match = "✓"
            else:
                match = f"❌ (官: `{off}`)"
        
        # 状态 icon
        if status == "platform_confirmed":
            status_icon = "✅"
        elif status == "verified":
            status_icon = "🟢"
        elif status == "disputed":
            status_icon = "🔴"
        else:
            status_icon = "⚪"
        
        lines.append(f"| {qid} | {qtext} | `{answer}` | {conf} | {status_icon} {status} | {match} |")
    lines.append("")

# 没答的题 (缺失的 qid)
lines.append("## 未答题 (缺失)")
lines.append("")
any_missing = False
for cat in cats:
    if cat not in cat_data:
        continue
    answers, total_in_cat = cat_data[cat]
    by_qid = {a["qid"]: a for a in answers}
    expected_qids = set(qmeta.get(cat, {}).keys())
    missing = expected_qids - set(by_qid.keys())
    if missing:
        any_missing = True
        lines.append(f"- **{CAT_CN[cat]}**: {sorted(missing)}")
if not any_missing:
    lines.append("无。所有 52 题均已答。")
lines.append("")

# 修正记录
lines.append("## 主持 (main_designer) 关键修正")
lines.append("")
lines.append("| 分类 | QID | 原答案 | 修正为 | 原因 |")
lines.append("|---|---|---|---|---|")
lines.append("| server | Q5 | `admin1.php` | `user.php` | admin1.php 物理文件不存在, user.php 源码 ENTRANCE='admin' 明确是改名后的 admin 入口 |")
lines.append("| server | Q12 | `docker` | `lxc` | mytidb 容器在 `/var/lib/lxc/mytidb/config` (LXC 不是 docker) |")
lines.append("| server | Q14 | `2026/04/15` | `2026/4/15` | 题目参考格式 `2000/1/1` 不补 0 |")
lines.append("| computer | Q1 | `Deepin 23.1` | `23.1` | 匹配 platform official 答案 `23.1` |")
lines.append("")

# 写入
OUT.write_text("\n".join(lines), encoding="utf-8")
print(f"已写入: {OUT}")
print(f"总题数: {total_q}, 已答: {total_solved}, 官方确认: {total_platform}")
print(f"估算得分: {total_est_score:.0f} / {total_max_score}")
