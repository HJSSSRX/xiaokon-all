#!/usr/bin/env python3
"""方案2: API 端点提取器 — 分析 JS 源码找到后端 API 直接获取结构化数据

策略:
    1. 抓取 HTML，提取所有 <script src="...">
    2. 下载每个 JS 文件，用正则匹配 API 端点模式
    3. 按优先级探测找到的端点
    4. 返回结构化 JSON 数据

优势:
    - 不需要浏览器，纯 HTTP 请求
    - 直接获取 JSON 数据，无需解析 HTML
    - 速度快，资源占用小
    - 适合 SPA 网站（React/Vue 等前后端分离架构）
"""
from __future__ import annotations

import json
import re
import sys
from urllib.parse import urljoin, urlparse
from typing import Optional

import requests as rq
from bs4 import BeautifulSoup


# ── 常见 API 端点模式 ────────────────────────────────────────────────

# JS 中的 API 调用模式
FETCH_PATTERNS = [
    # fetch('/api/...')
    re.compile(r"""fetch\s*\(\s*['"]([^'"]*?)['"]"""),
    # fetch(`${API_BASE}/path`)
    re.compile(r"""fetch\s*\(\s*(`[^`]*?`)"""),
    # axios.get('/api/...'), axios.post('/api/...')
    re.compile(r"""axios\.(?:get|post|put|delete|patch)\s*\(\s*['"]([^'"]*?)['"]"""),
    # baseURL = '/api'
    re.compile(r"""baseURL\s*[=:]\s*['"]([^'"]+)['"]"""),
    # apiUrl / API_URL = "..."
    re.compile(r"""api_?url\s*[=:]\s*['"]([^'"]+)['"]"""),
    # url: '/api/...'  (常见于 Vue/React config)
    re.compile(r"""url\s*:\s*['"](/[a-zA-Z][^'"]*)['"]"""),
    # XMLHttpRequest.open('GET', '/api/...')
    re.compile(r"""\.open\s*\(\s*['"](?:GET|POST|PUT)['"]\s*,\s*['"]([^'"]+)['"]"""),
    # Template literal endpoints: /api/${resource}
    re.compile(r"""['"](/[a-zA-Z][a-zA-Z0-9_/-]*?\$\{[^}]+\}[a-zA-Z0-9_/-]*?)['"]"""),
]

# URL 中表明是数据接口的关键词
API_KEYWORDS = [
    "api", "graphql", "data", "query", "search", "list", "tree",
    "node", "nodes", "category", "topic", "mindmap", "knowledge",
    "article", "post", "content", "page", "catalog", "index",
]

# 常见端点后缀（用于生成探测URL）
COMMON_ENDPOINTS = [
    "/api/mindmap",
    "/api/mindmap/tree",
    "/api/knowledge",
    "/api/knowledge/tree",
    "/api/knowledge/nodes",
    "/api/knowledge/categories",
    "/api/knowledge/list",
    "/api/articles",
    "/api/articles/list",
    "/api/topics",
    "/api/topics/tree",
    "/api/tags",
    "/api/categories",
    "/api/tree",
    "/api/nodes",
    "/api/graphql",
    "/graphql",
    "/api/v1/mindmap",
    "/api/v1/knowledge",
    "/api/data",
    "/data/mindmap.json",
    "/data/knowledge.json",
    "/data/tree.json",
]


def fetch_js_files(page_url: str, soup: BeautifulSoup | None = None) -> list[str]:
    """从页面提取所有 JS 文件 URL。"""
    if soup is None:
        resp = rq.get(page_url, timeout=30, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        })
        soup = BeautifulSoup(resp.text, "html.parser")

    js_urls = []
    for script in soup.find_all("script", src=True):
        src = script["src"]
        js_urls.append(src if src.startswith("http") else urljoin(page_url, src))
    return js_urls


