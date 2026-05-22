r"""
Huoyan (GoldenEyes V4) Adapter — 标准 MCP 客户端

# 真实协议 (实地探测 2026-05-09)

火眼主进程 goldeneyes.exe 在 127.0.0.1:8477 直接暴露 **标准 MCP 协议**:
    - Transport: streamable-http (MCP 2024-11-05 规范)
    - Format:    JSON-RPC 2.0
    - Session:   initialize 时服务器分配 Mcp-Session-Id, 后续请求带 header
    - Endpoint:  POST /mcp   (GET /ping 返回 pong 是健康检查)
    - ServerInfo: "GoldenEyes MCP Server"

# 13 个暴露的 tools (真实签名, 从 tools/list 拿到)

核心取证:
    data_analysis      (file_path, data_cmd)
    ges_data_search    (case_id, keyword?, eid?, start_time?, end_time?)
    vector_search      (query, cid, timerange?, max_results?, top_k?, ...)
    chat_record_clue   (case_id, analysis_focus, ...)
    ges_knowledge_qa   (case_id, question, eid?)

VFS (把案件证据抽象成文件系统):
    ls         (cid, path?, file_type?, name_pattern?, sort_by?, limit?)
    glob       (cid, pattern, base_path?, limit?)
    read       (cid, path, offset?, limit?, columns?, filters?)
    grep       (cid, pattern, path, case_sensitive?, recursive?, limit?)
    search     (cid, query, path?, file_types?, search_mode?, limit?)
    fetch_next (cid, handle_id, page, page_size?)
    outline    (cid, path?, max_depth?)
    node_to_path (cid, nid)

# 用法 (Python)

    from huoyan_adapter import HuoyanClient
    hy = HuoyanClient()              # 默认连 127.0.0.1:8477
    hy.connect()                     # initialize + notifications/initialized
    tools = hy.list_tools()          # 返回 13 个 tool 的完整定义
    r = hy.call("ges_knowledge_qa", case_id=1, question="李安弘的邮箱")
    r = hy.call("ges_data_search", case_id=1, keyword="黄金")
    r = hy.call("outline", cid=1, max_depth=3)

# 用法 (CLI)

    python3 huoyan_adapter.py probe              # 握手 + 列 tool
    python3 huoyan_adapter.py call ges_knowledge_qa --case-id 1 --question "李安弘的邮箱"
    python3 huoyan_adapter.py outline --cid 1

# 关键点

1. 所有 tool 都需要 cid 或 case_id (当前打开的案件 ID, 未知时默认试 1)
2. MCP 协议必须先 initialize (拿 session) → notifications/initialized → 才能 tools/list / tools/call
3. 响应里可能含 SSE 流, 但标准 Request 一次性拿全, 不需要 event parser

Author: AutoForensicAI v0.5 (重写 2026-05-09)
"""
from __future__ import annotations

import argparse
import json
import os
import socket
import sys
from dataclasses import dataclass
from typing import Any
from urllib import error as urlerror
from urllib import request as urlreq


# ─── 常量 ─────────────────────────────────────────────

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8477                # goldeneyes.exe 主进程真实监听端口
CANDIDATE_PORTS = [8477, 8478, 8001, 9112, 8002]  # 扫描兜底
MCP_PATH = "/mcp"
PING_PATH = "/ping"
DEFAULT_TIMEOUT = 30               # GES 向量/图谱查询可能慢
MCP_PROTOCOL = "2024-11-05"
CLIENT_NAME = "AutoForensicAI"
CLIENT_VERSION = "0.5"


# ─── 异常 ───────────────────────────────────────────

class HuoyanError(Exception):
    """Huoyan adapter 通用异常."""
    pass


class HuoyanNotRunning(HuoyanError):
    """目标端口未监听或非火眼 MCP."""
    pass


class HuoyanHttpError(HuoyanError):
    """HTTP 非 2xx."""
    def __init__(self, status: int, detail: str = ""):
        super().__init__(f"HTTP {status}: {detail}")
        self.status = status
        self.detail = detail


class HuoyanMcpError(HuoyanError):
    """MCP JSON-RPC 错误 (code, message)."""
    def __init__(self, code: int, message: str, data: Any = None):
        super().__init__(f"MCP error {code}: {message}")
        self.code = code
        self.message = message
        self.data = data


# ─── 配置 ─────────────────────────────────────────────

