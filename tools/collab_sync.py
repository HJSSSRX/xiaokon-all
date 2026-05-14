#!/usr/bin/env python3
"""
Collaboration Sync — share findings across machines via Git or LAN.

Modes:
  1. Git mode (internet):  push/pull shared/ to a GitHub case repo
  2. LAN mode (air-gapped): simple HTTP server for local network sync
  3. Smart conflict resolution: duplicate detection and version comparison
  4. Progressive sync: layered synchronization strategy

Usage:
  # ── Git mode ──
  python collab_sync.py git-init <case_dir> --repo <github_url>
  python collab_sync.py git-push <case_dir> --message "traffic: found MAC"
  python collab_sync.py git-pull <case_dir>

  # ── LAN mode (server) ──
  python collab_sync.py lan-serve <case_dir> --port 9999

  # ── LAN mode (client) ──
  python collab_sync.py lan-pull <case_dir> --server 192.168.1.100:9999
  python collab_sync.py lan-push <case_dir> --server 192.168.1.100:9999

  # ── Progressive sync (智能分层同步) ──
  python collab_sync.py sync <case_dir> --server 192.168.1.100:9999
  python collab_sync.py sync <case_dir> --mode git

  # ── Conflict resolution ──
  python collab_sync.py detect-duplicates <case_dir>
  python collab_sync.py resolve-conflict <case_dir> --id F001 --keep newer
  python collab_sync.py version-compare <case_dir> --file findings.yaml

  # ── Common ──
  python collab_sync.py post <case_dir> --from mobile --summary "Found trojan MD5" --detail "MD5=ABC..." --related server,traffic
  python collab_sync.py status <case_dir>
  python collab_sync.py answers <case_dir>
"""
import argparse
import datetime
import http.server
import json
import os
import shutil
import subprocess
import sys
import threading
import urllib.request
from pathlib import Path

try:
    import yaml
except ImportError:
    subprocess.run([sys.executable, "-m", "pip", "install", "pyyaml", "-q"], check=False)
    import yaml


# ─── Helpers ───

def shared_dir(case_dir):
    d = Path(case_dir) / "shared"
    d.mkdir(parents=True, exist_ok=True)
    return d


def load_yaml(path):
    if not path.exists():
        return []
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data if isinstance(data, list) else []


def save_yaml(path, data):
    with open(path, "w", encoding="utf-8") as f:
        yaml.dump(data, f, allow_unicode=True, default_flow_style=False, sort_keys=False)


def now_str():
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def next_id(findings):
    if not findings:
        return "F001"
    ids = [f.get("id", "") for f in findings if isinstance(f, dict)]
    nums = [int(i[1:]) for i in ids if i and i[0] == "F" and i[1:].isdigit()]
    return f"F{max(nums, default=0) + 1:03d}"


# ─── 智能冲突解决 ───

def compute_content_hash(item):
    """计算项目内容的哈希值，用于重复检测"""
    if not isinstance(item, dict):
        return None
    
    # 提取关键字段进行哈希计算
    key_fields = ["summary", "detail", "from", "type"]
    content = ""
    for field in key_fields:
        content += str(item.get(field, ""))
    
    import hashlib
    return hashlib.md5(content.encode("utf-8")).hexdigest()


def detect_duplicates(case_dir, threshold=0.9):
    """检测重复的 findings"""
    sd = shared_dir(case_dir)
    findings_path = sd / "findings.yaml"
    findings = load_yaml(findings_path)
    
    if not findings:
        return {"duplicates": [], "total": 0}
    
    # 按内容哈希分组
    hash_groups = {}
    for item in findings:
        if isinstance(item, dict):
            h = compute_content_hash(item)
            if h:
                hash_groups.setdefault(h, []).append(item)
    
    # 找出重复项（同一哈希有多个项目）
    duplicates = []
    for h, items in hash_groups.items():
        if len(items) > 1:
            duplicates.append({
                "hash": h,
                "count": len(items),
                "items": items,
            })
    
    return {"duplicates": duplicates, "total": len(duplicates), "checked": len(findings)}


