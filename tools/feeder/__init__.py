#!/usr/bin/env python3
"""喂食者模块 - 知识爬取工具包"""

from .parsers import WebPageParser
from .storage import get_storage_path, save_article, load_article, list_saved_articles
from .organizer import FeederOrganizer

__all__ = [
    "WebPageParser",
    "FeederOrganizer",
    "get_storage_path",
    "save_article",
    "load_article",
    "list_saved_articles",
]

__version__ = "1.0.0"