@dataclass
class HuoyanConfig:
    host: str = DEFAULT_HOST
    port: int = DEFAULT_PORT
    timeout: int = DEFAULT_TIMEOUT
    # 案件 ID (当前打开的 case)  用户/AI 需要告知
    default_cid: int | None = None
    # 火眼安装根 (仅供指引文本用)
    huoyan_root: str = r"D:\ffffffff\fireeyes"
    case_root: str = r"E:\fffff-TEMP"

    @property
    def base_url(self) -> str:
        return f"http://{self.host}:{self.port}"

    @classmethod
    def from_env(cls) -> "HuoyanConfig":
        cfg = cls()
        if v := os.environ.get("HUOYAN_HOST"): cfg.host = v
        if v := os.environ.get("HUOYAN_PORT"): cfg.port = int(v)
        if v := os.environ.get("HUOYAN_TIMEOUT"): cfg.timeout = int(v)
        if v := os.environ.get("HUOYAN_CID"): cfg.default_cid = int(v)
        if v := os.environ.get("HUOYAN_ROOT"): cfg.huoyan_root = v
        if v := os.environ.get("HUOYAN_CASE_ROOT"): cfg.case_root = v
        return cfg


# ─── 主客户端 ───────────────────────────────────────

class HuoyanClient:
    """
    火眼 MCP 客户端 (streamable-http, JSON-RPC 2.0).
    
    生命周期:
        hy = HuoyanClient()
        hy.connect()              # initialize + notifications/initialized
        hy.list_tools()           # 可用后才能列 tool
        hy.call(name, **params)   # 调 tool
        hy.close()                # (可选) 释放 session
    """

    def __init__(self, config: HuoyanConfig | None = None):
        self.cfg = config or HuoyanConfig.from_env()
        self._session_id: str | None = None
        self._server_info: dict | None = None
        self._capabilities: dict | None = None
        self._next_id: int = 1

    # ─── 低层: socket + HTTP ────────────────────────

    @staticmethod
    def is_port_open(host: str, port: int, timeout: float = 1.0) -> bool:
        try:
            with socket.create_connection((host, port), timeout=timeout):
                return True
        except (socket.timeout, ConnectionRefusedError, OSError):
            return False

    def _http_request(self, method: str, path: str, body: Any = None,
                     extra_headers: dict | None = None) -> tuple[int, dict, str]:
        """发 HTTP, 返回 (status, headers, text)."""
        url = self.cfg.base_url + path
        data = None
        headers = {}
        if body is not None:
            data = json.dumps(body).encode("utf-8")
            headers["Content-Type"] = "application/json"
            headers["Accept"] = "application/json, text/event-stream"
        if self._session_id and path == MCP_PATH:
            headers["Mcp-Session-Id"] = self._session_id
        if extra_headers:
            headers.update(extra_headers)

        req = urlreq.Request(url, data=data, method=method, headers=headers)
        try:
            with urlreq.urlopen(req, timeout=self.cfg.timeout) as resp:
                return resp.status, dict(resp.headers), resp.read().decode("utf-8", errors="replace")
        except urlerror.HTTPError as e:
            # 读错误响应体, 方便排障
            try:
                detail = e.read().decode("utf-8", errors="replace")
            except Exception:
                detail = str(e)
            raise HuoyanHttpError(e.code, detail) from e
        except urlerror.URLError as e:
            if isinstance(e.reason, ConnectionRefusedError):
                raise HuoyanNotRunning(
                    f"连不上 {url} - goldeneyes 主程序未运行或未开 MCP 服务") from e
            raise HuoyanError(f"URLError: {e}") from e

    # ─── MCP 协议层 ────────────────────────────────

    def _next_request_id(self) -> int:
        i = self._next_id
        self._next_id += 1
        return i

    def _mcp_request(self, method: str, params: dict | None = None) -> dict:
        """发一个 JSON-RPC request (带 id), 返回 result dict."""
        body = {
            "jsonrpc": "2.0",
            "id": self._next_request_id(),
            "method": method,
        }
        if params is not None:
            body["params"] = params

        status, headers, text = self._http_request("POST", MCP_PATH, body)

        # initialize 时服务器回 Mcp-Session-Id header, 捕获
        if method == "initialize":
            sid = headers.get("Mcp-Session-Id") or headers.get("mcp-session-id")
            if sid:
                self._session_id = sid

        # 解析 JSON-RPC 响应
        try:
            resp = json.loads(text)
        except json.JSONDecodeError:
            # SSE 流可能以 "data: {...}" 格式返回, 简易剥离
            for line in text.splitlines():
                line = line.strip()
                if line.startswith("data:"):
                    try:
                        resp = json.loads(line[5:].strip())
                        break
                    except Exception:
                        continue
            else:
                raise HuoyanError(f"无法解析响应: {text[:200]}")

        if "error" in resp:
            err = resp["error"]
            raise HuoyanMcpError(err.get("code", -1),
                                 err.get("message", ""),
                                 err.get("data"))
        return resp.get("result", {})

    def _mcp_notify(self, method: str, params: dict | None = None) -> None:
        """发一个 JSON-RPC notification (无 id), 不等响应."""
        body = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            body["params"] = params
        # 通知类请求, 服务器返 202, 错误一般不抛
        try:
            self._http_request("POST", MCP_PATH, body)
        except HuoyanHttpError:
            pass  # 202 以外的状态也可能被 urllib 当 error, 忽略

    # ─── 握手 / 生命周期 ─────────────────────────────

    def ping(self) -> dict | None:
        """GET /ping 健康检查. 返回 {'message': 'pong'} 或 None (超时)."""
        try:
            status, _, text = self._http_request("GET", PING_PATH)
            if status == 200:
                return json.loads(text)
        except Exception:
            pass
        return None

    def connect(self) -> dict:
        """
        完整 MCP 握手:
          1. initialize  → 拿 session_id + serverInfo
          2. notifications/initialized → 告诉服务器可以开始 tools/call
        返回: {'session_id': ..., 'server_info': ..., 'capabilities': ...}
        """
        init_result = self._mcp_request("initialize", {
            "protocolVersion": MCP_PROTOCOL,
            "capabilities": {},
            "clientInfo": {"name": CLIENT_NAME, "version": CLIENT_VERSION},
        })
        self._server_info = init_result.get("serverInfo", {})
        self._capabilities = init_result.get("capabilities", {})

        # 必须发 initialized 通知, 否则 tools/* 会报 invalid params
        self._mcp_notify("notifications/initialized")

        return {
            "session_id": self._session_id,
            "server_info": self._server_info,
            "capabilities": self._capabilities,
        }

    def probe(self, verbose: bool = False) -> dict:
        """
        自动探测:
          1. 扫 候选端口 TCP 连通性
          2. 第一个通的 GET /ping 看是不是火眼
          3. 完整 connect() 握手 + list_tools()
        """
        candidates = [self.cfg.port] + [p for p in CANDIDATE_PORTS if p != self.cfg.port]
        for port in candidates:
            if not self.is_port_open(self.cfg.host, port):
                if verbose: print(f"  [×] {self.cfg.host}:{port} TCP 未监听")
                continue

            # 临时切到这个 port 做一次握手
            saved = self.cfg.port
            self.cfg.port = port
            try:
                pong = self.ping()
                if pong and pong.get("message") == "pong":
                    if verbose: print(f"  [✓] {self.cfg.host}:{port} /ping ok")
                    info = self.connect()
                    tools = self.list_tools()
                    if verbose:
                        name = info["server_info"].get("name", "?")
                        print(f"  [✓] {self.cfg.host}:{port} MCP ok: {name}, {len(tools)} tools")
                    return {
                        "ok": True,
                        "host": self.cfg.host,
                        "port": port,
                        "server_info": info["server_info"],
                        "session_id": info["session_id"],
                        "tools": tools,
                    }
                else:
                    if verbose: print(f"  [~] {self.cfg.host}:{port} 没回 pong, 不是火眼")
            except Exception as e:
                if verbose: print(f"  [~] {self.cfg.host}:{port} 握手失败: {type(e).__name__}: {e}")
            finally:
                if not self._session_id:
                    self.cfg.port = saved  # 失败回滚

        return {
            "ok": False,
            "checked_ports": candidates,
            "hint": (
                "火眼 MCP 未就绪. 检查:\n"
                "  1. 启动 GoldenEyesV4.exe 并登录\n"
                "     账号: myirce123456@126.com, 密码: wuyi@2026\n"
                "  2. 打开 (或创建) 一个案件 (位于 E:\\fffff-TEMP 下)\n"
                "  3. 火眼主界面等案件解析完\n"
                "  4. 确认 goldeneyes.exe 进程在 127.0.0.1:8477 监听"
            ),
        }

    # ─── 标准 MCP 方法 ─────────────────────────────

    def list_tools(self) -> list[dict]:
        """tools/list. 返回 tool 定义数组."""
        r = self._mcp_request("tools/list", {})
        return r.get("tools", [])

    def call(self, tool_name: str, **params) -> dict:
        """
        tools/call. 调用具体工具.
        
        特殊处理: case_id / cid 未传时自动用 cfg.default_cid.
        """
        schema_keys = ("case_id", "cid")
        if not any(k in params for k in schema_keys) and self.cfg.default_cid is not None:
            # 先给 cid, 如果 tool 不接受 cid 再改 case_id (简易启发)
            params["cid"] = self.cfg.default_cid

        # 把 None 值去掉 (有些 tool schema 不允许 null)
        params = {k: v for k, v in params.items() if v is not None}

        return self._mcp_request("tools/call", {
            "name": tool_name,
            "arguments": params,
        })

    # ─── 便利封装 (13 个 tool 的高层包装) ─────────

    def data_analysis(self, file_path: str, data_cmd: str) -> dict:
        return self.call("data_analysis", file_path=file_path, data_cmd=data_cmd)

    def ges_data_search(self, case_id: int, keyword: str | None = None,
                       eid: int | None = None,
                       start_time: str | None = None,
                       end_time: str | None = None) -> dict:
        return self.call("ges_data_search", case_id=case_id,
                        keyword=keyword, eid=eid,
                        start_time=start_time, end_time=end_time)

    def vector_search(self, query: str, cid: int | None = None,
                     timerange: str | None = None,
                     max_results: int = 10, top_k: int = 20,
                     rerank_top_k: int = 10,
                     rerank_threshold: float = 0.025) -> dict:
        return self.call("vector_search", query=query, cid=cid,
                        timerange=timerange, max_results=max_results,
                        top_k=top_k, rerank_top_k=rerank_top_k,
                        rerank_threshold=rerank_threshold)

    def chat_record_clue(self, case_id: int, analysis_focus: str,
                        **kwargs) -> dict:
        return self.call("chat_record_clue", case_id=case_id,
                        analysis_focus=analysis_focus, **kwargs)

    def ges_knowledge_qa(self, case_id: int, question: str,
                        eid: int | None = None) -> dict:
        return self.call("ges_knowledge_qa", case_id=case_id,
                        question=question, eid=eid)

    # VFS
    def vfs_ls(self, cid: int, path: str = "/", **kwargs) -> dict:
        return self.call("ls", cid=cid, path=path, **kwargs)

    def vfs_glob(self, cid: int, pattern: str, **kwargs) -> dict:
        return self.call("glob", cid=cid, pattern=pattern, **kwargs)

    def vfs_read(self, cid: int, path: str, **kwargs) -> dict:
        return self.call("read", cid=cid, path=path, **kwargs)

    def vfs_grep(self, cid: int, pattern: str, path: str = "/",
                **kwargs) -> dict:
        return self.call("grep", cid=cid, pattern=pattern, path=path, **kwargs)

    def vfs_search(self, cid: int, query: str, **kwargs) -> dict:
        return self.call("search", cid=cid, query=query, **kwargs)

    def vfs_fetch_next(self, cid: int, handle_id: str, page: int,
                      page_size: int | None = None) -> dict:
        return self.call("fetch_next", cid=cid, handle_id=handle_id,
                        page=page, page_size=page_size)

    def vfs_outline(self, cid: int, path: str = "/", max_depth: int = 3) -> dict:
        return self.call("outline", cid=cid, path=path, max_depth=max_depth)

    def vfs_node_to_path(self, cid: int, nid: int) -> dict:
        return self.call("node_to_path", cid=cid, nid=nid)


