#!/usr/bin/env python3
"""
2026FIC 取证知识库检索工具

用法:
    python tools/fic_kb_search.py --keywords 推广设计图 apk
    python tools/fic_kb_search.py --question "服务器上怎么查 IP 字段"
    python tools/fic_kb_search.py --category server
    python tools/fic_kb_search.py --result incorrect    # 只看错题
    python tools/fic_kb_search.py --tech rsa            # 找 rsa 相关技巧卡
    python tools/fic_kb_search.py --all                 # 列出全部

输出: 排名前 N 的相关 problems / techniques / retrospectives
"""
from __future__ import annotations
import argparse
import os
import re
import sys
from pathlib import Path

# Windows GBK console fix — must run before any print() with non-ASCII content
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

try:
    import yaml
except ImportError:
    print("请先 pip install pyyaml", file=sys.stderr)
    sys.exit(1)

REPO_ROOT = Path(__file__).resolve().parent.parent

# KB_ROOT is resolved at runtime via resolve_kb_root().
# Initially None — set in main() / by tests via set_kb_root().
KB_ROOT: Path | None = None


def resolve_kb_root(cli_arg: str | None = None) -> Path | None:
    """Find the FIC knowledge base directory.

    Search order (first hit wins):
      1. --kb-dir CLI arg
      2. $AUTOFORENSICAI_KB env var
      3. <repo>/cases/2026FIC-*/case/shared/knowledge_base
      4. <repo>/cases/2026fic*/knowledge_base
      5. <repo>/data/kb
      6. legacy hardcoded E:\\ffffff-JIANCAI\\... (only on machine that owns it)
    Returns None if nothing found.
    """
    candidates: list[Path] = []
    if cli_arg:
        candidates.append(Path(cli_arg))
    env = os.environ.get("AUTOFORENSICAI_KB")
    if env:
        candidates.append(Path(env))
    # Auto-discover under cases/
    cases_dir = REPO_ROOT / "cases"
    if cases_dir.is_dir():
        for sub in cases_dir.glob("2026FIC*/case/shared/knowledge_base"):
            candidates.append(sub)
        for sub in cases_dir.glob("2026fic*/knowledge_base"):
            candidates.append(sub)
        for sub in cases_dir.glob("*/knowledge_base"):
            candidates.append(sub)
    candidates.append(REPO_ROOT / "data" / "kb")
    # Legacy hardcoded path (only valid on A_main)
    candidates.append(Path(r"E:\ffffff-JIANCAI\2026FIC团体赛\case\shared\knowledge_base"))

    for c in candidates:
        if c.exists() and (c / "problems").exists():
            return c
    return None


def set_kb_root(path: Path) -> None:
    """Test/programmatic override."""
    global KB_ROOT
    KB_ROOT = path


