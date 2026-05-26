#!/usr/bin/env python3
"""SPA 爬虫 — 通过 Chrome CDP 提取 Vue/React 单页应用的完整数据。

整合 tools/browser/ 的所有 CDP 交互能力，为喂食者提供：
- 网络拦截: 捕获已认证的 API 响应（解决 CORS + 登录态问题）
- 框架状态提取: Vuex store, Vue Router routes, React state
- Cookie 提取: 复用浏览器登录态
- DOM 交互: 点击、导航、表单填写
- 自动爬取: 按路由遍历 SPA，收集所有 API 数据
"""
from __future__ import annotations

import json
import time
import urllib.request
from typing import Any, Callable, Optional

import websocket


CDP_DEFAULT = "http://127.0.0.1:9222"


# ── 工具函数 ────────────────────────────────────────────────────────────

def _fetch_json(url: str) -> dict:
    with urllib.request.urlopen(url) as resp:
        return json.loads(resp.read().decode())


# ── 主类 ────────────────────────────────────────────────────────────────

class SpaCrawler:
    """通过 Chrome CDP 爬取 SPA 应用的结构化数据。

    使用前需启动 Chrome 并开启调试端口:
        chrome.exe --remote-debugging-port=9222 --remote-allow-origins=*

    核心能力:
        - api_intercept(url_fragment, route) → 拦截指定路由触发的 API 响应
        - extract_vuex_state() → 完整 Vuex store 状态
        - extract_router_routes() → Vue Router 路由表
        - extract_cookies() → 所有浏览器 Cookie
        - click_text(text) → 按文本点击元素
        - evaluate(js) → 在页面中执行任意 JS
        - navigate(route) → Vue Router 导航
    """

    def __init__(self, cdp_url: str = CDP_DEFAULT, timeout: int = 30):
        self.cdp_url = cdp_url.rstrip("/")
        self.timeout = timeout
        self._ws: Optional[websocket.WebSocket] = None
        self._msg_id = 0
        self._current_tab: Optional[dict] = None

    # ── 连接管理 ──────────────────────────────────────────────────────

    @property
    def is_ready(self) -> bool:
        """检查 CDP 服务是否可用。"""
        try:
            resp = urllib.request.urlopen(f"{self.cdp_url}/json/version", timeout=3)
            return resp.status == 200
        except Exception:
            return False

    def list_tabs(self) -> list[dict]:
        """列出所有打开的标签页。"""
        return _fetch_json(f"{self.cdp_url}/json")

    def find_tab(self, url_fragment: str) -> Optional[dict]:
        """查找 URL 包含指定片段的标签页。"""
        tabs = self.list_tabs()
        for t in tabs:
            if t.get("type") == "page" and url_fragment in t.get("url", "").lower():
                return t
        return None

    def connect(self, url_fragment: str) -> bool:
        """连接到匹配 URL 片段的标签页。"""
        tab = self.find_tab(url_fragment)
        if not tab:
            print(f"[SpaCrawler] 未找到匹配 '{url_fragment}' 的标签页")
            return False
        self._current_tab = tab
        ws_url = tab.get("webSocketDebuggerUrl")
        if not ws_url:
            print("[SpaCrawler] 标签页无 WebSocket URL")
            return False
        self._ws = websocket.create_connection(ws_url, timeout=self.timeout)
        self._msg_id = 0
        self._enable_domains()
        print(f"[SpaCrawler] 已连接: {tab['title'][:80]}")
        return True

    def _enable_domains(self):
        """启用必要的 CDP 域。"""
        for domain in ["Runtime", "Page", "Network", "DOM"]:
            self._send(f"{domain}.enable")
        time.sleep(0.3)
        # 清空启动消息
        while True:
            msg = self._recv_any(0.2)
            if msg is None:
                break

    def close(self):
        if self._ws:
            self._ws.close()
            self._ws = None

    # ── CDP 通信 ──────────────────────────────────────────────────────

    def _send(self, method: str, params: dict = None, msg_id: int = None):
        if msg_id is None:
            self._msg_id += 1
            msg_id = self._msg_id
        self._ws.send(json.dumps({"id": msg_id, "method": method, "params": params or {}}))
        return msg_id

    def _recv_any(self, timeout: float = 0.5) -> Optional[dict]:
        """接收任意消息（带超时）。"""
        try:
            self._ws.settimeout(timeout)
            return json.loads(self._ws.recv())
        except websocket.WebSocketTimeoutException:
            return None
        except Exception:
            return None

    def _recv_response(self, msg_id: int, timeout: float = 10) -> Optional[dict]:
        """等待指定 ID 的响应。"""
        deadline = time.time() + timeout
        while time.time() < deadline:
            self._ws.settimeout(max(0.3, deadline - time.time()))
            try:
                msg = json.loads(self._ws.recv())
                if msg.get("id") == msg_id:
                    return msg.get("result", {})
            except websocket.WebSocketTimeoutException:
                break
            except Exception:
                break
        return None

    def evaluate(self, expression: str, await_promise: bool = False,
                 timeout: float = 12) -> Any:
        """在页面中执行 JavaScript 并返回结果。

        Args:
            expression: JS 表达式或 IIFE
            await_promise: 是否等待 Promise 完成
            timeout: 超时秒数

        Returns:
            返回值（primitive / dict / list），失败返回 None
        """
        mid = self._send("Runtime.evaluate", {
            "expression": expression,
            "returnByValue": True,
            "awaitPromise": await_promise,
        })
        result = self._recv_response(mid, timeout)
        if not result:
            return None
        inner = result.get("result", {})
        if inner.get("subtype") == "error":
            print(f"[SpaCrawler] JS error: {inner.get('description', '')[:200]}")
            return None
        return inner.get("value")

    # ── SPA 导航 ──────────────────────────────────────────────────────

    def navigate(self, url: str):
        """通过 Page.navigate 跳转。"""
        self._send("Page.navigate", {"url": url})
        time.sleep(2)

    def router_push(self, route: str) -> bool:
        """通过 Vue Router 导航（SPA 内部跳转）。

        Args:
            route: Vue Router 路径，如 '/skilltree'

        Returns:
            是否导航成功
        """
        result = self.evaluate(f"""
            (function() {{
                var app = document.querySelector('#app');
                if (app && app.__vue__ && app.__vue__.$router) {{
                    app.__vue__.$router.push('{route}');
                    return true;
                }}
                return false;
            }})()
        """)
        time.sleep(1.5)
        return bool(result)

    # ── Cookie 提取 ───────────────────────────────────────────────────

    def extract_cookies(self, domain_filter: str = None) -> dict[str, str]:
        """提取浏览器中的所有 / 指定域名的 Cookie。

        Returns:
            {name: value, ...}
        """
        mid = self._send("Network.getAllCookies")
        result = self._recv_response(mid, 5)
        if not result:
            return {}

        cookies = result.get("cookies", [])
        jar = {}
        for c in cookies:
            domain = c.get("domain", "")
            if domain_filter and domain_filter not in domain:
                continue
            jar[c["name"]] = c["value"]
        return jar

    # ── 框架状态提取 ──────────────────────────────────────────────────

    def extract_vuex_state(self) -> Optional[dict]:
        """提取 Vuex store 完整状态（序列化安全）。"""
        result = self.evaluate("""
            (function() {
                var app = document.querySelector('#app');
                if (!app || !app.__vue__ || !app.__vue__.$store) return null;
                var state = app.__vue__.$store.state;
                return JSON.parse(JSON.stringify(state, function(key, val) {
                    if (typeof val === 'function') return undefined;
                    if (val && val._isVue) return undefined;
                    return val;
                }));
            })()
        """, timeout=15)
        return result

    def extract_router_routes(self) -> list[dict]:
        """提取 Vue Router 路由表。"""
        result = self.evaluate("""
            (function() {
                var app = document.querySelector('#app');
                if (!app || !app.__vue__ || !app.__vue__.$router) return null;
                var routes = app.__vue__.$router.options.routes || [];
                return routes.map(function(r) {
                    return {
                        path: r.path, name: r.name,
                        children: (r.children || []).map(function(c) { return c.path; }),
                        redirect: r.redirect
                    };
                });
            })()
        """, timeout=10)
        return result or []

    def extract_vue_components(self, keyword: str = "") -> list[dict]:
        """搜索 Vue 组件树，找到名称含 keyword 的组件。

        Returns:
            [{"name": ..., "depth": ..., "methods": [...], "dataKeys": [...]}, ...]
        """
        result = self.evaluate(f"""
            (function() {{
                var root = document.querySelector('#app').__vue__;
                if (!root) return [];
                var matches = [];
                (function search(vm, depth) {{
                    if (depth > 6 || !vm) return;
                    var name = (vm.$options && vm.$options.name) || '';
                    if (name.toLowerCase().indexOf('{keyword}') > -1) {{
                        matches.push({{
                            name: name,
                            depth: depth,
                            methods: vm.$options.methods ? Object.keys(vm.$options.methods) : [],
                            dataKeys: vm.$data ? Object.keys(vm.$data).slice(0, 20) : []
                        }});
                    }}
                    if (vm.$children) {{
                        vm.$children.forEach(function(c) {{ search(c, depth + 1); }});
                    }}
                }})(root, 0);
                return matches;
            }})()
        """, timeout=15)
        return result or []

    # ── DOM 交互 ──────────────────────────────────────────────────────

    def dom_query(self, selector: str) -> list[dict]:
        """查询匹配 CSS 选择器的 DOM 元素信息。"""
        result = self.evaluate(f"""
            (function() {{
                var els = document.querySelectorAll('{selector}');
                return Array.from(els).slice(0, 30).map(function(el) {{
                    return {{
                        tag: el.tagName,
                        id: el.id,
                        cls: (el.className || '').slice(0, 60),
                        text: (el.innerText || '').trim().slice(0, 100)
                    }};
                }});
            }})()
        """)
        return result or []

    def click_text(self, text: str) -> str:
        """点击页面上包含指定文本的元素。"""
        result = self.evaluate(f"""
            (function() {{
                var els = document.querySelectorAll('*');
                for (var i = 0; i < els.length; i++) {{
                    if (els[i].children.length === 0 && els[i].innerText.trim() === '{text}') {{
                        els[i].click();
                        return 'clicked: ' + els[i].tagName;
                    }}
                }}
                return 'not found';
            }})()
        """)
        return str(result)

    def click_selector(self, selector: str) -> str:
        """点击匹配 CSS 选择器的第一个元素。"""
        result = self.evaluate(f"""
            (function() {{
                var el = document.querySelector('{selector}');
                if (el) {{ el.click(); return 'clicked'; }}
                return 'not found';
            }})()
        """)
        return str(result)

    def page_text(self, max_chars: int = 5000) -> str:
        """获取页面可见文本。"""
        result = self.evaluate(f"document.body ? document.body.innerText.slice(0, {max_chars}) : ''")
        return str(result or "")

    def page_html(self) -> str:
        """获取页面完整 HTML。"""
        result = self.evaluate("document.documentElement.outerHTML")
        return str(result or "")

    # ── 网络拦截（核心能力）─────────────────────────────────────────────

    def intercept_api(self, url_fragment: str, route: str = None,
                      api_pattern: str = None, timeout: float = 15,
                      include_request_headers: bool = False,
                      away_first: str = "/index") -> dict[str, dict]:
        """拦截 SPA 路由跳转后触发的 API 调用，返回响应数据。

        Args:
            url_fragment: 标签页 URL 匹配片段
            route: Vue Router 路径，导航到此会触发 API 调用
            api_pattern: API URL 匹配模式（如 'getTree'）
            timeout: 最长等待时间
            include_request_headers: 是否同时捕获请求头
            away_first: 先 Page.navigate 到此 URL（强制刷新避免缓存）

        Returns:
            {api_short_name: response_body_string, ...}
        """
        if not self._ws:
            if not self.connect(url_fragment):
                return {}

        # 清空待处理消息
        while self._recv_any(0.2):
            pass

        # 阶段0：离开当前路由，用 Page.navigate 强制刷新确保缓存失效
        if away_first:
            full_url = away_first
            if not full_url.startswith("http"):
                full_url = f"https://www.ctfhub.com/#{away_first}"
            self._send("Page.navigate", {"url": full_url})
            time.sleep(2.5)
            while self._recv_any(0.2):
                pass

        # 阶段1：先发出导航命令（不等待响应，避免 evaluate 的 _recv_response
        # 消费掉 Network 事件），然后在主循环中同时捕获导航响应和 Network 事件。
        route_push_mid = None
        if route:
            self._msg_id += 1
            route_push_mid = self._msg_id
            self._send("Runtime.evaluate", {
                "expression": (
                    "(function(){var app=document.querySelector('#app');"
                    f"if(app&&app.__vue__&&app.__vue__.$router){{"
                    f"app.__vue__.$router.push('{route}');return true;"
                    f"}}return false;}})()"
                ),
                "returnByValue": True,
            }, msg_id=route_push_mid)

        # 阶段2：拦截响应
        # body_requests 映射：body_mid → short_name
        captured = {}
        request_ids = set()
        body_requests = {}

        deadline = time.time() + timeout
        while time.time() < deadline:
            remaining = deadline - time.time()
            if remaining <= 0:
                break
            msg = self._recv_any(min(1.0, remaining))
            if msg is None:
                continue

            msg_id = msg.get("id")
            method = msg.get("method", "")

            # 匹配 body 响应
            if msg_id and msg_id in body_requests:
                body = msg.get("result", {}).get("body", "")
                if body:
                    short = body_requests.pop(msg_id)
                    captured[short] = body
                continue

            # 匹配 route push 响应（忽略）
            if route_push_mid and msg_id == route_push_mid:
                continue

            # 记录请求
            if method == "Network.requestWillBeSent":
                url = msg["params"]["request"]["url"]
                if api_pattern is None or api_pattern.lower() in url.lower():
                    rid = msg["params"]["requestId"]
                    request_ids.add(rid)
                    if include_request_headers:
                        headers = msg["params"]["request"].get("headers", {})
                        short = self._short_api_name(url) + "_req"
                        captured[short] = json.dumps(headers)

            # 捕获响应 → 发出 getResponseBody
            if method == "Network.responseReceived":
                url = msg["params"]["response"]["url"]
                if api_pattern is None or api_pattern.lower() in url.lower():
                    rid = msg["params"]["requestId"]
                    if rid in request_ids:
                        self._msg_id += 1
                        body_mid = self._msg_id
                        short = self._short_api_name(url)
                        body_requests[body_mid] = short
                        self._send("Network.getResponseBody",
                                   {"requestId": rid}, msg_id=body_mid)

        return captured

    def _get_response_body(self, request_id: str, timeout: float = 5) -> Optional[str]:
        """获取网络请求的响应体。"""
        mid = self._send("Network.getResponseBody", {"requestId": request_id})
        result = self._recv_response(mid, timeout)
        if result:
            return result.get("body", "")
        return None

    @staticmethod
    def _short_api_name(url: str) -> str:
        """从完整 URL 提取简短的 API 名称。"""
        if "User_API/" in url:
            return url.split("User_API/")[-1].split("?")[0]
        return url.split("/")[-1].split("?")[0][:40]

    def intercept_all_apis(self, url_fragment: str, routes: list[str],
                           api_pattern: str = "api.", timeout_per_route: float = 12,
                           pre_navigate: str = None) -> dict[str, dict]:
        """遍历多个路由，收集所有 API 响应。

        Args:
            url_fragment: 标签页匹配
            routes: 要访问的 Vue Router 路径列表
            api_pattern: API URL 匹配模式
            timeout_per_route: 每个路由的超时时间
            pre_navigate: 在开始前先导航到此 URL（如 '/index' 加载 SPA 壳）

        Returns:
            {route: {api_name: response_body}}
        """
        if not self._ws:
            if not self.connect(url_fragment):
                return {}

        # 确保 SPA 已加载
        if pre_navigate:
            self.navigate(pre_navigate)
            time.sleep(2)
            while self._recv_any(0.2):
                pass

        all_data = {}
        for route in routes:
            print(f"[SpaCrawler] 抓取路由: {route}")
            data = self.intercept_api(
                url_fragment, route=route,
                api_pattern=api_pattern, timeout=timeout_per_route
            )
            all_data[route] = data

        return all_data

    # ── 页面内容提取 ──────────────────────────────────────────────────

    def extract_page(self, url_fragment: str, route: str = None,
                     pre_navigate: str = "https://www.ctfhub.com/#/index") -> dict:
        """提取 SPA 页面的完整内容（文本、链接、图片、代码块）。

        Args:
            url_fragment: 标签页匹配
            route: 要访问的 Vue Router 路径
            pre_navigate: 先导航至此 URL 加载 SPA 壳

        Returns:
            {"url", "title", "text", "links", "images", "code_blocks"}
        """
        if not self._ws:
            if not self.connect(url_fragment):
                return {"error": "连接失败"}

        if pre_navigate:
            self.navigate(pre_navigate)
            time.sleep(2)
            while self._recv_any(0.2):
                pass

        if route:
            self.router_push(route)
            time.sleep(1)

        title = self.evaluate("document.title") or ""
        text = self.page_text()
        links = self.evaluate("""
            Array.from(document.querySelectorAll('a[href]')).map(function(a) {
                return {text: a.innerText.trim().slice(0, 80), href: a.href};
            }).slice(0, 50)
        """) or []
        images = self.evaluate("""
            Array.from(document.querySelectorAll('img[src]')).map(function(img) {
                return img.src;
            }).slice(0, 30)
        """) or []
        code_blocks = self.evaluate("""
            Array.from(document.querySelectorAll('pre code, pre')).map(function(el) {
                return {code: el.innerText.slice(0, 2000), lang: el.className.replace('language-', '')};
            }).slice(0, 20)
        """) or []

        return {
            "url": route or "",
            "title": title,
            "text": text,
            "links": links,
            "images": images,
            "code_blocks": code_blocks,
        }

    # ── SPA 结构发现 ──────────────────────────────────────────────────

    def discover_structure(self, url_fragment: str,
                           pre_navigate: str = "https://www.ctfhub.com/#/index") -> dict:
        """自动发现 SPA 结构：路由表 + Vuex 模块 + API 端点。

        Returns:
            {"routes": [...], "vuex_modules": [...], "components": [...]}
        """
        if not self._ws:
            if not self.connect(url_fragment):
                return {"error": "连接失败"}

        if pre_navigate:
            self.navigate(pre_navigate)
            time.sleep(3)
            while self._recv_any(0.2):
                pass

        routes = self.extract_router_routes()
        components = self.extract_vue_components("skill") or self.extract_vue_components("tree")

        vuex_info = self.evaluate("""
            (function() {
                var app = document.querySelector('#app');
                if (!app || !app.__vue__ || !app.__vue__.$store) return {};
                var store = app.__vue__.$store;
                var modules = {};
                if (store._modules && store._modules.root) {
                    function walk(mod, name) {
                        var info = {};
                        if (mod._rawModule) {
                            var raw = mod._rawModule;
                            if (raw._children) info.children = Object.keys(raw._children);
                            if (raw._rawModule && raw._rawModule.getters)
                                info.getters = Object.keys(raw._rawModule.getters);
                        }
                        if (mod.state) {
                            try { info.stateKeys = Object.keys(mod.state); } catch(e) {}
                        }
                        if (Object.keys(info).length > 0)
                            modules[name || 'root'] = info;
                        if (mod._children) {
                            Object.keys(mod._children).forEach(function(k) {
                                walk(mod._children[k], name ? name + '/' + k : k);
                            });
                        }
                    }
                    walk(store._modules.root, '');
                }
                return modules;
            })()
        """)

        return {
            "routes": routes,
            "vuex_modules": vuex_info or {},
            "components": components,
        }