# 给旧代码提供别名 (有的地方叫 HuoyanAdapter)
HuoyanAdapter = HuoyanClient


# ─── CLI ─────────────────────────────────────────────

def cmd_probe(hy: HuoyanClient, args) -> int:
    print(f"Huoyan adapter v0.5 (MCP streamable-http)")
    print(f"候选端口: {[hy.cfg.port] + [p for p in CANDIDATE_PORTS if p != hy.cfg.port]}\n")
    r = hy.probe(verbose=True)
    if r["ok"]:
        print(f"\n✓ 火眼 MCP 已就绪")
        print(f"  服务器: {r['server_info'].get('name', '?')}")
        print(f"  端口:   {r['host']}:{r['port']}")
        print(f"  Session: {r['session_id']}")
        print(f"\n  {len(r['tools'])} 个 tool 可用:")
        for t in r["tools"]:
            req = t.get("inputSchema", {}).get("required", [])
            print(f"    · {t['name']:<20s}  required={req}")
        return 0
    print(f"\n✗ 火眼未就绪\n\n{r['hint']}")
    return 1


def cmd_list(hy: HuoyanClient, args) -> int:
    info = hy.connect()
    print(f"Server: {info['server_info'].get('name', '?')}  Session: {info['session_id']}")
    tools = hy.list_tools()
    for t in tools:
        schema = t.get("inputSchema", {})
        props = schema.get("properties", {})
        required = schema.get("required", [])
        print(f"\n{t['name']}")
        print(f"  desc: {t.get('description','').splitlines()[0][:100]}")
        for p, spec in props.items():
            star = "*" if p in required else " "
            desc = spec.get("description", "")[:60]
            print(f"  {star} {p}: {desc}")
    return 0


