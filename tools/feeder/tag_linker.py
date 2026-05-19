#!/usr/bin/env python3
"""喂食者核心模块 - 标签关联器"""
from pathlib import Path
import re
import yaml
from ..core import load_yaml, save_yaml, ensure_dir, now_str
from collections import defaultdict


TAG_CATEGORIES = {
    "forensics_type": {
        "name": "取证类型",
        "tags": [
            "内存取证", "磁盘取证", "网络取证", "移动取证",
            "数据库取证", "日志分析", "流量分析", "注册表分析",
            "memory_forensics", "disk_forensics", "network_forensics",
        ]
    },
    "attack_type": {
        "name": "攻击类型",
        "tags": [
            "sql注入", "xss", "csrf", "文件上传", "命令注入",
            "反序列化", "ssrf", "xxe", "缓冲区溢出", "uaf",
            "sql_injection", "deserialization", "buffer_overflow",
        ]
    },
    "tool": {
        "name": "工具",
        "tags": [
            "volatility", "wireshark", "ida", "ghidra", "sqlmap",
            "burpsuite", "nmap", "foremost", "binwalk", "tshark",
            "autopsy", "ftk", "encase",
        ]
    },
    "os": {
        "name": "操作系统",
        "tags": ["windows", "linux", "macos", "android", "ios"],
    },
    "language": {
        "name": "编程语言",
        "tags": [
            "python", "php", "javascript", "java", "c", "cpp",
            "golang", "rust", "ruby",
        ]
    },
    "protocol": {
        "name": "协议",
        "tags": [
            "http", "https", "tcp", "udp", "dns", "smtp",
            "ftp", "ssh", "tls", "ssl",
        ]
    },
    "difficulty": {
        "name": "难度",
        "tags": ["easy", "medium", "hard", "beginner", "advanced"],
    },
}


def extract_tags(text: str) -> list:
    """从文本中提取标签"""
    tags = []
    text_lower = text.lower()

    for category, data in TAG_CATEGORIES.items():
        for tag in data["tags"]:
            if tag.lower() in text_lower:
                tags.append({
                    "tag": tag,
                    "category": category,
                    "category_name": data["name"],
                })

    keywords = re.findall(r"[a-zA-Z]{4,}", text_lower)
    seen = {t["tag"].lower() for t in tags}
    for kw in set(keywords):
        if kw not in seen:
            tags.append({
                "tag": kw,
                "category": "keyword",
                "category_name": "关键词",
            })
            seen.add(kw)

    return tags[:20]


def link_by_tags(kb_dir: str) -> dict:
    """基于标签建立关联"""
    kb_path = Path(kb_dir)

    tag_map = defaultdict(lambda: {
        "sources": [],
        "practice": [],
        "skills": [],
    })

    sources_dir = kb_path / "sources"
    if sources_dir.exists():
        for yaml_file in sources_dir.rglob("*.yaml"):
            if yaml_file.name == "_index.yaml":
                continue
            with open(yaml_file, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}

            tags = data.get("tags", [])
            for tag in tags:
                tag_lower = tag.lower() if isinstance(tag, str) else str(tag).lower()
                relative_path = str(yaml_file.relative_to(kb_path))
                tag_map[tag_lower]["sources"].append(relative_path)

    practice_dir = kb_path / "practice"
    if practice_dir.exists():
        for yaml_file in practice_dir.rglob("*.yaml"):
            if yaml_file.name == "_index.yaml":
                continue
            with open(yaml_file, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}

            tags = data.get("tags", [])
            for tag in tags:
                tag_lower = tag.lower() if isinstance(tag, str) else str(tag).lower()
                relative_path = str(yaml_file.relative_to(kb_path))
                tag_map[tag_lower]["practice"].append(relative_path)

    skills_dir = kb_path / "skills"
    if skills_dir.exists():
        for yaml_file in skills_dir.rglob("*.yaml"):
            if yaml_file.name == "_index.yaml":
                continue
            with open(yaml_file, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}

            tags = data.get("tags", [])
            for tag in tags:
                tag_lower = tag.lower() if isinstance(tag, str) else str(tag).lower()
                relative_path = str(yaml_file.relative_to(kb_path))
                tag_map[tag_lower]["skills"].append(relative_path)

    relations_dir = kb_path / "_relations"
    ensure_dir(relations_dir)

    tag_index_file = relations_dir / "tag_index.yaml"
    with open(tag_index_file, "w", encoding="utf-8") as f:
        yaml.dump(dict(tag_map), f, allow_unicode=True, sort_keys=False)

    print(f"[TAG_LINKER] 已建立 {len(tag_map)} 个标签关联")

    return dict(tag_map)


