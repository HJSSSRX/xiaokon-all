#!/usr/bin/env python3
"""CLI entry point for collaboration sync — post, status, answers, git, LAN, conflicts, progressive sync."""

import argparse
import datetime
import urllib.request
from pathlib import Path

from ..core import now_str, load_yaml, load_yaml_str, save_yaml, shared_dir
from .conflict import detect_duplicates, resolve_duplicate, compare_versions
from .git_sync import cmd_git_init, cmd_git_push, cmd_git_pull
from .hub_ids import next_finding_id
from .lan_sync import cmd_lan_serve, cmd_lan_pull, cmd_lan_push
from .progressive import progressive_sync


# ─── Post / Status / Answers ───

def cmd_post(args):
    sd = shared_dir(args.case_dir)
    findings_path = sd / "findings.yaml"
    findings = load_yaml(findings_path)

    entry = {
        "id": next_finding_id(findings, args.sender),
        "time": now_str(),
        "from": args.sender,
        "summary": args.summary,
        "detail": args.detail or "",
        "related_to": [r.strip() for r in args.related.split(",")] if args.related else [],
    }
    findings.append(entry)
    save_yaml(findings_path, findings)
    print(f"[+] Posted {entry['id']}: {entry['summary']}")
    return entry


def cmd_status(args):
    sd = shared_dir(args.case_dir)

    findings = load_yaml(sd / "findings.yaml")
    print(f"\n=== Findings: {len(findings)} ===")
    for f in findings[-10:]:
        print(f"  {f.get('id','?')} [{f.get('from','?')}] {f.get('summary','')}")

    progress = load_yaml(sd / "progress.yaml")
    if isinstance(progress, dict):
        print(f"\n=== Progress ===")
        for role, status in progress.items():
            if isinstance(status, dict):
                print(f"  {role:20s} {status.get('status', '?')}: {status.get('current_task', '')}")

    answers_path = sd / "answers.yaml"
    if answers_path.exists():
        answers = load_yaml(answers_path)
        total = sum(len(items) for items in answers.values()) if isinstance(answers, dict) else len(answers)
        print(f"\n=== Answers: {total} ===")


def cmd_answers(args):
    sd = shared_dir(args.case_dir)
    answers_path = sd / "answers.yaml"
    answers = load_yaml(answers_path)

    if not answers:
        print("No answers yet.")
        return

    if isinstance(answers, dict):
        all_answers = []
        for category, items in answers.items():
            for item in items:
                if isinstance(item, dict):
                    item["category"] = category
                    all_answers.append(item)
    else:
        all_answers = answers

    print(f"\n{'#':<5} {'Category':<12} {'Summary':<30} {'Answer':<25} {'Status':<8} {'Source':<10}")
    print("-" * 90)
    for a in all_answers:
        if not isinstance(a, dict):
            continue
        status = "OK" if a.get("answer") else "??"
        print(f"{a.get('qid','?'):<5} {a.get('category',''):<12} {a.get('question','')[:28]:<30} {str(a.get('answer',''))[:23]:<25} {status:<8} {a.get('source_role','')[:10]:<10}")


# ─── Conflict CLI wrappers ───

def cmd_detect_duplicates(args):
    result = detect_duplicates(args.case_dir)
    print(f"\n=== Duplicate Detection Results ===")
    print(f"Checked {result['checked']} records")
    print(f"Found {result['total']} duplicate groups")

    if result["duplicates"]:
        for i, group in enumerate(result["duplicates"], 1):
            print(f"\n[{i}] Hash: {group['hash']}")
            print(f"  Count: {group['count']}")
            for item in group["items"]:
                print(f"    - {item.get('id', '?')} [{item.get('time', '')}] {item.get('summary', '')[:50]}...")


def cmd_resolve_conflict(args):
    sd = shared_dir(args.case_dir)
    findings_path = sd / "findings.yaml"
    findings = load_yaml(findings_path)

    result = resolve_duplicate(findings, args.id, args.keep)

    if result["status"] == "resolved":
        save_yaml(findings_path, findings)
        print(f"\n=== Conflict Resolved ===")
        print(f"Kept: {result['kept'].get('id', '?')} - {result['kept'].get('summary', '')[:50]}")
        print(f"Removed: {result['removed']} duplicates")
        print(f"Remaining: {result['remaining_count']}")
    else:
        print(f"\n{result['status'].upper()}: {result['message']}")


