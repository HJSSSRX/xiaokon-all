"""
huoyan_adapter.py 测试 — MCP streamable-http 客户端.

策略:
  1. Fake MCP Server (标准库 http.server) 模拟火眼 8477 的 JSON-RPC 协议
  2. 验证完整握手流程: initialize → initialized → tools/list → tools/call
  3. 验证 Mcp-Session-Id header 传递
  4. 验证 probe 能识别就绪 / 未就绪
  5. 验证 cid/case_id 默认值注入
  6. 验证错误处理

Run:
  python3 tests/test_huoyan_adapter.py
"""
from __future__ import annotations

import json
import socket
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

from huoyan_adapter import (  # noqa: E402
    DEFAULT_PORT,
    HuoyanClient,
    HuoyanConfig,
    HuoyanError,
    HuoyanHttpError,
    HuoyanMcpError,
    HuoyanNotRunning,
)

# ─── Fake MCP Server ─────────────────────────────────

FAKE_TOOLS = [
    {
        "name": "data_analysis",
        "description": "数据分析工具",
        "inputSchema": {
            "type": "object",
            "required": ["file_path", "data_cmd"],
            "properties": {"file_path": {"type": "string"}, "data_cmd": {"type": "string"}},
        },
    },
    {
        "name": "ges_data_search",
        "description": "关键词检索",
        "inputSchema": {
            "type": "object",
            "required": ["case_id"],
            "properties": {"case_id": {"type": "integer"}, "keyword": {"type": "string"}},
        },
    },
    {
        "name": "ges_knowledge_qa",
        "description": "知识图谱问答",
        "inputSchema": {
            "type": "object",
            "required": ["case_id", "question"],
            "properties": {"case_id": {"type": "integer"}, "question": {"type": "string"}},
        },
    },
    {
        "name": "vector_search",
        "description": "向量检索",
        "inputSchema": {
            "type": "object",
            "required": ["query", "cid"],
            "properties": {"query": {"type": "string"}, "cid": {"type": "integer"}},
        },
    },
    {
        "name": "outline",
        "description": "目录树",
        "inputSchema": {
            "type": "object",
            "required": ["cid"],
            "properties": {"cid": {"type": "integer"}, "max_depth": {"type": "integer"}},
        },
    },
]

FAKE_SESSION = "test-sess-abc123"


class FakeMcpHandler(BaseHTTPRequestHandler):
    """最小 MCP server mock. 标准 JSON-RPC 2.0 + session header."""

    received: list[dict] = []
    initialized_sent: bool = False  # 是否已收到 notifications/initialized

    def log_message(self, format, *args):
        pass

    def _send_json(self, status: int, obj: dict | None, extra_headers: dict | None = None):
        payload = json.dumps(obj, ensure_ascii=False).encode("utf-8") if obj is not None else b""
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        if extra_headers:
            for k, v in extra_headers.items():
                self.send_header(k, v)
        self.end_headers()
        self.wfile.write(payload)

    def _send_text(self, status: int, text: str):
        data = text.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/plain")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        FakeMcpHandler.received.append({"method": "GET", "path": self.path})
        if self.path == "/ping":
            self._send_json(200, {"message": "pong"})
        else:
            self._send_text(404, "not found")

    def do_POST(self):
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length).decode("utf-8") if length else ""
        body = json.loads(raw) if raw else {}
        session = self.headers.get("Mcp-Session-Id", "")
        FakeMcpHandler.received.append({
            "method": "POST", "path": self.path, "body": body, "session": session,
        })

        if self.path != "/mcp":
            self._send_text(404, "not found")
            return

        rpc_method = body.get("method", "")
        rpc_id = body.get("id")

        # 握手: initialize 分配 session
        if rpc_method == "initialize":
            self._send_json(200, {
                "jsonrpc": "2.0", "id": rpc_id,
                "result": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {"tools": {"listChanged": False}},
                    "serverInfo": {"name": "Fake GoldenEyes MCP", "version": "test-1.0"},
                },
            }, extra_headers={"Mcp-Session-Id": FAKE_SESSION})
            return

        # 通知 (无 id): 202 不带 body
        if rpc_method == "notifications/initialized":
            FakeMcpHandler.initialized_sent = True
            self.send_response(202)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return

        # tools/list
        if rpc_method == "tools/list":
            if not FakeMcpHandler.initialized_sent:
                # 模拟火眼: 没发 initialized 就 tools/list 会报 invalid params
                self._send_json(200, {
                    "jsonrpc": "2.0", "id": rpc_id,
                    "error": {"code": -32602, "message": "Invalid request parameters"},
                })
                return
            self._send_json(200, {
                "jsonrpc": "2.0", "id": rpc_id,
                "result": {"tools": FAKE_TOOLS},
            })
            return

        # tools/call
        if rpc_method == "tools/call":
            params = body.get("params", {})
            name = params.get("name")
            args = params.get("arguments", {})
            self._send_json(200, {
                "jsonrpc": "2.0", "id": rpc_id,
                "result": {"content": [{"type": "text", "text": f"called {name}"}],
                          "echo_args": args},
            })
            return

        # 未知方法
        self._send_json(200, {
            "jsonrpc": "2.0", "id": rpc_id,
            "error": {"code": -32601, "message": f"Method not found: {rpc_method}"},
        })


