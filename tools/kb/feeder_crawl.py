#!/usr/bin/env python3
"""喂食者 - 知识爬取工具

整合知识爬取工具，支持多种网站类型自动识别，一键整理到知识库。

快捷命令：
    python tools/feeder_crawl.py fetch <url> --kb-dir knowledge
    python tools/feeder_crawl.py fetch <url> --render      (JS渲染: Chrome CDP)
    python tools/feeder_crawl.py fetch <url> --api-extract  (JS渲染: API提取)

支持网站：
    - CSDN / 微信公众号 / 简书 / 知乎 / GitHub / Medium / 通用博客
    - SPA (React/Vue) JS渲染页面 (--render / --api-extract)
"""

import argparse
import os
import sys
from pathlib import Path

# 添加项目根目录到路径，确保 tools 包可被导入
_project_root = str(Path(__file__).parent.parent)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

# 依赖检查
def check_dependencies():
    required = ['requests', 'bs4', 'yaml']
    missing = []
    for pkg in required:
        try:
            __import__(pkg)
        except ImportError:
            missing.append(pkg)
    if missing:
        print(f"[FEEDER] 缺少必需依赖: {', '.join(missing)}")
        print(f"[FEEDER] 请执行: pip install {' '.join(missing)}")
        sys.exit(1)

check_dependencies()

# 使用完整包路径导入，确保相对导入 ..core 正常工作
from tools.feeder import (WebPageParser, organize_article_to_kb, organize_mindmap_to_kb,
                          get_storage_path, save_article, JsRenderer, JsApiExtractor,
                          launch_chrome_with_debug)

FEEDER_STORAGE_ENV = "FEEDER_STORAGE"


def cmd_fetch(args):
    """通用网页爬取命令 - 支持多种网站类型"""
    # JS 渲染模式
    if args.render or args.api_extract:
        return cmd_fetch_js(args)

    print(f"[FEEDER] 正在爬取: {args.url}")

    parser = WebPageParser()
    result = parser.parse(args.url, site_type=args.type)

    if "error" in result:
        print(f"[FEEDER] 爬取失败: {result['error']}")
        return

    print(f"[FEEDER] 成功获取页面")
    print(f"  标题: {result['title']}")
    print(f"  站点类型: {result['site_type']}")
    print(f"  作者: {result.get('author', '')}")
    print(f"  内容长度: {len(result.get('text_content', ''))} 字符")
    print(f"  代码块数: {len(result.get('code_blocks', []))}")

    output_dir = Path(args.output) if args.output else get_storage_path()
    print(f"[FEEDER] 使用存储: {output_dir}")

    saved_path = save_article(result, output_dir)
    print(f"[FEEDER] 保存到: {saved_path}")

    if args.kb_dir:
        print(f"[FEEDER] 正在整理到知识库...")
        organize_article_to_kb(result, args.kb_dir)

    print(f"[FEEDER] 完成！")


def cmd_fetch_js(args):
    """JS 渲染爬取 — 支持方案1 (Chrome CDP) 和方案2 (API提取)"""
    method = "cdp" if args.render else "api"

    if args.render:
        print(f"[FEEDER] 方案1: Chrome CDP 渲染模式")
        if args.launch_chrome:
            launch_chrome_with_debug(port=args.cdp_port, headless=args.headless)

        renderer = JsRenderer(cdp_port=args.cdp_port)
        if not renderer.is_chrome_ready:
            print(f"[FEEDER] Chrome 调试端口 {args.cdp_port} 未就绪")
            print(f"[FEEDER] 请启动 Chrome: chrome.exe --remote-debugging-port={args.cdp_port}")
            print(f"[FEEDER] 或加 --launch-chrome 自动启动")
            if args.fallback:
                print(f"[FEEDER] 降级到静态解析...")
            else:
                sys.exit(1)

        result = renderer.fetch(args.url, wait_for=args.wait_selector, wait_ms=args.wait_ms)
        print(f"[FEEDER] 方法: {result['method']}, 渲染: {result['rendered']}")
    else:
        print(f"[FEEDER] 方案2: API 端点提取模式")
        extractor = JsApiExtractor()
        result = extractor.extract(args.url)
        print(f"[FEEDER] JS 文件: {len(result.get('js_files', []))} 个")
        print(f"[FEEDER] API 候选: {len(result.get('api_candidates', []))} 个")
        print(f"[FEEDER] API 命中: {len(result.get('api_endpoints', []))} 个")
        print(f"[FEEDER] API 数据: {len(result.get('api_data', []))} 组")

    if result.get("error"):
        print(f"[FEEDER] 错误: {result['error']}")
        if args.fallback:
            print(f"[FEEDER] 降级到静态解析...")
            parser = WebPageParser()
            result = parser.parse(args.url)
        else:
            return

    print(f"  标题: {result.get('title', '')}")
    text_len = len(result.get('text_content', ''))
    print(f"  纯文本长度: {text_len} 字符")

    output_dir = Path(args.output) if args.output else get_storage_path()
    saved_path = save_article(result, output_dir)
    print(f"[FEEDER] 保存到: {saved_path}")

    if args.kb_dir:
        print(f"[FEEDER] 正在整理到知识库...")
        organize_article_to_kb(result, args.kb_dir)

    print(f"[FEEDER] 完成！")


