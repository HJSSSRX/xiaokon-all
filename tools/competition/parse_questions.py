"""
parse_questions.py — C2 方案: 题目解析工具 (独立脚本)

功能:
  将题目内容(markdown 粘贴 或 F12 JSON)解析成结构化数据,输出:
    1. case/shared/questions_meta.yaml   → 供 lint/captain 使用
    2. dashboard QUESTIONS 代码块        → 复制粘贴到 dashboard.html
    3. role_prompt 题目表格              → 复制粘贴到 role_prompt_*.md

支持 3 种输入格式:
  --md   FILE    : Markdown 格式题目 (类似 role_prompt_*.md 或比赛题目页粘贴)
  --json FILE    : 从浏览器 F12 → Network → 复制的 API 响应 JSON
  --paste        : 直接从标准输入读 markdown (比赛现场直接粘贴)

用法:
  # 方式一: markdown 文件
  python tools/parse_questions.py --md my_questions.md --cat mobile_forensics --role mobile_analyst

  # 方式二: 浏览器 F12 复制的 JSON
  python tools/parse_questions.py --json api_response.json --cat server_forensics

  # 方式三: 直接粘贴 (按 Ctrl+Z 或 Ctrl+D 结束)
  python tools/parse_questions.py --paste --cat binary_forensics --role binary_analyst

  # 输出到文件
  python tools/parse_questions.py --md q.md --cat mobile_forensics --out-yaml shared/questions_meta.yaml

Markdown 格式识别规则:
  ### 手机取证-1 (简答, 10分)           ← 标题行 (提取分类/编号/分值)
  题面文本...                             ← 题面
  > 参考格式: HUAWEIP90                  ← 参考格式 (可选)

  或者简单格式:
  **Q1** 该手机型号为？ 参考格式: HUAWEIP90

JSON 格式识别规则 (didctf 常见 response 结构):
  {"data": [{"id": 1, "title": "...", "type": "...", "score": 10, "category": "..."}]}
  或 {"list": [...]} 或直接 [...]
"""
from __future__ import annotations
import argparse
import io
import json
import re
import sys
from pathlib import Path

import yaml

# ─── 常量 ─────────────────────────────────────────────────────────────────────

CATEGORY_ALIASES = {
    "手机取证": "mobile_forensics",
    "mobile": "mobile_forensics",
    "计算机取证": "computer_forensics",
    "computer": "computer_forensics",
    "服务器取证": "server_forensics",
    "server": "server_forensics",
    "互联网取证": "internet_forensics",
    "internet": "internet_forensics",
    "二进制取证": "binary_forensics",
    "binary": "binary_forensics",
    "二进制程序取证": "binary_forensics",
}

CATEGORY_TITLES = {
    "mobile_forensics":   "手机取证",
    "computer_forensics": "计算机取证",
    "server_forensics":   "服务器取证",
    "internet_forensics": "互联网取证",
    "binary_forensics":   "二进制取证",
}

ROLE_FOR_CATEGORY = {
    "mobile_forensics":   "mobile_analyst",
    "computer_forensics": "computer_analyst",
    "server_forensics":   "server_analyst",
    "internet_forensics": "server_analyst",
    "binary_forensics":   "binary_analyst",
}

# ─── Markdown 解析 ────────────────────────────────────────────────────────────

def _detect_category_from_title(title: str) -> str:
    """从标题行 '### 手机取证-1' 里提取分类。"""
    for alias, cat in CATEGORY_ALIASES.items():
        if alias in title:
            return cat
    return ""


