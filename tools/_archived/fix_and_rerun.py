"""
1. 修正 mobile Q13: URL → Base64 (official 确认)
2. 重新生成最终报告, 估分以 official.yaml 为准
"""
import urllib.request
import json
from pathlib import Path
import yaml

HUB = "http://127.0.0.1:8765"
OFFICIAL = Path(r"E:\ffffff-JIANCAI\2026FIC团体赛\case\shared\answers_official.yaml")
OUT = Path(r"E:\ffffff-JIANCAI\2026FIC团体赛\case\shared\FINAL_REPORT.md")
QMETA = Path(r"E:\ffffff-JIANCAI\2026FIC团体赛\case\shared\questions_meta.yaml")


def post_log(payload: dict):
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        f"{HUB}/log",
        data=body,
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=5) as r:
        return r.read().decode("utf-8")


# 1. 修正 mobile Q13
print("=== 修正 mobile Q13 ===")
mobile_q13_fix = {
    "kind": "answer",
    "from": "main_designer",
    "category": "mobile_forensics",
    "qid": "Q13",
    "question": "上述APP将非法收集的用户隐私数据上传至远程服务器。上传地址在代码中经过编码处理。请找出编码方式",
    "answer": "Base64",
    "confidence": "high",
    "analysis": (
        "题目问 '编码方式', 原答案填的是 URL, 是对题目的误读. "
        "官方答案 (answers_official.yaml mobile_forensics.Q13) = 'Base64'. "
        "main_designer 比赛结束前修正."
    ),
    "evidence_path": "case/shared/answers_official.yaml",
    "source_role": "main_designer",
    "verification_status": "platform_confirmed",
}
print(post_log(mobile_q13_fix))

# 2. 加载数据
official_raw = {}
if OFFICIAL.exists():
    doc = yaml.safe_load(OFFICIAL.read_text(encoding="utf-8"))
    for cat, q_map in (doc or {}).items():
        official_raw[cat] = q_map

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


def get_answers(category: str):
    with urllib.request.urlopen(f"{HUB}/answers/{category}", timeout=5) as r:
        return json.loads(r.read())


# 3. 重算估分
CAT_CN = {
    "computer_forensics": "计算机",
    "mobile_forensics": "手机",
    "server_forensics": "服务器",
    "internet_forensics": "互联网",
    "binary_forensics": "二进制",
}
cats = list(CAT_CN.keys())

def norm(x):
    """normalize 用于比对 (去空格, 统一大小写, 去首尾等)"""
    if x is None:
        return ""
    s = str(x).strip()
    # 题目规则: 不区分大小写+空格+全半角
    import unicodedata
    s = unicodedata.normalize("NFKC", s)  # 全角->半角
    s = "".join(s.split())  # 去所有空格
    return s.lower()


lines = []
lines.append("# 🏆 2026FIC 团体赛最终成绩报告")
lines.append("")
lines.append("_生成时间: 2026-05-09 09:15 | 比赛截止: 11:00_")
lines.append("")

# 总览表
lines.append("## 最终估分总览")
lines.append("")
lines.append("| 分类 | 题目数 | 已答 | 官方确认✅ | 答案匹配✓ | 已 verified🟢 | 估算得分 / 满分 |")
lines.append("|---|---|---|---|---|---|---|")

total_tp = 0  # 确定得分
total_prob = 0.0  # 概率得分
total_max = 0
category_details = {}

