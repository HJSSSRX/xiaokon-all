#!/usr/bin/env python3
"""方案1: Chrome CDP 渲染器 — 连接用户已有的 Google Chrome 渲染 JS 页面"""
from __future__ import annotations

import asyncio
import json
import subprocess
import sys
from typing import Optional
from urllib.parse import urljoin, urlparse

import requests as rq
from bs4 import BeautifulSoup


# ── Chrome 启动辅助 ──────────────────────────────────────────────────

def launch_chrome_with_debug(port: int = 9222, headless: bool = False) -> subprocess.Popen | None:
    """启动 Google Chrome 并开启远程调试端口。返回 Popen 对象或 None。"""
    chrome_paths = [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "/usr/bin/google-chrome",
        "/usr/bin/chromium-browser",
    ]
    chrome = None
    for p in chrome_paths:
        try:
            from pathlib import Path
            if Path(p).exists():
                chrome = p
                break
        except Exception:
            pass

    if not chrome:
        print("[ChromeCDP] 未找到 Chrome 安装路径，请手动启动：")
        print(f"  chrome.exe --remote-debugging-port={port}")
        return None

    args = [chrome, f"--remote-debugging-port={port}"]
    if headless:
        args.append("--headless=new")
    try:
        proc = subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        print(f"[ChromeCDP] Chrome 已启动 (port={port}, pid={proc.pid})")
        return proc
    except Exception as e:
        print(f"[ChromeCDP] 启动 Chrome 失败: {e}")
        return None


# ── CDP 协议渲染器 ───────────────────────────────────────────────────