def parse_markdown(text: str, default_cat: str = "") -> list[dict]:
    """
    解析 markdown 格式题目文本,返回题目列表:
      [{"qid": "Q1", "text": "...", "ref_format": "...", "score": 10, "type": "..."}]
    """
    items = []
    lines = text.splitlines()
    i = 0
    current_cat = default_cat

    # 匹配题目标题的各种格式
    TITLE_PATTERNS = [
        # "### 手机取证-1（简答，10分）" / "### 手机取证-1(简答,10分)"
        re.compile(
            r"^#{1,4}\s+"
            r"(?P<cat>[^\-—\d#]+)"   # 分类名
            r"[-—]\s*(?P<num>\d+)"   # 题号
            r"(?:[（(][^）)]*[）)])?" # 题型/分值 (可选)
        ),
        # "**Q1** 题目..." 或 "Q1. 题目..."
        re.compile(r"^(?:\*\*)?(?P<qid>Q\d+)(?:\*\*)?\s*[.。\s]"),
        # "1. 题目..."  或  "（1）题目..."
        re.compile(r"^[（(]?(?P<num>\d+)[）).][\s）]"),
    ]

    REF_PATTERN = re.compile(
        r"参考格式[：:]\s*`?([^`\n]+)`?"
        r"|[>＞]\s*参考格式[：:]\s*`?([^`\n]+)`?"
        r"|答案格式[：:]\s*`?([^`\n]+)`?",
        re.IGNORECASE,
    )

    SCORE_PATTERN = re.compile(r"(\d+)\s*分")
    TYPE_PATTERN  = re.compile(r"(简答|多选|单选|判断|填空)")

    def flush(cur):
        if not cur:
            return
        cur["text"] = cur.get("text", "").strip()
        if cur["text"]:
            items.append(cur)

    current: dict | None = None

    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        # 尝试所有标题格式
        matched = False
        for pat in TITLE_PATTERNS:
            m = pat.match(stripped)
            if not m:
                continue

            # 提取信息
            groups = m.groupdict()
            cat_str = groups.get("cat", "").strip()
            num_str = groups.get("num") or groups.get("qid", "").lstrip("Qq")
            if groups.get("qid"):
                qid = groups["qid"].upper()
            elif num_str:
                qid = f"Q{int(num_str)}"
            else:
                break

            if cat_str:
                for alias, cat in CATEGORY_ALIASES.items():
                    if alias in cat_str:
                        current_cat = cat
                        break

            score_m = SCORE_PATTERN.search(stripped)
            type_m  = TYPE_PATTERN.search(stripped)

            flush(current)
            current = {
                "qid":        qid,
                "cat":        current_cat,
                "text":       "",
                "ref_format": "",
                "score":      int(score_m.group(1)) if score_m else 10,
                "type":       type_m.group(1) if type_m else "简答",
            }
            matched = True
            break

        if not matched and current is not None:
            # 检查参考格式
            ref_m = REF_PATTERN.search(stripped)
            if ref_m:
                current["ref_format"] = (
                    ref_m.group(1) or ref_m.group(2) or ref_m.group(3) or ""
                ).strip().strip("`").strip()
            elif stripped and not stripped.startswith("#") and not stripped.startswith("---"):
                # 追加题面
                sep = "\n" if current["text"] else ""
                current["text"] = current["text"] + sep + stripped

        i += 1

    flush(current)
    return items


# ─── JSON 解析 ────────────────────────────────────────────────────────────────

