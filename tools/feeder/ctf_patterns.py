#!/usr/bin/env python3
"""CTF vulnerability pattern database.

Structured vulnerability patterns extracted from solved challenges and
general web security knowledge. Used by ctf_recognizer.py for automatic
challenge classification and attack planning.

Pattern structure:
    VulnerabilityPattern(
        id="sqli_blind",
        category="Web",
        subcategory="SQL注入",
        technique="Boolean盲注",
        tags=["SQL注入", "Web"],
        indicators={
            "url_params": ["id=", "uid=", "pid=", "page=", "cat="],
            "url_patterns": ["\\?id=\\d+"],
            "response": {
                "different_sizes": True,  # TRUE/FALSE give different response sizes
                "error_keywords": ["mysql", "mariadb", "syntax", "SQL"],
            },
        },
        prerequisites={
            "db_type": ["mysql", "mariadb", "postgresql"],
            "injection_type": ["boolean", "union", "error", "time"],
        },
        attack_chain=[
            {"phase": "recon", "action": "test_injection", "tool": "manual"},
            {"phase": "exploit", "action": "extract_data", "tool": "blind_sqli_extractor"},
            {"phase": "flag", "action": "read_flag", "tool": "direct"},
        ],
        waf_bypass={
            "space": "/**/",
            "and": "&&",
            "blocked": ["limit", "table", "handler", "union", "load_file"],
        },
        solved_examples=["WebsiteManger"],
        confidence_base=0.8,
    )
"""

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple


@dataclass
class VulnerabilityPattern:
    """A known vulnerability pattern / attack template."""

    id: str                           # Unique ID, e.g. "sqli_blind_boolean"
    category: str                     # Top-level: Web, Pwn, Crypto, Misc, Reverse
    subcategory: str                  # e.g. SQL注入, 文件包含, SSRF
    technique: str                    # e.g. Boolean盲注, UNION注入, file://读取
    tags: List[str]                   # CTFHub tags associated with this pattern
    keywords: List[str]               # Chinese/English keywords in description
    indicators: Dict = field(default_factory=dict)
    prerequisites: Dict = field(default_factory=dict)
    attack_chain: List[Dict] = field(default_factory=list)
    waf_bypass: Dict = field(default_factory=dict)
    solved_examples: List[str] = field(default_factory=list)  # Challenge names
    confidence_base: float = 0.7      # Base confidence when tags match
    difficulty_range: Tuple[float, float] = (5.0, 10.0)

    def match_score(self, tags: Set[str], description: str = "") -> float:
        """Calculate match score (0-1) against challenge metadata."""
        score = 0.0
        total = 0.0

        # Tag matching (weight: 0.5) — case-insensitive
        if self.tags:
            self_tags_lower = {t.lower() for t in self.tags}
            tags_lower = {t.lower() for t in tags}
            tag_overlap = len(self_tags_lower & tags_lower)
            tag_coverage = tag_overlap / max(len(self_tags_lower), 1)
            score += 0.5 * tag_coverage
        total += 0.5

        # Keyword matching (weight: 0.3)
        if self.keywords and description:
            desc_lower = description.lower()
            kw_matches = sum(1 for kw in self.keywords if kw.lower() in desc_lower)
            kw_score = kw_matches / max(len(self.keywords), 1)
            score += 0.3 * kw_score
        total += 0.3

        # Tag priority bonus (weight: 0.2)
        if self.subcategory.lower() in {t.lower() for t in tags}:
            score += 0.2
        total += 0.2

        return score / total if total > 0 else 0.0

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "category": self.category,
            "subcategory": self.subcategory,
            "technique": self.technique,
            "tags": self.tags,
            "keywords": self.keywords,
            "solved_examples": self.solved_examples,
            "confidence_base": self.confidence_base,
        }


# ── Pattern Database ──────────────────────────────────────────────────────