def resolve_duplicate(findings, item_id, keep_strategy="newer"):
    """
    解决重复项
    :param findings: findings 列表
    :param item_id: 要保留的项目 ID
    :param keep_strategy: 保留策略: newer(最新), older(最早), first(第一个), specified(指定ID)
    """
    if not findings:
        return {"status": "error", "message": "No findings to process"}
    
    # 找到指定 ID 的项目
    target = None
    for item in findings:
        if isinstance(item, dict) and item.get("id") == item_id:
            target = item
            break
    
    if not target:
        return {"status": "error", "message": f"Item {item_id} not found"}
    
    # 找到重复项（基于内容哈希）
    target_hash = compute_content_hash(target)
    duplicates = []
    to_remove = []
    
    for i, item in enumerate(findings):
        if isinstance(item, dict) and item.get("id") != item_id:
            h = compute_content_hash(item)
            if h == target_hash:
                duplicates.append(item)
                to_remove.append(i)
    
    if not duplicates:
        return {"status": "info", "message": "No duplicates found", "kept": target}
    
    # 根据策略决定保留哪个
    if keep_strategy == "specified":
        # 保留指定的 item_id
        kept = target
    elif keep_strategy == "newer":
        # 保留最新的（时间戳最大）
        all_candidates = [target] + duplicates
        kept = max(all_candidates, key=lambda x: x.get("time", ""))
    elif keep_strategy == "older":
        # 保留最早的
        all_candidates = [target] + duplicates
        kept = min(all_candidates, key=lambda x: x.get("time", ""))
    else:  # first
        # 保留第一个（ID 最小）
        all_candidates = [target] + duplicates
        kept = min(all_candidates, key=lambda x: x.get("id", "Z"))
    
    # 移除重复项
    # 从后往前移除，避免索引偏移
    to_remove.sort(reverse=True)
    for i in to_remove:
        del findings[i]
    
    return {
        "status": "resolved",
        "kept": kept,
        "removed": len(duplicates),
        "removed_items": duplicates,
        "remaining_count": len(findings),
    }


def compare_versions(local_items, remote_items, key_field="id"):
    """
    比较本地和远程版本
    :return: 添加的项、删除的项、修改的项
    """
    local_dict = {item.get(key_field): item for item in local_items if isinstance(item, dict)}
    remote_dict = {item.get(key_field): item for item in remote_items if isinstance(item, dict)}
    
    added = []
    removed = []
    modified = []
    
    # 找出新增的项（远程有，本地没有）
    for key, remote_item in remote_dict.items():
        if key not in local_dict:
            added.append(remote_item)
    
    # 找出删除的项（本地有，远程没有）
    for key, local_item in local_dict.items():
        if key not in remote_dict:
            removed.append(local_item)
    
    # 找出修改的项（两边都有，但内容不同）
    for key, local_item in local_dict.items():
        if key in remote_dict:
            remote_item = remote_dict[key]
            if local_item != remote_item:
                modified.append({
                    "local": local_item,
                    "remote": remote_item,
                    "key": key,
                })
    
    return {
        "added": added,
        "removed": removed,
        "modified": modified,
        "local_count": len(local_items),
        "remote_count": len(remote_items),
    }


# ─── 渐进式同步策略 ───

SYNC_PRIORITIES = [
    {"name": "answers", "file": "answers.yaml", "priority": 1, "sync_interval": 10},
    {"name": "findings", "file": "findings.yaml", "priority": 2, "sync_interval": 30},
    {"name": "progress", "file": "progress.yaml", "priority": 3, "sync_interval": 60},
    {"name": "questions", "file": "questions.yaml", "priority": 4, "sync_interval": 120},
    {"name": "session_log", "file": "session_log.yaml", "priority": 5, "sync_interval": 300},
    {"name": "blockers", "file": "blockers.yaml", "priority": 5, "sync_interval": 300},
    {"name": "strategy", "file": "strategy.yaml", "priority": 5, "sync_interval": 300},
]


def progressive_sync(case_dir, server=None, mode="lan"):
    """
    渐进式同步：按优先级分层同步
    :param case_dir: 案件目录
    :param server: 服务器地址 (LAN模式)
    :param mode: 同步模式: lan 或 git
    """
    sd = shared_dir(case_dir)
    results = []
    
    for sync_item in SYNC_PRIORITIES:
        fname = sync_item["file"]
        priority = sync_item["priority"]
        
        try:
            if mode == "lan" and server:
                result = sync_lan_file(sd, fname, server)
            elif mode == "git":
                result = sync_git_file(case_dir, fname)
            else:
                result = {"status": "error", "file": fname, "message": "Unknown mode"}
            
            result["priority"] = priority
            results.append(result)
            
            # 低优先级文件如果上次同步时间很近，跳过
            last_sync = get_last_sync_time(case_dir, fname)
            if last_sync and priority >= 4:
                age = (datetime.datetime.now() - last_sync).total_seconds()
                if age < sync_item["sync_interval"]:
                    result["skipped"] = True
                    result["reason"] = "Recent sync"
                    continue
            
        except Exception as e:
            results.append({
                "file": fname,
                "priority": priority,
                "status": "error",
                "message": str(e),
            })
    
    summary = {
        "total": len(results),
        "success": sum(1 for r in results if r.get("status") == "success"),
        "failed": sum(1 for r in results if r.get("status") == "error"),
        "skipped": sum(1 for r in results if r.get("skipped")),
    }
    
    return {"results": results, "summary": summary}


