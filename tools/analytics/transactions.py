"""Transaction extraction from the AutoForensicAI knowledge base.

Walks the knowledge base directory, parses YAML frontmatter from solved
problems, skill files, and retrospectives, and extracts item sets for
association rule mining.

Each knowledge file = one transaction. Items = tags + tools from frontmatter.
"""

import os
import re
import yaml
from pathlib import Path
from typing import Dict, List, Set, Optional, Tuple


def _parse_frontmatter(content: str) -> Dict:
    """Extract YAML frontmatter from markdown content."""
    m = re.match(r"^---\s*\n(.*?)\n---", content, re.DOTALL)
    if not m:
        return {}
    try:
        return yaml.safe_load(m.group(1)) or {}
    except yaml.YAMLError:
        return {}


def _read_file_items(filepath: str) -> Tuple[Set[str], Set[str], Set[str]]:
    """Read a file and extract tags, tools, and category.

    Returns:
        (tags_set, tools_set, categories_set)
    """
    tags: Set[str] = set()
    tools: Set[str] = set()
    categories: Set[str] = set()

    ext = os.path.splitext(filepath)[1].lower()

    try:
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()
    except (OSError, UnicodeDecodeError):
        return tags, tools, categories

    if ext in (".md",):
        fm = _parse_frontmatter(content)
    elif ext in (".yaml", ".yml"):
        # For pure YAML files, try parsing the whole thing as a document.
        # Some solved/ YAML files have nested walkthrough structures.
        try:
            fm = yaml.safe_load(content) or {}
        except yaml.YAMLError:
            return tags, tools, categories

        # Flatten nested tools from walkthrough steps
        if isinstance(fm, dict):
            for walkthrough in fm.get("walkthrough", []):
                if isinstance(walkthrough, dict):
                    for tool in walkthrough.get("tools", []):
                        if isinstance(tool, str):
                            tools.add(tool.lower().strip())
            # Extract from meta
            meta = fm.get("meta", {})
            if isinstance(meta, dict):
                fm_tags = meta.get("tags", [])
                fm_tools = meta.get("tools", [])
                fm_cat = meta.get("category", "")
                if isinstance(fm_tags, list):
                    tags.update(t.lower().strip() for t in fm_tags if isinstance(t, str))
                if isinstance(fm_tools, list):
                    tools.update(t.lower().strip() for t in fm_tools if isinstance(t, str))
                if fm_cat:
                    categories.add(fm_cat.lower().strip())
            return tags, tools, categories
    else:
        return tags, tools, categories

    if not isinstance(fm, dict):
        return tags, tools, categories

    fm_tags = fm.get("tags", [])
    fm_tools = fm.get("tools", [])
    fm_cat = fm.get("category", "")

    if isinstance(fm_tags, list):
        tags.update(t.lower().strip() for t in fm_tags if isinstance(t, str))
    if isinstance(fm_tools, list):
        tools.update(t.lower().strip() for t in fm_tools if isinstance(t, str))
    if fm_cat and isinstance(fm_cat, str):
        categories.add(fm_cat.lower().strip())

    return tags, tools, categories


def extract_transactions(
    kb_root: str,
    item_types: Tuple[str, ...] = ("tags", "tools"),
    source_dirs: Optional[List[str]] = None,
) -> Tuple[List[Set[str]], List[str]]:
    """Extract transactions from knowledge base files.

    Each file with frontmatter becomes one transaction. Items are taken from
    the specified frontmatter fields.

    Args:
        kb_root: Path to the knowledge/ directory.
        item_types: Which frontmatter fields to use as items.
                    Any combination of ('tags', 'tools', 'categories').
        source_dirs: Subdirectories to scan (relative to kb_root).
                     Default: ['solved', 'skills'].

    Returns:
        (transactions, filenames) where transactions[i] is the item set from
        filenames[i]. Files with empty item sets are excluded.
    """
    if source_dirs is None:
        source_dirs = ["solved", "skills"]

    transactions: List[Set[str]] = []
    filenames: List[str] = []

    for subdir in source_dirs:
        scan_dir = os.path.join(kb_root, subdir)
        if not os.path.isdir(scan_dir):
            continue

        for root, _dirs, files in os.walk(scan_dir):
            for fname in files:
                # Skip templates, indexes, and non-content files
                if fname.startswith("_") or fname.startswith("."):
                    continue
                ext = os.path.splitext(fname)[1].lower()
                if ext not in (".md", ".yaml", ".yml"):
                    continue

                filepath = os.path.join(root, fname)
                tags, tools, categories = _read_file_items(filepath)

                items: Set[str] = set()
                if "tags" in item_types:
                    items.update(tags)
                if "tools" in item_types:
                    items.update(tools)
                if "categories" in item_types:
                    items.update(categories)

                if items:
                    transactions.append(items)
                    filenames.append(os.path.relpath(filepath, kb_root))

    return transactions, filenames


def load_all_transactions(kb_root: str) -> Tuple[List[Set[str]], List[str]]:
    """Load all available transactions with tags and tools combined."""
    return extract_transactions(kb_root, item_types=("tags", "tools", "categories"))