# ── CLI ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys

    crawler = SpaCrawler()

    if not crawler.is_ready:
        print("[SpaCrawler] CDP 未就绪。请启动 Chrome:")
        print("  chrome.exe --remote-debugging-port=9222 --remote-allow-origins=*")
        sys.exit(1)

    if len(sys.argv) < 3:
        print("用法: python spa_crawler.py <url_fragment> <action> [args...]")
        print()
        print("Actions:")
        print("  structure              — 发现 SPA 结构（路由+状态+组件）")
        print("  vuex                   — 提取 Vuex store 完整状态")
        print("  routes                 — 提取 Vue Router 路由表")
        print("  cookies                — 提取浏览器 Cookie")
        print("  api <route> <pattern>  — 拦截路由跳转后的 API 响应")
        print("  page <route>           — 提取页面完整内容")
        print("  text                   — 提取页面可见文本")
        print("  eval <js_code>         — 执行 JS 并返回结果")
        print()
        print("示例:")
        print("  python spa_crawler.py ctfhub structure")
        print("  python spa_crawler.py ctfhub api /skilltree getTree")
        print("  python spa_crawler.py ctfhub cookies")
        print("  python spa_crawler.py ctfhub page /challenge")
        sys.exit(1)

    fragment = sys.argv[1]
    action = sys.argv[2]

    if not crawler.connect(fragment):
        print("可用的标签页:")
        for t in crawler.list_tabs():
            print(f"  [{t['type']}] {t.get('title','')[:60]} | {t.get('url','')[:80]}")
        sys.exit(1)

    try:
        if action == "structure":
            result = crawler.discover_structure(fragment)
            print(json.dumps(result, indent=2, ensure_ascii=False))

        elif action == "vuex":
            state = crawler.extract_vuex_state()
            if state:
                print(json.dumps(state, indent=2, ensure_ascii=False)[:10000])
            else:
                print("(无 Vuex 状态)")

        elif action == "routes":
            routes = crawler.extract_router_routes()
            for r in routes:
                print(f"  {r['path']} → {r.get('redirect', '')}")
                if r.get("children"):
                    for c in r["children"]:
                        print(f"    /{c}")

        elif action == "cookies":
            cookies = crawler.extract_cookies()
            for name, value in cookies.items():
                print(f"  {name}={value[:80]}")

        elif action == "api":
            if len(sys.argv) < 5:
                print("用法: python spa_crawler.py <fragment> api <route> <pattern>")
                sys.exit(1)
            route = sys.argv[3]
            pattern = sys.argv[4]
            data = crawler.intercept_api(fragment, route=route, api_pattern=pattern)
            for name, body in data.items():
                print(f"\n=== {name} ({len(body)} bytes) ===")
                try:
                    parsed = json.loads(body)
                    print(json.dumps(parsed, indent=2, ensure_ascii=False)[:5000])
                except Exception:
                    print(body[:2000])

        elif action == "page":
            route = sys.argv[3] if len(sys.argv) > 3 else None
            result = crawler.extract_page(fragment, route=route)
            print(f"标题: {result.get('title')}")
            print(f"文本 ({len(result.get('text', ''))} 字符):")
            print(result.get('text', '')[:3000])

        elif action == "text":
            print(crawler.page_text())

        elif action == "eval":
            if len(sys.argv) < 4:
                print("用法: python spa_crawler.py <fragment> eval <js_code>")
                sys.exit(1)
            code = " ".join(sys.argv[3:])
            result = crawler.evaluate(code)
            print(json.dumps(result, indent=2, ensure_ascii=False)[:5000])

        else:
            print(f"未知操作: {action}")
            sys.exit(1)

    finally:
        crawler.close()
