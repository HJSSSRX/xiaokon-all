#!/usr/bin/env python3
"""Static HTTP backend — wraps the existing WebPageParser (requests + BeautifulSoup).

Zero new dependencies. Fast for simple sites, no JS rendering.
"""

from pathlib import Path
from typing import Optional

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from feeder.parsers import WebPageParser
from .base import BrowserBackend, BrowserResult


class StaticBackend(BrowserBackend):
    """Static HTTP fetcher. Inherits all existing site handlers from WebPageParser."""

    name = "static"

    def __init__(self):
        self._parser = WebPageParser()

    def fetch(self, url: str, screenshot: bool = False, output_dir: Optional[Path] = None) -> BrowserResult:
        raw = self._parser.parse(url)

        if "error" in raw:
            return BrowserResult(url=url, error=raw["error"], backend_used="static")

        return BrowserResult(
            url=url,
            title=raw.get("title", ""),
            site_type=raw.get("site_type", "unknown"),
            text_content=raw.get("text_content", ""),
            html_content=raw.get("content", ""),
            author=raw.get("author", ""),
            publish_date=raw.get("publish_date", ""),
            tags=raw.get("tags", []),
            code_blocks=raw.get("code_blocks", []),
            images=raw.get("images", []),
            links=raw.get("links", []),
            language=raw.get("language", "unknown"),
            backend_used="static",
        )

    def health_check(self) -> bool:
        try:
            import requests
            return True
        except ImportError:
            return False

    def close(self):
        self._parser.session.close()