def cmd_version_compare(args):
    sd = shared_dir(args.case_dir)
    local_path = sd / args.file

    if not local_path.exists():
        print(f"Error: file {args.file} not found")
        return

    local_items = load_yaml(local_path)

    if args.server:
        server = args.server.rstrip("/")
        if not server.startswith("http"):
            server = f"http://{server}"

        try:
            url = f"{server}/{args.file}"
            data = urllib.request.urlopen(url, timeout=5).read()
            remote_items = load_yaml_str(data, [])
        except Exception as e:
            print(f"Cannot connect to server: {e}")
            return
    else:
        print("Need --server parameter")
        return

    comparison = compare_versions(local_items, remote_items)

    print(f"\n=== Version Compare: {args.file} ===")
    print(f"Local: {comparison['local_count']} items")
    print(f"Remote: {comparison['remote_count']} items")
    print(f"\nAdded (remote has, local missing): {len(comparison['added'])}")
    print(f"Removed (local has, remote missing): {len(comparison['removed'])}")
    print(f"Modified: {len(comparison['modified'])}")


def cmd_sync(args):
    if args.mode == "lan" and not args.server:
        print("LAN mode requires --server parameter")
        return

    result = progressive_sync(args.case_dir, args.server, args.mode)

    print(f"\n=== Progressive Sync Results ===")
    for r in result["results"]:
        icon = "+" if r["status"] == "success" else "!"
        skipped = "(skipped: recently synced)" if r.get("skipped") else ""
        print(f"  [{icon}] [P{r['priority']}] {r['file']}: {r['status']} {skipped}")

    print(f"\nSummary: {result['summary']['success']} success, {result['summary']['failed']} failed, {result['summary']['skipped']} skipped")


# ─── Main ───

def main():
    parser = argparse.ArgumentParser(description="AutoForensicAI Collaboration Sync")
    sub = parser.add_subparsers(dest="command")

    p = sub.add_parser("post", help="Post a finding")
    p.add_argument("case_dir")
    p.add_argument("--from", dest="sender", required=True, help="Role name")
    p.add_argument("--summary", required=True)
    p.add_argument("--detail", default="")
    p.add_argument("--related", default="", help="Comma-separated role names")

    p = sub.add_parser("status", help="Show collaboration status")
    p.add_argument("case_dir")

    p = sub.add_parser("answers", help="Show answers table")
    p.add_argument("case_dir")

    p = sub.add_parser("git-init", help="Initialize case git repo")
    p.add_argument("case_dir")
    p.add_argument("--repo", help="Remote GitHub URL")

    p = sub.add_parser("git-push", help="Push shared/ to remote")
    p.add_argument("case_dir")
    p.add_argument("--message", "-m", default="")

    p = sub.add_parser("git-pull", help="Pull shared/ from remote")
    p.add_argument("case_dir")

    p = sub.add_parser("lan-serve", help="Start LAN sync server")
    p.add_argument("case_dir")
    p.add_argument("--port", type=int, default=9999)

    p = sub.add_parser("lan-pull", help="Pull from LAN server")
    p.add_argument("case_dir")
    p.add_argument("--server", required=True, help="host:port")

    p = sub.add_parser("lan-push", help="Push to LAN server")
    p.add_argument("case_dir")
    p.add_argument("--server", required=True, help="host:port")

    p = sub.add_parser("detect-duplicates", help="Detect duplicate findings")
    p.add_argument("case_dir")

    p = sub.add_parser("resolve-conflict", help="Resolve duplicate conflicts")
    p.add_argument("case_dir")
    p.add_argument("--id", required=True, help="ID of record to keep")
    p.add_argument("--keep", default="newer", choices=["newer", "older", "first", "specified"],
                   help="Keep strategy")

    p = sub.add_parser("version-compare", help="Compare local vs remote versions")
    p.add_argument("case_dir")
    p.add_argument("--file", required=True, help="File name")
    p.add_argument("--server", help="Server address")

    p = sub.add_parser("sync", help="Progressive sync")
    p.add_argument("case_dir")
    p.add_argument("--server", help="LAN server address")
    p.add_argument("--mode", default="lan", choices=["lan", "git"], help="Sync mode")

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        return

    commands = {
        "post": cmd_post,
        "status": cmd_status,
        "answers": cmd_answers,
        "git-init": cmd_git_init,
        "git-push": cmd_git_push,
        "git-pull": cmd_git_pull,
        "lan-serve": cmd_lan_serve,
        "lan-pull": cmd_lan_pull,
        "lan-push": cmd_lan_push,
        "detect-duplicates": cmd_detect_duplicates,
        "resolve-conflict": cmd_resolve_conflict,
        "version-compare": cmd_version_compare,
        "sync": cmd_sync,
    }
    commands[args.command](args)


if __name__ == "__main__":
    main()
