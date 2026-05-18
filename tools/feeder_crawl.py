#!/usr/bin/env python3
"""喂食者 - 知识爬取工具

整合知识爬取工具，支持多种网站类型自动识别，一键整理到知识库。

快捷命令：
    python tools/feeder_crawl.py fetch <url> --kb-dir knowledge

支持网站：
    - CSDN
    - 微信公众号
    - 简书
    - 知乎
    - GitHub
    - Medium
    - 通用博客
"""

import argparse
import os
import sys
from pathlib import Path

# 添加 tools 目录到路径
sys.path.insert(0, str(Path(__file__).parent))

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

# 导入模块化组件
from feeder import WebPageParser, FeederOrganizer, get_storage_path, save_article

FEEDER_STORAGE_ENV = "FEEDER_STORAGE"


def cmd_fetch(args):
    """通用网页爬取命令 - 支持多种网站类型"""
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
        FeederOrganizer.organize_article_to_kb(result, args.kb_dir)

    print(f"[FEEDER] 完成！")


def cmd_mindmap(args):
    """爬取思维导图页面"""
    from feeder.parsers import WebPageParser as MindmapParser
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
        parser = MindmapParser()
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
    filename = f"mindmap_{abs(hash(args.url))[:8]}.json"
    with open(output_dir / filename, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"[FEEDER] 保存到: {output_dir / filename}")

    if args.kb_dir:
        print(f"[FEEDER] 正在整理到知识库...")
        FeederOrganizer.organize_mindmap_to_kb(result, args.kb_dir)

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
                         choices=["auto", "csdn", "weixin", "jianshu", "zhihu", "blog", "github", "medium"],
                         help="站点类型（默认自动识别）")

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