class JsRenderer:
    """通过 Chrome DevTools Protocol 连接本地 Chrome 渲染 JS 页面。

    使用前需启动 Chrome 并开启调试端口:
        chrome.exe --remote-debugging-port=9222

    或调用 launch_chrome_with_debug() 自动启动。

    优势:
        - 使用用户已有 Chrome，无需下载 Playwright 浏览器 (~400MB)
        - 复用 Chrome 的 Cookie、登录态、扩展
        - 支持 headless 和 headed 两种模式
    """

    def __init__(self, cdp_host: str = "127.0.0.1", cdp_port: int = 9222,
                 timeout: int = 30, wait_ms: int = 3000):
        self.cdp_base = f"http://{cdp_host}:{cdp_port}"
        self.timeout = timeout
        self.wait_ms = wait_ms

    # ── 连接检测 ────────────────────────────────────────────────────

    @property
    def is_chrome_ready(self) -> bool:
        """检查 Chrome 调试端口是否已就绪。"""
        try:
            resp = rq.get(f"{self.cdp_base}/json/version", timeout=3)
            return resp.status_code == 200
        except Exception:
            return False

    def list_pages(self) -> list[dict]:
        """列出所有打开的页面标签。"""
        try:
            return rq.get(f"{self.cdp_base}/json", timeout=3).json()
        except Exception:
            return []

    def new_page(self, url: str = "about:blank") -> Optional[str]:
        """创建新标签页，返回页面 ID。"""
        try:
            resp = rq.get(f"{self.cdp_base}/json/new?{url}", timeout=5)
            data = resp.json()
            return data.get("id")
        except Exception as e:
            print(f"[ChromeCDP] 创建新页面失败: {e}")
            return None

    # ── 主方法: 渲染页面并提取内容 ─────────────────────────────────

    def fetch(self, url: str, wait_for: Optional[str] = None,
              wait_ms: Optional[int] = None, site_type: str = "auto") -> dict:
        """同步入口：渲染页面并返回结构化内容。"""
        return asyncio.run(self.fetch_async(url, wait_for, wait_ms, site_type))

    async def fetch_async(self, url: str, wait_for: Optional[str] = None,
                          wait_ms: Optional[int] = None, site_type: str = "auto") -> dict:
        """异步入口：连接 Chrome CDP 渲染页面并提取内容。

        Args:
            url: 目标 URL
            wait_for: 等待某个 CSS 选择器出现后再提取（如 ".mindmap-node"）
            wait_ms: 额外等待毫秒数（默认 self.wait_ms）
            site_type: 传给 WebPageParser 的站点类型

        Returns:
            {"url", "title", "content", "text_content", "rendered", "method", ...}
        """
        wait_ms = wait_ms if wait_ms is not None else self.wait_ms
        result = {
            "url": url,
            "title": "",
            "content": "",
            "text_content": "",
            "code_blocks": [],
            "links": [],
            "images": [],
            "rendered": False,
            "method": "chrome_cdp",
            "error": None,
        }

        if not self.is_chrome_ready:
            result["error"] = f"Chrome 调试端口未就绪 ({self.cdp_base})"
            return self._fallback_static(url, result)

        try:
            import websocket

            ws_url = await self._get_page_ws(url)
            if not ws_url:
                result["error"] = "无法获取页面 WebSocket URL"
                return self._fallback_static(url, result)

            html, page_title, text_content = await self._cdp_render(ws_url, url, wait_for, wait_ms)
            soup = BeautifulSoup(html, "html.parser")

            result["title"] = page_title
            result["content"] = html
            result["text_content"] = text_content or JsRenderer._extract_text(html)
            result["code_blocks"] = JsRenderer._extract_code_blocks(html)
            result["links"] = JsRenderer._extract_links(html, url)
            result["images"] = JsRenderer._extract_images(html, url)
            result["rendered"] = True

        except ImportError:
            result["error"] = "缺少 websocket-client 依赖: pip install websocket-client"
            return self._fallback_static(url, result)
        except Exception as e:
            result["error"] = str(e)
            return self._fallback_static(url, result)

        return result

    # ── CDP 核心通信 ────────────────────────────────────────────────

    async def _get_page_ws(self, url: str) -> Optional[str]:
        """获取页面 WebSocket 调试 URL。优先复用已有页面，否则新建。"""
        pages = self.list_pages()

        ws_url = None
        for p in pages:
            if p.get("url") == url or p.get("url") == "about:blank":
                ws_url = p.get("webSocketDebuggerUrl")
                break

        if not ws_url:
            page_id = self.new_page(url)
            if page_id:
                import time
                time.sleep(0.5)
                pages = self.list_pages()
                for p in pages:
                    if p.get("id") == page_id:
                        ws_url = p.get("webSocketDebuggerUrl")
                        break

        return ws_url

    async def _cdp_render(self, ws_url: str, url: str,
                          wait_for: Optional[str], wait_ms: int) -> tuple[str, str, str]:
        """通过 WebSocket 发送 CDP 命令，控制 Chrome 渲染页面。"""
        import websocket

        ws = websocket.WebSocket()
        ws.connect(ws_url, timeout=self.timeout)
        msg_id = 0

        def send(method: str, params: dict | None = None) -> dict:
            nonlocal msg_id
            msg_id += 1
            payload = {"id": msg_id, "method": method, "params": params or {}}
            ws.send(json.dumps(payload))
            return self._recv_result(ws, msg_id)

        def _recv(ws_obj, expected_id: int) -> dict:
            while True:
                raw = ws_obj.recv()
                data = json.loads(raw)
                if data.get("id") == expected_id:
                    return data

        def _recv_result(ws_obj, expected_id):
            while True:
                raw = ws_obj.recv()
                data = json.loads(raw)
                if data.get("id") == expected_id:
                    if "error" in data:
                        raise Exception(data["error"].get("message", str(data["error"])))
                    return data.get("result", {})

        # 1) 启用 Page domain
        send("Page.enable")

        # 2) 导航到目标 URL
        nav_result = send("Page.navigate", {"url": url})

        if "error" in nav_result:
            error_msg = nav_result["error"].get("message", str(nav_result))
            raise Exception(f"导航失败: {error_msg}")

        # 3) 等待页面加载
        send("Page.loadEventFired")

        # 4) 额外等待
        if wait_for:
            send("Runtime.evaluate", {
                "expression": f"""
                new Promise((resolve) => {{
                    const start = Date.now();
                    const maxWait = {wait_ms};
                    const check = () => {{
                        const el = document.querySelector('{wait_for}');
                        if (el) resolve(true);
                        else if (Date.now() - start > maxWait) resolve(false);
                        else setTimeout(check, 200);
                    }};
                    check();
                }})
                """
            })

        import time
        time.sleep(wait_ms / 1000.0)

        # 5) 注入 auto-scroll 确保懒加载内容可见
        send("Runtime.evaluate", {
            "expression": "window.scrollTo(0, document.body.scrollHeight); window.scrollTo(0, 0);"
        })
        time.sleep(0.5)

        # 6) 获取渲染后的 HTML
        doc_result = send("Runtime.evaluate", {
            "expression": "document.documentElement.outerHTML"
        })
        html = doc_result.get("result", {}).get("value", "")
        if not html and "exceptionDetails" in doc_result:
            html = ""

        # 7) 获取纯文本
        title_result = send("Runtime.evaluate", {
            "expression": "document.title"
        })
        title = title_result.get("result", {}).get("value", "")

        text_result = send("Runtime.evaluate", {
            "expression": "document.body ? document.body.innerText : ''"
        })
        text_content = text_result.get("result", {}).get("value", "")

        ws.close()
        return html, title, text_content

    # ── 静态降级 ────────────────────────────────────────────────────

    def _fallback_static(self, url: str, result: dict) -> dict:
        """CDP 不可用时降级为 requests + BS4。"""
        try:
            resp = rq.get(url, timeout=30, headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            })
            soup = BeautifulSoup(resp.text, "html.parser")
            result["title"] = soup.title.string if soup.title else ""
            result["content"] = soup.decode_contents()
            result["text_content"] = soup.get_text(separator="\n", strip=True)
            result["code_blocks"] = JsRenderer._extract_code_blocks(resp.text)
            result["links"] = JsRenderer._extract_links(resp.text, url)
            result["images"] = JsRenderer._extract_images(resp.text, url)
            result["method"] = "static_fallback"
            result["rendered"] = False
        except Exception as e:
            result["error"] = f"{result.get('error', '')}; static_fallback: {e}"
            result["method"] = "failed"
        return result

    # ── 静态工具方法 ─────────────────────────────────────────────────

    @staticmethod
    def _extract_text(html: str) -> str:
        soup = BeautifulSoup(html, "html.parser")
        for tag in soup(["script", "style", "noscript"]):
            tag.decompose()
        return soup.get_text(separator="\n", strip=True)

    @staticmethod
    def _extract_code_blocks(html: str) -> list[dict]:
        soup = BeautifulSoup(html, "html.parser")
        blocks = []
        for pre in soup.find_all("pre"):
            code = pre.find("code")
            lang = ""
            if code and code.get("class"):
                lang = code.get("class", [""])[0].replace("language-", "")
            blocks.append({
                "language": lang,
                "code": code.get_text(strip=True) if code else pre.get_text(strip=True),
            })
        return blocks

    @staticmethod
    def _extract_links(html: str, base_url: str) -> list[str]:
        soup = BeautifulSoup(html, "html.parser")
        links = []
        for a in soup.find_all("a", href=True):
            href = a["href"]
            links.append(href if href.startswith("http") else urljoin(base_url, href))
        return list(set(links))[:50]

    @staticmethod
    def _extract_images(html: str, base_url: str) -> list[str]:
        soup = BeautifulSoup(html, "html.parser")
        imgs = []
        for img in soup.find_all("img", src=True):
            src = img["src"]
            imgs.append(src if src.startswith("http") else urljoin(base_url, src))
        return imgs[:30]