def free_port() -> int:
    s = socket.socket(); s.bind(("127.0.0.1", 0)); p = s.getsockname()[1]; s.close()
    return p


def start_fake() -> tuple[HTTPServer, threading.Thread, int]:
    port = free_port()
    FakeMcpHandler.received = []
    FakeMcpHandler.initialized_sent = False
    server = HTTPServer(("127.0.0.1", port), FakeMcpHandler)
    th = threading.Thread(target=server.serve_forever, daemon=True)
    th.start()
    for _ in range(20):
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.5): break
        except OSError: time.sleep(0.05)
    return server, th, port


# ─── 测试 ───────────────────────────────────────────

PASSED = 0
FAILED = 0


def t(name: str, cond: bool, msg: str = ""):
    global PASSED, FAILED
    if cond:
        print(f"[OK]   {name}")
        PASSED += 1
    else:
        print(f"[FAIL] {name}  {msg}")
        FAILED += 1


def test_config_defaults():
    cfg = HuoyanConfig()
    t("Config.port 默认 8477 (真实端口)", cfg.port == 8477)
    t("Config.host 默认 127.0.0.1", cfg.host == "127.0.0.1")
    t("Config.timeout 默认 30", cfg.timeout == 30)


def test_config_from_env(set_env):
    set_env("HUOYAN_HOST", "10.0.0.1")
    set_env("HUOYAN_PORT", "9999")
    set_env("HUOYAN_CID", "42")
    cfg = HuoyanConfig.from_env()
    t("Env HUOYAN_HOST 生效", cfg.host == "10.0.0.1")
    t("Env HUOYAN_PORT 生效", cfg.port == 9999)
    t("Env HUOYAN_CID 生效", cfg.default_cid == 42)


def test_ping_not_running():
    cfg = HuoyanConfig(port=free_port())
    hy = HuoyanClient(cfg)
    t("未跑时 ping() 返回 None", hy.ping() is None)


def test_ping_ok(fake):
    _, _, port = fake
    cfg = HuoyanConfig(port=port)
    hy = HuoyanClient(cfg)
    r = hy.ping()
    t("ping 返回 dict", isinstance(r, dict))
    t("ping.message == pong", r.get("message") == "pong")


def test_connect_and_session(fake):
    _, _, port = fake
    cfg = HuoyanConfig(port=port)
    hy = HuoyanClient(cfg)
    info = hy.connect()
    t("connect 返回 session_id", info["session_id"] == FAKE_SESSION)
    t("connect 返回 server_info", info["server_info"]["name"] == "Fake GoldenEyes MCP")
    t("客户端保存了 session", hy._session_id == FAKE_SESSION)
    # 验证通知被发了
    t("发了 notifications/initialized", FakeMcpHandler.initialized_sent)


def test_connect_sends_session_header(fake):
    """后续请求必须带 Mcp-Session-Id header."""
    _, _, port = fake
    cfg = HuoyanConfig(port=port)
    hy = HuoyanClient(cfg)
    hy.connect()
    hy.list_tools()
    # 找到 tools/list 请求, 验证 session header
    calls = [r for r in FakeMcpHandler.received if r.get("body", {}).get("method") == "tools/list"]
    t("tools/list 带了 Mcp-Session-Id header",
      calls and calls[-1]["session"] == FAKE_SESSION)