def load_problems():
    """加载所有题目卡"""
    problems = []
    pdir = KB_ROOT / "problems"
    if not pdir.exists():
        return problems
    for f in pdir.rglob("*.yaml"):
        try:
            data = yaml.safe_load(f.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                data["_path"] = f
                problems.append(data)
        except Exception as e:
            print(f"⚠ 解析失败 {f}: {e}", file=sys.stderr)
    return problems


def load_techniques():
    """加载所有技巧卡"""
    techs = []
    tdir = KB_ROOT / "techniques"
    if not tdir.exists():
        return techs
    for f in tdir.rglob("*.yaml"):
        try:
            data = yaml.safe_load(f.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                data["_path"] = f
                techs.append(data)
        except Exception as e:
            print(f"⚠ 解析失败 {f}: {e}", file=sys.stderr)
    return techs


def load_retrospectives():
    """加载所有经验卡"""
    retros = []
    rdir = KB_ROOT / "retrospectives"
    if not rdir.exists():
        return retros
    for f in rdir.rglob("*.yaml"):
        try:
            data = yaml.safe_load(f.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                data["_path"] = f
                retros.append(data)
        except Exception as e:
            print(f"⚠ 解析失败 {f}: {e}", file=sys.stderr)
    return retros


def score_match(item: dict, keywords: list[str]) -> int:
    """简单关键词打分: keyword 命中 keywords 字段 +3, 其他字段 +1"""
    score = 0
    item_kw_str = " ".join(str(x) for x in (item.get("keywords") or []))
    # 排除 _path (WindowsPath 不可 yaml 序列化), 用 dict→str 取全文
    safe_item = {k: v for k, v in item.items() if not k.startswith("_")}
    try:
        full_text = yaml.safe_dump(safe_item, allow_unicode=True, sort_keys=False, default_flow_style=False)
    except Exception:
        full_text = str(safe_item)
    for kw in keywords:
        kw_lower = kw.lower()
        # keywords 字段 (高权重)
        if kw_lower in item_kw_str.lower():
            score += 5
        # question / name 字段
        if kw_lower in str(item.get("question", "")).lower():
            score += 3
        if kw_lower in str(item.get("name", "")).lower():
            score += 3
        # 全文
        score += full_text.lower().count(kw_lower)
    return score


def fmt_problem(p: dict, score: int) -> str:
    qid = p.get("qid", "?")
    cat = p.get("category", "?")
    qno = p.get("question_no", "?")
    result = p.get("result", "?")
    icon = {"correct": "✅", "incorrect": "❌", "not_answered": "⚪"}.get(result, "?")
    q = (p.get("question") or "").split("【")[0][:50]
    method = p.get("method_summary") or ""
    lines = [
        f"  [{score} pts] {icon} {qid} ({cat} Q{qno}): {q}",
        f"      官方答: {p.get('official_answer', '')}",
        f"      我们答: {p.get('our_actual_answer', '')}",
    ]
    if method:
        lines.append(f"      方法: {method}")
    if p.get("lessons"):
        lines.append(f"      教训: {p['lessons'][0] if p['lessons'] else ''}")
    return "\n".join(lines)


def fmt_technique(t: dict, score: int) -> str:
    name = t.get("name", t.get("slug", "?"))
    cat = t.get("category", "?")
    seen = ", ".join(t.get("seen_in") or [])
    lines = [
        f"  [{score} pts] 🔧 {name} ({cat})",
        f"      slug: {t.get('slug')}",
        f"      用于: {seen[:60] + '...' if len(seen) > 60 else seen}",
    ]
    when = t.get("when_to_use") or []
    if when:
        lines.append(f"      时机: {when[0]}")
    return "\n".join(lines)


def fmt_retro(r: dict, score: int) -> str:
    role = r.get("role", "?")
    topic = r.get("topic", "?")
    return f"  [{score} pts] 💡 {role} | {topic}"


def cmd_keywords(args):
    keywords = args.keywords
    problems = load_problems()
    techs = load_techniques()
    retros = load_retrospectives()

    p_results = sorted([(score_match(p, keywords), p) for p in problems], key=lambda x: -x[0])
    t_results = sorted([(score_match(t, keywords), t) for t in techs], key=lambda x: -x[0])
    r_results = sorted([(score_match(r, keywords), r) for r in retros], key=lambda x: -x[0])

    p_results = [(s, p) for s, p in p_results if s > 0][: args.top]
    t_results = [(s, t) for s, t in t_results if s > 0][: args.top]
    r_results = [(s, r) for s, r in r_results if s > 0][: args.top]

    print(f"\n=== 关键词检索: {keywords} ===\n")

    if p_results:
        print(f"📋 题目卡 ({len(p_results)}):")
        for s, p in p_results:
            print(fmt_problem(p, s))
            print()
    else:
        print("📋 题目卡: 无命中")

    if t_results:
        print(f"\n🔧 技巧卡 ({len(t_results)}):")
        for s, t in t_results:
            print(fmt_technique(t, s))
            print()
    else:
        print("\n🔧 技巧卡: 无命中")

    if r_results:
        print(f"\n💡 经验卡 ({len(r_results)}):")
        for s, r in r_results:
            print(fmt_retro(r, s))
    else:
        print("\n💡 经验卡: 无 (远程机暂未上传)")


def cmd_question(args):
    """从自然语言问题提取关键词检索"""
    text = args.question
    # 提取中文/英文/数字
    cn = re.findall(r"[\u4e00-\u9fff]{2,}", text)
    en = re.findall(r"[A-Za-z][A-Za-z0-9_]{1,}", text)
    keywords = list(dict.fromkeys(cn + en))
    print(f"提取关键词: {keywords}")
    args.keywords = keywords
    cmd_keywords(args)


def cmd_category(args):
    problems = [p for p in load_problems() if p.get("category", "").startswith(args.category)]
    print(f"\n=== 分类 {args.category}: {len(problems)} 题 ===\n")
    for p in sorted(problems, key=lambda x: x.get("question_no", 0)):
        print(fmt_problem(p, 0))
        print()


def cmd_result(args):
    """按结果筛选 (incorrect/correct/not_answered)"""
    problems = [p for p in load_problems() if p.get("result") == args.result]
    print(f"\n=== 结果={args.result}: {len(problems)} 题 ===\n")
    for p in sorted(problems, key=lambda x: (x.get("category", ""), x.get("question_no", 0))):
        print(fmt_problem(p, 0))
        print()


def cmd_tech(args):
    """搜技巧卡 (按 slug/name 模糊匹配)"""
    techs = load_techniques()
    matches = [t for t in techs if args.tech.lower() in (t.get("slug", "") + t.get("name", "")).lower()]
    print(f"\n=== 技巧卡匹配 '{args.tech}': {len(matches)} 张 ===\n")
    for t in matches:
        print(fmt_technique(t, 0))
        print(f"      路径: {t.get('_path')}")
        print()


def cmd_all(args):
    problems = load_problems()
    techs = load_techniques()
    retros = load_retrospectives()
    print(f"\n=== 知识库总览 ===\n")
    print(f"📋 题目卡: {len(problems)}")
    by_cat = {}
    by_result = {"correct": 0, "incorrect": 0, "not_answered": 0, "unknown": 0}
    for p in problems:
        by_cat[p.get("category", "?")] = by_cat.get(p.get("category", "?"), 0) + 1
        by_result[p.get("result", "unknown")] = by_result.get(p.get("result", "unknown"), 0) + 1
    for cat, n in sorted(by_cat.items()):
        print(f"   {cat}: {n}")
    print(f"   结果: ✅ {by_result.get('correct',0)} / ❌ {by_result.get('incorrect',0)} / ⚪ {by_result.get('not_answered',0)}")
    print(f"\n🔧 技巧卡: {len(techs)}")
    for t in sorted(techs, key=lambda x: x.get("slug", "")):
        print(f"   - {t.get('slug', '?')}: {t.get('name', '?')}")
    print(f"\n💡 经验卡: {len(retros)}")
    for r in retros:
        print(f"   - {r.get('role')}: {r.get('topic')}")


def main():
    p = argparse.ArgumentParser(description="2026FIC 知识库检索")
    sub = p.add_subparsers(dest="cmd", required=False)

    p_kw = sub.add_parser("keywords", help="按关键词检索")
    p_kw.add_argument("keywords", nargs="+")
    p_kw.add_argument("--top", type=int, default=5)
    p_kw.set_defaults(func=cmd_keywords)

    p_q = sub.add_parser("question", help="自然语言问题")
    p_q.add_argument("question")
    p_q.add_argument("--top", type=int, default=5)
    p_q.set_defaults(func=cmd_question)

    p_cat = sub.add_parser("category", help="按分类列题")
    p_cat.add_argument("category", choices=["computer", "mobile", "server", "internet", "binary"])
    p_cat.set_defaults(func=cmd_category)

    p_res = sub.add_parser("result", help="按结果筛选")
    p_res.add_argument("result", choices=["correct", "incorrect", "not_answered"])
    p_res.set_defaults(func=cmd_result)

    p_tech = sub.add_parser("tech", help="找技巧卡")
    p_tech.add_argument("tech")
    p_tech.set_defaults(func=cmd_tech)

    p_all = sub.add_parser("all", help="全库总览")
    p_all.set_defaults(func=cmd_all)

    # 简化别名: --keywords / --question / --all
    p.add_argument("--keywords", nargs="+", help="同 keywords 子命令")
    p.add_argument("--question", help="同 question 子命令")
    p.add_argument("--category", choices=["computer", "mobile", "server", "internet", "binary"])
    p.add_argument("--result", choices=["correct", "incorrect", "not_answered"])
    p.add_argument("--tech", help="同 tech 子命令")
    p.add_argument("--all", action="store_true")
    p.add_argument("--top", type=int, default=5)
    p.add_argument("--kb-dir", help="KB 根目录 (默认: 自动检测; 也可设 $AUTOFORENSICAI_KB)")

    args = p.parse_args()

    # Resolve KB_ROOT before any data load
    kb = resolve_kb_root(getattr(args, "kb_dir", None))
    if kb is None:
        print("[fic_kb_search] 找不到 KB 根目录. 候选搜索路径全部失败.", file=sys.stderr)
        print("  解决: 用 --kb-dir <path> 或 export AUTOFORENSICAI_KB=<path>", file=sys.stderr)
        print("  典型 KB 长这样: <kb>/problems/<category>/*.yaml", file=sys.stderr)
        sys.exit(2)
    set_kb_root(kb)

    # 兼容: 旧式 --xxx 调用
    if args.cmd is None:
        if args.all:
            cmd_all(args)
        elif args.keywords:
            cmd_keywords(args)
        elif args.question:
            cmd_question(args)
        elif args.category:
            cmd_category(args)
        elif args.result:
            cmd_result(args)
        elif args.tech:
            cmd_tech(args)
        else:
            p.print_help()
    else:
        args.func(args)


if __name__ == "__main__":
    main()
