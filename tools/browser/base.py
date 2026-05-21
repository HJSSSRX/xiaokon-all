#!/usr/bin/env python3
"""Browser backend abstract base — all backends return the same normalized dict."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional
from pathlib import Path


@dataclass
class BrowserResult:
    """Normalized output across all backends. Compatible with feeder pipeline."""

    url: str
    title: str = ""
    site_type: str = "unknown"
    text_content: str = ""
    html_content: str = ""
    author: str = ""
    publish_date: str = ""
    tags: list = field(default_factory=list)
    code_blocks: list = field(default_factory=list)
    images: list = field(default_factory=list)
    links: list = field(default_factory=list)
    language: str = "unknown"
    screenshot_path: str = ""          # Only set when screenshot requested
    backend_used: str = "static"       # "static" | "playwright" | "cdp"
    error: str = ""

    def to_dict(self) -> dict:
        return {
            "url": self.url,
            "title": self.title,
            "site_type": self.site_type,
            "text_content": self.text_content,
            "html_content": self.html_content,
            "author": self.author,
            "publish_date": self.publish_date,
            "tags": self.tags,
            "code_blocks": self.code_blocks,
            "images": self.images,
            "links": self.links,
            "language": self.language,
            "screenshot_path": self.screenshot_path,
            "backend_used": self.backend_used,
            "error": self.error,
        }


class BrowserBackend(ABC):
    """Abstract browser backend."""

    name: str = "base"

    @abstractmethod
    def fetch(self, url: str, screenshot: bool = False, output_dir: Optional[Path] = None) -> BrowserResult:
        ...

    @abstractmethod
    def health_check(self) -> bool:
        ...

    def close(self):
        pass