def parse_json(data, default_cat: str = "") -> list[dict]:
    """
    解析 didctf / 各种比赛平台的 JSON 响应,返回统一题目列表。
    尝试多种字段名猜测: title/question/name, answer_format/ref/format...
    """
    # 找到题目数组
    question_list = None
    if isinstance(data, list):
        question_list = data
    elif isinstance(data, dict):
        for key in ("data", "list", "questions", "items", "result", "rows"):
            if isinstance(data.get(key), list):
                question_list = data[key]
                break
        if question_list is None:
            # 可能嵌套了一层 {"data": {"list": [...]}}
            for key in ("data", "result"):
                sub = data.get(key)
                if isinstance(sub, dict):
                    for inner in ("list", "questions", "items", "rows"):
                        if isinstance(sub.get(inner), list):
                            question_list = sub[inner]
                            break
                if question_list:
                    break

    if not question_list:
        print("[parse_json] 找不到题目数组, 尝试把整个 JSON 当做一个题目...", file=sys.stderr)
        question_list = [data] if isinstance(data, dict) else []

    items = []
    for idx, q in enumerate(question_list):
        if not isinstance(q, dict):
            continue

        # qid
        num = q.get("id") or q.get("num") or q.get("order") or (idx + 1)
        qid_raw = q.get("qid") or q.get("question_id") or ""
        qid = qid_raw if qid_raw else f"Q{int(num)}"

        # 题面
        text = (
            q.get("title") or q.get("question") or q.get("name")
            or q.get("content") or q.get("body") or ""
        ).strip()

        # 参考格式
        ref_format = (
            q.get("answer_format") or q.get("ref_format") or q.get("format")
            or q.get("reference") or q.get("hint") or q.get("demo") or ""
        ).strip()

        # 分类
        cat_raw = (
            q.get("category") or q.get("type_name") or q.get("tag")
            or q.get("chapter") or q.get("module") or ""
        ).lower()
        cat = CATEGORY_ALIASES.get(cat_raw, "") or default_cat

        # 分值 / 题型
        score = q.get("score") or q.get("point") or q.get("points") or 10
        q_type = q.get("type") or q.get("question_type") or "简答"

        items.append({
            "qid": qid, "cat": cat, "text": text,
            "ref_format": ref_format, "score": int(score), "type": str(q_type),
        })

    return items


# ─── 输出生成 ─────────────────────────────────────────────────────────────────

def group_by_cat(items: list[dict]) -> dict[str, list[dict]]:
    grouped: dict[str, list[dict]] = {}
    for item in items:
        cat = item.get("cat") or "unknown"
        grouped.setdefault(cat, []).append(item)
    return grouped


def gen_questions_meta_yaml(grouped: dict) -> str:
    """生成 questions_meta.yaml 内容。"""
    out = {}
    for cat, items in grouped.items():
        out[cat] = [
            {
                "qid": it["qid"],
                "text": it["text"][:120],
                "ref_format": it.get("ref_format", ""),
                "score": it.get("score", 10),
                "type": it.get("type", "简答"),
            }
            for it in items
        ]
    return yaml.dump(out, allow_unicode=True, sort_keys=False, default_flow_style=False)


def gen_dashboard_questions_js(grouped: dict) -> str:
    """生成 dashboard.html 的 QUESTIONS 常量代码块。"""
    lines = ["const QUESTIONS = {"]
    for cat, items in grouped.items():
        title = CATEGORY_TITLES.get(cat, cat)
        owner = ROLE_FOR_CATEGORY.get(cat, "")
        lines.append(f"  {cat}: {{")
        lines.append(f'    title: "{title}", owner: "{owner}",')
        lines.append("    items: [")
        for it in items:
            text_short = it["text"][:40].replace('"', '\\"')
            ref = it.get("ref_format", "")
            ref_comment = f'  // 格式: {ref}' if ref else ""
            lines.append(f'      ["{it["qid"]}", "{text_short}"],{ref_comment}')
        lines.append("    ],")
        lines.append("  },")
    lines.append("};")
    return "\n".join(lines)


def gen_role_prompt_table(grouped: dict) -> str:
    """生成 role_prompt 题目表格 (Markdown)。"""
    parts = []
    for cat, items in grouped.items():
        title = CATEGORY_TITLES.get(cat, cat)
        parts.append(f"### {title}")
        parts.append("")
        parts.append("| # | 题面 | 答案格式 |")
        parts.append("|---|---|---|")
        for it in items:
            ref = it.get("ref_format") or ""
            text = it["text"].replace("|", "\\|").replace("\n", " ")[:60]
            parts.append(f"| {it['qid']} | {text} | {ref} |")
        parts.append("")
    return "\n".join(parts)


# ─── 主函数 ───────────────────────────────────────────────────────────────────

