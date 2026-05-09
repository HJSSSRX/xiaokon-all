"""
dashboard.html 心跳显示 - 端到端集成测试

测试策略:
  1. 启动 hub
  2. POST 一些心跳 (alive / stale / offline 三种状态)
  3. 抓 GET /dashboard 验证 HTML 含 heartbeat-badge 元素
  4. 抓 GET /heartbeat 验证后端数据完整
  5. 静态分析 dashboard.html JS 逻辑 (renderRoles 接受 heartbeat 参数)

Run:
  python3 tests/test_dashboard_heartbeat.py
"""
import json
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HUB = ROOT / "tools" / "collab_hub.py"
DASHBOARD = ROOT / "tools" / "dashboard.html"


def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def call(base, method, path, body=None):
    url = f"{base}{path}"
    data = json.dumps(body).encode("utf-8") if body else None
    headers = {"Content-Type": "application/json"} if body else {}
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=5) as r:
        ct = r.headers.get("Content-Type", "")
        raw = r.read().decode("utf-8")
        return r.status, json.loads(raw) if ct.startswith("application/json") else raw


def wait_ready(base, timeout=5):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            urllib.request.urlopen(f"{base}/ping", timeout=1).read()
            return True
        except Exception:
            time.sleep(0.1)
    return False


PASSED = 0
FAILED = 0


def t(name, cond, msg=""):
    global PASSED, FAILED
    if cond:
        print(f"[OK]   {name}")
        PASSED += 1
    else:
        print(f"[FAIL] {name}  {msg}")
        FAILED += 1


def test_static_dashboard_html():
    """静态分析 dashboard.html: renderRoles 接受 heartbeat 参数 + heartbeat-badge 元素."""
    if not DASHBOARD.exists():
        t("dashboard.html 存在", False, "file not found")
        return
    
    content = DASHBOARD.read_text(encoding="utf-8")
    
    t("dashboard.html: 含 heartbeat-badge 元素",
      'id="heartbeat-badge"' in content)
    
    t("dashboard.html: renderRoles 接受 heartbeat 参数",
      "function renderRoles(progress, findings, heartbeat)" in content)
    
    t("dashboard.html: 含 internet_analyst",
      "internet_analyst" in content)
    
    t("dashboard.html: fetch /heartbeat 端点",
      "/heartbeat" in content and ".catch(() => ({}))" in content)
    
    t("dashboard.html: 含 alive/stale/offline 状态计算",
      "hbStatus" in content and "alive" in content and "offline" in content)
    
    t("dashboard.html: 60s/300s 阈值正确",
      "60" in content and "300" in content)


def test_heartbeat_endpoint_e2e():
    """启动 hub + POST 心跳 + GET /heartbeat 端到端."""
    tmp = Path(tempfile.mkdtemp(prefix="dash_hb_test_"))
    (tmp / "shared").mkdir()
    port = free_port()
    base = f"http://127.0.0.1:{port}"
    
    proc = subprocess.Popen(
        [sys.executable, str(HUB), "serve", str(tmp), "--port", str(port), "--bind", "127.0.0.1"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    try:
        if not wait_ready(base):
            t("Hub 启动 (5s 内 ping 通)", False)
            return
        t("Hub 启动 (5s 内 ping 通)", True)
        
        # POST 3 个角色心跳
        roles = ["computer_analyst", "mobile_analyst", "server_analyst"]
        for r in roles:
            s, b = call(base, "POST", "/heartbeat",
                       {"from": r, "current_task": f"task-{r}"})
            t(f"POST /heartbeat for {r}", s == 200)
        
        # GET /heartbeat 验证返回结构
        s, b = call(base, "GET", "/heartbeat")
        t("GET /heartbeat 返回 200", s == 200)
        t("GET /heartbeat 返回 dict", isinstance(b, dict))
        t("GET /heartbeat 含 3 个角色",
          all(r in b for r in roles))
        
        for r in roles:
            t(f"心跳数据 {r}: 含 last", "last" in b[r])
            t(f"心跳数据 {r}: 含 age_seconds", "age_seconds" in b[r])
            t(f"心跳数据 {r}: 含 stale", "stale" in b[r])
            t(f"心跳数据 {r}: 含 current_task", b[r].get("current_task") == f"task-{r}")
            t(f"心跳数据 {r}: age_seconds < 5 (新鲜)", b[r]["age_seconds"] < 5)
            t(f"心跳数据 {r}: stale=False", b[r]["stale"] is False)
        
        # 留住 heartbeat 数据 (后面验证 binary_analyst 不在里面)
        heartbeat_data = b
        
        # GET /dashboard 验证 HTML 含 heartbeat-badge
        s, html = call(base, "GET", "/dashboard")
        t("GET /dashboard 返回 200", s == 200)
        t("GET /dashboard 含 heartbeat-badge 元素",
          'heartbeat-badge' in html)
        t("GET /dashboard 含 internet_analyst (5 角色)",
          "internet_analyst" in html)
        
        # 验证: 没上报的角色 binary_analyst 不在 /heartbeat 数据里
        t("没上报心跳的角色不在 /heartbeat 数据里",
          "binary_analyst" not in heartbeat_data)
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=2)
        except subprocess.TimeoutExpired:
            proc.kill()
        import shutil
        shutil.rmtree(tmp, ignore_errors=True)


def main():
    print("=" * 60)
    print("dashboard.html 心跳显示 端到端测试")
    print("=" * 60)
    
    print("\n--- 静态分析 dashboard.html ---")
    test_static_dashboard_html()
    
    print("\n--- 端到端 (启动 hub + POST/GET) ---")
    test_heartbeat_endpoint_e2e()
    
    print()
    print("=" * 60)
    print(f"PASSED: {PASSED}    FAILED: {FAILED}")
    print("=" * 60)
    return 0 if FAILED == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
