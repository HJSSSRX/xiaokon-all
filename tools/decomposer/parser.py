"""Challenge description parser.

Parses challenge descriptions from multiple sources:
- Directory mode: scans for challenge.md, questions.yaml, evidence files
- Text mode: natural language description with regex extraction
- Stdin mode: pipe text description
"""

import os
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple


def _parse_frontmatter(text: str) -> Tuple[dict, str]:
    """Extract YAML frontmatter from markdown text. Returns (frontmatter_dict, body)."""
    if not text.startswith("---\n"):
        return {}, text
    parts = text.split("---\n", 2)
    if len(parts) < 3:
        return {}, text
    try:
        import yaml
        return yaml.safe_load(parts[1]) or {}, parts[2]
    except Exception:
        return {}, parts[2]


def _extract_questions_from_text(text: str) -> List[dict]:
    """Extract question items from free-form text using regex patterns."""
    questions = []

    # Pattern: "Q1:" / "Q1 text" / "1." / "Question 1:" / "第1题"
    patterns = [
        # "Q1:" or "Q1." — newline-separated questions
        r'(?:^|\n)(?:Q|q)(\d+)[：:.\s)]+\s*(.+?)(?=\n(?:Q|q)\d+[：:.\s)]|\n\d+[.、]|\n\Z)',
        r'(?:^|\n)([1-9]\d{0,1})[.、]\s*(.+?)(?=\n[1-9]\d{0,1}[.、]|\n\Z)',
        r'(?:^|\n)(?:Question|问题|题目)\s*(\d+)[：:.\s)]+\s*(.+?)(?=\n(?:Question|问题|题目)\s*\d+|\n\Z)',
        r'第\s*(\d+)\s*题[：:.\s)]*(.+?)(?=\n第\s*\d+\s*题|\n\Z)',
        # Same-line Qs with separator: "Q1: find X. Q2: recover Y."
        r'(?:Q|q)(\d+)[：:.\s)]+\s*(.+?)(?=\s*(?:Q|q)\d+[：:.\s)]|\Z)',
        # Same-line Qs without separator: "Q1 find X. Q2 recover Y."
        r'(?:^|\s)(?:Q|q)(\d+)\s+(.+?)(?=\s*(?:Q|q)\d+\s|\Z)',
    ]

    found_any = False
    for pattern in patterns:
        matches = list(re.finditer(pattern, text, re.DOTALL))
        if matches:
            found_any = True
            for m in matches:
                qid = f"Q{m.group(1)}"
                qtext = m.group(2).strip().replace("\n", " ")[:300]
                if qtext and not any(q["qid"] == qid for q in questions):
                    questions.append({"qid": qid, "question": qtext, "answer_format": ""})
        if found_any:
            break

    # If no structured patterns found, try to find question-like lines
    if not questions:
        for line in text.split("\n"):
            line = line.strip()
            if re.search(r'[fF]lag|答案|answer|密码|password|密钥|key', line):
                if len(line) > 5 and len(line) < 200:
                    questions.append({
                        "qid": f"Q{len(questions) + 1}",
                        "question": line,
                        "answer_format": "",
                    })

    # Detect answer formats
    for q in questions:
        qtext = q["question"]
        if re.search(r'flag\s*[{(]', qtext, re.IGNORECASE):
            q["answer_format"] = "flag{...}"
        elif re.search(r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}', qtext):
            q["answer_format"] = "IP地址"
        elif re.search(r'[0-9a-fA-F]{32,}', qtext):
            q["answer_format"] = "MD5/SHA"
        elif re.search(r'密码|password', qtext, re.IGNORECASE):
            q["answer_format"] = "文本/密码"
        elif re.search(r'时间|time|timestamp', qtext, re.IGNORECASE):
            q["answer_format"] = "时间戳/日期"
        elif re.search(r'手机号|phone|电话|号码', qtext, re.IGNORECASE):
            q["answer_format"] = "手机号/号码"
        elif re.search(r'路径|path|目录|folder', qtext, re.IGNORECASE):
            q["answer_format"] = "文件路径"
        else:
            q["answer_format"] = "文本"

    return questions