def sync_lan_file(shared_dir, fname, server):
    """同步单个文件 (LAN模式)"""
    server = server.rstrip("/")
    if not server.startswith("http"):
        server = f"http://{server}"
    
    fpath = shared_dir / fname
    local_items = load_yaml(fpath)
    
    try:
        url = f"{server}/{fname}"
        data = urllib.request.urlopen(url, timeout=5).read()
        remote_items = yaml.safe_load(data) or []
        
        # 比较版本
        comparison = compare_versions(local_items, remote_items)
        
        # 合并：添加远程新增的项
        local_ids = {item.get("id") for item in local_items if isinstance(item, dict)}
        added = 0
        for item in comparison["added"]:
            if isinstance(item, dict) and item.get("id") not in local_ids:
                local_items.append(item)
                added += 1
        
        if added > 0:
            save_yaml(fpath, local_items)
        
        # 更新同步时间
        update_sync_time(shared_dir.parent, fname)
        
        return {
            "file": fname,
            "status": "success",
            "added": added,
            "removed_in_remote": len(comparison["removed"]),
            "modified": len(comparison["modified"]),
        }
    
    except Exception as e:
        return {
            "file": fname,
            "status": "error",
            "message": str(e),
        }


def sync_git_file(case_dir, fname):
    """同步单个文件 (Git模式)"""
    case_dir = Path(case_dir)
    fpath = case_dir / "shared" / fname
    
    try:
        # Pull 最新更改
        git_run(case_dir, "pull", "--rebase")
        
        # 检查文件是否有变更
        result = git_run(case_dir, "status", "--porcelain", "shared/" + fname)
        if result.stdout.strip():
            # 有变更，已自动合并
            return {"file": fname, "status": "success", "updated": True}
        else:
            return {"file": fname, "status": "success", "updated": False}
    
    except Exception as e:
        return {
            "file": fname,
            "status": "error",
            "message": str(e),
        }


def get_last_sync_time(case_dir, fname):
    """获取上次同步时间"""
    sync_times_path = Path(case_dir) / ".sync_times.yaml"
    if not sync_times_path.exists():
        return None
    
    sync_times = load_yaml(sync_times_path)
    if isinstance(sync_times, dict) and fname in sync_times:
        try:
            return datetime.datetime.strptime(sync_times[fname], "%Y-%m-%d %H:%M:%S")
        except Exception:
            return None
    return None


def update_sync_time(case_dir, fname):
    """更新同步时间"""
    sync_times_path = Path(case_dir) / ".sync_times.yaml"
    if sync_times_path.exists():
        sync_times = load_yaml(sync_times_path)
    else:
        sync_times = {}
    
    if not isinstance(sync_times, dict):
        sync_times = {}
    
    sync_times[fname] = now_str()
    save_yaml(sync_times_path, sync_times)


# ─── Post a finding ───