def main():
    if hasattr(sys.stdout, "buffer"):
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    p = argparse.ArgumentParser(description="题目解析工具 (C2 方案)")
    src = p.add_mutually_exclusive_group()
    src.add_argument("--md",    help="Markdown 题目文件路径")
    src.add_argument("--json",  help="API JSON 响应文件路径 (F12 复制)")
    src.add_argument("--paste", action="store_true", help="从 stdin 粘贴 markdown")
    p.add_argument("--cat",     default="", help="默认分类 (如 mobile_forensics)")
    p.add_argument("--role",    default="", help="默认角色 (如 mobile_analyst)")
    p.add_argument("--case",    default=r"E:\ffffff-JIANCAI\2026FIC团体赛\case", help="case 目录")
    p.add_argument("--out-yaml",default="", help="输出 questions_meta.yaml 路径 (留空=打印)")
    p.add_argument("--no-js",   action="store_true", help="不输出 JS 代码块")
    p.add_argument("--no-table",action="store_true", help="不输出 Markdown 表格")
    args = p.parse_args()

    # 读取输入
    text_raw = ""
    json_raw = None

    if args.paste or (not args.md and not args.json):
        if args.paste:
            print("请粘贴题目内容 (Markdown 格式), 然后按 Ctrl+Z (Windows) 或 Ctrl+D 结束:", file=sys.stderr)
        text_raw = sys.stdin.read()
    elif args.md:
        text_raw = Path(args.md).read_text(encoding="utf-8")
    elif args.json:
        with open(args.json, encoding="utf-8") as f:
            json_raw = json.load(f)

    # 解析
    if json_raw is not None:
        items = parse_json(json_raw, default_cat=args.cat)
    else:
        items = parse_markdown(text_raw, default_cat=args.cat)

    if not items:
        print("[ERROR] 未解析出任何题目。请检查输入格式。", file=sys.stderr)
        sys.exit(1)

    print(f"[INFO] 解析到 {len(items)} 题", file=sys.stderr)

    # 按分类分组
    grouped = group_by_cat(items)

    # ── 1. questions_meta.yaml ──
    meta_yaml = gen_questions_meta_yaml(grouped)
    if args.out_yaml:
        out_path = Path(args.out_yaml)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(meta_yaml, encoding="utf-8")
        print(f"[INFO] 已写入 {out_path}", file=sys.stderr)
    else:
        # 自动写到 case/shared/questions_meta.yaml
        auto_path = Path(args.case) / "shared" / "questions_meta.yaml"
        if auto_path.parent.exists():
            auto_path.write_text(meta_yaml, encoding="utf-8")
            print(f"[INFO] 已写入 {auto_path}", file=sys.stderr)

    # ── 2. dashboard QUESTIONS JS ──
    if not args.no_js:
        print()
        print("=" * 70)
        print("【复制以下代码块 → 粘贴到 dashboard.html 的 QUESTIONS 位置】")
        print("=" * 70)
        print(gen_dashboard_questions_js(grouped))

    # ── 3. role_prompt 题目表格 ──
    if not args.no_table:
        print()
        print("=" * 70)
        print("【复制以下内容 → 粘贴到 role_prompt_*.md 的题目表格位置】")
        print("=" * 70)
        print(gen_role_prompt_table(grouped))

    # ── 4. 汇总统计 ──
    print()
    print("=" * 70)
    print("【题目汇总】")
    print("=" * 70)
    for cat, cat_items in grouped.items():
        with_fmt = sum(1 for it in cat_items if it.get("ref_format"))
        print(f"  {CATEGORY_TITLES.get(cat, cat):10s} {len(cat_items):2d} 题  (含参考格式: {with_fmt} 题)")
    missing = [it for it in items if not it.get("ref_format")]
    if missing:
        print(f"\n  ⚠️  {len(missing)} 题缺少参考格式 (lint 无法校验):")
        for it in missing[:10]:
            print(f"     {it['qid']}: {it['text'][:50]}")


if __name__ == "__main__":
    main()
