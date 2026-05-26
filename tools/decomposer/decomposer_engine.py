"""Core decomposition engine.

Takes classified evidence + parsed challenge description and produces a
complete DecompositionPlan with 4-level sub-goal hierarchy, dependency DAG,
topological sort, and critical path analysis.
"""

from collections import deque
from datetime import datetime
from typing import Dict, List, Optional, Set, Tuple

from tools.decomposer.models import (
    DecompositionPlan, EvidenceInfo, SubGoal, SubGoalLevel,
)
from tools.decomposer.shared_input_detector import detect_shared_inputs

# Domain → task type mapping (consistent with smart_scheduler.TaskType)
DOMAIN_TASK_MAP = {
    "memory": "memory_analysis",
    "disk": "disk_analysis",
    "network": "network_analysis",
    "mobile": "mobile_analysis",
    "binary": "binary_analysis",
    "stego": "stego_analysis",
    "crypto": "crypto_analysis",
    "log": "log_analysis",
    "web": "web_pentest",
}

TASK_TYPE_DESCRIPTIONS = {
    "memory_analysis": "内存取证分析",
    "disk_analysis": "磁盘/文件系统分析",
    "network_analysis": "网络流量分析",
    "mobile_analysis": "移动端分析",
    "binary_analysis": "逆向工程分析",
    "stego_analysis": "隐写分析",
    "crypto_analysis": "密码学分析",
    "log_analysis": "日志分析",
    "web_pentest": "Web渗透测试",
    "data_recovery": "数据恢复/预处理",
}

_DEFAULT_TOOLS: Dict[str, List[str]] = {
    "memory_analysis": ["volatility3", "strings", "grep"],
    "disk_analysis": ["fls", "fsstat", "strings", "grep", "sqlite3"],
    "network_analysis": ["tshark", "wireshark", "strings", "ngrep"],
    "mobile_analysis": ["adb", "sqlite3", "apktool", "strings"],
    "binary_analysis": ["file", "strings", "objdump", "readelf"],
    "stego_analysis": ["binwalk", "strings", "exiftool", "steghide"],
    "crypto_analysis": ["openssl", "strings", "hashcat"],
    "log_analysis": ["strings", "grep", "jq"],
    "data_recovery": ["file", "strings", "binwalk"],
}