def cmd_post(args):
    sd = shared_dir(args.case_dir)
    findings_path = sd / "findings.yaml"
    findings = load_yaml(findings_path)

    entry = {
        "id": next_id(findings),
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


# ─── Status overview ───

def cmd_status(args):
    sd = shared_dir(args.case_dir)

    # Findings
    findings = load_yaml(sd / "findings.yaml")
    print(f"\n=== Findings: {len(findings)} ===")
    for f in findings[-10:]:
        print(f"  {f.get('id','?')} [{f.get('from','?')}] {f.get('summary','')}")

    # Progress
    progress = load_yaml(sd / "progress.yaml")
    if isinstance(progress, list):
        print(f"\n=== Progress ===")
        for p in progress:
            if isinstance(p, dict):
                role = p.get("role", "?")
                status = p.get("status", "?")
                done = p.get("done", 0)
                total = p.get("total", "?")
                print(f"  {role:20s} {done}/{total} ({status})")

    # Answers
    answers_path = sd / "answers.yaml"
    if answers_path.exists():
        answers = load_yaml(answers_path)
        answered = sum(1 for a in answers if isinstance(a, dict) and a.get("answer"))
        print(f"\n=== Answers: {answered}/{len(answers)} ===")


# ─── Answers table ───

def cmd_answers(args):
    sd = shared_dir(args.case_dir)
    answers_path = sd / "answers.yaml"
    answers = load_yaml(answers_path)

    if not answers:
        print("No answers yet.")
        return

    # Print as table
    print(f"\n{'#':<5} {'Category':<12} {'Summary':<30} {'Answer':<25} {'Status':<8} {'Source':<10}")
    print("-" * 90)
    for a in answers:
        if not isinstance(a, dict):
            continue
        status = "✅" if a.get("answer") else "❌"
        print(f"{a.get('num','?'):<5} {a.get('category',''):<12} {a.get('summary','')[:28]:<30} {str(a.get('answer',''))[:23]:<25} {status:<8} {a.get('source',''):<10}")


# ─── Git operations ───

def git_run(case_dir, *git_args):
    result = subprocess.run(
        ["git"] + list(git_args),
        cwd=case_dir,
        capture_output=True, text=True, encoding="utf-8", errors="replace"
    )
    if result.returncode != 0 and result.stderr:
        print(f"[git] {result.stderr.strip()}")
    return result


def cmd_git_init(args):
    case_dir = Path(args.case_dir)
    shared = shared_dir(case_dir)

    # Init git in case_dir if not already
    if not (case_dir / ".git").exists():
        git_run(case_dir, "init")
        print("[+] Initialized git repo")

    # Create .gitignore for large evidence files
    gitignore = case_dir / ".gitignore"
    if not gitignore.exists():
        gitignore.write_text(
            "# Evidence files (too large for git)\n"
            "*.E01\n*.e01\n*.vmdk\n*.vhd\n*.dd\n*.raw\n*.zip\n"
            "*.bak\n"
            "mobile/backup/\n"
            "computer/mounted/\n"
            "server/vmdk_root/\n"
            "\n# Keep shared/ tracked\n"
            "!shared/\n",
            encoding="utf-8"
        )

    # Ensure shared files exist
    for fname in ["findings.yaml", "progress.yaml", "answers.yaml"]:
        fpath = shared / fname
        if not fpath.exists():
            save_yaml(fpath, [])

    if args.repo:
        git_run(case_dir, "remote", "add", "origin", args.repo)
        print(f"[+] Remote set to {args.repo}")

    git_run(case_dir, "add", "-A")
    git_run(case_dir, "commit", "-m", "init case workspace")
    print("[+] Case workspace initialized. Now push with: git push -u origin main")


def cmd_git_push(args):
    case_dir = args.case_dir
    git_run(case_dir, "add", "shared/")
    msg = args.message or f"sync {now_str()}"
    git_run(case_dir, "commit", "-m", msg)
    result = git_run(case_dir, "push")
    if result.returncode == 0:
        print(f"[+] Pushed: {msg}")
    else:
        print("[!] Push failed. Try: git pull --rebase first")


def cmd_git_pull(args):
    result = git_run(args.case_dir, "pull", "--rebase")
    if result.returncode == 0:
        print("[+] Pulled latest changes")
    else:
        print("[!] Pull failed — check for conflicts")


# ─── LAN HTTP sync ───

class SyncHandler(http.server.BaseHTTPRequestHandler):
    """Serve and accept shared/ files over HTTP."""

    shared_root = None

    def log_message(self, *a):
        pass  # suppress default logging

    def do_GET(self):
        # GET /findings.yaml → return file content
        fname = self.path.strip("/")
        if fname not in ("findings.yaml", "progress.yaml", "answers.yaml", "status"):
            self.send_error(404)
            return

        if fname == "status":
            # Return all files as JSON
            data = {}
            for fn in ["findings.yaml", "progress.yaml", "answers.yaml"]:
                fpath = self.shared_root / fn
                data[fn] = load_yaml(fpath)
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(data, ensure_ascii=False).encode())
            return

        fpath = self.shared_root / fname
        if not fpath.exists():
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header("Content-Type", "text/yaml")
        self.end_headers()
        self.wfile.write(fpath.read_bytes())

    def do_POST(self):
        # POST /findings.yaml → append to file
        fname = self.path.strip("/")
        if fname not in ("findings.yaml", "progress.yaml", "answers.yaml"):
            self.send_error(400)
            return

        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length)

        try:
            incoming = yaml.safe_load(body)
        except Exception:
            self.send_error(400, "Invalid YAML")
            return

        fpath = self.shared_root / fname
        existing = load_yaml(fpath)

        if isinstance(incoming, list):
            # Merge: add items with new IDs
            existing_ids = {e.get("id") for e in existing if isinstance(e, dict)}
            for item in incoming:
                if isinstance(item, dict) and item.get("id") not in existing_ids:
                    existing.append(item)
        elif isinstance(incoming, dict):
            existing.append(incoming)

        save_yaml(fpath, existing)
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.end_headers()
        self.wfile.write(b"OK")
        print(f"  [sync] {fname} updated (+{len(incoming) if isinstance(incoming, list) else 1} items)")


