"""
sim_recon.py — 仿真启动后自动巡检 + log_finding 到 hub

目的:
  仿真起来后, 不要让 server_analyst / internet_analyst 一题一题问.
  一次性把环境信息查出来 (OS / 容器 / 端口 / 站点 / DB), 自动 log_finding,
  让所有角色看到同一份"已知世界状态".

用法:
  # 启动后跑:
  python3 sim_recon.py --target server --hub http://127.0.0.1:8765 --role server_analyst

  # 或调用 API:
  >>> from sim_recon import recon_server, recon_full
  >>> ssh = ForensicSSH("server").connect()
  >>> recon_server(ssh, hub_url="http://127.0.0.1:8765", role="server_analyst")
"""
import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from ssh_helper import ForensicSSH, SSHRunError


# ─── Hub 客户端 ───

def _hub_post(hub_url: str, path: str, payload: dict, timeout: int = 5) -> tuple:
    """向 hub POST JSON. 失败静默 (返回 (False, error)) — 巡检不应阻塞主流程."""
    if not hub_url:
        return False, "no hub_url"
    url = f"{hub_url.rstrip('/')}{path}"
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        url, data=data,
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return True, json.loads(resp.read().decode("utf-8", errors="replace"))
    except Exception as e:
        return False, str(e)


def log_finding(hub_url: str, role: str, summary: str, *, detail: str = "",
                kind: str = "evidence", related_to: list = None) -> tuple:
    """log_finding via /log endpoint."""
    return _hub_post(hub_url, "/log", {
        "kind": "finding",
        "from": role,
        "type": kind,
        "summary": summary,
        "detail": detail,
        "related_to": related_to or [],
    })


# ─── 巡检命令清单 ───

# 服务器通用巡检 (Linux)
SERVER_PROBES = [
    ("OS", "cat /etc/os-release 2>/dev/null | head -10"),
    ("Hostname + Kernel", "hostname; uname -a"),
    ("Network IPs", "ip -4 -o addr 2>/dev/null || ifconfig | grep 'inet '"),
    ("Listening Ports", "ss -tlnp 2>/dev/null || netstat -tlnp 2>/dev/null"),
    ("LXC Containers", "sudo lxc-ls -f 2>/dev/null"),
    ("Docker Containers", "docker ps -a 2>/dev/null"),
    ("Web Sites", "ls /var/www/ 2>/dev/null; ls /etc/nginx/sites-enabled/ 2>/dev/null"),
    ("DB Services Installed", "dpkg -l 2>/dev/null | grep -iE 'mysql|tidb|postgres|mariadb|redis|mongo' | awk '{print $2}'"),
    ("DB Services Running", "for svc in mysql mariadb postgresql tidb redis mongodb; do "
                            "printf '%-12s ' $svc; systemctl is-active $svc 2>/dev/null || echo '(missing)'; done"),
    ("Block Devices", "lsblk -f 2>/dev/null"),
    ("Mounted FS", "df -hT 2>/dev/null"),
]

# maccms 专项 (S 类必查, 一次覆盖 Q5/Q8/Q15/Q10 多题)
MACCMS_PROBES = [
    ("maccms ENTRANCE", "grep -E 'ENTRANCE|ADMIN_PATH' /var/www/html/maccms/application/extra/maccms.php 2>/dev/null"),
    ("maccms 数据库密码", "grep -E 'DB.*hostname|DB.*username|DB.*password|DB.*database' "
                          "/var/www/html/maccms/application/database.php 2>/dev/null"),
    ("nginx 伪静态", "grep -A 5 'rewrite\\|try_files' /etc/nginx/sites-enabled/default 2>/dev/null"),
]

# TiDB 容器内查询 (I 类必查)
TIDB_PROBES = [
    ("TiDB Databases", "SHOW DATABASES"),
    ("TiDB mac_vod 样本", "SELECT vod_id, vod_name, vod_pic FROM maccms.mac_vod LIMIT 10"),
    ("TiDB 用户登录 IP", "SELECT user_name, inet_ntoa(user_last_login_ip) AS ip FROM maccms.mac_user"),
]


# ─── 巡检函数 ───

def recon_server(ssh: ForensicSSH, *, hub_url: str = "", role: str = "server_analyst",
                 verbose: bool = True) -> dict:
    """
    服务器通用巡检. 跑所有 SERVER_PROBES, 每个结果 log_finding 到 hub.

    返回: {probe_name: stdout} 字典.
    """
    results = {}
    for name, cmd in SERVER_PROBES:
        if verbose:
            print(f"  [recon] {name}...")
        try:
            out, err, rc = ssh.run(cmd, timeout=20)
            results[name] = out
            if hub_url and out.strip():
                log_finding(
                    hub_url, role,
                    f"[recon] {name}",
                    detail=out[:2000],
                    kind="environment",
                    related_to=["main_designer"],
                )
        except Exception as e:
            results[name] = f"<error: {e}>"
            if verbose:
                print(f"    error: {e}")
    return results