PATTERNS: List[VulnerabilityPattern] = [
    # ── SQL Injection ──
    VulnerabilityPattern(
        id="sqli_blind_boolean",
        category="Web",
        subcategory="SQL注入",
        technique="Boolean盲注",
        tags=["SQL注入", "Web"],
        keywords=["sql", "注入", "injection", "database", "query", "select",
                   "盲注", "blind", "boolean", "bool"],
        indicators={
            "url_params": ["id", "uid", "pid", "page", "cat", "item", "product", "news", "article"],
            "injection_chars": ["'", '"', "\\", ")", " AND ", " OR "],
            "response": {"different_sizes": True, "image_oracle": True},
        },
        prerequisites={"db_type": ["mysql", "mariadb", "sqlite", "postgresql"]},
        attack_chain=[
            {"phase": "recon", "action": "test_injection_point", "detail": "Test single quote, double quote, backslash"},
            {"phase": "recon", "action": "identify_oracle", "detail": "Find TRUE/FALSE response difference"},
            {"phase": "recon", "action": "check_waf", "detail": "Test space, AND, SELECT, UNION keywords"},
            {"phase": "recon", "action": "bypass_waf", "detail": "Use /**/ for space, && for AND, case variation"},
            {"phase": "extract", "action": "get_db_info", "detail": "Extract database(), version(), user()"},
            {"phase": "extract", "action": "get_tables", "detail": "Extract table names from information_schema"},
            {"phase": "extract", "action": "get_columns", "detail": "Extract column names for each table"},
            {"phase": "extract", "action": "get_data", "detail": "Extract flag or credentials from relevant table"},
            {"phase": "alt", "action": "check_ssrf", "detail": "If SQLi too slow, check for SSRF/file read endpoints"},
        ],
        waf_bypass={
            "space": "/**/", "and": "&&", "or": "||",
            "blocked": ["limit", "handler", "union", "load_file", "sleep", "benchmark"],
        },
        solved_examples=["WebsiteManger"],
        confidence_base=0.85,
    ),

    VulnerabilityPattern(
        id="sqli_union",
        category="Web",
        subcategory="SQL注入",
        technique="UNION注入",
        tags=["SQL注入", "Web"],
        keywords=["sql", "注入", "injection", "union", "database", "query"],
        indicators={
            "url_params": ["id", "uid", "pid", "page", "cat"],
            "response": {"column_count_discovery": True, "visible_output": True},
        },
        prerequisites={"db_type": ["mysql", "mariadb", "sqlite"]},
        attack_chain=[
            {"phase": "recon", "action": "find_column_count", "detail": "ORDER BY 1,2,3... until error"},
            {"phase": "recon", "action": "find_visible_columns", "detail": "UNION SELECT 1,2,3... find output position"},
            {"phase": "extract", "action": "dump_data", "detail": "UNION SELECT to extract table/column/flag data"},
        ],
        solved_examples=[],
        confidence_base=0.8,
    ),

    VulnerabilityPattern(
        id="sqli_error_based",
        category="Web",
        subcategory="SQL注入",
        technique="报错注入",
        tags=["SQL注入", "Web"],
        keywords=["sql", "注入", "injection", "error", "报错", "extractvalue", "updatexml"],
        indicators={
            "url_params": ["id", "uid", "pid"],
            "response": {"error_messages": True, "stack_traces": True},
        },
        prerequisites={"db_type": ["mysql", "mariadb"]},
        attack_chain=[
            {"phase": "recon", "action": "trigger_error", "detail": "Test extractvalue/updatexml/floor rand"},
            {"phase": "extract", "action": "error_extract", "detail": "Use error-based functions to leak data"},
        ],
        solved_examples=[],
        confidence_base=0.75,
    ),

    VulnerabilityPattern(
        id="sqli_time_blind",
        category="Web",
        subcategory="SQL注入",
        technique="时间盲注",
        tags=["SQL注入", "Web"],
        keywords=["sql", "注入", "injection", "time", "时间", "sleep", "benchmark", "delay"],
        indicators={
            "url_params": ["id", "uid", "pid"],
            "response": {"consistent_size": True, "no_error": True},
        },
        prerequisites={"db_type": ["mysql", "mariadb", "postgresql"]},
        attack_chain=[
            {"phase": "recon", "action": "test_sleep", "detail": "Test sleep()/benchmark()/pg_sleep()"},
            {"phase": "extract", "action": "time_extract", "detail": "Extract data via time delays"},
        ],
        solved_examples=[],
        confidence_base=0.7,
    ),

    # ── File Inclusion ──
    VulnerabilityPattern(
        id="lfi_include",
        category="Web",
        subcategory="文件包含",
        technique="本地文件包含(LFI)",
        tags=["文件包含", "Web", "PHP"],
        keywords=["include", "require", "file", "文件包含", "lfi", "readfile",
                   "include_once", "require_once", "file_get_contents"],
        indicators={
            "url_params": ["file", "page", "include", "path", "template", "lang", "view", "load"],
            "response": {"php_execution": True, "source_visible": False},
        },
        prerequisites={"language": ["php"]},
        attack_chain=[
            {"phase": "recon", "action": "check_phpinfo", "detail": "Look for phpinfo() output"},
            {"phase": "recon", "action": "test_path_traversal", "detail": "Try ../../etc/passwd or /etc/passwd"},
            {"phase": "recon", "action": "test_wrappers", "detail": "php://filter, php://input, data://, expect://"},
            {"phase": "recon", "action": "test_session", "detail": "Check session.upload_progress for temp file inclusion"},
            {"phase": "recon", "action": "test_log_injection", "detail": "Inject PHP to Apache/Nginx error/access logs"},
            {"phase": "exploit", "action": "read_flag", "detail": "Read /flag or flag.php via include"},
        ],
        waf_bypass={
            "blocked_chars": [":", "?", " ", "+", "-", "%", "*", "`"],
            "bypass": "session.upload_progress temp file",
        },
        solved_examples=["EasyCleanup"],
        confidence_base=0.85,
    ),

    VulnerabilityPattern(
        id="lfi_php_wrapper",
        category="Web",
        subcategory="文件包含",
        technique="php://filter 伪协议",
        tags=["文件包含", "Web", "PHP"],
        keywords=["include", "file", "php", "filter", "wrapper", "伪协议"],
        indicators={
            "url_params": ["file", "page", "include", "path"],
            "response": {"php_execution": True},
        },
        prerequisites={"language": ["php"], "allow_url_include": True},
        attack_chain=[
            {"phase": "recon", "action": "test_filter", "detail": "php://filter/convert.base64-encode/resource=flag.php"},
            {"phase": "exploit", "action": "decode_base64", "detail": "Decode base64 response to get source/flag"},
        ],
        solved_examples=[],
        confidence_base=0.7,
    ),

    # ── SSRF ──
    VulnerabilityPattern(
        id="ssrf_curl_file",
        category="Web",
        subcategory="SSRF",
        technique="curl file:// 本地文件读取",
        tags=["SSRF", "Web"],
        keywords=["ssrf", "curl", "fetch", "url", "proxy", "website", "alive",
                   "网站", "检测", "代理", "fetch_url", "test_url", "webcheck"],
        indicators={
            "url_params": ["host", "url", "target", "site", "website", "fetch", "check", "proxy"],
            "form_fields": ["host", "url", "target", "website", "site"],
            "response": {"curl_output": True, "var_dump": True, "json_encoded": True},
        },
        prerequisites={"backend": ["curl", "wget", "file_get_contents"]},
        attack_chain=[
            {"phase": "recon", "action": "identify_fetcher", "detail": "Find URL/submit form that fetches external URLs"},
            {"phase": "recon", "action": "test_http", "detail": "Submit http://127.0.0.1/ to confirm SSRF"},
            {"phase": "recon", "action": "test_file_protocol", "detail": "Submit file:///etc/passwd to check local read"},
            {"phase": "exploit", "action": "read_flag", "detail": "Submit file:///flag or file:///flag.txt"},
            {"phase": "alt", "action": "test_other_protocols", "detail": "Try gopher://, dict://, ftp:// for expanded SSRF"},
            {"phase": "alt", "action": "port_scan", "detail": "Use SSRF to scan internal ports (127.0.0.1:3306, 6379, etc.)"},
        ],
        solved_examples=["WebsiteManger"],
        confidence_base=0.9,
    ),

    VulnerabilityPattern(
        id="ssrf_internal_api",
        category="Web",
        subcategory="SSRF",
        technique="内网API探测",
        tags=["SSRF", "Web"],
        keywords=["ssrf", "internal", "内网", "api", "metadata", "169.254"],
        indicators={
            "url_params": ["url", "target", "host", "proxy", "fetch", "redirect"],
            "response": {"internal_services": True},
        },
        prerequisites={},
        attack_chain=[
            {"phase": "recon", "action": "scan_internal", "detail": "Scan common internal IPs and ports"},
            {"phase": "recon", "action": "check_cloud_metadata", "detail": "169.254.169.254 for cloud creds"},
            {"phase": "exploit", "action": "access_internal", "detail": "Access internal services via SSRF"},
        ],
        solved_examples=[],
        confidence_base=0.65,
    ),

    # ── PHP Deserialization ──
    VulnerabilityPattern(
        id="php_unserialize_pop",
        category="Web",
        subcategory="反序列化",
        technique="PHP POP链",
        tags=["反序列化(Unserialize)", "Web", "PHP"],
        keywords=["unserialize", "serialize", "反序列化", "__wakeup", "__destruct",
                   "__toString", "__call", "__get", "__set", "pop", "gadget"],
        indicators={
            "url_params": ["data", "param", "input", "pks", "serialized", "obj"],
            "response": {"class_definition": True, "magic_methods": True},
        },
        prerequisites={"language": ["php"], "unserialize": True},
        attack_chain=[
            {"phase": "recon", "action": "audit_source", "detail": "Find all classes with magic methods"},
            {"phase": "recon", "action": "build_pop_chain", "detail": "Construct gadget chain from source to sink"},
            {"phase": "recon", "action": "bypass_filters", "detail": "Handle null byte encoding, property visibility"},
            {"phase": "exploit", "action": "trigger_chain", "detail": "Send serialized payload to unserialize endpoint"},
        ],
        solved_examples=["pklovecloud"],
        confidence_base=0.8,
    ),

    # ── Backup File Leak ──
    VulnerabilityPattern(
        id="backup_file_leak",
        category="Web",
        subcategory="备份文件泄露",
        technique="编辑器备份文件 + 源码审计",
        tags=["备份文件泄露", "Web"],
        keywords=["backup", "备份", "swp", "swo", "bak", "old", "temp",
                   "vim", "emacs", "nano", ".git", ".svn", ".DS_Store"],
        indicators={
            "url_patterns": [r"\.swp$", r"\.bak$", r"\.old$", r"\.git/", r"\.svn/"],
            "response": {"source_code": True, "hidden_files": True},
        },
        prerequisites={},
        attack_chain=[
            {"phase": "recon", "action": "scan_backup_files", "detail": "Check .swp, .bak, .old, .git, .svn, .DS_Store"},
            {"phase": "recon", "action": "audit_source", "detail": "Read leaked source code for vulnerabilities"},
            {"phase": "recon", "action": "find_sink", "detail": "Identify write/exe c/eval/file read sinks"},
            {"phase": "exploit", "action": "bypass_filter", "detail": "Craft payload bypassing keyword/char filters"},
            {"phase": "exploit", "action": "write_webshell", "detail": "Write PHP webshell via discovered sink"},
        ],
        solved_examples=["find_it"],
        confidence_base=0.85,
    ),

    # ── Command Injection / RCE ──
    VulnerabilityPattern(
        id="rce_command_injection",
        category="Web",
        subcategory="RCE",
        technique="命令注入",
        tags=["RCE", "Web"],
        keywords=["rce", "exec", "system", "eval", "passthru", "shell_exec",
                   "popen", "cmd", "command", "命令执行", "代码执行", "命令注入"],
        indicators={
            "url_params": ["cmd", "command", "exec", "shell", "ping", "run", "action", "do"],
            "form_fields": ["cmd", "command", "ip", "host"],
            "response": {"command_output": True, "ping_output": True},
        },
        prerequisites={"language": ["php", "python", "ruby", "java", "node"]},
        attack_chain=[
            {"phase": "recon", "action": "test_pipe", "detail": "Test |, ||, &&, ;, \n, \r\n command separators"},
            {"phase": "recon", "action": "test_backtick", "detail": "Test backtick and $() subshell"},
            {"phase": "recon", "action": "test_encoding", "detail": "Try URL/hex/base64 encoding bypass"},
            {"phase": "exploit", "action": "read_flag", "detail": "cat /flag*, type C:\\flag*"},
        ],
        solved_examples=[],
        confidence_base=0.75,
    ),

    # ── SSTI ──
    VulnerabilityPattern(
        id="ssti_template_injection",
        category="Web",
        subcategory="SSTI",
        technique="服务端模板注入",
        tags=["SSTI", "Web"],
        keywords=["ssti", "template", "模板", "jinja", "twig", "freemarker",
                   "velocity", "thymeleaf", "{{", "{%"],
        indicators={
            "url_params": ["name", "user", "input", "search", "q", "msg", "template"],
            "response": {"reflected_input": True, "template_engine": True},
        },
        prerequisites={"language": ["python", "ruby", "java", "php"]},
        attack_chain=[
            {"phase": "recon", "action": "detect_engine", "detail": "Test {{7*7}}, ${7*7}, <%=7*7%> to identify engine"},
            {"phase": "exploit", "action": "rce_via_ssti", "detail": "Use engine-specific RCE payloads"},
        ],
        solved_examples=[],
        confidence_base=0.7,
    ),

    # ── Type Juggling ──
    VulnerabilityPattern(
        id="php_type_juggling",
        category="Web",
        subcategory="弱类型",
        technique="PHP弱类型比较绕过",
        tags=["弱类型", "Web", "PHP"],
        keywords=["弱类型", "type", "juggling", "loose", "comparison", "=="],
        indicators={
            "url_params": ["password", "token", "hash", "auth", "key"],
            "response": {"authentication_bypass": True},
        },
        prerequisites={"language": ["php"]},
        attack_chain=[
            {"phase": "recon", "action": "audit_source", "detail": "Find loose comparison (==) with user input"},
            {"phase": "exploit", "action": "type_juggle", "detail": "Use 0, true, null, [], or hash collision"},
        ],
        solved_examples=[],
        confidence_base=0.65,
    ),

    # ── XSS ──
    VulnerabilityPattern(
        id="xss_reflected",
        category="Web",
        subcategory="XSS",
        technique="反射型XSS",
        tags=["XSS", "Web"],
        keywords=["xss", "cross", "script", "alert", "html", "javascript"],
        indicators={
            "url_params": ["q", "search", "keyword", "msg", "name", "comment", "feedback"],
            "response": {"reflected_input": True, "no_escaping": True},
        },
        prerequisites={},
        attack_chain=[
            {"phase": "recon", "action": "test_reflection", "detail": "Inject <script>alert(1)</script> to check for reflection"},
            {"phase": "exploit", "action": "cookie_theft", "detail": "Craft XSS payload to steal cookies or token"},
        ],
        solved_examples=[],
        confidence_base=0.65,
    ),

    # ── File Upload ──
    VulnerabilityPattern(
        id="file_upload_webshell",
        category="Web",
        subcategory="文件上传",
        technique="文件上传Webshell",
        tags=["文件上传", "Web", "PHP"],
        keywords=["upload", "上传", "file", "image", "avatar", "webshell"],
        indicators={
            "url_params": ["upload", "file", "image", "avatar"],
            "form_fields": ["file", "upload", "image", "avatar"],
            "response": {"file_path": True, "upload_success": True},
        },
        prerequisites={"language": ["php", "python", "java"]},
        attack_chain=[
            {"phase": "recon", "action": "test_upload", "detail": "Upload legitimate file, observe response"},
            {"phase": "recon", "action": "bypass_extension", "detail": "Try .php5, .phtml, .pHp, .php., .php%00, double extension"},
            {"phase": "recon", "action": "bypass_content_type", "detail": "Change Content-Type: image/jpeg, add GIF89a header"},
            {"phase": "exploit", "action": "execute_webshell", "detail": "Access uploaded file, execute commands"},
        ],
        solved_examples=[],
        confidence_base=0.7,
    ),

    # ── XXE ──
    VulnerabilityPattern(
        id="xxe_injection",
        category="Web",
        subcategory="XXE",
        technique="XML外部实体注入",
        tags=["XXE", "Web"],
        keywords=["xxe", "xml", "dtd", "entity", "doctype", "external"],
        indicators={
            "content_type": ["xml", "application/xml", "text/xml"],
            "url_params": ["xml", "data", "input"],
            "response": {"xml_parsing": True},
        },
        prerequisites={},
        attack_chain=[
            {"phase": "recon", "action": "test_entity", "detail": "Inject DOCTYPE with internal entity"},
            {"phase": "recon", "action": "test_external", "detail": "Test external entity with your server"},
            {"phase": "exploit", "action": "read_file", "detail": "Use file:// entity to read /flag"},
        ],
        solved_examples=[],
        confidence_base=0.6,
    ),

    # ── Misc / Recon ──
    VulnerabilityPattern(
        id="recon_endpoint_discovery",
        category="Web",
        subcategory="信息收集",
        technique="端点扫描",
        tags=["Web", "Misc"],
        keywords=["hidden", "admin", "panel", "manage", "test", "backup"],
        indicators={
            "response": {"login_forms": True, "directory_listing": True},
        },
        prerequisites={},
        attack_chain=[
            {"phase": "recon", "action": "scan_endpoints", "detail": "Try common paths: admin, backup, test, api, config"},
            {"phase": "recon", "action": "check_source", "detail": "View page source, check JS files for hidden endpoints"},
            {"phase": "recon", "action": "check_robots", "detail": "Check robots.txt, sitemap.xml"},
        ],
        solved_examples=[],
        confidence_base=0.4,
    ),
]


