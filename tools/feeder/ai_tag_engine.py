#!/usr/bin/env python3
"""喂食者核心模块 - AI标签引擎（高效版）"""
from pathlib import Path
import re
import yaml
import json
from collections import defaultdict


class AITagEngine:
    """AI标签引擎 - 为AI Agent优化的高效标签系统"""

    _cache = None
    _cache_path = None

    @staticmethod
    def load_index(kb_dir: str, use_cache: bool = True) -> dict:
        """加载标签索引（带缓存）"""
        kb_path = Path(kb_dir)
        cache_file = kb_path / "_relations" / "tag_index_cache.json"
        
        # 检查缓存
        if use_cache and AITagEngine._cache is not None:
            if AITagEngine._cache_path == str(kb_path):
                return AITagEngine._cache
        
        # 尝试加载JSON缓存
        if cache_file.exists():
            with open(cache_file, "r", encoding="utf-8") as f:
                AITagEngine._cache = json.load(f)
                AITagEngine._cache_path = str(kb_path)
                return AITagEngine._cache
        
        # 加载YAML并转换为高效格式
        tag_file = kb_path / "_relations" / "tag_index.yaml"
        if tag_file.exists():
            with open(tag_file, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
            
            # 转换为高效格式
            optimized = {}
            for tag, info in data.items():
                optimized[tag] = {
                    "s": info.get("sources", []),
                    "p": info.get("practice", []),
                    "k": info.get("skills", []),
                }
            
            # 保存缓存
            cache_file.parent.mkdir(parents=True, exist_ok=True)
            with open(cache_file, "w", encoding="utf-8") as f:
                json.dump(optimized, f, ensure_ascii=False)
            
            AITagEngine._cache = optimized
            AITagEngine._cache_path = str(kb_path)
            return optimized
        
        return {}

    @staticmethod
    def quick_search(kb_dir: str, tags: list) -> dict:
        """快速搜索 - AI专用接口"""
        index = AITagEngine.load_index(kb_dir)
        
        result = {"s": [], "p": [], "k": []}
        seen = {"s": set(), "p": set(), "k": set()}
        
        for tag in tags:
            tag_lower = tag.lower().replace(" ", "_").replace("-", "_")
            if tag_lower in index:
                for key in ["s", "p", "k"]:
                    for item in index[tag_lower][key]:
                        if item not in seen[key]:
                            seen[key].add(item)
                            result[key].append(item)
        
        return result

    @staticmethod
    def get_context_for_practice(kb_dir: str, question_data: dict) -> dict:
        """为做题提供上下文 - AI专用接口"""
        tags = question_data.get("tags", [])
        domain = question_data.get("domain", "")
        
        # 快速搜索相关内容
        related = AITagEngine.quick_search(kb_dir, tags)
        
        # 加载最相关的技能卡片
        skills_content = []
        for skill_path in related["k"][:3]:
            skill_file = Path(kb_dir) / skill_path
            if skill_file.exists():
                with open(skill_file, "r", encoding="utf-8") as f:
                    skill_data = yaml.safe_load(f) or {}
                    skills_content.append({
                        "name": skill_data.get("name", ""),
                        "summary": skill_data.get("summary", ""),
                        "techniques": skill_data.get("techniques", []),
                        "commands": skill_data.get("commands", []),
                    })
        
        # 加载最相关的知识来源
        sources_content = []
        for source_path in related["s"][:2]:
            source_file = Path(kb_dir) / source_path
            if source_file.exists():
                with open(source_file, "r", encoding="utf-8") as f:
                    source_data = yaml.safe_load(f) or {}
                    sources_content.append({
                        "name": source_data.get("name", ""),
                        "preview": source_data.get("content_preview", "")[:500],
                    })
        
        return {
            "related_skills": skills_content,
            "related_sources": sources_content,
            "similar_questions": related["p"][:5],
        }

    @staticmethod
    def get_context_for_learning(kb_dir: str, topic: str) -> dict:
        """为学习提供上下文 - AI专用接口"""
        # 从主题提取标签
        tags = AITagEngine._extract_tags_from_topic(topic)
        
        # 快速搜索
        related = AITagEngine.quick_search(kb_dir, tags)
        
        # 构建学习路径
        learning_path = []
        
        # 1. 先学技能
        for skill_path in related["k"][:2]:
            skill_file = Path(kb_dir) / skill_path
            if skill_file.exists():
                with open(skill_file, "r", encoding="utf-8") as f:
                    skill_data = yaml.safe_load(f) or {}
                    learning_path.append({
                        "type": "skill",
                        "name": skill_data.get("name", ""),
                        "summary": skill_data.get("summary", ""),
                        "difficulty": skill_data.get("difficulty", "medium"),
                    })
        
        # 2. 再练题目
        for practice_path in related["p"][:3]:
            practice_file = Path(kb_dir) / practice_path
            if practice_file.exists():
                with open(practice_file, "r", encoding="utf-8") as f:
                    practice_data = yaml.safe_load(f) or {}
                    learning_path.append({
                        "type": "practice",
                        "name": practice_data.get("title", ""),
                        "difficulty": practice_data.get("difficulty", "medium"),
                    })
        
        return {
            "learning_path": learning_path,
            "related_sources": related["s"][:5],
            "tags": tags,
        }

    @staticmethod
    def suggest_next_action(kb_dir: str, current_context: dict) -> dict:
        """建议下一步行动 - AI专用接口"""
        tags = current_context.get("tags", [])
        completed = current_context.get("completed", [])
        
        related = AITagEngine.quick_search(kb_dir, tags)
        
        # 过滤已完成的内容
        suggestions = {
            "learn": [],
            "practice": [],
            "review": [],
        }
        
        for item in related["s"]:
            if item not in completed:
                suggestions["learn"].append(item)
        
        for item in related["p"]:
            if item not in completed:
                suggestions["practice"].append(item)
        
        for item in related["k"]:
            if item not in completed:
                suggestions["review"].append(item)
        
        # 只返回前5个
        for key in suggestions:
            suggestions[key] = suggestions[key][:5]
        
        return suggestions

    @staticmethod
    def _extract_tags_from_topic(topic: str) -> list:
        """从主题提取标签"""
        tags = []
        topic_lower = topic.lower()
        
        # 取证类型
        forensics_keywords = {
            "内存": "memory_forensics",
            "磁盘": "disk_forensics",
            "网络": "network_forensics",
            "移动": "mobile_forensics",
            "流量": "traffic_analysis",
            "日志": "log_analysis",
        }
        
        for kw, tag in forensics_keywords.items():
            if kw in topic_lower:
                tags.append(tag)
        
        # 攻击类型
        attack_keywords = {
            "sql": "sql_injection",
            "注入": "sql_injection",
            "xss": "xss",
            "反序列化": "deserialization",
            "溢出": "buffer_overflow",
        }
        
        for kw, tag in attack_keywords.items():
            if kw in topic_lower:
                tags.append(tag)
        
        # 工具
        tools = ["volatility", "wireshark", "ida", "sqlmap", "burpsuite"]
        for tool in tools:
            if tool in topic_lower:
                tags.append(tool)
        
        return tags

    @staticmethod
    def rebuild_cache(kb_dir: str) -> bool:
        """重建缓存"""
        AITagEngine._cache = None
        AITagEngine._cache_path = None
        
        cache_file = Path(kb_dir) / "_relations" / "tag_index_cache.json"
        if cache_file.exists():
            cache_file.unlink()
        
        AITagEngine.load_index(kb_dir, use_cache=False)
        return True

    @staticmethod
    def get_stats(kb_dir: str) -> dict:
        """获取统计信息 - AI专用接口"""
        index = AITagEngine.load_index(kb_dir)
        
        stats = {
            "total_tags": len(index),
            "total_sources": 0,
            "total_practice": 0,
            "total_skills": 0,
            "hot_tags": [],
        }
        
        tag_counts = []
        for tag, data in index.items():
            count = len(data["s"]) + len(data["p"]) + len(data["k"])
            tag_counts.append((tag, count))
            stats["total_sources"] += len(data["s"])
            stats["total_practice"] += len(data["p"])
            stats["total_skills"] += len(data["k"])
        
        # 去重计数
        all_sources = set()
        all_practice = set()
        all_skills = set()
        
        for data in index.values():
            all_sources.update(data["s"])
            all_practice.update(data["p"])
            all_skills.update(data["k"])
        
        stats["total_sources"] = len(all_sources)
        stats["total_practice"] = len(all_practice)
        stats["total_skills"] = len(all_skills)
        
        # 热门标签
        tag_counts.sort(key=lambda x: x[1], reverse=True)
        stats["hot_tags"] = tag_counts[:10]
        
        return stats
