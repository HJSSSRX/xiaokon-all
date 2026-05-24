"""Role assignment with workload-aware balancing.

Maps sub-goals to analyst roles using the existing ROLE_CAPABILITIES
mapping from smart_scheduler, with workload-based assignment to
minimize the makespan.
"""

from typing import Dict, List

from tools.decomposer.models import SubGoal

# Mirrored from smart_scheduler.py for zero-dependency operation
# Aligned with config/roles.yaml (8 roles: 5 forensic + 3 attack-specialized)
ROLE_CAPABILITIES: Dict[str, List[str]] = {
    "computer_analyst": [
        "memory_analysis", "disk_analysis", "log_analysis", "data_recovery",
        "stego_analysis", "crypto_analysis", "registry_analysis",
    ],
    "mobile_analyst": [
        "mobile_analysis", "app_analysis", "chat_forensics",
    ],
    "server_analyst": [
        "disk_analysis", "network_analysis", "log_analysis",
        "data_recovery", "database_forensics", "container_forensics",
    ],
    "network_analyst": [
        "network_analysis", "log_analysis", "traffic_analysis",
        "protocol_analysis", "pcap_analysis",
    ],
    "binary_analyst": [
        "binary_analysis", "crypto_analysis", "memory_analysis",
        "malware_analysis", "reverse_engineering",
    ],
    "web_pentester": [
        "web_pentest", "web_attack", "sql_injection", "xss", "ssrf",
        "file_upload", "command_injection", "auth_bypass",
    ],
    "stego_crypto_analyst": [
        "stego_analysis", "crypto_analysis", "encoding_analysis",
        "hash_cracking", "file_carving",
    ],
    "misc_analyst": [
        "file_carving", "unknown_analysis", "protocol_reverse",
        "multi_layer_decode", "forensic_triage",
    ],
}

# Fixed assignments for certain sub-goal levels
FIXED_ASSIGNMENTS = {
    0: "main_designer",  # Level 0 (shared context) always goes to main designer
}


def assign_roles(sub_goals: Dict[str, SubGoal]) -> Dict[str, List[str]]:
    """Assign roles to sub-goals with workload balancing.

    Level 0 sub-goals go to main_designer.
    Levels 1-3 are assigned to the most capable role with the lowest current load.

    Args:
        sub_goals: All sub-goals keyed by ID.

    Returns:
        {role_name: [sub_goal_ids]} mapping.
    """
    # Workload tracker: total estimated minutes per role
    workloads: Dict[str, int] = {}
    assignments: Dict[str, List[str]] = {}

    def _add_assignment(role: str, sg_id: str, minutes: int):
        if role not in assignments:
            assignments[role] = []
        assignments[role].append(sg_id)
        workloads[role] = workloads.get(role, 0) + minutes

    # Sort sub-goals by level then by priority (lower priority = more urgent)
    ordered = sorted(
        sub_goals.items(),
        key=lambda item: (item[1].level, item[1].priority, item[0])
    )

    for sg_id, sg in ordered:
        # Fixed assignment for certain levels
        if sg.level in FIXED_ASSIGNMENTS:
            _add_assignment(FIXED_ASSIGNMENTS[sg.level], sg_id, sg.estimated_minutes)
            sg.assigned_role = FIXED_ASSIGNMENTS[sg.level]
            continue

        # Already assigned?
        if sg.assigned_role and sg.assigned_role != "main_designer":
            _add_assignment(sg.assigned_role, sg_id, sg.estimated_minutes)
            continue

        # Find candidate roles
        candidates = _find_candidates(sg.task_type)
        if not candidates:
            # Any role can handle untyped sub-goals
            candidates = list(ROLE_CAPABILITIES.keys())

        # Pick candidate with lowest current workload
        best_role = min(candidates, key=lambda r: workloads.get(r, 0))
        _add_assignment(best_role, sg_id, sg.estimated_minutes)
        sg.assigned_role = best_role

    return assignments


def _find_candidates(task_type: str) -> List[str]:
    """Find all roles capable of handling a given task type."""
    candidates = []
    for role, capabilities in ROLE_CAPABILITIES.items():
        if task_type in capabilities:
            candidates.append(role)
    if not candidates:
        candidates = list(ROLE_CAPABILITIES.keys())
    return candidates


def get_role_for_domain(domain: str) -> str:
    """Map a forensic domain to its default analyst role."""
    domain_role_map = {
        "memory": "computer_analyst",
        "disk": "computer_analyst",
        "registry": "computer_analyst",
        "network": "network_analyst",
        "pcap": "network_analyst",
        "traffic": "network_analyst",
        "mobile": "mobile_analyst",
        "android": "mobile_analyst",
        "ios": "mobile_analyst",
        "binary": "binary_analyst",
        "malware": "binary_analyst",
        "reverse": "binary_analyst",
        "stego": "stego_crypto_analyst",
        "crypto": "stego_crypto_analyst",
        "hash": "stego_crypto_analyst",
        "encoding": "stego_crypto_analyst",
        "log": "server_analyst",
        "database": "server_analyst",
        "container": "server_analyst",
        "web": "web_pentester",
        "sqli": "web_pentester",
        "xss": "web_pentester",
        "ssrf": "web_pentester",
        "misc": "misc_analyst",
        "unknown": "misc_analyst",
    }
    return domain_role_map.get(domain, "computer_analyst")