def decompose(
    evidence_files: List[EvidenceInfo],
    challenge_name: str = "Unnamed Challenge",
    challenge_description: str = "",
    questions: Optional[List[dict]] = None,
    kb_root: Optional[str] = None,
    recommend_tools: bool = True,
) -> DecompositionPlan:
    """Decompose a challenge into structured sub-goals.

    Args:
        evidence_files: Classified evidence files from evidence_classifier.
        challenge_name: Human-readable challenge name.
        challenge_description: Natural language description of the challenge.
        questions: Parsed question list (qid, question, answer_format, domain, category).
        kb_root: Knowledge base root for tool recommendations.
        recommend_tools: Whether to use the KB recommendation engine.

    Returns:
        Complete DecompositionPlan ready for output.
    """
    if questions is None:
        questions = []

    plan = DecompositionPlan(
        challenge_name=challenge_name,
        challenge_description=challenge_description[:5000],
        created_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        evidence_files=evidence_files,
    )

    sub_goals: Dict[str, SubGoal] = {}
    sg_counter = 0

    # ── Level 0: Shared Context ──────────────────────────────────────
    sg_counter += 1
    sg_shared = SubGoal(
        id=f"SG-{sg_counter:03d}",
        level=SubGoalLevel.SHARED,
        description="检材索引与分类 — 对所有检材文件进行类型检测、哈希计算、元数据提取",
        domain="",
        task_type="data_recovery",
        inputs=[e.path for e in evidence_files],
        outputs=["evidence_index.yaml", "all_hashes", "all_types"],
        dependencies=[],
        tools=["file", "sha256sum", "stat"],
        assigned_role="main_designer",
        estimated_minutes=_estimate_shared_time(evidence_files),
        priority=1,
    )
    sub_goals[sg_shared.id] = sg_shared

    # ── Level 1: Evidence Preparation ────────────────────────────────
    prep_goals: Dict[str, SubGoal] = {}
    for ev in evidence_files:
        if not (ev.is_archive or ev.is_encrypted or ev.mount_required):
            continue
        sg_counter += 1
        prep_id = f"SG-{sg_counter:03d}"

        if ev.mount_required:
            desc = f"挂载镜像: {ev.path}"
            task_type = "disk_analysis"
            tools = ["ewfmount" if ev.extension == ".e01" else "mount", "losetup"]
        elif ev.is_encrypted:
            desc = f"解密文件: {ev.path}"
            task_type = "crypto_analysis"
            tools = ["gpg", "openssl"]
        else:
            desc = f"解压归档: {ev.path}"
            task_type = "data_recovery"
            tools = ["7z", "unzip"]

        prep = SubGoal(
            id=prep_id,
            level=SubGoalLevel.PREP,
            description=desc,
            domain=ev.detected_type if ev.detected_type != "unknown" else "",
            task_type=task_type,
            inputs=[ev.path],
            outputs=[f"{ev.path}_prepared"],
            dependencies=[sg_shared.id],
            tools=tools,
            assigned_role="",
            estimated_minutes=_estimate_prep_time(ev),
            priority=2,
        )
        prep_goals[prep.id] = prep
        sub_goals[prep_id] = prep

    # ── Level 2: Domain Analysis ─────────────────────────────────────
    domains_detected = _detect_domains(evidence_files, questions, challenge_description)

    analysis_goals: Dict[str, SubGoal] = {}
    for domain in domains_detected:
        task_type = DOMAIN_TASK_MAP.get(domain, "data_recovery")

        # Find evidence for this domain
        domain_evidence = [
            e for e in evidence_files
            if e.detected_type == domain
        ]
        if not domain_evidence:
            domain_evidence = [e for e in evidence_files if e.detected_type != "unknown"]

        # Determine inputs — either raw evidence or prep outputs
        inputs: List[str] = []
        deps: List[str] = [sg_shared.id]
        for ev in domain_evidence:
            prep_id = _find_prep_for_evidence(ev.path, prep_goals)
            if prep_id:
                inputs.append(f"{ev.path}_prepared")
                if prep_id not in deps:
                    deps.append(prep_id)
            else:
                inputs.append(ev.path)

        sg_counter += 1
        task_desc = TASK_TYPE_DESCRIPTIONS.get(task_type, f"{domain}分析")

        analysis = SubGoal(
            id=f"SG-{sg_counter:03d}",
            level=SubGoalLevel.ANALYSIS,
            description=f"{task_desc} — 检材中的{domain}相关证据分析",
            domain=domain,
            task_type=task_type,
            inputs=inputs,
            outputs=[f"{domain}_findings", f"{domain}_report"],
            dependencies=deps,
            tools=list(_DEFAULT_TOOLS.get(task_type, [])),
            assigned_role="",
            estimated_minutes=_estimate_analysis_time(domain, domain_evidence),
            priority=3,
        )
        analysis_goals[analysis.id] = analysis
        sub_goals[analysis.id] = analysis

    # Apply shared input optimization
    if len(analysis_goals) > 1:
        shared_preps = detect_shared_inputs(evidence_files, analysis_goals)
        for sp in shared_preps:
            sub_goals[sp.id] = sp
            # Shared preps depend on shared context too
            if sg_shared.id not in sp.dependencies:
                sp.dependencies.append(sg_shared.id)

    # ── Level 3: Question Sub-Goals ──────────────────────────────────
    for q in questions:
        sg_counter += 1
        qid = q.get("qid", f"Q{sg_counter}")
        q_domain = q.get("domain", "")
        if not q_domain:
            q_domain = _infer_question_domain(q.get("question", ""), domains_detected)

        # Find which analysis sub-goal this question depends on
        q_deps = [sg_shared.id]
        if q_domain and q_domain in domains_detected:
            domain_analysis = [
                a for a in analysis_goals.values()
                if a.domain == q_domain
            ]
            for da in domain_analysis:
                q_deps.append(da.id)
        elif analysis_goals:
            # If domain unknown, depend on all analysis
            q_deps.extend(analysis_goals.keys())

        # Also depend on prep goals if applicable
        for prep_id, prep in prep_goals.items():
            if prep_id not in q_deps:
                q_deps.append(prep_id)

        question = SubGoal(
            id=f"SG-{sg_counter:03d}",
            level=SubGoalLevel.QUESTION,
            description=f"{qid}: {q.get('question', '')[:120]}",
            domain=q_domain,
            task_type=DOMAIN_TASK_MAP.get(q_domain, "data_recovery"),
            inputs=[],
            outputs=[f"answer_{qid}"],
            dependencies=list(set(q_deps)),
            tools=[],
            assigned_role="",
            estimated_minutes=_estimate_question_time(q),
            priority=4,
            answer_format=q.get("answer_format", ""),
            question_text=q.get("question", ""),
        )
        sub_goals[question.id] = question

    # ── Build Dependency Graph ───────────────────────────────────────
    plan.sub_goals = sub_goals

    # ── Topological Sort (Kahn's algorithm) with level grouping ──────
    plan.topological_order = _topological_sort(sub_goals)

    # ── Critical Path ────────────────────────────────────────────────
    critical_path, cp_minutes = _critical_path(sub_goals)
    plan.critical_path = critical_path
    plan.critical_path_minutes = cp_minutes

    # ── Tool Recommendations ─────────────────────────────────────────
    if recommend_tools and kb_root:
        try:
            from tools.decomposer.tool_recommender import recommend_tools_for_sub_goals
            plan.tool_recommendations = recommend_tools_for_sub_goals(sub_goals, kb_root)
            for sg_id, tools in plan.tool_recommendations.items():
                if sg_id in sub_goals and tools:
                    sub_goals[sg_id].tools = tools
        except Exception:
            pass

    # ── Role Assignments ─────────────────────────────────────────────
    try:
        from tools.decomposer.role_assigner import assign_roles
        plan.role_assignments = assign_roles(sub_goals)
        for role, sg_ids in plan.role_assignments.items():
            for sg_id in sg_ids:
                if sg_id in sub_goals:
                    sub_goals[sg_id].assigned_role = role
    except Exception:
        pass

    return plan


