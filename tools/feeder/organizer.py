#!/usr/bin/env python3
"""喂食者核心模块 - 知识库组织器"""
from pathlib import Path
import re
import yaml


class FeederOrganizer:
    """知识库组织器 - 将爬取的数据整理到知识库"""

    @staticmethod
    def organize_article_to_kb(data: dict, kb_dir: str):
        """将文章数据组织到知识库"""
        kb_path = Path(kb_dir)
        skills_dir = kb_path / "skills"
        skills_dir.mkdir(parents=True, exist_ok=True)

        title = data.get("title", "unknown").strip()
        safe_name = re.sub(r'[\\/:*?"<>|]', "_", title[:50])

        text_content = data.get("text_content", "")
        code_blocks = data.get("code_blocks", [])

        content_lines = []
        if text_content:
            content_lines.append("## 文章内容\n")
            content_lines.append(text_content[:2000])
            if len(text_content) > 2000:
                content_lines.append(f"\n...[内容过长，共{len(text_content)}字符]...")

        if code_blocks:
            content_lines.append("\n## 代码示例\n")
            for i, cb in enumerate(code_blocks[:5], 1):
                lang = cb.get("language", "")
                code = cb.get("code", "")[:300]
                content_lines.append(f"\n### 代码块 {i} ({lang})\n```\n{code}\n```")

        site_type = data.get("site_type", "unknown")
        category = "web"
        if site_type == "github":
            category = "server"
        elif site_type in ["csdn", "jianshu", "zhihu", "medium"]:
            category = "web"

        entry = {
            "name": title,
            "category": category,
            "description": f"{site_type} 文章: {title}",
            "content": "\n".join(content_lines),
            "keywords": FeederOrganizer._extract_keywords_from_text(title + " " + text_content[:500]),
            "related": [],
            "source": data.get("url", ""),
        }

        file_path = skills_dir / f"{safe_name}.md"
        with open(file_path, "w", encoding="utf-8") as f:
            yaml.dump(entry, f, allow_unicode=True, sort_keys=False)
        print(f"[FEEDER] 创建技能卡片: {file_path}")

    @staticmethod
    def organize_mindmap_to_kb(data: dict, kb_dir: str):
        """将思维导图数据组织到知识库"""
        kb_path = Path(kb_dir)
        kb_path.mkdir(parents=True, exist_ok=True)

        skills_dir = kb_path / "skills"
        skills_dir.mkdir(parents=True, exist_ok=True)

        categories = data.get("categories", [])
        knowledge_items = data.get("knowledge_items", [])

        for category in categories:
            cat_name = category.get("name", "unknown")
            items_in_category = [
                item for item in knowledge_items
                if item.get("category") == cat_name
            ]

            if items_in_category:
                skill_entry = {
                    "name": cat_name,
                    "category": FeederOrganizer._infer_category(cat_name),
                    "description": f"{cat_name} 相关知识要点",
                    "content": "\n".join([f"- {item['title']}" for item in items_in_category]),
                    "keywords": FeederOrganizer._extract_keywords_from_text(cat_name),
                    "related": []
                }

                safe_name = re.sub(r'[\\/:*?"<>|]', "_", cat_name)
                file_path = skills_dir / f"{safe_name}.yaml"

                with open(file_path, "w", encoding="utf-8") as f:
                    yaml.dump(skill_entry, f, allow_unicode=True, sort_keys=False)

                print(f"[FEEDER] 创建技能卡片: {file_path}")

        nodes = data.get("nodes", [])
        if nodes:
            mindmap_dir = kb_path / "mindmap"
            mindmap_dir.mkdir(parents=True, exist_ok=True)

            for node in nodes:
                node_entry = {
                    "id": node["id"],
                    "name": node["name"],
                    "level": node["level"],
                    "parent_id": node["parent_id"],
                    "children": node.get("children", []),
                    "category": next(
                        (c["name"] for c in categories if c["id"] == node["parent_id"]),
                        "root"
                    )
                }

                file_path = mindmap_dir / f"{node['id']}.yaml"
                with open(file_path, "w", encoding="utf-8") as f:
                    yaml.dump(node_entry, f, allow_unicode=True, sort_keys=False)

        print(f"\n思维导图整理完成！")
        print(f"创建了 {len(categories)} 个分类技能卡片")
        print(f"创建了 {len(nodes)} 个节点文件")

    @staticmethod
    def _infer_category(text: str) -> str:
        """根据文本推断分类"""
        text_lower = text.lower()
        if any(keyword in text_lower for keyword in ["web", "php", "javascript", "frontend"]):
            return "web"
        elif any(keyword in text_lower for keyword in ["binary", "pwn", "exploit", "memory"]):
            return "binary"
        elif any(keyword in text_lower for keyword in ["forensics", "取证", "证据"]):
            return "forensics"
        elif any(keyword in text_lower for keyword in ["crypto", "crypto", "密码"]):
            return "crypto"
        else:
            return "other"

    @staticmethod
    def _extract_keywords(rel):
        text = " ".join([rel.get("question_text", "")] + rel.get("answers", []))
        keywords = re.findall(r"[a-zA-Z]{4,}", text.lower())
        return list(set(keywords))[:10]

    @staticmethod
    def _extract_keywords_from_text(text):
        keywords = re.findall(r"[a-zA-Z]{4,}", text.lower())
        return list(set(keywords))[:10]
