"""Smart conflict resolution: duplicate detection, resolution, version comparison."""

from typing import Any, Dict, List

from ..core import load_yaml, save_yaml, shared_dir, compute_dict_hash


def detect_duplicates(case_dir: str, threshold: float = 0.9) -> Dict[str, Any]:
    """Detect duplicate findings based on content hash."""
    sd = shared_dir(case_dir)
    findings_path = sd / "findings.yaml"
    findings = load_yaml(findings_path)

    if not findings:
        return {"duplicates": [], "total": 0}

    hash_groups = {}
    for item in findings:
        if isinstance(item, dict):
            h = compute_dict_hash(item, ["summary", "detail", "from", "type"])
            if h:
                hash_groups.setdefault(h, []).append(item)

    duplicates = []
    for h, items in hash_groups.items():
        if len(items) > 1:
            duplicates.append({"hash": h, "count": len(items), "items": items})

    return {"duplicates": duplicates, "total": len(duplicates), "checked": len(findings)}


def resolve_duplicate(findings: List[Dict], item_id: str, keep_strategy: str = "newer") -> Dict[str, Any]:
    """Resolve duplicates based on specified strategy."""
    if not findings:
        return {"status": "error", "message": "No findings to process"}

    target = None
    for item in findings:
        if isinstance(item, dict) and item.get("id") == item_id:
            target = item
            break

    if not target:
        return {"status": "error", "message": f"Item {item_id} not found"}

    target_hash = compute_dict_hash(target, ["summary", "detail", "from", "type"])
    duplicates = []
    to_remove = []

    for i, item in enumerate(findings):
        if isinstance(item, dict) and item.get("id") != item_id:
            h = compute_dict_hash(item, ["summary", "detail", "from", "type"])
            if h == target_hash:
                duplicates.append(item)
                to_remove.append(i)

    if not duplicates:
        return {"status": "info", "message": "No duplicates found", "kept": target}

    if keep_strategy == "specified":
        kept = target
    elif keep_strategy == "newer":
        all_candidates = [target] + duplicates
        kept = max(all_candidates, key=lambda x: x.get("time", ""))
    elif keep_strategy == "older":
        all_candidates = [target] + duplicates
        kept = min(all_candidates, key=lambda x: x.get("time", ""))
    else:
        all_candidates = [target] + duplicates
        kept = min(all_candidates, key=lambda x: x.get("id", "Z"))

    to_remove.sort(reverse=True)
    for i in to_remove:
        del findings[i]

    return {
        "status": "resolved",
        "kept": kept,
        "removed": len(duplicates),
        "removed_items": duplicates,
        "remaining_count": len(findings),
    }


def compare_versions(local_items: List[Dict], remote_items: List[Dict], key_field: str = "id") -> Dict[str, Any]:
    """Compare local and remote versions."""
    local_dict = {item.get(key_field): item for item in local_items if isinstance(item, dict)}
    remote_dict = {item.get(key_field): item for item in remote_items if isinstance(item, dict)}

    added = [remote_dict[k] for k in remote_dict if k not in local_dict]
    removed = [local_dict[k] for k in local_dict if k not in remote_dict]

    modified = []
    for key, local_item in local_dict.items():
        if key in remote_dict:
            remote_item = remote_dict[key]
            if local_item != remote_item:
                modified.append({"local": local_item, "remote": remote_item, "key": key})

    return {
        "added": added,
        "removed": removed,
        "modified": modified,
        "local_count": len(local_items),
        "remote_count": len(remote_items),
    }
