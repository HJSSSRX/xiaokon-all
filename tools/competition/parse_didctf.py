"""parse_didctf_md.py  —  抽取 DIDCTF 平台导出的 markdown 题库

输入: 用户从 https://forensics.didctf.com/practice/questions 复制的网页文本
输出: 三个文件
  - questions_meta.yaml   题号 + 题目 + 参考格式 + 题型 + 分值
  - answers_official.yaml 平台显示的标准答案 (说明本队已答对)
  - todo.yaml             还没答对的题目, 按分类分组 (待解列表)

格式特征:
  {分类}-{编号}              ← 题目开始
  简答 | 多选 | 单选         ← 题型
  分值 10
  {分类}                    ← 标签 (重复)
  [题目正文 + 【参考格式：...】]
  [选项 A. ... / B. ... ...]   (多选/单选)
  [官方答案]                  ← 仅当本队已答对该题时存在
  N个用户已解出              ← 题目结束

usage:
  python3 parse_didctf_md.py <input.md> --out-dir <case/shared>
"""

from __future__ import annotations
import argparse, re, sys, io, pathlib

try:
    import yaml
except ImportError:
    print("ERROR: pip install pyyaml", file=sys.stderr)
    sys.exit(1)

# 分类中文 → 英文 ID
CATEGORY_MAP = {
    "计算机取证":     "computer_forensics",
    "手机取证":       "mobile_forensics",
    "服务器取证":     "server_forensics",
    "互联网取证":     "internet_forensics",
    "二进制程序取证": "binary_forensics",
}

# 题号匹配: "计算机取证-1" / "二进制程序取证-3"
RE_QID = re.compile(r"^(" + "|".join(re.escape(k) for k in CATEGORY_MAP) + r")-(\d+)\s*$")
RE_TYPE = re.compile(r"^(简答|多选|单选|多选填空)\s*$")
RE_SCORE = re.compile(r"^分值\s+(\d+)\s*$")
RE_SOLVED = re.compile(r"^(\d+)\s*个用户已解出\s*$")
RE_OPTION = re.compile(r"^([A-G])\s*[\.、）)]\s*(.+)$")
RE_FORMAT_HINT = re.compile(r"【参考格式[：:]([^】]*)】|（答案格式[：:]([^）]*)）|【答案格式[：:]([^】]*)】")


