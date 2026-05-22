"""
Import findings/progress/blockers/etc from a yaml file into a running Hub.

Use case: a remote role (e.g. mobile_analyst) was network-isolated and
synced via GitHub. After main designer pulls the data repo, run this
script to push the role's findings into the Hub so other roles can see them.

Usage:
  python import_yaml_to_hub.py <yaml_file> [--hub URL] [--role ROLE_NAME] [--dry-run]

Supports:
  - findings.yaml          → POST /findings  (skips ones already present)
  - progress yaml fragment → POST /progress/<role>
  - blockers.yaml          → POST /session/blocker
"""
import argparse
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

import yaml


def call(hub, method, path, body=None):
    url = f"{hub}{path}"
    data = json.dumps(body, ensure_ascii=False).encode("utf-8") if body else None
    headers = {"Content-Type": "application/json; charset=utf-8"} if body else {}
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            ct = r.headers.get("Content-Type", "")
            raw = r.read().decode("utf-8")
            return r.status, json.loads(raw) if ct.startswith("application/json") else raw
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode("utf-8"))


def import_findings(hub, items, dry_run=False):
    s, existing = call(hub, "GET", "/findings")
    existing_keys = {(f.get("from"), f.get("summary")) for f in existing}
    pushed = skipped = 0
    for f in items:
        key = (f.get("from"), f.get("summary"))
        if key in existing_keys:
            print(f"  [skip] already present: [{f.get('id','?')}] {f.get('summary','')[:50]}")
            skipped += 1
            continue
        body = {
            "from": f["from"],
            "type": f.get("type", "evidence"),
            "summary": f.get("summary", ""),
            "detail": f.get("detail", ""),
            "related_to": f.get("related_to", []),
        }
        if dry_run:
            print(f"  [dry] would POST: {body['from']}: {body['summary'][:60]}")
            continue
        s, r = call(hub, "POST", "/findings", body)
        if s == 201:
            print(f"  [+] {r.get('id')} from {body['from']}: {body['summary'][:50]}")
            pushed += 1
        else:
            print(f"  [!] FAILED ({s}): {r}")
    return pushed, skipped


def import_progress(hub, role, prog, dry_run=False):
    body = {
        "status": prog.get("status", "in_progress"),
        "current_task": prog.get("current_task", ""),
        "completed": prog.get("completed", []),
        "pending": prog.get("pending", []),
    }
    if "blocker" in prog and prog["blocker"]:
        body["blocker"] = prog["blocker"]
    if dry_run:
        print(f"  [dry] would POST progress/{role}: status={body['status']}")
        return
    s, r = call(hub, "POST", f"/progress/{role}", body)
    print(f"  [{s}] progress/{role}: status={body['status']}")


def import_blockers(hub, items, dry_run=False):
    for b in items:
        body = {
            "from": b["from"],
            "blocker": b.get("blocker", ""),
            "needs": b.get("needs", ""),
            "status": b.get("status", "open"),
        }
        if dry_run:
            print(f"  [dry] would POST blocker: {body['blocker'][:50]}")
            continue
        s, r = call(hub, "POST", "/session/blocker", body)
        print(f"  [{s}] blocker {r.get('id','?')}: {body['blocker'][:50]}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("yaml_file", help="Path to yaml file")
    ap.add_argument("--hub", default="http://127.0.0.1:8765")
    ap.add_argument("--role", help="Only used for progress.yaml: which role this is for")
    ap.add_argument("--type", choices=["findings", "progress", "blockers", "auto"],
                    default="auto", help="What kind of yaml (default: auto-detect by filename)")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    p = Path(args.yaml_file)
    if not p.exists():
        sys.exit(f"File not found: {p}")
    data = yaml.safe_load(p.read_text(encoding="utf-8"))
    if data is None:
        sys.exit("Empty yaml file")

    # Verify hub
    try:
        s, r = call(args.hub, "GET", "/ping")
        if s != 200:
            sys.exit(f"Hub not healthy: {s}")
        print(f"[*] Hub at {args.hub}: {r.get('status')} {r.get('version')}")
    except Exception as e:
        sys.exit(f"Cannot reach hub: {e}")

    # Auto-detect type
    kind = args.type
    if kind == "auto":
        name = p.name.lower()
        if "finding" in name:
            kind = "findings"
        elif "progress" in name:
            kind = "progress"
        elif "blocker" in name:
            kind = "blockers"
        else:
            sys.exit(f"Cannot auto-detect type from filename '{p.name}', use --type")

    print(f"[*] Importing {kind} from {p}")
    if kind == "findings":
        items = data if isinstance(data, list) else [data]
        pushed, skipped = import_findings(args.hub, items, args.dry_run)
        print(f"[+] Done: pushed={pushed}, skipped={skipped}")
    elif kind == "progress":
        if not args.role:
            sys.exit("--role required for progress import")
        prog = data.get(args.role) if args.role in (data or {}) else data
        import_progress(args.hub, args.role, prog, args.dry_run)
    elif kind == "blockers":
        items = data if isinstance(data, list) else [data]
        import_blockers(args.hub, items, args.dry_run)


if __name__ == "__main__":
    main()
