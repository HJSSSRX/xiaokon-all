#!/usr/bin/env python3
"""喂食者模块 - 知识爬取工具包（双轨架构 + AI优化）"""

from .parsers import WebPageParser
from .storage import get_storage_path, save_article, load_article, list_saved_articles
from .organizer import (
    organize_article_to_kb,
    organize_solved_to_kb,
    link_source_to_practice,
    search_related_knowledge,
    organize_mindmap_to_kb,
)
from .skill_generator import (
    generate_skill_from_source,
    generate_skill_from_practice,
    merge_skills,
    SKILL_DOMAINS,
)
from .tag_linker import (
    link_by_tags,
    find_related,
    recommend_next,
    update_entry_tags,
    get_tag_statistics,
    suggest_tags,
    extract_tags,
    TAG_CATEGORIES,
)
from .ai_tag_engine import (
    load_index,
    quick_search,
    get_context_for_practice,
    get_context_for_learning,
    suggest_next_action,
    rebuild_cache,
    get_stats,
)
from .js_renderer import JsRenderer, launch_chrome_with_debug
from .api_extractor import JsApiExtractor
from .spa_crawler import SpaCrawler

__all__ = [
    "WebPageParser",
    "get_storage_path", "save_article", "load_article", "list_saved_articles",
    "organize_article_to_kb", "organize_solved_to_kb",
    "link_source_to_practice", "search_related_knowledge", "organize_mindmap_to_kb",
    "generate_skill_from_source", "generate_skill_from_practice", "merge_skills",
    "SKILL_DOMAINS",
    "link_by_tags", "find_related", "recommend_next", "update_entry_tags",
    "get_tag_statistics", "suggest_tags", "extract_tags", "TAG_CATEGORIES",
    "load_index", "quick_search", "get_context_for_practice",
    "get_context_for_learning", "suggest_next_action", "rebuild_cache", "get_stats",
    "JsRenderer", "launch_chrome_with_debug",
    "JsApiExtractor",
    "SpaCrawler",
]

__version__ = "2.2.0"