def scan_js_for_apis(js_content: str, base_url: str) -> list[dict]:
    """扫描 JS 源码，提取所有可能的 API 端点。

    Returns:
        [{"endpoint": "/api/xxx", "confidence": 0.8, "source": "fetch"}, ...]
    """
    candidates = []

    for pattern in FETCH_PATTERNS:
        for match in pattern.finditer(js_content):
            raw = match.group(1)
            if raw.startswith("`"):
                # 模板字面量 — 标记为需要进一步处理
                candidates.append({
                    "endpoint": raw.replace("`", ""),
                    "confidence": 0.3,
                    "source": "template_literal",
                })
            elif raw.startswith("http"):
                candidates.append({
                    "endpoint": raw,
                    "confidence": 0.7,
                    "source": pattern.pattern[:30],
                })
            elif raw.startswith("/"):
                candidates.append({
                    "endpoint": raw,
                    "confidence": 0.6,
                    "source": pattern.pattern[:30],
                })

    # 按 API 关键词加权
    for c in candidates:
        ep = c["endpoint"]
        keyword_score = 0
        for kw in API_KEYWORDS:
            if kw in ep.lower():
                keyword_score += 0.1
        c["confidence"] = min(1.0, c["confidence"] + keyword_score)

    # 去重
    seen = {}
    for c in sorted(candidates, key=lambda x: x["confidence"], reverse=True):
        ep = c["endpoint"]
        if ep not in seen:
            seen[ep] = c

    return list(seen.values())


def probe_endpoints(api_candidates: list[dict], base_url: str, timeout: int = 10) -> list[dict]:
    """探测候选 API 端点，返回可用的端点及其响应数据。"""
    results = []
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "application/json, text/plain, */*",
        "X-Requested-With": "XMLHttpRequest",
    }

    parsed = urlparse(base_url)
    origin = f"{parsed.scheme}://{parsed.netloc}"

    for c in api_candidates:
        ep = c["endpoint"]
        url = ep if ep.startswith("http") else urljoin(origin, ep)

        try:
            resp = rq.get(url, headers=headers, timeout=timeout)
            if resp.status_code == 200:
                ct = resp.headers.get("Content-Type", "")
                info = {
                    "url": url,
                    "endpoint": ep,
                    "status": resp.status_code,
                    "size": len(resp.content),
                    "type": "json" if "json" in ct else ct[:50],
                }

                if "application/json" in ct:
                    try:
                        data = resp.json()
                        info["data"] = data
                        info["data_keys"] = list(data.keys())[:10] if isinstance(data, dict) else f"array[{len(data)}]"
                    except Exception:
                        info["preview"] = resp.text[:200]
                else:
                    info["preview"] = resp.text[:200]

                results.append(info)
        except Exception:
            pass

    return results


def probe_common_endpoints(base_url: str, timeout: int = 10) -> list[dict]:
    """探测常见 API 端点（不依赖 JS 分析）。"""
    results = []
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "application/json",
        "X-Requested-With": "XMLHttpRequest",
    }

    parsed = urlparse(base_url)
    origin = f"{parsed.scheme}://{parsed.netloc}"

    for ep in COMMON_ENDPOINTS:
        url = urljoin(origin, ep)
        try:
            resp = rq.get(url, headers=headers, timeout=timeout)
            if resp.status_code == 200 and "application/json" in resp.headers.get("Content-Type", ""):
                try:
                    data = resp.json()
                    results.append({
                        "url": url,
                        "endpoint": ep,
                        "size": len(resp.content),
                        "data": data,
                    })
                except Exception:
                    pass
        except Exception:
            pass

    return results


# ── 主类 ─────────────────────────────────────────────────────────────