def _detect_domains(
    evidence: List[EvidenceInfo],
    questions: List[dict],
    description: str,
) -> List[str]:
    """Detect which forensic domains are needed for this challenge."""
    domains: Set[str] = set()

    # From evidence files
    for ev in evidence:
        if ev.detected_type not in ("unknown", "archive"):
            domains.add(ev.detected_type)

    # From questions
    for q in questions:
        q_domain = q.get("domain", "")
        if q_domain:
            domains.add(q_domain)
        else:
            text = q.get("question", "").lower()
            for domain, keywords in _DOMAIN_KEYWORDS.items():
                if any(kw in text for kw in keywords):
                    domains.add(domain)

    # From description
    for domain, keywords in _DOMAIN_KEYWORDS.items():
        if any(kw in description.lower() for kw in keywords):
            domains.add(domain)

    # Priority order: forensic domains first, then attack-specialized, then misc
    priority = ["memory", "disk", "network", "mobile", "binary", "log",
                "web", "stego", "crypto", "database", "container", "registry",
                "pcap", "traffic", "malware", "encoding", "misc"]
    ordered = [d for d in priority if d in domains]
    for d in domains:
        if d not in ordered:
            ordered.append(d)

    return ordered if ordered else ["disk"]


_DOMAIN_KEYWORDS = {
    "memory": ["memory", "内存", "进程", "volatility", "vol3", "malfind", "pslist"],
    "disk": ["disk", "磁盘", "硬盘", "e01", "vmdk", "vhd", "filesystem", "文件系统", "ntfs", "fat", "ext4", "apfs"],
    "network": ["pcap", "网络", "流量", "wireshark", "tshark", "http", "dns", "tcp", "udp", "tls", "ssl"],
    "mobile": ["mobile", "手机", "apk", "ipa", "android", "ios", "备份", "adb", "sqlcipher", "jadx"],
    "binary": ["binary", "逆向", "reverse", "二进制", "elf", "pe", "ida", "ghidra", "malware", "radare2", "objdump"],
    "stego": ["stego", "隐写", "lsb", "binwalk", "水印", "watermark", "steghide", "zsteg", "stegsolve"],
    "crypto": ["crypto", "密码", "加密", "解密", "rsa", "aes", "哈希", "hash", "md5", "sha256", "openssl", "hashcat"],
    "log": ["log", "日志", "event", "evtx", "syslog", "audit", "登录"],
    "web": ["web", "sqli", "xss", "ssrf", "csrf", "注入", "webshell", "文件上传", "命令注入", "反序列化", "文件包含", "sqlmap", "nuclei", "burp"],
    "database": ["database", "数据库", "mysql", "sqlite", "postgres", "mongodb", ".db", "sqlcipher"],
    "registry": ["registry", "注册表", "ntuser", "sam", "system hive"],
    "pcap": ["pcap", "pcapng", "cap", "抓包", "数据包", "ngrep"],
    "traffic": ["traffic", "c2", "beacon", "dns tunnel", "socks", "proxy", "代理", "反弹shell"],
    "malware": ["malware", "木马", "病毒", "ransomware", "勒索", "rootkit", "后门", "trojan"],
    "container": ["container", "docker", "lxc", "k8s", "kubernetes", "容器", "逃逸"],
    "encoding": ["encoding", "编码", "base64", "rot13", "hex", "urlencode", "xor", "解码"],
    "misc": ["misc", "杂项", "未知", "unknown", "forensic", "triage", "carving", "file_carve",
              "qr", "qrcode", "barcode", "条形码", "二维码", "qr_code",
              "hex", "hexdump", "raw_bytes", "十六进制", "binwalk",
              "magic_bytes", "file_signature", "magic", "文件头",
              "methodology", "workflow", "方法论", "工作流",
              "chainsaw", "evtx_dump", "hayabusa", "chainsaw", "json", "csv",
              "strings", "字符串", "bulk_extractor", "scalpel",
              "foremost", "photorec", "数据恢复", "data_recovery",
              "log_triage", "triage", "日志", "log_analysis",
              "email", "eml", "mbox", "邮件", "pst", "ost",
    ],
}


