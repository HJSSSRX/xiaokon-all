#!/usr/bin/env python3
"""喂食者核心模块 - 知识库组织器（双轨架构）"""
from pathlib import Path
import re
import yaml
from datetime import datetime

from . import skill_generator
from . import tag_linker


def organize_article_to_kb(data: dict, kb_dir: str, reindex: bool = True) -> str:
    """将文章数据组织到知识库（轨道一：Sources）"""
    kb_path = Path(kb_dir)

    sources_dir = kb_path / "sources" / "articles"
    sources_dir.mkdir(parents=True, exist_ok=True)

    domain = _infer_domain(data)
    domain_dir = sources_dir / domain
    domain_dir.mkdir(parents=True, exist_ok=True)

    title = data.get("title", "unknown").strip()
    safe_name = re.sub(r'[\\/:*?"<>|]', "_", title[:50])

    source_entry = {
        "type": "source",
        "category": "article",
        "domain": domain,
        "name": title,
        "source_url": data.get("url", ""),
        "site_type": data.get("site_type", "unknown"),
        "date": datetime.now().strftime("%Y-%m-%d"),
        "tags": _extract_tags(data),
        "related_practice": [],
        "content_preview": data.get("text_content", "")[:500],
    }

    source_file = domain_dir / f"{safe_name}.yaml"
    with open(source_file, "w", encoding="utf-8") as f:
        yaml.dump(source_entry, f, allow_unicode=True, sort_keys=False)
    print(f"[FEEDER] 创建知识来源: {source_file}")

    _update_skills_index(kb_path, domain, safe_name, data)
    _update_sources_index(kb_path, domain, safe_name, source_entry)

    if reindex:
        skill_generator.generate_skill_from_source(data, kb_dir)
        tag_linker.link_by_tags(kb_dir)

    return str(source_file)


def organize_solved_to_kb(data: dict, kb_dir: str, reindex: bool = True) -> str:
    """将解题数据组织到知识库（轨道二：Practice）"""
    kb_path = Path(kb_dir)

    practice_dir = kb_path / "practice" / "solved"
    practice_dir.mkdir(parents=True, exist_ok=True)

    competition = data.get("competition", "unknown")
    question_id = data.get("question_id", "unknown")

    comp_dir = practice_dir / competition
    comp_dir.mkdir(parents=True, exist_ok=True)

    practice_entry = {
        "type": "practice",
        "category": "solved",
        "competition": competition,
        "question_id": question_id,
        "title": data.get("title", ""),
        "domain": data.get("domain", "unknown"),
        "difficulty": data.get("difficulty", "medium"),
        "date": datetime.now().strftime("%Y-%m-%d"),
        "tags": data.get("tags", []),
        "related_sources": [],
        "learned_skills": [],
        "solution": data.get("solution", ""),
        "key_findings": data.get("key_findings", []),
    }

    practice_file = comp_dir / f"{question_id}.yaml"
    with open(practice_file, "w", encoding="utf-8") as f:
        yaml.dump(practice_entry, f, allow_unicode=True, sort_keys=False)
    print(f"[FEEDER] 创建解题记录: {practice_file}")

    _update_practice_index(kb_path, competition, question_id, practice_entry)

    if reindex:
        skill_generator.generate_skill_from_practice(data, kb_dir)
        tag_linker.link_by_tags(kb_dir)

    return str(practice_file)


def link_source_to_practice(kb_dir: str, source_path: str, practice_path: str):
    """关联知识来源到题目"""
    kb_path = Path(kb_dir)
    relations_dir = kb_path / "_relations"
    relations_dir.mkdir(parents=True, exist_ok=True)

    stp_file = relations_dir / "source_to_practice.yaml"
    stp_data = {}
    if stp_file.exists():
        with open(stp_file, "r", encoding="utf-8") as f:
            stp_data = yaml.safe_load(f) or {}

    source_key = source_path.replace("/", ".").replace("\\", ".")
    if source_key not in stp_data:
        stp_data[source_key] = []
    if practice_path not in stp_data[source_key]:
        stp_data[source_key].append(practice_path)

    with open(stp_file, "w", encoding="utf-8") as f:
        yaml.dump(stp_data, f, allow_unicode=True, sort_keys=False)

    pts_file = relations_dir / "practice_to_source.yaml"
    pts_data = {}
    if pts_file.exists():
        with open(pts_file, "r", encoding="utf-8") as f:
            pts_data = yaml.safe_load(f) or {}

    practice_key = practice_path.replace("/", ".").replace("\\", ".")
    if practice_key not in pts_data:
        pts_data[practice_key] = {"sources": [], "skills": []}
    if source_path not in pts_data[practice_key]["sources"]:
        pts_data[practice_key]["sources"].append(source_path)

    with open(pts_file, "w", encoding="utf-8") as f:
        yaml.dump(pts_data, f, allow_unicode=True, sort_keys=False)

    print(f"[FEEDER] 创建关联: {source_path} <-> {practice_path}")