def find_related(kb_dir: str, path: str, max_results: int = 10) -> dict:
    """查找与指定条目相关的内容"""
    kb_path = Path(kb_dir)
    target_file = kb_path / path

    if not target_file.exists():
        return {"sources": [], "practice": [], "skills": []}

    with open(target_file, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}

    tags = data.get("tags", [])
    if not tags:
        return {"sources": [], "practice": [], "skills": []}

    relations_dir = kb_path / "_relations"
    tag_index_file = relations_dir / "tag_index.yaml"

    if not tag_index_file.exists():
        link_by_tags(kb_dir)

    with open(tag_index_file, "r", encoding="utf-8") as f:
        tag_index = yaml.safe_load(f) or {}

    results = {"sources": [], "practice": [], "skills": []}

    for tag in tags:
        tag_lower = tag.lower() if isinstance(tag, str) else str(tag).lower()
        if tag_lower in tag_index:
            for key in ["sources", "practice", "skills"]:
                for item in tag_index[tag_lower][key]:
                    if item != path and item not in results[key]:
                        results[key].append(item)

    for key in results:
        results[key] = results[key][:max_results]

    return results


def recommend_next(kb_dir: str, current_path: str) -> dict:
    """推荐下一步学习内容"""
    related = find_related(kb_dir, current_path)

    return {
        "learn_next": related["sources"][:5],
        "practice_next": related["practice"][:5],
        "related_skills": related["skills"][:5],
    }


def _update_single_tag_index(kb_dir: str, tag_index: dict, path: str,
                              old_tags: list, new_tags: list):
    """Incrementally update tag index for a single entry's tag changes."""
    path_str = path
    removed = set(old_tags) - set(new_tags)
    added = set(new_tags) - set(old_tags)

    for tag in removed:
        tag_lower = tag.lower() if isinstance(tag, str) else str(tag).lower()
        if tag_lower in tag_index:
            for key in ["sources", "practice", "skills"]:
                if path_str in tag_index[tag_lower].get(key, []):
                    tag_index[tag_lower][key].remove(path_str)

    for tag in added:
        tag_lower = tag.lower() if isinstance(tag, str) else str(tag).lower()
        if tag_lower not in tag_index:
            tag_index[tag_lower] = {"sources": [], "practice": [], "skills": []}
        # Determine which key based on path prefix
        if path_str.startswith("sources"):
            key = "sources"
        elif path_str.startswith("practice"):
            key = "practice"
        elif path_str.startswith("skills"):
            key = "skills"
        else:
            continue
        if path_str not in tag_index[tag_lower][key]:
            tag_index[tag_lower][key].append(path_str)

    tag_index_file = Path(kb_dir) / "_relations" / "tag_index.yaml"
    with open(tag_index_file, "w", encoding="utf-8") as f:
        yaml.dump(tag_index, f, allow_unicode=True, sort_keys=False)


def update_entry_tags(kb_dir: str, path: str, new_tags: list) -> bool:
    """更新条目的标签"""
    kb_path = Path(kb_dir)
    target_file = kb_path / path

    if not target_file.exists():
        return False

    with open(target_file, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}

    old_tags = set(data.get("tags", []))
    for tag in new_tags:
        old_tags.add(tag)

    data["tags"] = list(old_tags)

    with open(target_file, "w", encoding="utf-8") as f:
        yaml.dump(data, f, allow_unicode=True, sort_keys=False)

    # Incremental update instead of full reindex
    tag_index_file = kb_path / "_relations" / "tag_index.yaml"
    tag_index = {}
    if tag_index_file.exists():
        with open(tag_index_file, "r", encoding="utf-8") as f:
            tag_index = yaml.safe_load(f) or {}
    _update_single_tag_index(kb_dir, tag_index, path, list(old_tags), data["tags"])

    return True


def get_tag_statistics(kb_dir: str) -> dict:
    """获取标签统计信息"""
    kb_path = Path(kb_dir)
    relations_dir = kb_path / "_relations"
    tag_index_file = relations_dir / "tag_index.yaml"

    if not tag_index_file.exists():
        link_by_tags(kb_dir)

    with open(tag_index_file, "r", encoding="utf-8") as f:
        tag_index = yaml.safe_load(f) or {}

    stats = {
        "total_tags": len(tag_index),
        "by_category": defaultdict(int),
        "hot_tags": [],
    }

    tag_counts = []
    for tag, data in tag_index.items():
        count = len(data["sources"]) + len(data["practice"]) + len(data["skills"])
        tag_counts.append((tag, count))

        for category, cat_data in TAG_CATEGORIES.items():
            if tag in [t.lower() for t in cat_data["tags"]]:
                stats["by_category"][category] += 1

    tag_counts.sort(key=lambda x: x[1], reverse=True)
    stats["hot_tags"] = tag_counts[:20]

    return stats


def suggest_tags(kb_dir: str, text: str) -> list:
    """根据文本内容建议标签"""
    extracted = extract_tags(text)

    suggestions = defaultdict(list)
    for item in extracted:
        suggestions[item["category"]].append(item["tag"])

    return dict(suggestions)
