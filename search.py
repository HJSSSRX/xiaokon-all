#!/usr/bin/env python3
"""
[DEPRECATED] Use `python tools/kb_search.py` instead — it has YAML solution support,
broader term aliases, consultant mode, and is the actively maintained version.

This standalone copy is kept for reference only.

Usage:
    python search.py --ask "内存取证怎么查可疑进程"
    python search.py --tags memory_forensics volatility
    python search.py --tools vol3 strings
    python search.py --text "reverse shell"
    python search.py --category computer_forensics
    python search.py --list                          # list all entries
"""
import argparse
import os
import re
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    print("需要 pyyaml: pip install pyyaml")
    sys.exit(1)

KB_DIR = Path(__file__).parent / "knowledge"

# Chinese → English aliases for --ask mode
ALIASES = {
    "内存": ["memory_forensics", "volatility", "memory"],
    "取证": ["forensics", "disk_forensics"],
    "注册表": ["registry", "regedit", "windows_registry"],
    "磁盘": ["disk_forensics", "disk", "ntfs", "ext4"],
    "手机": ["mobile", "android", "ios"],
    "微信": ["wechat"],
    "流量": ["pcap", "traffic", "wireshark", "tshark"],
    "蓝牙": ["bluetooth", "ble"],
    "服务器": ["server", "linux"],
    "隐写": ["steganography", "stego", "lsb"],
    "密码": ["password", "hash", "crack", "aes", "xor"],
    "逆向": ["reverse", "exe_reverse", "apk_reverse"],
    "注入": ["sql_injection", "injection"],
    "webshell": ["webshell", "webshell_traffic"],
    "挂载": ["mount", "e01", "vmdk", "disk_image"],
    "日志": ["event_log", "log"],
    "浏览器": ["browser", "chrome", "firefox"],
    "进程": ["process", "pslist", "pstree"],
}


def parse_frontmatter(path):
    """Extract YAML frontmatter from a markdown file."""
    try:
        text = path.read_text(encoding="utf-8")
    except Exception:
        return None, ""
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n", text, re.DOTALL)
    if not m:
        return {}, text
    try:
        meta = yaml.safe_load(m.group(1)) or {}
    except Exception:
        meta = {}
    body = text[m.end():]
    return meta, body


def scan_kb():
    """Scan all markdown files in knowledge/."""
    entries = []
    for md in sorted(KB_DIR.rglob("*.md")):
        meta, body = parse_frontmatter(md)
        if meta is None:
            continue
        rel = md.relative_to(KB_DIR)
        entries.append({
            "path": str(rel),
            "meta": meta,
            "body": body,
            "full": (str(meta) + " " + body).lower(),
        })
    return entries


def expand_query(query):
    """Expand Chinese query into search terms using aliases."""
    terms = set()
    words = re.findall(r"[\w]+", query.lower())
    for w in words:
        terms.add(w)
        for cn, en_list in ALIASES.items():
            if cn in query or w in en_list:
                terms.update(en_list)
    return terms


def score_entry(entry, tags=None, tools=None, text=None, category=None, ask_terms=None):
    s = 0
    meta = entry["meta"]
    e_tags = [t.lower() for t in (meta.get("tags") or [])]
    e_tools = [t.lower() for t in (meta.get("tools") or [])]
    e_cat = (meta.get("category") or "").lower()

    if tags:
        for t in tags:
            if t.lower() in e_tags:
                s += 10
    if tools:
        for t in tools:
            if t.lower() in e_tools:
                s += 10
    if category:
        if category.lower() == e_cat:
            s += 15
    if text:
        for t in text:
            if t.lower() in entry["full"]:
                s += 5
    if ask_terms:
        for t in ask_terms:
            if t in e_tags:
                s += 8
            elif t in e_tools:
                s += 8
            elif t in entry["full"]:
                s += 3
    return s


def display(results, verbose=False):
    if not results:
        print("未找到匹配结果。")
        return
    for r in results[:15]:
        meta = r["meta"]
        tags = ", ".join(meta.get("tags", [])[:5])
        tools = ", ".join(meta.get("tools", [])[:5])
        diff = meta.get("difficulty", "")
        print(f"\n{'='*60}")
        print(f"📄 {r['path']}  (score: {r['score']})")
        if tags:
            print(f"   Tags:  {tags}")
        if tools:
            print(f"   Tools: {tools}")
        if diff:
            print(f"   Difficulty: {diff}")

        # Show first few lines of Solution Steps
        if verbose:
            lines = r["body"].split("\n")
            in_solution = False
            shown = 0
            for line in lines:
                if "## Solution" in line or "## solution" in line:
                    in_solution = True
                    continue
                if in_solution:
                    if line.startswith("## "):
                        break
                    if line.strip():
                        print(f"   {line.strip()}")
                        shown += 1
                        if shown >= 5:
                            print("   ...")
                            break

    print(f"\n共 {len(results)} 条结果（显示前 {min(15, len(results))} 条）")


def main():
    p = argparse.ArgumentParser(description="Forensics Knowledge Base Search")
    p.add_argument("--ask", help="Natural language query (中英文)")
    p.add_argument("--tags", nargs="+", help="Filter by tags")
    p.add_argument("--tools", nargs="+", help="Filter by tools")
    p.add_argument("--text", nargs="+", help="Full-text search terms")
    p.add_argument("--category", help="Filter by category")
    p.add_argument("--list", action="store_true", help="List all entries")
    p.add_argument("-v", "--verbose", action="store_true", help="Show solution steps")
    args = p.parse_args()

    if not any([args.ask, args.tags, args.tools, args.text, args.category, args.list]):
        p.print_help()
        return

    entries = scan_kb()
    print(f"知识库: {len(entries)} 篇文档")

    if args.list:
        for e in entries:
            meta = e["meta"]
            tags = ", ".join((meta.get("tags") or [])[:3])
            print(f"  {e['path']:50s} [{tags}]")
        return

    ask_terms = None
    if args.ask:
        ask_terms = expand_query(args.ask)

    results = []
    for e in entries:
        s = score_entry(e, args.tags, args.tools, args.text, args.category, ask_terms)
        if s > 0:
            e["score"] = s
            results.append(e)

    results.sort(key=lambda x: x["score"], reverse=True)
    display(results, args.verbose)


if __name__ == "__main__":
    main()
