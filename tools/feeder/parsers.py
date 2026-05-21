#!/usr/bin/env python3
"""喂食者核心模块 - 解析器模块

支持两种 JS 渲染方案:
    方案1 (CDP): 连接 Google Chrome 渲染页面 → JsRenderer
    方案2 (API): 分析 JS 源码找后端 API 直接获取数据 → JsApiExtractor
    兜底:      requests + BeautifulSoup 静态解析
"""
from urllib.parse import urljoin, urlparse
from bs4 import BeautifulSoup
import re
import requests


class WebPageParser:
    """通用网页解析器 - 自动识别网站类型并提取内容。

    新增 parse_js_page() 方法，自动尝试 JS 渲染方案获取动态内容。
    """

    SITE_HANDLERS = {
        "csdn": "_parse_csdn",
        "weixin": "_parse_wechat",
        "jianshu": "_parse_jianshu",
        "zhihu": "_parse_zhihu",
        "blog": "_parse_blog",
        "github": "_parse_github",
        "medium": "_parse_medium",
        "reddit": "_parse_reddit",
        "spa": "_parse_spa",
    }

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        })

    def detect_site_type(self, url: str) -> str:
        """根据URL自动识别网站类型"""
        parsed = urlparse(url)
        domain = parsed.netloc.lower()
        if "csdn.net" in domain:
            return "csdn"
        elif "mp.weixin.qq.com" in domain:
            return "weixin"
        elif "jianshu.com" in domain:
            return "jianshu"
        elif "zhihu.com" in domain:
            return "zhihu"
        elif "github.com" in domain:
            return "github"
        elif "medium.com" in domain:
            return "medium"
        elif "calif.io" in domain or "blog." in domain:
            return "blog"
        else:
            return "blog"

    def parse(self, url: str, site_type: str = "auto") -> dict:
        """解析网页并提取结构化数据"""
        result = {
            "url": url,
            "title": "",
            "site_type": site_type,
            "content": "",
            "text_content": "",
            "author": "",
            "publish_date": "",
            "tags": [],
            "code_blocks": [],
            "images": [],
            "links": [],
            "language": "unknown",
        }
        try:
            response = self.session.get(url, timeout=30)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, "html.parser")

            if site_type == "auto":
                site_type = self.detect_site_type(url)
                result["site_type"] = site_type

            handler_name = self.SITE_HANDLERS.get(site_type, "_parse_blog")
            handler = getattr(self, handler_name, self._parse_blog)
            handler(soup, url, result)

            result["text_content"] = self._clean_text(result.get("content", ""))
            result["code_blocks"] = self._extract_code_blocks(soup)
            result["links"] = self._extract_links(soup, url)
            result["language"] = self._detect_language(result.get("text_content", ""))

        except Exception as e:
            result["error"] = str(e)

        return result

    def _parse_csdn(self, soup, url, result):
        """解析CSDN文章"""
        result["title"] = soup.title.string if soup.title else ""
        article = soup.find("article") or soup.find("div", id="content_views")
        if article:
            result["content"] = article.decode_contents()

    def _parse_wechat(self, soup, url, result):
        """解析微信公众号文章"""
        title = soup.find("h1") or soup.find("meta", property="og:title")
        if title:
            result["title"] = title.get("content", title.get_text(strip=True))
        article = soup.find("div", id="js_content") or soup.find("div", class_="rich_media_content")
        if article:
            result["content"] = article.decode_contents()

    def _parse_github(self, soup, url, result):
        """解析GitHub页面"""
        title = soup.find("h1") or soup.title
        if title:
            result["title"] = title.get_text(strip=True).split("\n")[0]
        article = soup.find("div", class_="markdown-body") or soup.find("article")
        if article:
            result["content"] = article.decode_contents()

    def _parse_blog(self, soup, url, result):
        """解析通用博客"""
        title = soup.find("h1") or soup.find("meta", property="og:title") or soup.title
        if title:
            result["title"] = title.get("content", title.get_text(strip=True))
        article = soup.find("article") or soup.find("div", class_=re.compile(r"content|article|post"))
        if article:
            result["content"] = article.decode_contents()
        else:
            main = soup.find("main") or soup.find("div", class_=re.compile(r"main|container"))
            if main:
                result["content"] = main.decode_contents()

    def _parse_jianshu(self, soup, url, result):
        """解析简书文章"""
        title = soup.find("h1", class_="title")
        if title:
            result["title"] = title.get_text(strip=True)
        article = soup.find("div", class_="article-content")
        if article:
            result["content"] = article.decode_contents()

    def _parse_zhihu(self, soup, url, result):
        """解析知乎文章"""
        title = soup.find("h1", class_="Post-Title")
        if title:
            result["title"] = title.get_text(strip=True)
        article = soup.find("div", class_="RichText")
        if article:
            result["content"] = article.decode_contents()

    def _parse_medium(self, soup, url, result):
        """解析Medium文章"""
        title = soup.find("h1") or soup.find("meta", property="og:title")
        if title:
            result["title"] = title.get("content", title.get_text(strip=True))
        article = soup.find("article")
        if article:
            result["content"] = article.decode_contents()

    def _parse_reddit(self, soup, url, result):
        """解析Reddit帖子"""
        title = soup.find("h1")
        if title:
            result["title"] = title.get_text(strip=True)
        article = soup.find("div", attrs={"data-testid": "post-content"})
        if article:
            result["content"] = article.decode_contents()

    def _parse_spa(self, soup, url, result):
        """解析 SPA / JS 渲染页面 — 尝试从内联数据和 API 获取内容"""
        scripts = soup.find_all("script", src=False)
        combined = "\n".join(s.string or "" for s in scripts if s.string)
        result["inline_scripts"] = combined[:5000]

    # ── JS 渲染集成 ────────────────────────────────────────────────

    def parse_js_page(self, url: str, method: str = "auto",
                      wait_for: str | None = None,
                      wait_ms: int = 3000,
                      cdp_port: int = 9222) -> dict:
        """解析 JS 渲染页面，自动选择最佳方案。

        Args:
            url: 目标 URL
            method: "cdp" (方案1) / "api" (方案2) / "auto" (先 CDP 后 API)
            wait_for: CDP 模式等待的 CSS 选择器
            wait_ms: 额外等待毫秒
            cdp_port: Chrome CDP 端口

        Returns:
            标准 parse result dict + "js_method" / "api_data" 额外字段
        """
        result = {
            "url": url,
            "title": "",
            "site_type": "spa",
            "content": "",
            "text_content": "",
            "author": "",
            "publish_date": "",
            "tags": [],
            "code_blocks": [],
            "images": [],
            "links": [],
            "language": "unknown",
            "js_method": "",
            "api_data": [],
            "error": None,
        }

        # 方案1: Chrome CDP 浏览器渲染
        if method in ("auto", "cdp"):
            try:
                from .js_renderer import JsRenderer
                renderer = JsRenderer(cdp_port=cdp_port)
                if renderer.is_chrome_ready:
                    cdp_result = renderer.fetch(url, wait_for=wait_for, wait_ms=wait_ms)
                    if cdp_result.get("rendered"):
                        result["js_method"] = "chrome_cdp"
                        result["title"] = cdp_result.get("title", "")
                        result["content"] = cdp_result.get("content", "")
                        result["text_content"] = cdp_result.get("text_content", "")
                        result["code_blocks"] = cdp_result.get("code_blocks", [])
                        result["links"] = cdp_result.get("links", [])
                        result["images"] = cdp_result.get("images", [])
                        result["language"] = self._detect_language(result["text_content"])
                        return result
                    else:
                        result["error"] = cdp_result.get("error")
                else:
                    result["error"] = f"Chrome CDP 端口 {cdp_port} 未就绪"
            except ImportError as e:
                result["error"] = f"JsRenderer 不可用: {e}"
            except Exception as e:
                result["error"] = f"CDP 渲染异常: {e}"

        # 方案2: API 端点提取 (JS 分析)
        if method in ("auto", "api"):
            try:
                from .api_extractor import JsApiExtractor
                extractor = JsApiExtractor()
                api_result = extractor.extract(url)
                result["api_data"] = api_result.get("api_data", [])
                result["api_candidates"] = api_result.get("api_candidates", [])
                result["api_endpoints"] = api_result.get("api_endpoints", [])

                if method == "api":
                    result["js_method"] = "api_extract"

                # 尝试从 API 获取的 JSON 构建文本内容
                if result["api_data"]:
                    result["js_method"] = result["js_method"] or "api_extract"
                    text_parts = []
                    for ad in result["api_data"]:
                        text_parts.append(self._flatten_json_text(ad.get("data", {})))
                    result["text_content"] = "\n".join(text_parts)
                    result["title"] = api_result.get("title", "")
                    return result
            except ImportError as e:
                if method == "api":
                    result["error"] = f"JsApiExtractor 不可用: {e}"
            except Exception as e:
                if method == "api":
                    result["error"] = f"API 提取异常: {e}"

        # 兜底: 静态解析
        if not result.get("text_content"):
            try:
                resp = self.session.get(url, timeout=30)
                resp.raise_for_status()
                soup = BeautifulSoup(resp.text, "html.parser")
                result["title"] = soup.title.string if soup.title else ""
                article = soup.find("article") or soup.find("main") or soup.find("div", id="root")
                if article:
                    result["content"] = article.decode_contents()
                else:
                    result["content"] = str(soup)
                result["text_content"] = self._clean_text(result["content"])
                result["code_blocks"] = self._extract_code_blocks(soup)
                result["links"] = self._extract_links(soup, url)
                result["language"] = self._detect_language(result["text_content"])
                result["js_method"] = result["js_method"] or "static_fallback"
            except Exception as e:
                result["error"] = f"{result.get('error', '')}; static: {e}"

        return result

    @staticmethod
    def _flatten_json_text(data, max_depth: int = 5) -> str:
        """递归展平 JSON 为可读文本。"""
        if max_depth <= 0:
            return ""
        parts = []
        if isinstance(data, dict):
            for k, v in data.items():
                if isinstance(v, str) and len(v) > 2:
                    parts.append(f"{k}: {v}")
                elif isinstance(v, (dict, list)):
                    sub = WebPageParser._flatten_json_text(v, max_depth - 1)
                    if sub:
                        parts.append(sub)
        elif isinstance(data, list):
            for item in data[:20]:
                if isinstance(item, dict):
                    parts.append(WebPageParser._flatten_json_text(item, max_depth - 1))
                elif isinstance(item, str):
                    parts.append(item)
        return "\n".join(parts)

    def _clean_text(self, html_content: str) -> str:
        """清理HTML获取纯文本"""
        soup = BeautifulSoup(html_content, "html.parser")
        return soup.get_text(separator="\n", strip=True)

    def _extract_code_blocks(self, soup) -> list:
        """提取代码块"""
        code_blocks = []
        for pre in soup.find_all("pre"):
            code = pre.find("code")
            lang = ""
            if code and code.get("class"):
                lang = code.get("class", [""])[0].replace("language-", "")
            code_blocks.append({
                "language": lang,
                "code": code.get_text(strip=True) if code else pre.get_text(strip=True)
            })
        return code_blocks

    def _extract_links(self, soup, base_url) -> list:
        """提取链接"""
        links = []
        for a in soup.find_all("a", href=True):
            href = a["href"]
            links.append(href if href.startswith("http") else urljoin(base_url, href))
        return list(set(links))[:50]

    def _detect_language(self, text: str) -> str:
        """检测内容语言"""
        chinese_chars = len(re.findall(r"[\u4e00-\u9fff]", text))
        total_chars = len(re.findall(r"[\u4e00-\u9fff]|[a-zA-Z]", text))
        if total_chars > 0 and chinese_chars / total_chars > 0.3:
            return "zh"
        elif total_chars > 0 and chinese_chars / total_chars > 0.1:
            return "mixed"
        else:
            return "en"