def search_related_knowledge(kb_dir: str, tags: list) -> dict:
    """根据标签搜索相关知识和题目"""
    kb_path = Path(kb_dir)
    relations_dir = kb_path / "_relations"

    results = {"sources": [], "practice": [], "skills": []}

    tag_index_file = relations_dir / "tag_index.yaml"
    if not tag_index_file.exists():
        return results

    with open(tag_index_file, "r", encoding="utf-8") as f:
        tag_index = yaml.safe_load(f) or {}

    for tag in tags:
        tag_lower = tag.lower().replace(" ", "_")
        if tag_lower in tag_index:
            tag_data = tag_index[tag_lower]
            results["sources"].extend(tag_data.get("sources", []))
            results["practice"].extend(tag_data.get("practice", []))
            results["skills"].extend(tag_data.get("skills", []))

    for key in results:
        results[key] = list(set(results[key]))

    return results


def organize_mindmap_to_kb(data: dict, kb_dir: str):
    """将思维导图数据组织到知识库"""
    kb_path = Path(kb_dir)
    kb_path.mkdir(parents=True, exist_ok=True)

    mindmaps_dir = kb_path / "sources" / "mindmaps"
    mindmaps_dir.mkdir(parents=True, exist_ok=True)

    categories = data.get("categories", [])
    knowledge_items = data.get("knowledge_items", [])

    mindmap_entry = {
        "type": "source",
        "category": "mindmap",
        "categories": [{"id": c["id"], "name": c["name"]} for c in categories],
        "items_count": len(knowledge_items),
        "date": datetime.now().strftime("%Y-%m-%d"),
    }

    mindmap_file = mindmaps_dir / f"mindmap_{datetime.now().strftime('%Y%m%d_%H%M%S')}.yaml"
    with open(mindmap_file, "w", encoding="utf-8") as f:
        yaml.dump(mindmap_entry, f, allow_unicode=True, sort_keys=False)

    skills_dir = kb_path / "skills"
    skills_dir.mkdir(parents=True, exist_ok=True)

    for category in categories:
        cat_name = category.get("name", "unknown")
        items_in_category = [
            item for item in knowledge_items
            if item.get("category") == cat_name
        ]

        if items_in_category:
            skill_entry = {
                "name": cat_name,
                "category": _infer_category(cat_name),
                "description": f"{cat_name} 相关知识要点",
                "content": "\n".join([f"- {item['title']}" for item in items_in_category]),
                "keywords": _extract_keywords_from_text(cat_name),
                "related": []
            }

            safe_name = re.sub(r'[\\/:*?"<>|]', "_", cat_name)
            file_path = skills_dir / f"{safe_name}.yaml"

            with open(file_path, "w", encoding="utf-8") as f:
                yaml.dump(skill_entry, f, allow_unicode=True, sort_keys=False)

            print(f"[FEEDER] 创建技能卡片: {file_path}")

    print(f"\n思维导图整理完成！")
    print(f"创建了 {len(categories)} 个分类技能卡片")


