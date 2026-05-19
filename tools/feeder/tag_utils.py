#!/usr/bin/env python3
"""标签工具 — 统一的标签提取、标准化、领域推断"""
import re


def extract_tags(text: str, max_tags: int = 10) -> list:
    """从文本提取英文关键词标签"""
    keywords = re.findall(r"[a-zA-Z]{4,}", text.lower())
    return list(set(keywords))[:max_tags]


def extract_tags_from_data(data: dict, max_tags: int = 10) -> list:
    """从数据字典提取标签（title + text_content 前500字符）"""
    text = data.get("title", "") + " " + data.get("text_content", "")[:500]
    return extract_tags(text, max_tags)


def normalize_tag(tag: str) -> str:
    """标准化标签：小写、空格和下划线统一"""
    return tag.lower().replace(" ", "_").replace("-", "_")


def infer_domain(text: str) -> str:
    """推断取证领域"""
    text_lower = text.lower()

    if any(kw in text_lower for kw in ["web", "php", "javascript", "html", "sql", "xss", "csrf"]):
        return "web"
    elif any(kw in text_lower for kw in ["binary", "pwn", "exploit", "buffer", "overflow", "uaf"]):
        return "binary"
    elif any(kw in text_lower for kw in ["forensics", "取证", "内存", "volatility", "registry"]):
        return "forensics"
    elif any(kw in text_lower for kw in ["crypto", "密码", "rsa", "aes", "encrypt"]):
        return "crypto"
    elif any(kw in text_lower for kw in ["android", "ios", "mobile", "apk", "手机"]):
        return "mobile"
    elif any(kw in text_lower for kw in ["network", "网络", "pcap", "wireshark", "流量"]):
        return "network"
    return "misc"
