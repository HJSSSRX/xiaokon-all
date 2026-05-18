#!/usr/bin/env python3
"""喂食者核心模块 - 存储管理"""
import os
from pathlib import Path

FEEDER_STORAGE_ENV = "FEEDER_STORAGE"


def get_storage_path(custom_path=None) -> Path:
    """获取存储路径，优先级：参数 > 环境变量 > 默认路径"""
    if custom_path:
        path = Path(custom_path)
    elif FEEDER_STORAGE_ENV in os.environ:
        path = Path(os.environ[FEEDER_STORAGE_ENV])
    else:
        path = Path("data/feeder")

    path.mkdir(parents=True, exist_ok=True)
    return path


def save_article(data: dict, output_dir: Path = None) -> str:
    """保存文章数据到JSON文件"""
    import json
    import re
    from hashlib import md5

    if output_dir is None:
        output_dir = get_storage_path()

    url_hash = str(abs(hash(data.get("url", ""))))[:8]
    safe_title = re.sub(r'[\\/:*?"<>|]', "_", data.get("title", "unknown")[:50])
    filename = f"article_{data.get('site_type', 'unknown')}_{safe_title}_{url_hash}.json"
    output_path = output_dir / filename

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    return str(output_path)


def load_article(filepath: str) -> dict:
    """加载已保存的文章数据"""
    import json
    with open(filepath, "r", encoding="utf-8") as f:
        return json.load(f)


def list_saved_articles(storage_dir: Path = None) -> list:
    """列出已保存的文章文件"""
    if storage_dir is None:
        storage_dir = get_storage_path()

    articles = []
    for file in storage_dir.glob("article_*.json"):
        articles.append({
            "filename": file.name,
            "path": str(file),
            "size": file.stat().st_size,
            "modified": file.stat().st_mtime
        })
    return sorted(articles, key=lambda x: x["modified"], reverse=True)