def _infer_domain(data: dict) -> str:
    """推断文章领域"""
    text = (data.get("title", "") + " " + data.get("text_content", "")[:500]).lower()

    if any(kw in text for kw in ["web", "php", "javascript", "html", "sql", "xss", "csrf"]):
        return "web"
    elif any(kw in text for kw in ["binary", "pwn", "exploit", "buffer", "overflow", "uaf"]):
        return "binary"
    elif any(kw in text for kw in ["forensics", "取证", "内存", "volatility", "registry"]):
        return "forensics"
    elif any(kw in text for kw in ["crypto", "密码", "rsa", "aes", "encrypt"]):
        return "crypto"
    elif any(kw in text for kw in ["android", "ios", "mobile", "apk", "手机"]):
        return "mobile"
    elif any(kw in text for kw in ["network", "网络", "pcap", "wireshark", "流量"]):
        return "network"
    else:
        return "misc"


def _infer_category(text: str) -> str:
    """根据文本推断分类"""
    text_lower = text.lower()
    if any(keyword in text_lower for keyword in ["web", "php", "javascript", "frontend"]):
        return "web"
    elif any(keyword in text_lower for keyword in ["binary", "pwn", "exploit", "memory"]):
        return "binary"
    elif any(keyword in text_lower for keyword in ["forensics", "取证", "证据"]):
        return "forensics"
    elif any(keyword in text_lower for keyword in ["crypto", "密码"]):
        return "crypto"
    else:
        return "other"


def _extract_tags(data: dict) -> list:
    """提取标签"""
    text = data.get("title", "") + " " + data.get("text_content", "")[:500]
    keywords = re.findall(r"[a-zA-Z]{4,}", text.lower())
    return list(set(keywords))[:10]


def _extract_keywords_from_text(text):
    keywords = re.findall(r"[a-zA-Z]{4,}", text.lower())
    return list(set(keywords))[:10]


def _update_sources_index(kb_path: Path, domain: str, name: str, entry: dict):
    """更新知识来源索引"""
    index_file = kb_path / "sources" / "_index.yaml"
    index_data = {"articles": {}}

    if index_file.exists():
        with open(index_file, "r", encoding="utf-8") as f:
            index_data = yaml.safe_load(f) or {"articles": {}}

    if domain not in index_data.get("articles", {}):
        index_data["articles"][domain] = []

    index_data["articles"][domain].append({
        "name": entry["name"],
        "path": f"sources/articles/{domain}/{name}.yaml",
        "tags": entry["tags"],
    })

    with open(index_file, "w", encoding="utf-8") as f:
        yaml.dump(index_data, f, allow_unicode=True, sort_keys=False)


def _update_practice_index(kb_path: Path, competition: str, question_id: str, entry: dict):
    """更新解题索引"""
    index_file = kb_path / "practice" / "_index.yaml"
    index_data = {"solved": {}}

    if index_file.exists():
        with open(index_file, "r", encoding="utf-8") as f:
            index_data = yaml.safe_load(f) or {"solved": {}}

    if competition not in index_data.get("solved", {}):
        index_data["solved"][competition] = {"questions": []}

    index_data["solved"][competition]["questions"].append({
        "id": question_id,
        "title": entry["title"],
        "tags": entry["tags"],
    })

    with open(index_file, "w", encoding="utf-8") as f:
        yaml.dump(index_data, f, allow_unicode=True, sort_keys=False)


def _update_skills_index(kb_path: Path, domain: str, name: str, data: dict):
    """更新技能索引（融合层）"""
    skills_dir = kb_path / "skills" / domain
    skills_dir.mkdir(parents=True, exist_ok=True)

    text_content = data.get("text_content", "")
    code_blocks = data.get("code_blocks", [])

    content_lines = []
    if text_content:
        content_lines.append("## 文章内容\n")
        content_lines.append(text_content[:2000])

    if code_blocks:
        content_lines.append("\n## 代码示例\n")
        for i, cb in enumerate(code_blocks[:5], 1):
            lang = cb.get("language", "")
            code = cb.get("code", "")[:300]
            content_lines.append(f"\n### 代码块 {i} ({lang})\n```\n{code}\n```")

    skill_entry = {
        "name": data.get("title", "unknown"),
        "domain": domain,
        "source": data.get("url", ""),
        "content": "\n".join(content_lines),
        "keywords": _extract_keywords_from_text(text_content[:500]),
    }

    skill_file = skills_dir / f"{name}.yaml"
    with open(skill_file, "w", encoding="utf-8") as f:
        yaml.dump(skill_entry, f, allow_unicode=True, sort_keys=False)