class JsApiExtractor:
    """JS API 端点提取器。

    用法:
        extractor = JsApiExtractor()
        result = extractor.extract("https://example.com/knowledge")
        # result["api_endpoints"]  — 找到的 API 端点
        # result["api_data"]       — 成功获取的 API 数据
    """

    def __init__(self, timeout: int = 15):
        self.timeout = timeout
        self.session = rq.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "text/html,application/json,*/*",
        })

    def extract(self, url: str, probe_all: bool = True) -> dict:
        """完整提取流程: HTML → JS → API 端点 → API 数据。"""
        result = {
            "url": url,
            "title": "",
            "js_files": [],
            "api_candidates": [],
            "api_endpoints": [],
            "api_data": [],
            "method": "api_extract",
            "error": None,
        }

        try:
            # Step 1: 获取 HTML
            resp = self.session.get(url, timeout=self.timeout)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "html.parser")
            result["title"] = soup.title.string if soup.title else ""

            # Step 2: 提取 JS 文件
            js_urls = fetch_js_files(url, soup)
            result["js_files"] = js_urls

            # Step 3: 扫描每个 JS 文件
            all_candidates = []
            for js_url in js_urls:
                try:
                    js_resp = self.session.get(js_url, timeout=15)
                    candidates = scan_js_for_apis(js_resp.text, url)
                    all_candidates.extend(candidates)
                except Exception:
                    pass

            # 去重排序
            seen = {}
            unique = []
            for c in sorted(all_candidates, key=lambda x: x["confidence"], reverse=True):
                if c["endpoint"] not in seen:
                    seen[c["endpoint"]] = True
                    unique.append(c)
            result["api_candidates"] = unique[:50]

            # Step 4: 探测 API 端点
            if probe_all and unique:
                result["api_endpoints"] = probe_endpoints(unique, url, self.timeout)

            # Step 5: 也探测常见端点
            common = probe_common_endpoints(url, self.timeout)
            existing_urls = {e["url"] for e in result["api_endpoints"]}
            for c in common:
                if c["url"] not in existing_urls:
                    result["api_endpoints"].append(c)

            # 提取 API 返回的原始数据
            result["api_data"] = [
                {"url": ep["url"], "data": ep.get("data")}
                for ep in result["api_endpoints"]
                if ep.get("data")
            ]

        except Exception as e:
            result["error"] = str(e)

        return result

    def quick_scan(self, url: str) -> list[dict]:
        """仅扫描 JS 源码的 API 端点，不探测。"""
        result = self.extract(url, probe_all=False)
        return result["api_candidates"]

    def quick_probe(self, url: str) -> list[dict]:
        """仅探测常见端点。"""
        return probe_common_endpoints(url, self.timeout)


# ── CLI ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: python api_extractor.py <url> [--quick|--probe-only]")
        print("示例: python api_extractor.py https://forensics.didctf.com/knowledge")
        sys.exit(1)

    url = sys.argv[1]
    extractor = JsApiExtractor()

    if "--probe-only" in sys.argv:
        print(f"探测常见 API 端点: {url}\n")
        results = extractor.quick_probe(url)
        for r in results:
            print(f"  {r['url']}")
            data = r.get("data", {})
            if isinstance(data, dict):
                print(f"    键: {list(data.keys())[:5]}")
            print()
    elif "--quick" in sys.argv:
        print(f"快速扫描 JS 中的 API: {url}\n")
        candidates = extractor.quick_scan(url)
        for c in sorted(candidates, key=lambda x: x["confidence"], reverse=True):
            print(f"  [{c['confidence']:.1f}] {c['endpoint']}")
    else:
        print(f"完整提取: {url}\n")
        result = extractor.extract(url)
        print(f"标题: {result['title']}")
        print(f"JS 文件: {len(result['js_files'])} 个")
        print(f"API 候选: {len(result['api_candidates'])} 个")
        print(f"API 命中: {len(result['api_endpoints'])} 个")
        print(f"API 数据: {len(result['api_data'])} 组")
        if result["error"]:
            print(f"错误: {result['error']}")
        print(f"\n=== API 端点 ===")
        for ep in result["api_endpoints"]:
            print(f"  {ep['url']}  ({ep['type']}, {ep['size']} bytes)")
            if "data_keys" in ep:
                print(f"    数据键: {ep['data_keys']}")
        print(f"\n=== API 候选(未探测) ===")
        for c in result["api_candidates"][:20]:
            print(f"  [{c['confidence']:.1f}] {c['endpoint']}")
