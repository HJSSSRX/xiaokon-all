#!/usr/bin/env python3
"""
export_answers.py — 比赛模式答案纯文本导出

从 Hub 或本地 answers.yaml 读取答案，输出纯净 .txt 文件供比赛提交。
答案优先出炉，思考过程赛后复盘。

用法:
  python tools/competition/export_answers.py --output answers.txt
  python tools/competition/export_answers.py --format numbered --flat --output submit.txt
  python -m tools.cli export answers --output answers.txt --format simple

数据源优先级:
  1. Hub GET /answers (默认 http://127.0.0.1:8765)
  2. 本地 {case_dir}/shared/answers.yaml (回退)
"""

import argparse
import io
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

import yaml

CATEGORY_ORDER = [
    "mobile_forensics",
    "computer_forensics",
    "server_forensics",
    "internet_forensics",
    "binary_forensics",
]

CATEGORY_TITLES = {
    "mobile_forensics":   "手机取证",
    "computer_forensics": "计算机取证",
    "server_forensics":   "服务器取证",
    "internet_forensics": "互联网取证",
    "binary_forensics":   "二进制取证",
}

CONFIDENCE_RANK = {
    "platform_confirmed": 100,
    "verified": 90,
    "high": 70,
    "medium": 50,
    "low": 30,
}


def _ensure_utf8_stdout():
    if hasattr(sys.stdout, "buffer"):
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")


def _qid_sort_key(qid: str) -> int:
    """Extract numeric portion from QID for natural sort."""
    try:
        return int(qid.lstrip("Qq"))
    except ValueError:
        return 9999


def fetch_from_hub(hub_url: str, timeout: int = 5):
    """Fetch answers from running Hub. Returns {category: [entries...]} or None."""
    url = f"{hub_url}/answers"
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))
    except (urllib.error.URLError, OSError, json.JSONDecodeError) as e:
        print(f"[!] Hub unreachable ({e})", file=sys.stderr)
        return None