def cmd_lan_serve(args):
    sd = shared_dir(args.case_dir)
    SyncHandler.shared_root = sd

    port = args.port
    server = http.server.HTTPServer(("0.0.0.0", port), SyncHandler)

    # Show local IPs
    import socket
    hostname = socket.gethostname()
    ips = socket.getaddrinfo(hostname, None, socket.AF_INET)
    unique_ips = sorted(set(addr[4][0] for addr in ips))

    print(f"\n╔══════════════════════════════════════════╗")
    print(f"║   LAN Sync Server — port {port}            ║")
    print(f"╚══════════════════════════════════════════╝")
    print(f"  Serving: {sd}")
    print(f"  Other machines connect with:")
    for ip in unique_ips:
        print(f"    python collab_sync.py lan-pull <case_dir> --server {ip}:{port}")
    print(f"\n  Press Ctrl+C to stop.\n")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[+] Server stopped.")


def cmd_lan_pull(args):
    sd = shared_dir(args.case_dir)
    server = args.server.rstrip("/")
    if not server.startswith("http"):
        server = f"http://{server}"

    for fname in ["findings.yaml", "progress.yaml", "answers.yaml"]:
        try:
            url = f"{server}/{fname}"
            data = urllib.request.urlopen(url, timeout=5).read()
            remote_items = yaml.safe_load(data) or []

            local_path = sd / fname
            local_items = load_yaml(local_path)
            local_ids = {e.get("id") for e in local_items if isinstance(e, dict)}

            added = 0
            for item in remote_items:
                if isinstance(item, dict) and item.get("id") not in local_ids:
                    local_items.append(item)
                    added += 1

            if added > 0:
                save_yaml(local_path, local_items)
                print(f"  [+] {fname}: +{added} new items")
            else:
                print(f"  [=] {fname}: up to date")
        except Exception as e:
            print(f"  [!] {fname}: {e}")


def cmd_lan_push(args):
    sd = shared_dir(args.case_dir)
    server = args.server.rstrip("/")
    if not server.startswith("http"):
        server = f"http://{server}"

    for fname in ["findings.yaml", "progress.yaml", "answers.yaml"]:
        fpath = sd / fname
        if not fpath.exists():
            continue
        try:
            data = fpath.read_bytes()
            req = urllib.request.Request(
                f"{server}/{fname}",
                data=data,
                headers={"Content-Type": "text/yaml"},
                method="POST"
            )
            urllib.request.urlopen(req, timeout=5)
            print(f"  [+] {fname}: pushed")
        except Exception as e:
            print(f"  [!] {fname}: {e}")


# ─── Command wrappers for new features ───

def cmd_detect_duplicates(args):
    result = detect_duplicates(args.case_dir)
    print(f"\n=== 重复检测结果 ===")
    print(f"检查了 {result['checked']} 条记录")
    print(f"发现 {result['total']} 组重复")
    
    if result["duplicates"]:
        for i, group in enumerate(result["duplicates"], 1):
            print(f"\n[{i}] 哈希: {group['hash']}")
            print(f"  重复次数: {group['count']}")
            for item in group["items"]:
                print(f"    - {item.get('id', '?')} [{item.get('time', '')}] {item.get('summary', '')[:50]}...")


def cmd_resolve_conflict(args):
    sd = shared_dir(args.case_dir)
    findings_path = sd / "findings.yaml"
    findings = load_yaml(findings_path)
    
    result = resolve_duplicate(findings, args.id, args.keep)
    
    if result["status"] == "resolved":
        save_yaml(findings_path, findings)
        print(f"\n=== 冲突已解决 ===")
        print(f"保留: {result['kept'].get('id', '?')} - {result['kept'].get('summary', '')[:50]}")
        print(f"移除: {result['removed']} 条重复项")
        print(f"剩余记录: {result['remaining_count']}")
    else:
        print(f"\n{result['status'].upper()}: {result['message']}")