def cmd_mindmap(args):
    """爬取思维导图页面"""
    from feeder.parsers import WebPageParser
    print(f"[FEEDER] 正在爬取思维导图: {args.url}")

    # 使用示例数据（如果指定）
    if args.sample:
        sample_data = {
            "categories": [
                {"id": "cat1", "name": "Web安全"},
                {"id": "cat2", "name": "二进制安全"},
                {"id": "cat3", "name": "取证分析"},
            ],
            "knowledge_items": [
                {"title": "SQL注入", "category": "Web安全", "level": 1},
                {"title": "XSS攻击", "category": "Web安全", "level": 1},
                {"title": "缓冲区溢出", "category": "二进制安全", "level": 1},
                {"title": "内存取证", "category": "取证分析", "level": 1},
            ],
            "nodes": [
                {"id": "n1", "name": "SQL注入", "level": 2, "parent_id": "cat1", "children": []},
                {"id": "n2", "name": "XSS攻击", "level": 2, "parent_id": "cat1", "children": []},
                {"id": "n3", "name": "缓冲区溢出", "level": 2, "parent_id": "cat2", "children": []},
            ]
        }
        result = sample_data
    else:
        # 实际爬取（如果网站支持）
        parser = WebPageParser()
        result = parser.parse(args.url)
        if "error" in result:
            print(f"[FEEDER] 爬取失败，使用示例数据")
            sample_data = {
                "categories": [{"id": "cat1", "name": "知识分类"}],
                "knowledge_items": [{"title": "示例知识项", "category": "知识分类"}],
                "nodes": []
            }
            result = sample_data

    # 保存数据
    output_dir = Path(args.output) if args.output else get_storage_path()
    import json
    from hashlib import md5
    filename = f"mindmap_{md5(args.url.encode()).hexdigest()[:8]}.json"
    with open(output_dir / filename, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"[FEEDER] 保存到: {output_dir / filename}")

    if args.kb_dir:
        print(f"[FEEDER] 正在整理到知识库...")
        organize_mindmap_to_kb(result, args.kb_dir)

    print(f"[FEEDER] 完成！")


def main():
    parser = argparse.ArgumentParser(description="喂食者 - 知识爬取工具")
    parser.add_argument("--storage", help="自定义存储目录")

    subparsers = parser.add_subparsers(dest="cmd", help="可用命令")

    p_fetch = subparsers.add_parser("fetch", help="通用网页爬取（自动识别站点类型）")
    p_fetch.add_argument("url", help="目标URL")
    p_fetch.add_argument("--output", help="输出目录")
    p_fetch.add_argument("--kb-dir", help="知识库目录（自动整理）")
    p_fetch.add_argument("--type", default="auto",
                         choices=["auto", "csdn", "weixin", "jianshu", "zhihu", "blog", "github", "medium", "spa"],
                         help="站点类型（默认自动识别）")

    # JS 渲染方案
    js_group = p_fetch.add_argument_group("JS 渲染方案（处理 React/Vue 等动态页面）")
    js_group.add_argument("--render", action="store_true",
                          help="方案1: Chrome CDP 浏览器渲染")
    js_group.add_argument("--api-extract", action="store_true",
                          help="方案2: 分析 JS 源码提取 API 端点")
    js_group.add_argument("--launch-chrome", action="store_true",
                          help="自动启动 Chrome (需 --render)")
    js_group.add_argument("--cdp-port", type=int, default=9222,
                          help="Chrome 调试端口 (默认 9222)")
    js_group.add_argument("--headless", action="store_true",
                          help="Chrome 无头模式 (需 --launch-chrome)")
    js_group.add_argument("--wait-selector", help="等待 CSS 选择器出现后提取 (需 --render)")
    js_group.add_argument("--wait-ms", type=int, default=3000,
                          help="额外等待毫秒数 (需 --render, 默认 3000)")
    js_group.add_argument("--fallback", action="store_true",
                          help="JS 渲染失败时降级到静态解析")

    p_mindmap = subparsers.add_parser("mindmap", help="爬取思维导图页面")
    p_mindmap.add_argument("url", help="思维导图页面URL")
    p_mindmap.add_argument("--output", help="输出目录")
    p_mindmap.add_argument("--kb-dir", help="知识库目录（自动整理）")
    p_mindmap.add_argument("--sample", action="store_true", help="使用示例数据（非交互式）")

    args = parser.parse_args()

    if args.storage:
        os.environ[FEEDER_STORAGE_ENV] = args.storage

    if args.cmd == "fetch":
        cmd_fetch(args)
    elif args.cmd == "mindmap":
        cmd_mindmap(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
