"""LAN-based HTTP collaboration sync."""

import datetime
import http.server
import json
import socket
import urllib.request
from pathlib import Path

from ..core import now_str, load_yaml, load_yaml_str, save_yaml, shared_dir


def get_last_sync_time(case_dir, fname):
    """Get last sync time for a file."""
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
    """Update sync time for a file."""
    sync_times_path = Path(case_dir) / ".sync_times.yaml"
    sync_times = load_yaml(sync_times_path) if sync_times_path.exists() else {}
    if not isinstance(sync_times, dict):
        sync_times = {}
    sync_times[fname] = now_str()
    save_yaml(sync_times_path, sync_times)


def sync_lan_file(shared_dir, fname, server):
    """Sync single file via LAN."""
    from .conflict import compare_versions

    server = server.rstrip("/")
    if not server.startswith("http"):
        server = f"http://{server}"

    fpath = shared_dir / fname
    local_items = load_yaml(fpath)

    try:
        url = f"{server}/{fname}"
        data = urllib.request.urlopen(url, timeout=5).read()
        remote_items = load_yaml_str(data, [])

        comparison = compare_versions(local_items, remote_items)

        local_ids = {item.get("id") for item in local_items if isinstance(item, dict)}
        added = 0
        for item in comparison["added"]:
            if isinstance(item, dict) and item.get("id") not in local_ids:
                local_items.append(item)
                added += 1

        if added > 0:
            save_yaml(fpath, local_items)

        update_sync_time(shared_dir.parent, fname)

        return {
            "file": fname, "status": "success",
            "added": added,
            "removed_in_remote": len(comparison["removed"]),
            "modified": len(comparison["modified"]),
        }
    except Exception as e:
        return {"file": fname, "status": "error", "message": str(e)}


class SyncHandler(http.server.BaseHTTPRequestHandler):
    """Serve and accept shared/ files over HTTP."""

    shared_root = None

    def log_message(self, *a):
        pass

    def do_GET(self):
        fname = self.path.strip("/")
        if fname not in ("findings.yaml", "progress.yaml", "answers.yaml", "status"):
            self.send_error(404)
            return

        if fname == "status":
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
        fname = self.path.strip("/")
        if fname not in ("findings.yaml", "progress.yaml", "answers.yaml"):
            self.send_error(400)
            return

        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length)

        try:
            incoming = load_yaml_str(body)
        except Exception:
            self.send_error(400, "Invalid YAML")
            return

        fpath = self.shared_root / fname
        existing = load_yaml(fpath)

        if isinstance(incoming, list):
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
        count = len(incoming) if isinstance(incoming, list) else 1
        print(f"  [sync] {fname} updated (+{count} items)")


def cmd_lan_serve(args):
    sd = shared_dir(args.case_dir)
    SyncHandler.shared_root = sd

    port = args.port
    server = http.server.HTTPServer(("0.0.0.0", port), SyncHandler)

    hostname = socket.gethostname()
    ips = socket.getaddrinfo(hostname, None, socket.AF_INET)
    unique_ips = sorted(set(addr[4][0] for addr in ips))

    print(f"\n  LAN Sync Server — port {port}")
    print(f"  Serving: {sd}")
    print(f"  Other machines connect with:")
    for ip in unique_ips:
        print(f"    python collab_sync.py lan-pull <case_dir> --server {ip}:{port}")
    print()

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
            remote_items = load_yaml_str(data, [])

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
                f"{server}/{fname}", data=data,
                headers={"Content-Type": "text/yaml"}, method="POST",
            )
            urllib.request.urlopen(req, timeout=5)
            print(f"  [+] {fname}: pushed")
        except Exception as e:
            print(f"  [!] {fname}: {e}")