def recon_maccms(ssh: ForensicSSH, *, hub_url: str = "", role: str = "server_analyst",
                 verbose: bool = True) -> dict:
    """maccms 专项巡检."""
    results = {}
    for name, cmd in MACCMS_PROBES:
        if verbose:
            print(f"  [maccms] {name}...")
        out, err, rc = ssh.run(cmd, timeout=15)
        results[name] = out
        if hub_url and out.strip():
            log_finding(
                hub_url, role,
                f"[maccms-recon] {name}",
                detail=out[:2000],
                kind="environment",
                related_to=["main_designer", "internet_analyst"],
            )
    return results


def recon_tidb(ssh: ForensicSSH, container: str = "mytidb",
               db: str = "maccms", *, hub_url: str = "", role: str = "internet_analyst",
               verbose: bool = True) -> dict:
    """TiDB 容器专项巡检 (lxc-attach 进容器跑 mysql)."""
    results = {}
    for name, query in TIDB_PROBES:
        if verbose:
            print(f"  [tidb] {name}...")
        try:
            out = ssh.tidb(query, db=db, container=container)
            results[name] = out
            if hub_url and out.strip():
                log_finding(
                    hub_url, role,
                    f"[tidb-recon] {name}",
                    detail=out[:2000],
                    kind="environment",
                    related_to=["main_designer", "server_analyst"],
                )
        except Exception as e:
            results[name] = f"<error: {e}>"
    return results


def recon_full(ssh: ForensicSSH, *, hub_url: str = "", role: str = "server_analyst",
               do_maccms: bool = True, do_tidb: bool = True, tidb_container: str = "mytidb",
               verbose: bool = True) -> dict:
    """
    完整巡检 = server + maccms + tidb. 适合 server_analyst/internet_analyst 启动时一键跑.

    返回: {"server": {...}, "maccms": {...}, "tidb": {...}}
    """
    out = {"server": recon_server(ssh, hub_url=hub_url, role=role, verbose=verbose)}
    if do_maccms:
        out["maccms"] = recon_maccms(ssh, hub_url=hub_url, role=role, verbose=verbose)
    if do_tidb:
        out["tidb"] = recon_tidb(ssh, container=tidb_container, hub_url=hub_url,
                                 role=role, verbose=verbose)
    return out


# ─── CLI ───

def main():
    ap = argparse.ArgumentParser(description="仿真启动后自动巡检")
    ap.add_argument("--target", required=True,
                    help="ssh 配置名 (~/.forensic_ssh.yaml 里的 key)")
    ap.add_argument("--hub", default=os.environ.get("HUB_URL", ""),
                    help="Hub URL (e.g. http://127.0.0.1:8765)")
    ap.add_argument("--role", default=os.environ.get("ROLE", "server_analyst"),
                    help="发起 finding 的角色名")
    ap.add_argument("--scope", default="full", choices=["server", "maccms", "tidb", "full"],
                    help="巡检范围")
    ap.add_argument("--tidb-container", default="mytidb")
    ap.add_argument("--output", "-o", help="把巡检结果保存为 JSON 文件")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    print(f"[sim_recon] 连接 {args.target}...")
    try:
        ssh = ForensicSSH(args.target).connect()
    except Exception as e:
        print(f"[FAIL] 连接失败: {e}", file=sys.stderr)
        return 1

    print(f"[sim_recon] 巡检 scope={args.scope}, hub={args.hub or '(无, 仅本地输出)'}")
    try:
        if args.scope == "server":
            results = {"server": recon_server(ssh, hub_url=args.hub, role=args.role, verbose=not args.quiet)}
        elif args.scope == "maccms":
            results = {"maccms": recon_maccms(ssh, hub_url=args.hub, role=args.role, verbose=not args.quiet)}
        elif args.scope == "tidb":
            results = {"tidb": recon_tidb(ssh, container=args.tidb_container,
                                          hub_url=args.hub, role=args.role, verbose=not args.quiet)}
        else:  # full
            results = recon_full(ssh, hub_url=args.hub, role=args.role,
                                 tidb_container=args.tidb_container, verbose=not args.quiet)
    finally:
        ssh.close()

    if args.output:
        Path(args.output).write_text(json.dumps(results, ensure_ascii=False, indent=2),
                                     encoding="utf-8")
        print(f"[sim_recon] 结果保存到 {args.output}")

    print(f"[sim_recon] 完成. {sum(len(v) for v in results.values())} 个探针.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