def test_list_tools(fake):
    _, _, port = fake
    cfg = HuoyanConfig(port=port)
    hy = HuoyanClient(cfg)
    hy.connect()
    tools = hy.list_tools()
    t("list_tools 返回 list", isinstance(tools, list))
    t("list_tools 有 5 个 tool (fake)", len(tools) == 5)
    names = {tt["name"] for tt in tools}
    t("含 ges_knowledge_qa", "ges_knowledge_qa" in names)
    t("含 outline", "outline" in names)


def test_list_tools_fails_without_initialized():
    """没 connect 就 list_tools 应该失败 (initialized 没发)."""
    server, _, port = start_fake()
    try:
        cfg = HuoyanConfig(port=port)
        hy = HuoyanClient(cfg)
        # 只 initialize, 手动跳过 initialized
        hy._mcp_request("initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "test", "version": "1"},
        })
        try:
            hy.list_tools()
            t("skipped initialized → list_tools 会抛 HuoyanMcpError", False, "没抛")
        except HuoyanMcpError as e:
            t("skipped initialized → list_tools 抛 McpError", e.code == -32602)
    finally:
        server.shutdown()


def test_call_tool_echo(fake):
    _, _, port = fake
    cfg = HuoyanConfig(port=port)
    hy = HuoyanClient(cfg)
    hy.connect()
    r = hy.call("ges_knowledge_qa", case_id=1, question="test")
    t("call 返回 dict", isinstance(r, dict))
    t("call.content 存在", "content" in r)
    t("call.echo_args 含 case_id", r["echo_args"]["case_id"] == 1)
    t("call.echo_args 含 question", r["echo_args"]["question"] == "test")


def test_call_default_cid_injection(fake):
    """default_cid 自动注入到没传 cid/case_id 的调用."""
    _, _, port = fake
    cfg = HuoyanConfig(port=port, default_cid=99)
    hy = HuoyanClient(cfg)
    hy.connect()
    r = hy.call("outline", max_depth=2)   # 没传 cid
    t("default_cid 注入成功",
      r["echo_args"].get("cid") == 99)
    t("其他参数不受影响", r["echo_args"].get("max_depth") == 2)


def test_call_none_filtered(fake):
    """None 值应该从 params 里剔除 (MCP schema 不允许 null)."""
    _, _, port = fake
    cfg = HuoyanConfig(port=port)
    hy = HuoyanClient(cfg)
    hy.connect()
    r = hy.ges_data_search(case_id=1, keyword=None, eid=None)
    t("ges_data_search case_id 传了", r["echo_args"].get("case_id") == 1)
    t("keyword=None 被过滤", "keyword" not in r["echo_args"])
    t("eid=None 被过滤", "eid" not in r["echo_args"])


def test_mcp_error(fake):
    """调不存在的 tool → MCP error -32601."""
    _, _, port = fake
    cfg = HuoyanConfig(port=port)
    hy = HuoyanClient(cfg)
    hy.connect()
    # 用 method 走底层测 error 解析
    try:
        hy._mcp_request("unknown/method")
        t("未知方法抛 HuoyanMcpError", False, "没抛")
    except HuoyanMcpError as e:
        t("未知方法抛 HuoyanMcpError", e.code == -32601)


def test_not_running_error():
    cfg = HuoyanConfig(port=free_port())
    hy = HuoyanClient(cfg)
    try:
        hy.connect()
        t("连不通时抛 HuoyanNotRunning", False, "没抛")
    except HuoyanNotRunning:
        t("连不通时抛 HuoyanNotRunning", True)
    except Exception as e:
        t("连不通时抛 HuoyanNotRunning", False,
          f"抛了 {type(e).__name__} 不是 HuoyanNotRunning")


def test_probe_ok(fake):
    _, _, port = fake
    cfg = HuoyanConfig(port=port)
    hy = HuoyanClient(cfg)
    r = hy.probe()
    t("probe.ok = True", r["ok"] is True)
    t("probe.port 正确", r["port"] == port)
    t("probe.server_info 有 name", "name" in r["server_info"])
    t("probe.tools 有 5 个", len(r["tools"]) == 5)