def fetch_from_local(case_dir: Path):
    """Read answers.yaml from local case directory."""
    yaml_path = case_dir / "shared" / "answers.yaml"
    if not yaml_path.exists():
        print(f"[!] Local answers file not found: {yaml_path}", file=sys.stderr)
        return None
    with open(yaml_path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_questions_meta(case_dir: Path):
    """Load questions_meta.yaml for normalization hints. Returns {category_qid: meta} or {}."""
    meta_path = case_dir / "shared" / "questions_meta.yaml"
    if not meta_path.exists():
        return {}
    with open(meta_path, encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}
    # Index by (category, qid)
    indexed = {}
    for cat, items in raw.items():
        if not isinstance(items, list):
            continue
        for item in items:
            qid = item.get("qid", "")
            indexed[(cat, qid)] = item
    return indexed


def normalize_answer(answer: str, ref_format: str) -> str:
    """Lightweight format normalization based on ref_format hint."""
    if not answer or not ref_format:
        return answer
    a = answer.strip()
    fmt = ref_format.lower().strip()
    # date: remove zero-padding on month/day
    if "date" in fmt or "/" in fmt:
        import re
        a = re.sub(r'(\d{4})/0?(\d{1,2})/0?(\d{1,2})', r'\1/\2/\3', a)
    # Remove surrounding quotes
    if (a.startswith('"') and a.endswith('"')) or (a.startswith("'") and a.endswith("'")):
        a = a[1:-1]
    return a


def select_best_answer(entries: list):
    """Select the best answer from multiple submissions for the same QID.
    Priority: platform_confirmed > verified > high > medium > low > unverified > first.
    """
    if not entries:
        return None
    best = None
    best_score = -1
    for entry in entries:
        vs = (entry.get("verification_status") or "unverified").lower()
        conf = (entry.get("confidence") or "").lower()
        if vs == "platform_confirmed":
            score = 100
        elif vs == "verified":
            score = 90
        elif conf in CONFIDENCE_RANK:
            score = CONFIDENCE_RANK[conf]
        else:
            score = 0
        if score > best_score:
            best_score = score
            best = entry
    return best


def collect_answers(data: dict, questions_meta: dict, normalize: bool):
    """Walk all categories, deduplicate per QID, select best answer.
    Returns list of (category, qid, answer_value).
    """
    results = []
    for cat in CATEGORY_ORDER:
        entries = data.get(cat, [])
        if not entries:
            continue
        if not isinstance(entries, list):
            entries = []
        # Group by QID
        by_qid = {}
        for entry in entries:
            qid = entry.get("qid", "")
            if not qid:
                continue
            by_qid.setdefault(qid, []).append(entry)
        # Select best per QID
        for qid in sorted(by_qid.keys(), key=_qid_sort_key):
            best = select_best_answer(by_qid[qid])
            if best is None:
                continue
            answer = best.get("answer", "")
            if answer is None:
                answer = ""
            answer = str(answer).strip()
            if normalize and questions_meta:
                meta = questions_meta.get((cat, qid), {})
                ref = meta.get("ref_format", "")
                if ref:
                    answer = normalize_answer(answer, ref)
            results.append((cat, qid, answer))
    return results


def render_simple_grouped(results):
    """QID: answer, grouped under category headers."""
    out = []
    current_cat = None
    for cat, qid, answer in results:
        if cat != current_cat:
            current_cat = cat
            title = CATEGORY_TITLES.get(cat, cat)
            out.append(f"# {title}")
        out.append(f"{qid}: {answer}")
    return "\n".join(out)


def render_simple_flat(results):
    """Global sequential numbering, no headers."""
    out = []
    for i, (_, qid, answer) in enumerate(results, 1):
        out.append(f"Q{i}: {answer}")
    return "\n".join(out)


def render_numbered_grouped(results):
    """Just answer values, grouped under category headers."""
    out = []
    current_cat = None
    for cat, _, answer in results:
        if cat != current_cat:
            current_cat = cat
            title = CATEGORY_TITLES.get(cat, cat)
            out.append(f"# {title}")
        out.append(answer)
    return "\n".join(out)


def render_numbered_flat(results):
    """Just answer values, one per line, no headers."""
    return "\n".join(answer for _, _, answer in results)


RENDERERS = {
    ("simple", True):   render_simple_grouped,
    ("simple", False):  render_simple_flat,
    ("numbered", True): render_numbered_grouped,
    ("numbered", False): render_numbered_flat,
}


def main():
    ap = argparse.ArgumentParser(
        description="比赛模式答案纯文本导出 — 输出 .txt 供直接提交"
    )
    ap.add_argument("--case-dir", default=None,
                    help="本地 case 目录 (回退时读取 shared/answers.yaml)")
    ap.add_argument("--hub", default="http://127.0.0.1:8765",
                    help="Hub URL (default: http://127.0.0.1:8765)")
    ap.add_argument("--output", "-o", default=None,
                    help="输出文件路径 (不传则打印到 stdout)")
    ap.add_argument("--format", choices=["simple", "numbered"], default="simple",
                    help="simple: Q1: answer / numbered: 纯答案逐行 (default: simple)")
    ap.add_argument("--grouped", action="store_true", default=True,
                    help="按类别分组 (default)")
    ap.add_argument("--flat", action="store_true", default=False,
                    help="全局连续编号，无类别标题")
    ap.add_argument("--normalize", action="store_true", default=False,
                    help="根据 questions_meta.yaml 的 ref_format 规范化答案格式")
    ap.add_argument("--no-local-fallback", action="store_true", default=False,
                    help="Hub 不可达时直接失败，不回退到本地 YAML")
    args = ap.parse_args()

    _ensure_utf8_stdout()
    grouped = not args.flat

    # Resolve data
    data = fetch_from_hub(args.hub)
    if data is None and not args.no_local_fallback:
        case_dir = Path(args.case_dir) if args.case_dir else None
        if case_dir is None:
            # Guess from working directory or default
            case_dir = Path.cwd()
        data = fetch_from_local(case_dir)

    if data is None:
        print("无法获取答案数据。请启动 Hub 或指定 --case-dir。", file=sys.stderr)
        sys.exit(1)

    # Load meta for normalization
    questions_meta = {}
    if args.normalize and args.case_dir:
        questions_meta = load_questions_meta(Path(args.case_dir))

    results = collect_answers(data, questions_meta, args.normalize)

    if not results:
        print("(暂无答案)", file=sys.stderr)
        if args.output:
            Path(args.output).write_text("", encoding="utf-8")
        return

    renderer = RENDERERS.get((args.format, grouped), render_simple_grouped)
    text = renderer(results) + "\n"

    if args.output:
        Path(args.output).write_text(text, encoding="utf-8")
        counts = {}
        for cat, _, _ in results:
            counts[cat] = counts.get(cat, 0) + 1
        summary = ", ".join(f"{CATEGORY_TITLES.get(c, c)}: {n}" for c, n in counts.items())
        print(f"[+] {args.output} — {len(results)} 个答案 ({summary})", file=sys.stderr)
    else:
        sys.stdout.write(text)


if __name__ == "__main__":
    main()