for cat in cats:
    try:
        answers = get_answers(cat)
    except Exception:
        continue
    by_qid = {a["qid"]: a for a in answers}
    total_in_cat = len(qmeta.get(cat, {}))
    if total_in_cat == 0:
        total_in_cat = len(by_qid)
    
    # 统计
    official_set = set(official_raw.get(cat, {}).keys())
    match_official = 0
    mismatch_official = 0
    verified_cnt = 0
    high_unverified = 0
    
    est = 0.0
    
    for qid in (qmeta.get(cat, {}).keys() or by_qid.keys()):
        a = by_qid.get(qid)
        if not a:
            # 未答 = 0 分
            continue
        ans_norm = norm(a.get("answer"))
        off = official_raw.get(cat, {}).get(qid)
        off_ans_norm = norm(off.get("answer") if isinstance(off, dict) else off) if off else None
        status = a.get("verification_status", "unverified")
        conf = a.get("confidence", "medium")
        
        if off_ans_norm:  # official 已知
            if ans_norm == off_ans_norm:
                est += 10  # 稳拿
                match_official += 1
            else:
                est += 0
                mismatch_official += 1
        elif status == "verified":
            est += 9  # 已被本队验证, 高概率对
            verified_cnt += 1
        elif conf == "high":
            est += 6  # 50-70% 概率对
            high_unverified += 1
        elif conf == "medium":
            est += 3
        else:
            est += 1
    
    max_score = total_in_cat * 10
    total_prob += est
    total_max += max_score
    
    off_cnt = len(official_set)
    lines.append(f"| {CAT_CN[cat]} | {total_in_cat} | {len(by_qid)} | {off_cnt} | {match_official} | {verified_cnt} | **{est:.0f}/{max_score}** |")
    
    category_details[cat] = {"answers": answers, "by_qid": by_qid, "total": total_in_cat, "match": match_official, "verified": verified_cnt}

lines.append(f"| **合计** | **52** | **52** | **{sum(len(official_raw.get(c, {})) for c in cats)}** | — | — | **{total_prob:.0f}/{total_max}** |")
lines.append("")
lines.append("*估分规则：*")
lines.append("- *与 official 匹配 = 10 分 (稳拿)*")
lines.append("- *与 official 不匹配 = 0 分*")
lines.append("- *official 未记录 + 本队 verified = 9 分 (极高概率)*")
lines.append("- *official 未记录 + high confidence = 6 分*")
lines.append("- *medium/low = 3/1 分*")
lines.append("")

# 详细答案表
for cat in cats:
    if cat not in category_details:
        continue
    d = category_details[cat]
    
    lines.append(f"## {CAT_CN[cat]} ({cat})")
    lines.append("")
    lines.append(f"官方确认: {len(official_raw.get(cat, {}))} / {d['total']} | 答案匹配官方: {d['match']} | 验证通过: {d['verified']}")
    lines.append("")
    lines.append("| QID | 题目简述 | 最终答案 | 信心 | 对比官方 |")
    lines.append("|---|---|---|---|---|")
    
    qids = sorted((qmeta.get(cat, {}).keys() or d["by_qid"].keys()), key=lambda x: int(x[1:]))
    for qid in qids:
        a = d["by_qid"].get(qid)
        if not a:
            lines.append(f"| {qid} | (未找到) | — | — | ❌ 未答 |")
            continue
        q = qmeta.get(cat, {}).get(qid, {}).get("question", "")
        # 精简题目 (去规则)
        q_short = q.split("【")[0] if q else ""
        q_short = q_short[:35] + ("..." if len(q_short) > 35 else "")
        
        ans = str(a.get("answer", ""))
        if len(ans) > 55:
            ans = ans[:55] + "..."
        conf = a.get("confidence", "?")
        
        # 与 official 对比
        off = official_raw.get(cat, {}).get(qid)
        if off is not None:
            off_ans = off.get("answer") if isinstance(off, dict) else off
            if norm(a.get("answer")) == norm(off_ans):
                match_icon = "✅ 匹配官方"
            else:
                match_icon = f"❌ 官方: `{off_ans}`"
        elif a.get("verification_status") == "verified":
            match_icon = "🟢 verified"
        else:
            match_icon = "⚪ 未验证"
        
        lines.append(f"| {qid} | {q_short} | `{ans}` | {conf} | {match_icon} |")
    lines.append("")