def _extract_evidence_from_text(text: str) -> List[str]:
    """Extract evidence file mentions from free-form text."""
    evidence = []

    # Look for common evidence patterns
    evidence_patterns = [
        r'([^\s,，。]+\.(?:e01|vmdk|vhd|vhdx|raw|dmp|vmem|mem|pcap|pcapng'
        r'|apk|ipa|zip|rar|7z|enc|exe|dll|evtx|log|img|dd))',
        r'(?:检材|证据|evidence|附件|镜像|内存|磁盘|流量|手机)\s*[:：]?\s*([^\s,，。\n]+)',
        r'(?:memory|disk|image|pcap|mobile|phone)\s*(?:dump|file|image)?\s*[:：]?\s*([^\s,，。\n]+)',
    ]

    for pattern in evidence_patterns:
        for m in re.finditer(pattern, text, re.IGNORECASE):
            path = m.group(1).strip()
            if path and path not in evidence and len(path) > 2:
                evidence.append(path)

    return evidence


def _extract_domains_from_text(text: str) -> List[str]:
    """Detect forensic domains mentioned in challenge text."""
    domain_keywords = {
        "memory": [r'memory', r'内存', r'进程', r'volatility', r'vol3', r'进程注入'],
        "disk": [r'disk', r'磁盘', r'硬盘', r'分区', r'e01', r'vmdk', r'vhd', r'文件系统'],
        "network": [r'network', r'pcap', r'网络', r'流量', r'wireshark', r'tshark', r'http', r'dns'],
        "mobile": [r'mobile', r'手机', r'apk', r'ipa', r'android', r'ios', r'备份'],
        "binary": [r'binary', r'逆向', r'reverse', r'二进制', r'elf', r'pe', r'ida', r'ghidra'],
        "stego": [r'stego', r'隐写', r'隐写术', r'lsb', r'binwalk', r'watermark'],
        "crypto": [r'crypto', r'密码', r'加密', r'解密', r'rsa', r'aes', r'哈希', r'hash'],
        "log": [r'log', r'日志', r'event', r'evtx', r'syslog', r'audit'],
    }

    detected = []
    text_lower = text.lower()
    for domain, keywords in domain_keywords.items():
        for kw in keywords:
            if re.search(kw, text_lower):
                detected.append(domain)
                break

    return detected


def _load_questions_yaml(filepath: str) -> List[dict]:
    """Load structured questions from a YAML file."""
    try:
        from tools.core.utils import load_yaml
        data = load_yaml(filepath)
        if isinstance(data, list):
            questions = []
            for i, item in enumerate(data):
                if isinstance(item, dict):
                    questions.append({
                        "qid": item.get("qid", f"Q{i + 1}"),
                        "question": item.get("question", item.get("title", "")),
                        "answer_format": item.get("answer_format", item.get("format", "")),
                        "category": item.get("category", ""),
                        "domain": item.get("domain", ""),
                    })
                elif isinstance(item, str):
                    questions.append({
                        "qid": f"Q{i + 1}", "question": item, "answer_format": "",
                        "category": "", "domain": "",
                    })
            return questions
        if isinstance(data, dict):
            questions = []
            for cat, qlist in data.items():
                if isinstance(qlist, list):
                    for j, qitem in enumerate(qlist):
                        if isinstance(qitem, dict):
                            questions.append({
                                "qid": qitem.get("qid", f"Q{len(questions) + 1}"),
                                "question": qitem.get("question", ""),
                                "answer_format": qitem.get("answer_format", ""),
                                "category": cat,
                                "domain": qitem.get("domain", cat),
                            })
            return questions
    except Exception:
        pass
    return []