class PatternDB:
    """Queryable vulnerability pattern database."""

    def __init__(self, patterns: List[VulnerabilityPattern] = None):
        self.patterns = patterns or PATTERNS
        self._build_index()

    def _build_index(self):
        """Build tag → patterns and keyword → patterns indices."""
        self.tag_index: Dict[str, List[VulnerabilityPattern]] = {}
        self.keyword_index: Dict[str, List[VulnerabilityPattern]] = {}
        self.id_index: Dict[str, VulnerabilityPattern] = {}

        for p in self.patterns:
            self.id_index[p.id] = p
            for tag in p.tags:
                self.tag_index.setdefault(tag.lower(), []).append(p)
            for kw in p.keywords:
                self.keyword_index.setdefault(kw.lower(), []).append(p)

    def search(self, tags: Set[str] = None, description: str = "",
               min_score: float = 0.0) -> List[Tuple[VulnerabilityPattern, float]]:
        """Search for matching patterns, ranked by score."""
        results = []
        for p in self.patterns:
            score = p.match_score(tags or set(), description)
            if score >= min_score:
                results.append((p, score))
        results.sort(key=lambda x: x[1], reverse=True)
        return results

    def get_top_match(self, tags: Set[str] = None, description: str = ""
                      ) -> Optional[Tuple[VulnerabilityPattern, float]]:
        """Get the single best matching pattern."""
        results = self.search(tags, description, min_score=0.1)
        return results[0] if results else None

    def get_by_id(self, pattern_id: str) -> Optional[VulnerabilityPattern]:
        """Get a pattern by its ID."""
        return self.id_index.get(pattern_id)

    def get_by_tag(self, tag: str) -> List[VulnerabilityPattern]:
        """Get all patterns matching a tag (case-insensitive)."""
        return self.tag_index.get(tag.lower(), [])

    def get_categories(self) -> List[str]:
        """List all unique subcategories."""
        return sorted(set(p.subcategory for p in self.patterns))

    def get_techniques_for_category(self, subcategory: str) -> List[str]:
        """List techniques for a subcategory."""
        return [p.technique for p in self.patterns if p.subcategory == subcategory]

    def get_solved_examples(self) -> List[str]:
        """List all challenge names that have solved examples in patterns."""
        examples = set()
        for p in self.patterns:
            examples.update(p.solved_examples)
        return sorted(examples)

    def find_isomorphic(self, pattern: VulnerabilityPattern
                        ) -> List[Tuple[VulnerabilityPattern, float]]:
        """Find patterns structurally similar (same category, different technique)."""
        results = []
        for p in self.patterns:
            if p.id == pattern.id:
                continue
            score = 0.0
            # Same subcategory = strong signal
            if p.subcategory == pattern.subcategory:
                score += 0.5
            # Same category
            if p.category == pattern.category:
                score += 0.2
            # Shared tags
            shared = set(p.tags) & set(pattern.tags)
            score += 0.15 * len(shared)
            # Shared keywords
            shared_kw = set(p.keywords) & set(pattern.keywords)
            score += 0.15 * len(shared_kw)
            if score > 0:
                results.append((p, score))
        results.sort(key=lambda x: x[1], reverse=True)
        return results

    def to_transactions(self) -> List[Set[str]]:
        """Export patterns as Apriori transactions (tag sets)."""
        return [set(p.tags) for p in self.patterns]

    def summary(self) -> str:
        """Human-readable summary of the pattern database."""
        cats = {}
        for p in self.patterns:
            cats.setdefault(p.subcategory, []).append(p.technique)

        lines = ["Pattern Database: %d patterns across %d categories" %
                 (len(self.patterns), len(cats))]
        for cat, techniques in cats.items():
            has_solved = any(p.solved_examples for p in self.patterns if p.subcategory == cat)
            marker = " [SOLVED]" if has_solved else ""
            lines.append("  %s%s: %s" % (cat, marker, ", ".join(techniques)))
        return "\n".join(lines)