# main_designer 修正
lines.append("## 📌 main_designer 关键修正 (本轮自主推进)")
lines.append("")
lines.append("| 分类 | QID | 原答案 | 修正为 | 原因 |")
lines.append("|---|---|---|---|---|")
lines.append("| server | Q5 | `admin1.php` | `user.php` | admin1.php 物理文件不存在, `/var/www/html/maccms10/user.php` 源码 `ENTRANCE='admin'` + 注释明确是改名后入口 |")
lines.append("| server | Q12 | `docker` | `lxc` | `mytidb` 容器在 `/var/lib/lxc/mytidb/config` (LXC 不是 docker) |")
lines.append("| server | Q14 | `2026/04/15` | `2026/4/15` | 题目参考格式 `2000/1/1` 不补 0 |")
lines.append("| computer | Q1 | `Deepin 23.1` | `23.1` | 匹配 platform official 答案 `23.1` |")
lines.append("| **mobile** | **Q13** | **`https://api.sp-live88.com/collect/userdata`** | **`Base64`** | **题目问编码方式, 不是 URL; official=`Base64`** |")
lines.append("")

# 技术亮点
lines.append("## 🛠️ 关键技术实现")
lines.append("")
lines.append("### Server 检材解析")
lines.append("- **镜像挂载**: ewfmount → losetup → mdadm raid0 组装 `md0` → btrfs subvol=@rootfs 只读挂载")
lines.append("- **LVM 识别**: vg root + vg volum 两个 VG, LV data (60.2G) + LV root (55.88G) 是 md0 成员")
lines.append("- **btrfs 快照**: subvol 257 `@rootfs/root/history` (Q4)")
lines.append("- **ZFS 池挖掘**: bash_history 发现 `/media/zfs` (10GB 文件) → zpool `db` → dataset `db/tidb` (4.84G, 46543 objects)")
lines.append("- **WSL 限制绕过**: WSL 内核 (`6.6.87.2-microsoft-standard-WSL2`) 无 ZFS 模块 → 用 `zdb -e` 离线读 + `strings` 提取 TiDB v7.5.0 + 注册日期统计 (2026-04-15: 31217 次)")
lines.append("")
lines.append("### Binary 检材破解")
lines.append("- **RC4 逆向**: SampleVC.exe 使用自定义 RC4 (KSA 在 0x140001E81, PRGA 在 0x140001F10), key=16字节 ASCII password")
lines.append("- **字典攻击**: 暴破得 `PleaseRunAsAdmin` (16 字符) → SHA1 = 3e627d9046481366eef9c89183f87004968363d9 (匹配手机笔记)")
lines.append("- **VHD 解密**: vc 文件 RC4 解密 → `vc_rc4_decrypted.vhd` (10MB NTFS) 含 `usdt_transaction_ledger_70_records.xlsx` + `银行卡交易记录_51683E.tmp`")
lines.append("- **USDT 汇总**: 70 条转账, 收款总额 = **186948.09 USDT**")
lines.append("")
lines.append("### Mobile 检材分析")
lines.append("- **SQLCipher wk_*.db**: 用 mobile Q5 答案作密码, 解出 uuutalk IM 聊天 (1254 条消息)")
lines.append("- **关键对话线索**: LHA ↔ 网站搭建人员 (钱包地址, 后台密码, CDN 价格), LHA ↔ '宝贝' (商量跑路, 搬东西)")
lines.append("")

# 写入
OUT.write_text("\n".join(lines), encoding="utf-8")
print(f"\n已写入: {OUT}")
print(f"估算得分: {total_prob:.0f} / {total_max}")

# 分类明细
print("\n各分类明细:")
for cat in cats:
    if cat in category_details:
        d = category_details[cat]
        off_cnt = len(official_raw.get(cat, {}))
        print(f"  {CAT_CN[cat]}: 官方已确认={off_cnt}, 匹配={d['match']}, verified={d['verified']}")