# ── CLI ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    renderer = JsRenderer()

    if len(sys.argv) < 2:
        print("用法: python js_renderer.py <url> [--launch-chrome] [--wait-selector <css>]")
        print("示例: python js_renderer.py https://example.com --launch-chrome")
        sys.exit(1)

    url = sys.argv[1]
    launch = "--launch-chrome" in sys.argv
    wait_sel = None
    if "--wait-selector" in sys.argv:
        idx = sys.argv.index("--wait-selector")
        wait_sel = sys.argv[idx + 1] if idx + 1 < len(sys.argv) else None

    if launch:
        launch_chrome_with_debug()

    if not renderer.is_chrome_ready:
        print("[ChromeCDP] Chrome 调试端口未就绪。请先启动 Chrome:")
        print("  chrome.exe --remote-debugging-port=9222")
        print("或使用 --launch-chrome 自动启动")
        sys.exit(1)

    result = renderer.fetch(url, wait_for=wait_sel)
    print(f"\n=== 渲染结果 ===")
    print(f"方法: {result['method']}")
    print(f"渲染: {'是' if result['rendered'] else '否'}")
    print(f"标题: {result['title']}")
    print(f"文本长度: {len(result.get('text_content', ''))}")
    print(f"链接数: {len(result.get('links', []))}")
    if result.get("error"):
        print(f"错误: {result['error']}")
    print(f"\n--- 前1000字符 ---")
    print(result.get("text_content", "")[:1000])