def cmd_call(hy: HuoyanClient, args) -> int:
    """通用 call. 从命令行拿 tool 名 + kwargs."""
    hy.connect()
    # 解析 --key value 形式的参数
    params = {}
    i = 0
    while i < len(args.params):
        arg = args.params[i]
        if arg.startswith("--"):
            key = arg[2:].replace("-", "_")
            val = args.params[i + 1] if i + 1 < len(args.params) else ""
            # 尝试转 int / float / json
            if val.isdigit():
                val = int(val)
            elif val.startswith("{") or val.startswith("["):
                try: val = json.loads(val)
                except Exception: pass
            params[key] = val
            i += 2
        else:
            i += 1
    r = hy.call(args.tool, **params)
    print(json.dumps(r, ensure_ascii=False, indent=2))
    return 0


def cmd_config(hy: HuoyanClient, args) -> int:
    print(f"Huoyan config:")
    print(f"  host:         {hy.cfg.host}")
    print(f"  port:         {hy.cfg.port}")
    print(f"  timeout:      {hy.cfg.timeout}s")
    print(f"  default_cid:  {hy.cfg.default_cid or '(未设)'}")
    print(f"  huoyan_root:  {hy.cfg.huoyan_root}")
    print(f"  case_root:    {hy.cfg.case_root}")
    print()
    print("环境变量 (覆盖默认):")
    print("  HUOYAN_HOST / HUOYAN_PORT / HUOYAN_TIMEOUT / HUOYAN_CID")
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description="火眼 V4 MCP 客户端")
    p.add_argument("--host", default=DEFAULT_HOST)
    p.add_argument("--port", type=int, default=DEFAULT_PORT)
    p.add_argument("--cid", type=int, default=None, help="默认 case ID")

    sub = p.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("probe", help="自检 + 握手 + 列 tool")
    sp.set_defaults(func=cmd_probe)

    sp = sub.add_parser("list", help="列所有 tool 详细签名")
    sp.set_defaults(func=cmd_list)

    sp = sub.add_parser("call", help="调任意 tool")
    sp.add_argument("tool", help="tool 名, 如 ges_knowledge_qa")
    sp.add_argument("params", nargs="*",
                   help="--key value 形式参数, 支持 int/json 自动转换")
    sp.set_defaults(func=cmd_call)

    sp = sub.add_parser("config", help="显示配置")
    sp.set_defaults(func=cmd_config)

    args = p.parse_args()

    cfg = HuoyanConfig.from_env()
    if args.host != DEFAULT_HOST: cfg.host = args.host
    if args.port != DEFAULT_PORT: cfg.port = args.port
    if args.cid is not None: cfg.default_cid = args.cid

    hy = HuoyanClient(cfg)
    try:
        return args.func(hy, args)
    except HuoyanError as e:
        print(f"[{type(e).__name__}] {e}", file=sys.stderr)
        return 2
    except Exception as e:
        print(f"[Error] {type(e).__name__}: {e}", file=sys.stderr)
        return 3


if __name__ == "__main__":
    sys.exit(main())