def cmd_version_compare(args):
    sd = shared_dir(args.case_dir)
    local_path = sd / args.file
    
    if not local_path.exists():
        print(f"错误: 文件 {args.file} 不存在")
        return
    
    local_items = load_yaml(local_path)
    
    if args.server:
        server = args.server.rstrip("/")
        if not server.startswith("http"):
            server = f"http://{server}"
        
        try:
            url = f"{server}/{args.file}"
            data = urllib.request.urlopen(url, timeout=5).read()
            remote_items = yaml.safe_load(data) or []
        except Exception as e:
            print(f"无法连接到服务器: {e}")
            return
    else:
        print("需要指定 --server 参数")
        return
    
    comparison = compare_versions(local_items, remote_items)
    
    print(f"\n=== 版本比较: {args.file} ===")
    print(f"本地: {comparison['local_count']} 条")
    print(f"远程: {comparison['remote_count']} 条")
    print(f"\n新增 (远程有，本地无): {len(comparison['added'])}")
    print(f"删除 (本地有，远程无): {len(comparison['removed'])}")
    print(f"修改: {len(comparison['modified'])}")


def cmd_sync(args):
    if args.mode == "lan" and not args.server:
        print("LAN 模式需要指定 --server 参数")
        return
    
    result = progressive_sync(args.case_dir, args.server, args.mode)
    
    print(f"\n=== 渐进式同步结果 ===")
    for r in result["results"]:
        status_icon = "✅" if r["status"] == "success" else "❌"
        skipped = "(跳过: 近期已同步)" if r.get("skipped") else ""
        print(f"  {status_icon} [{r['priority']}] {r['file']}: {r['status']} {skipped}")
    
    print(f"\n摘要: {result['summary']['success']} 成功, {result['summary']['failed']} 失败, {result['summary']['skipped']} 跳过")


# ─── Main ───

def main():
    parser = argparse.ArgumentParser(description="AutoForensicAI Collaboration Sync")
    sub = parser.add_subparsers(dest="command")

    # post
    p = sub.add_parser("post", help="Post a finding")
    p.add_argument("case_dir")
    p.add_argument("--from", dest="sender", required=True, help="Role name")
    p.add_argument("--summary", required=True)
    p.add_argument("--detail", default="")
    p.add_argument("--related", default="", help="Comma-separated role names")

    # status
    p = sub.add_parser("status", help="Show collaboration status")
    p.add_argument("case_dir")

    # answers
    p = sub.add_parser("answers", help="Show answers table")
    p.add_argument("case_dir")

    # git-init
    p = sub.add_parser("git-init", help="Initialize case git repo")
    p.add_argument("case_dir")
    p.add_argument("--repo", help="Remote GitHub URL")

    # git-push
    p = sub.add_parser("git-push", help="Push shared/ to remote")
    p.add_argument("case_dir")
    p.add_argument("--message", "-m", default="")

    # git-pull
    p = sub.add_parser("git-pull", help="Pull shared/ from remote")
    p.add_argument("case_dir")

    # lan-serve
    p = sub.add_parser("lan-serve", help="Start LAN sync server")
    p.add_argument("case_dir")
    p.add_argument("--port", type=int, default=9999)

    # lan-pull
    p = sub.add_parser("lan-pull", help="Pull from LAN server")
    p.add_argument("case_dir")
    p.add_argument("--server", required=True, help="host:port")

    # lan-push
    p = sub.add_parser("lan-push", help="Push to LAN server")
    p.add_argument("case_dir")
    p.add_argument("--server", required=True, help="host:port")

    # detect-duplicates
    p = sub.add_parser("detect-duplicates", help="检测重复的 findings")
    p.add_argument("case_dir")

    # resolve-conflict
    p = sub.add_parser("resolve-conflict", help="解决重复冲突")
    p.add_argument("case_dir")
    p.add_argument("--id", required=True, help="要保留的记录 ID")
    p.add_argument("--keep", default="newer", choices=["newer", "older", "first", "specified"],
                   help="保留策略")

    # version-compare
    p = sub.add_parser("version-compare", help="比较本地和远程版本")
    p.add_argument("case_dir")
    p.add_argument("--file", required=True, help="文件名")
    p.add_argument("--server", help="服务器地址")

    # sync (progressive)
    p = sub.add_parser("sync", help="渐进式同步")
    p.add_argument("case_dir")
    p.add_argument("--server", help="LAN 服务器地址")
    p.add_argument("--mode", default="lan", choices=["lan", "git"], help="同步模式")

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
