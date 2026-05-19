#!/usr/bin/env python3
"""喂食者模块 - 知识爬取工具包（双轨架构 + AI优化）"""

from .parsers import WebPageParser
from .storage import get_storage_path, save_article, load_article, list_saved_articles
from .organizer import FeederOrganizer
from .skill_generator import SkillGenerator
from .tag_linker import TagLinker
from .ai_tag_engine import AITagEngine

__all__ = [
    "WebPageParser",
    "FeederOrganizer",
    "SkillGenerator",
    "TagLinker",
    "AITagEngine",
    "get_storage_path",
    "save_article",
    "load_article",
    "list_saved_articles",
]

__version__ = "2.1.0"