def parse_challenge(
    challenge_dir: Optional[str] = None,
    challenge_text: Optional[str] = None,
    question_file: Optional[str] = None,
) -> Tuple[str, str, List[dict], List[str], List[str]]:
    """Parse a challenge from various sources.

    Args:
        challenge_dir: Directory containing evidence + optional challenge.md/questions.yaml.
        challenge_text: Free-text challenge description.
        question_file: Path to a specific questions YAML/JSON file.

    Returns:
        (challenge_name, description, questions, evidence_paths, domains)
    """
    name = "Unnamed Challenge"
    description = ""
    questions: List[dict] = []
    evidence_paths: List[str] = []
    domains: List[str] = []

    # Priority 1: Directory mode
    if challenge_dir and os.path.isdir(challenge_dir):
        name = os.path.basename(os.path.abspath(challenge_dir))

        # Look for challenge description file
        for fname in ("challenge.md", "README.md", "题目.md", "题目.txt", "CHALLENGE.md"):
            fpath = os.path.join(challenge_dir, fname)
            if os.path.isfile(fpath):
                with open(fpath, "r", encoding="utf-8") as f:
                    content = f.read()
                fm, body = _parse_frontmatter(content)
                description = body.strip()[:5000]
                name = fm.get("name", fm.get("title", name))
                if not questions:
                    questions = _extract_questions_from_text(body)
                    if fm.get("questions"):
                        questions = _load_questions_dict(fm["questions"])
                break

        if not description:
            description = f"Challenge directory: {name}"

        # Look for questions.yaml / questions.json
        for qfname in ("questions.yaml", "questions.yml", "questions.json", "题目.yaml"):
            qfpath = os.path.join(challenge_dir, qfname)
            if os.path.isfile(qfpath):
                qs = _load_questions_yaml(qfpath)
                if qs:
                    # Merge with existing questions (YAML takes priority)
                    existing_qids = {q["qid"] for q in questions}
                    for q in qs:
                        if q["qid"] not in existing_qids:
                            questions.append(q)
                break

    # Priority 2: Dedicated question file
    if question_file and os.path.isfile(question_file):
        qs = _load_questions_yaml(question_file)
        if qs:
            questions = qs

    # Priority 3: Text input
    if challenge_text:
        if not description:
            description = challenge_text[:5000]
        if not name or name == "Unnamed Challenge":
            # Extract first line as name
            first_line = challenge_text.strip().split("\n")[0][:100]
            name = first_line if first_line else "Text Challenge"
        if not questions:
            questions = _extract_questions_from_text(challenge_text)
        if not evidence_paths:
            evidence_paths = _extract_evidence_from_text(challenge_text)
        if not domains:
            domains = _extract_domains_from_text(challenge_text)

    # Priority 4: Stdin
    if not challenge_dir and not challenge_text and not question_file:
        if not sys.stdin.isatty():
            stdin_text = sys.stdin.read()
            challenge_text = stdin_text
            name = "Stdin Challenge"
            description = stdin_text[:5000]
            questions = _extract_questions_from_text(stdin_text)
            evidence_paths = _extract_evidence_from_text(stdin_text)
            domains = _extract_domains_from_text(stdin_text)

    # Post-process domains: infer from evidence files if not detected from text
    if challenge_dir and os.path.isdir(challenge_dir) and not domains:
        from tools.decomposer.evidence_classifier import classify_evidence, summarize_evidence
        try:
            evidence = classify_evidence(challenge_dir, compute_hashes=False)
            summary = summarize_evidence(evidence)
            domains = summary.get("types_detected", [])
            domains = [d for d in domains if d not in ("unknown", "archive")]
        except Exception:
            pass

    return name, description, questions, evidence_paths, domains


def _load_questions_dict(data) -> List[dict]:
    """Load questions from a dict structure embedded in YAML frontmatter."""
    questions = []
    if isinstance(data, list):
        for i, item in enumerate(data):
            if isinstance(item, dict):
                questions.append({
                    "qid": item.get("qid", f"Q{i + 1}"),
                    "question": item.get("question", item.get("title", str(item))),
                    "answer_format": item.get("answer_format", ""),
                    "category": item.get("category", ""),
                    "domain": item.get("domain", ""),
                })
            elif isinstance(item, str):
                questions.append({"qid": f"Q{i + 1}", "question": item, "answer_format": "", "category": "", "domain": ""})
    elif isinstance(data, dict):
        for cat, qlist in data.items():
            if isinstance(qlist, list):
                for j, qitem in enumerate(qlist):
                    if isinstance(qitem, dict):
                        questions.append({
                            "qid": qitem.get("qid", f"Q{len(questions) + 1}"),
                            "question": qitem.get("question", str(qitem)),
                            "answer_format": qitem.get("answer_format", ""),
                            "category": cat,
                            "domain": qitem.get("domain", cat),
                        })
    return questions