def detect_vulnerability_types(description: str = "", tags: List[str] = None,
                               evidence_files: List = None) -> Dict:
    """Detect CTF vulnerability types using the CTF pattern database.

    Complements the existing _DOMAIN_KEYWORDS (forensic domains) with
    web/CTF-specific vulnerability pattern recognition.

    Returns:
        {
            "vuln_types": [{"name": "SQL注入", "technique": "Boolean盲注", "confidence": 0.8}],
            "top_match": "Boolean盲注",
            "suggested_tools": ["blind_sqli_extractor", "sqlmap"],
            "attack_plan": [...],
        }
    """
    try:
        from tools.feeder.ctf_patterns import get_pattern_db
        from tools.feeder.ctf_recognizer import CTFRecognizer, CTFChallenge, get_recognizer
    except ImportError:
        return {"vuln_types": [], "top_match": None, "suggested_tools": [], "attack_plan": []}

    recognizer = get_recognizer()
    challenge = CTFChallenge(
        challenge_id=0,
        title="",
        description=description,
        tags=tags or [],
        level=0.0,
    )
    result = recognizer.recognize(challenge)

    vuln_types = []
    for p, score in (result.patterns or [])[:5]:
        if score > 0.15:
            vuln_types.append({
                "name": p.subcategory,
                "technique": p.technique,
                "confidence": round(score, 3),
                "category": p.category,
            })

    suggested_tools = []
    if result.top_match:
        for step in result.top_match.attack_chain:
            tool = step.get("tool", "")
            if tool and tool != "manual":
                suggested_tools.append(tool)
        # Add default tools based on category
        if result.top_match.subcategory == "SQL注入":
            suggested_tools.extend(["blind_sqli_extractor", "sqlmap"])
        elif result.top_match.subcategory == "SSRF":
            suggested_tools.append("curl")
        elif result.top_match.subcategory == "文件包含":
            suggested_tools.append("session_upload_exploit")

    return {
        "vuln_types": vuln_types,
        "top_match": result.top_match.technique if result.top_match else None,
        "top_match_score": result.top_match_score if result.top_match else 0.0,
        "suggested_tools": list(set(suggested_tools)),
        "attack_plan": result.attack_plan,
        "estimated_difficulty": result.estimated_difficulty,
        "estimated_time": result.estimated_time,
    }


def _topological_sort(sub_goals: Dict[str, SubGoal]) -> List[List[str]]:
    """Kahn's algorithm with level grouping.

    Returns groups of sub-goal IDs that can execute in parallel.
    Each group depends only on IDs from earlier groups.
    """
    adj: Dict[str, List[str]] = {}  # predecessor -> list of successors
    in_degree: Dict[str, int] = {}

    for sg_id in sub_goals:
        if sg_id not in adj:
            adj[sg_id] = []
        if sg_id not in in_degree:
            in_degree[sg_id] = 0

    for sg_id, sg in sub_goals.items():
        for dep_id in sg.dependencies:
            if dep_id not in adj:
                adj[dep_id] = []
            adj[dep_id].append(sg_id)
            in_degree[sg_id] = in_degree.get(sg_id, 0) + 1

    # Start with nodes having 0 in-degree
    queue = deque([sg_id for sg_id, deg in in_degree.items() if deg == 0])
    result: List[List[str]] = []
    processed: Set[str] = set()

    while queue:
        level = sorted(queue)
        result.append(level)
        next_queue = deque()

        for node in level:
            processed.add(node)
            for successor in adj.get(node, []):
                if successor in processed:
                    continue
                in_degree[successor] -= 1
                if in_degree[successor] == 0:
                    next_queue.append(successor)

        queue = next_queue

    # Add any remaining nodes not reached (shouldn't happen in a DAG)
    for sg_id in sub_goals:
        if sg_id not in processed:
            result.append([sg_id])

    return result