def parse_md(text: str) -> list[dict]:
    """解析整个 markdown, 返回题目列表"""
    lines = [l.rstrip() for l in text.splitlines()]
    questions = []

    i = 0
    while i < len(lines):
        m = RE_QID.match(lines[i])
        if not m:
            i += 1
            continue

        cat_zh, qnum = m.group(1), int(m.group(2))
        cat_en = CATEGORY_MAP[cat_zh]
        qid = f"Q{qnum}"

        # 收集这道题的所有行直到 "N个用户已解出"
        block = []
        i += 1
        while i < len(lines):
            if RE_SOLVED.match(lines[i]):
                solved_count = int(RE_SOLVED.match(lines[i]).group(1))
                i += 1
                break
            block.append(lines[i])
            i += 1
        else:
            solved_count = -1

        # 解析 block: 第一行是题型, 第二行是分值, 第三行是分类标签, 之后是题目+选项+答案
        qtype, score = "简答", 10
        body_lines = []
        idx = 0
        while idx < len(block):
            ln = block[idx]
            if RE_TYPE.match(ln):
                qtype = ln.strip()
                idx += 1
                continue
            mm = RE_SCORE.match(ln)
            if mm:
                score = int(mm.group(1))
                idx += 1
                continue
            if ln.strip() == cat_zh:  # 分类标签行
                idx += 1
                continue
            body_lines.append(ln)
            idx += 1

        # body_lines 结构:
        #   [题目正文 (含【参考格式：...】)]
        #   ([] 空行)
        #   [选项 A. xxx / B. xxx ...]   (仅多选/单选)
        #   ([] 空行)
        #   [官方答案]                   (仅已答对)
        body_lines = [b for b in body_lines if b.strip() != ""]

        question_text = ""
        options = []
        official_answer = None
        format_hint = ""

        # 第一行总是题目
        if body_lines:
            question_text = body_lines[0]
            # 提取参考格式
            mh = RE_FORMAT_HINT.search(question_text)
            if mh:
                format_hint = (mh.group(1) or mh.group(2) or mh.group(3) or "").strip()

        # 后续行: 区分选项 vs 答案
        for ln in body_lines[1:]:
            mo = RE_OPTION.match(ln.strip())
            if mo:
                options.append(f"{mo.group(1)}. {mo.group(2)}")
            else:
                # 如果不是选项, 那是官方答案
                # 但单选/多选题的答案可能是 "A,B,D" 之类
                if official_answer is None:
                    official_answer = ln.strip()
                else:
                    # 多行答案 (罕见)
                    official_answer += "\n" + ln.strip()

        questions.append({
            "qid": qid,
            "category": cat_en,
            "category_zh": cat_zh,
            "qtype": qtype,
            "score": score,
            "question": question_text,
            "format_hint": format_hint,
            "options": options,
            "official_answer": official_answer,
            "solved_count": solved_count,
        })

    return questions


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("input", help="输入 .md 文件")
    ap.add_argument("--out-dir", default=".", help="输出目录")
    args = ap.parse_args()

    if hasattr(sys.stdout, "buffer"):
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

    text = pathlib.Path(args.input).read_text(encoding="utf-8")
    questions = parse_md(text)

    out_dir = pathlib.Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    # 1. questions_meta.yaml — 题目元数据
    meta = {}
    for q in questions:
        cat = q["category"]
        meta.setdefault(cat, {})
        meta[cat][q["qid"]] = {
            "qid": q["qid"],
            "qtype": q["qtype"],
            "score": q["score"],
            "question": q["question"],
            "format_hint": q["format_hint"],
            "options": q["options"],
            "solved_count": q["solved_count"],
        }
    (out_dir / "questions_meta.yaml").write_text(
        yaml.safe_dump(meta, allow_unicode=True, sort_keys=False, indent=2),
        encoding="utf-8")

    # 2. answers_official.yaml — 平台显示的标准答案 (本队已答对)
    official = {}
    open_qs = {}
    for q in questions:
        cat = q["category"]
        if q["official_answer"]:
            official.setdefault(cat, {})[q["qid"]] = {
                "answer": q["official_answer"],
                "verification_status": "platform_confirmed",
            }
        else:
            open_qs.setdefault(cat, []).append({
                "qid": q["qid"],
                "qtype": q["qtype"],
                "question": q["question"][:80] + ("..." if len(q["question"]) > 80 else ""),
                "format_hint": q["format_hint"],
            })
    (out_dir / "answers_official.yaml").write_text(
        yaml.safe_dump(official, allow_unicode=True, sort_keys=False, indent=2),
        encoding="utf-8")

    # 3. todo.yaml — 待解题目
    (out_dir / "todo.yaml").write_text(
        yaml.safe_dump(open_qs, allow_unicode=True, sort_keys=False, indent=2),
        encoding="utf-8")

    # 输出统计
    total = len(questions)
    solved = sum(1 for q in questions if q["official_answer"])
    print(f"=== 解析完成 ===")
    print(f"总题数: {total}")
    print(f"已答对: {solved}")
    print(f"待解决: {total - solved}")
    print()
    print("各分类细分:")
    for cat_en in CATEGORY_MAP.values():
        cat_qs = [q for q in questions if q["category"] == cat_en]
        cat_done = sum(1 for q in cat_qs if q["official_answer"])
        cat_zh = next(k for k, v in CATEGORY_MAP.items() if v == cat_en)
        print(f"  [{cat_zh:8s}] {cat_done}/{len(cat_qs)}")
    print()
    print(f"输出文件:")
    print(f"  {out_dir / 'questions_meta.yaml'}")
    print(f"  {out_dir / 'answers_official.yaml'}")
    print(f"  {out_dir / 'todo.yaml'}")


if __name__ == "__main__":
    main()
