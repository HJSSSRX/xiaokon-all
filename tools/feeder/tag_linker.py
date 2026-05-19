#!/usr/bin/env python3
"""喂食者核心模块 - 标签关联器"""
from pathlib import Path
import re
import yaml
from collections import defaultdict
from datetime import datetime


class TagLinker:
    """标签关联器 - 增强技能、知识、题目之间的关联"""

    # 预定义标签分类
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
            "tags": [
                "windows", "linux", "macos", "android", "ios",
            ]
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
            "tags": [
                "easy", "medium", "hard", "beginner", "advanced",
            ]
        },
    }

    @staticmethod
    def extract_tags(text: str) -> list:
        """从文本中提取标签"""
        tags = []
        text_lower = text.lower()
        
        # 从预定义标签中匹配
        for category, data in TagLinker.TAG_CATEGORIES.items():
            for tag in data["tags"]:
                if tag.lower() in text_lower:
                    tags.append({
                        "tag": tag,
                        "category": category,
                        "category_name": data["name"],
                    })
        
        # 提取英文关键词
        keywords = re.findall(r"[a-zA-Z]{4,}", text_lower)
        for kw in set(keywords):
            if not any(t["tag"].lower() == kw for t in tags):
                tags.append({
                    "tag": kw,
                    "category": "keyword",
                    "category_name": "关键词",
                })
        
        return tags[:20]

    @staticmethod
    def link_by_tags(kb_dir: str) -> dict:
        """基于标签建立关联"""
        kb_path = Path(kb_dir)
        
        # 收集所有标签
        tag_map = defaultdict(lambda: {
            "sources": [],
            "practice": [],
            "skills": [],
        })
        
        # 扫描 sources
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
        
        # 扫描 practice
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
        
        # 扫描 skills
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
        
        # 保存标签索引
        relations_dir = kb_path / "_relations"
        relations_dir.mkdir(parents=True, exist_ok=True)
        
        tag_index_file = relations_dir / "tag_index.yaml"
        with open(tag_index_file, "w", encoding="utf-8") as f:
            yaml.dump(dict(tag_map), f, allow_unicode=True, sort_keys=False)
        
        print(f"[TAG_LINKER] 已建立 {len(tag_map)} 个标签关联")
        
        return dict(tag_map)

    @staticmethod
    def find_related(kb_dir: str, path: str, max_results: int = 10) -> dict:
        """查找与指定条目相关的内容"""
        kb_path = Path(kb_dir)
        target_file = kb_path / path
        
        if not target_file.exists():
            return {"sources": [], "practice": [], "skills": []}
        
        # 读取目标文件的标签
        with open(target_file, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        
        tags = data.get("tags", [])
        if not tags:
            return {"sources": [], "practice": [], "skills": []}
        
        # 从标签索引中查找
        relations_dir = kb_path / "_relations"
        tag_index_file = relations_dir / "tag_index.yaml"
        
        if not tag_index_file.exists():
            TagLinker.link_by_tags(kb_dir)
        
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
        
        # 限制结果数量
        for key in results:
            results[key] = results[key][:max_results]
        
        return results

    @staticmethod
    def recommend_next(kb_dir: str, current_path: str) -> dict:
        """推荐下一步学习内容"""
        related = TagLinker.find_related(kb_dir, current_path)
        
        recommendations = {
            "learn_next": [],
            "practice_next": [],
            "related_skills": [],
        }
        
        # 推荐学习：相关 sources
        recommendations["learn_next"] = related["sources"][:5]
        
        # 推荐练习：相关 practice
        recommendations["practice_next"] = related["practice"][:5]
        
        # 推荐技能：相关 skills
        recommendations["related_skills"] = related["skills"][:5]
        
        return recommendations

    @staticmethod
    def update_entry_tags(kb_dir: str, path: str, new_tags: list) -> bool:
        """更新条目的标签"""
        kb_path = Path(kb_dir)
        target_file = kb_path / path
        
        if not target_file.exists():
            return False
        
        with open(target_file, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        
        # 合并标签
        existing_tags = set(data.get("tags", []))
        for tag in new_tags:
            existing_tags.add(tag)
        
        data["tags"] = list(existing_tags)
        
        with open(target_file, "w", encoding="utf-8") as f:
            yaml.dump(data, f, allow_unicode=True, sort_keys=False)
        
        # 更新标签索引
        TagLinker.link_by_tags(kb_dir)
        
        return True

    @staticmethod
    def get_tag_statistics(kb_dir: str) -> dict:
        """获取标签统计信息"""
        kb_path = Path(kb_dir)
        relations_dir = kb_path / "_relations"
        tag_index_file = relations_dir / "tag_index.yaml"
        
        if not tag_index_file.exists():
            TagLinker.link_by_tags(kb_dir)
        
        with open(tag_index_file, "r", encoding="utf-8") as f:
            tag_index = yaml.safe_load(f) or {}
        
        stats = {
            "total_tags": len(tag_index),
            "by_category": defaultdict(int),
            "hot_tags": [],
        }
        
        # 统计每个标签的关联数量
        tag_counts = []
        for tag, data in tag_index.items():
            count = len(data["sources"]) + len(data["practice"]) + len(data["skills"])
            tag_counts.append((tag, count))
            
            # 分类统计
            for category, cat_data in TagLinker.TAG_CATEGORIES.items():
                if tag in [t.lower() for t in cat_data["tags"]]:
                    stats["by_category"][category] += 1
        
        # 热门标签
        tag_counts.sort(key=lambda x: x[1], reverse=True)
        stats["hot_tags"] = tag_counts[:20]
        
        return stats

    @staticmethod
    def suggest_tags(kb_dir: str, text: str) -> list:
        """根据文本内容建议标签"""
        extracted = TagLinker.extract_tags(text)
        
        # 按类别分组
        suggestions = defaultdict(list)
        for item in extracted:
            suggestions[item["category"]].append(item["tag"])
        
        return dict(suggestions)