# ── Tag → Category Mapping ──────────────────────────────────────────────────

TAG_TO_CATEGORY = {
    "sql注入": "SQL注入", "xss": "XSS", "csrf": "CSRF", "ssrf": "SSRF",
    "rce": "RCE", "文件包含": "文件包含", "反序列化(unserialize)": "反序列化",
    "反序列化": "反序列化", "unserialize": "反序列化",
    "备份文件泄露": "备份文件泄露", "弱类型": "弱类型", "ssti": "SSTI",
    "文件上传": "文件上传", "xxe": "XXE", "命令注入": "RCE",
    "php": "PHP", "ruby": "Ruby", "yii2": "SSTI", "流量分析": "流量分析",
}

CATEGORY_DIFFICULTY = {
    "SQL注入": "medium", "文件包含": "hard", "SSRF": "easy",
    "反序列化": "hard", "备份文件泄露": "easy", "RCE": "medium",
    "SSTI": "medium", "弱类型": "medium", "文件上传": "easy",
    "XSS": "easy", "XXE": "medium", "信息收集": "easy", "流量分析": "medium",
}


# ── Convenience ──

_default_db = None

def get_pattern_db() -> PatternDB:
    """Get or create the default pattern database singleton."""
    global _default_db
    if _default_db is None:
        _default_db = PatternDB()
    return _default_db


if __name__ == "__main__":
    db = PatternDB()
    print(db.summary())
    print()
    print("Solved examples:", db.get_solved_examples())

    # Test: search for SQL注入
    print("\n--- Search: tags={Web, SQL注入} ---")
    for p, score in db.search(tags={"Web", "SQL注入"}):
        print("  %.2f %s (%s)" % (score, p.id, p.technique))