def test_probe_not_ok():
    """probe 所有端口都不通 → ok=False + hint."""
    import huoyan_adapter as ha
    # 临时替换候选端口为纯空闲端口 (避开真实火眼 8477)
    original = ha.CANDIDATE_PORTS
    try:
        ha.CANDIDATE_PORTS = [free_port(), free_port(), free_port()]
        cfg = HuoyanConfig(port=free_port())
        hy = HuoyanClient(cfg)
        r = hy.probe()
        t("probe.ok = False (端口不通)", r["ok"] is False)
        t("probe.hint 有内容", "hint" in r and "火眼" in r["hint"])
        t("probe.checked_ports 非空", len(r["checked_ports"]) > 1)
    finally:
        ha.CANDIDATE_PORTS = original


def test_13_method_wrappers(fake):
    """13 个便利方法的存在性 + 能不能调通 (fake 只 echo args)."""
    _, _, port = fake
    cfg = HuoyanConfig(port=port)
    hy = HuoyanClient(cfg)
    hy.connect()
    method_tests = [
        ("data_analysis", {"file_path": "/x", "data_cmd": "cmd"}),
        ("ges_data_search", {"case_id": 1, "keyword": "x"}),
        ("vector_search", {"query": "x", "cid": 1}),
        ("chat_record_clue", {"case_id": 1, "analysis_focus": "x"}),
        ("ges_knowledge_qa", {"case_id": 1, "question": "x"}),
        ("vfs_ls", {"cid": 1, "path": "/"}),
        ("vfs_glob", {"cid": 1, "pattern": "**/*.db"}),
        ("vfs_read", {"cid": 1, "path": "/x"}),
        ("vfs_grep", {"cid": 1, "pattern": "x", "path": "/"}),
        ("vfs_search", {"cid": 1, "query": "x"}),
        ("vfs_fetch_next", {"cid": 1, "handle_id": "h", "page": 2}),
        ("vfs_outline", {"cid": 1}),
        ("vfs_node_to_path", {"cid": 1, "nid": 10}),
    ]
    for mname, kw in method_tests:
        method = getattr(hy, mname)
        try:
            r = method(**kw)
            t(f"{mname}({', '.join(kw.keys())})", isinstance(r, dict))
        except Exception as e:
            t(f"{mname}({', '.join(kw.keys())})", False, str(e)[:80])


# ─── helpers ───────────────────────────────────────

import os

_env_backup: dict[str, str | None] = {}


def set_env(key: str, value: str):
    _env_backup.setdefault(key, os.environ.get(key))
    os.environ[key] = value


def restore_env():
    for k, v in _env_backup.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v
    _env_backup.clear()


def main():
    print("=" * 60)
    print("huoyan_adapter.py 测试 (真实 MCP 协议)")
    print("=" * 60)

    print("\n--- Config ---")
    test_config_defaults()
    test_config_from_env(set_env)
    restore_env()

    print("\n--- ping (未起) ---")
    test_ping_not_running()

    print("\n--- 起 fake MCP server ---")
    server, th, port = start_fake()
    fake = (server, th, port)
    try:
        print("\n--- ping ---")
        test_ping_ok(fake)

        print("\n--- MCP 握手 ---")
        test_connect_and_session(fake)
        test_connect_sends_session_header(fake)

        print("\n--- list_tools ---")
        test_list_tools(fake)
    finally:
        server.shutdown()

    print("\n--- list_tools 握手不全 ---")
    test_list_tools_fails_without_initialized()

    server, th, port = start_fake()
    fake = (server, th, port)
    try:
        print("\n--- tools/call ---")
        test_call_tool_echo(fake)
        test_call_default_cid_injection(fake)
        test_call_none_filtered(fake)

        print("\n--- 错误处理 ---")
        test_mcp_error(fake)
    finally:
        server.shutdown()

    print("\n--- connect 连不通 ---")
    test_not_running_error()

    server, th, port = start_fake()
    fake = (server, th, port)
    try:
        print("\n--- probe ---")
        test_probe_ok(fake)
    finally:
        server.shutdown()

    print("\n--- probe 未就绪 ---")
    test_probe_not_ok()

    server, th, port = start_fake()
    fake = (server, th, port)
    try:
        print("\n--- 13 个便利方法 ---")
        test_13_method_wrappers(fake)
    finally:
        server.shutdown()

    print()
    print("=" * 60)
    print(f"PASSED: {PASSED}    FAILED: {FAILED}")
    print("=" * 60)
    return 0 if FAILED == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