def _critical_path(sub_goals: Dict[str, SubGoal]) -> Tuple[List[str], int]:
    """Find the longest path through the DAG (critical path).

    Uses DP on topologically sorted nodes:
      dist[v] = max(dist[v], dist[u] + weight[v]) for each edge u->v

    Returns (path_as_list_of_ids, total_minutes).
    """
    if not sub_goals:
        return [], 0

    # Build reverse adjacency: successor -> list of predecessors
    pred: Dict[str, List[str]] = {sg_id: [] for sg_id in sub_goals}
    for sg_id, sg in sub_goals.items():
        for dep_id in sg.dependencies:
            if dep_id in pred:
                pred[sg_id].append(dep_id)

    # Topological order (flat)
    flat_order: List[str] = []
    in_degree = {sg_id: len(sg.dependencies) for sg_id, sg in sub_goals.items()}
    queue = deque([sg_id for sg_id, deg in in_degree.items() if deg == 0])

    while queue:
        node = queue.popleft()
        flat_order.append(node)
        for other_id, other in sub_goals.items():
            if node in other.dependencies:
                in_degree[other_id] -= 1
                if in_degree[other_id] == 0 and other_id not in flat_order:
                    queue.append(other_id)

    if not flat_order:
        flat_order = list(sub_goals.keys())

    # DP: longest distance to each node
    dist: Dict[str, int] = {}
    prev: Dict[str, Optional[str]] = {}

    for sg_id in flat_order:
        weight = sub_goals[sg_id].estimated_minutes
        best_pred = None
        best_dist = weight  # start from this node's own weight

        for p in pred.get(sg_id, []):
            if p in dist:
                candidate = dist[p] + weight
                if candidate > best_dist:
                    best_dist = candidate
                    best_pred = p

        dist[sg_id] = best_dist
        prev[sg_id] = best_pred

    # Find endpoint with maximum distance
    if not dist:
        return [], 0

    end = max(dist, key=lambda k: dist[k])
    max_minutes = dist[end]

    # Reconstruct path backwards
    path: List[str] = []
    current = end
    while current is not None:
        path.append(current)
        current = prev.get(current)
    path.reverse()

    return path, max_minutes


def _find_prep_for_evidence(ev_path: str, prep_goals: Dict[str, SubGoal]) -> Optional[str]:
    """Find the prep sub-goal that handles a given evidence file."""
    for prep_id, prep in prep_goals.items():
        if ev_path in prep.inputs:
            return prep_id
    return None


def _estimate_shared_time(evidence: List[EvidenceInfo]) -> int:
    """Estimate time for Level 0 shared context creation."""
    n = len(evidence)
    if n <= 3:
        return 3
    elif n <= 10:
        return 5
    return min(10, n // 2)


def _estimate_prep_time(ev: EvidenceInfo) -> int:
    """Estimate prep time based on file size."""
    gb = ev.size_bytes / (1024 ** 3)
    if gb > 10:
        return 30
    elif gb > 2:
        return 15
    elif gb > 0.5:
        return 5
    return 2


def _estimate_analysis_time(domain: str, evidence: List[EvidenceInfo]) -> int:
    """Estimate analysis time for a domain based on evidence size."""
    total_gb = sum(e.size_bytes for e in evidence) / (1024 ** 3)
    base = {"memory": 30, "disk": 45, "network": 25, "mobile": 30,
            "binary": 45, "stego": 20, "crypto": 30, "log": 20}
    est = base.get(domain, 30)
    if total_gb > 5:
        est = int(est * 1.5)
    return est


def _estimate_question_time(q: dict) -> int:
    """Estimate time to answer a single question."""
    text = q.get("question", "").lower()
    # Difficulty indicators
    if any(k in text for k in ("分析", "分析", "explain", "describe", "why", "为什么")):
        return 20
    if any(k in text for k in ("提取", "找出", "寻找", "find", "extract", "recover")):
        return 15
    if any(k in text for k in ("密码", "解密", "crack", "decrypt")):
        return 25
    return 10


def _infer_question_domain(question: str, available_domains: List[str]) -> str:
    """Infer the forensic domain for a question based on keyword matching."""
    ql = question.lower()
    scores: Dict[str, int] = {}
    for domain, keywords in _DOMAIN_KEYWORDS.items():
        score = sum(1 for kw in keywords if kw in ql)
        if score > 0:
            scores[domain] = score

    if not scores:
        return available_domains[0] if available_domains else ""

    # Prefer domains that are actually available
    for domain in sorted(scores, key=lambda d: scores[d], reverse=True):
        if domain in available_domains:
            return domain
    return max(scores, key=lambda d: scores[d])
