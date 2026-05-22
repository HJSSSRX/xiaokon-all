"""Detect evidence files shared across multiple sub-goals.

When multiple analysis sub-goals need the same evidence file, we create
a single preparation sub-goal that all of them depend on — instead of
each one doing the same mount/extract/decrypt work independently.
"""

from typing import Dict, List, Set, Tuple
from tools.decomposer.models import EvidenceInfo, SubGoal, SubGoalLevel


def detect_shared_inputs(
    evidence_files: List[EvidenceInfo],
    analysis_sub_goals: Dict[str, SubGoal],
) -> List[SubGoal]:
    """Detect shared evidence inputs and create shared prep sub-goals.

    For each evidence file needed by 2+ analysis sub-goals, creates a
    single Level 1 prep sub-goal. Updates each analysis sub-goal to depend
    on the shared prep step instead of referencing raw evidence directly.

    Args:
        evidence_files: All evidence files in the challenge.
        analysis_sub_goals: Level 2 analysis sub-goals with their input lists.

    Returns:
        List of new prep sub-goals for shared inputs.
    """
    # Count how many analysis sub-goals reference each evidence file
    evidence_ref_count: Dict[str, List[str]] = {}  # evidence_path -> [sub_goal_ids]

    for sg_id, sg in analysis_sub_goals.items():
        for inp in sg.inputs:
            if inp not in evidence_ref_count:
                evidence_ref_count[inp] = []
            evidence_ref_count[inp].append(sg_id)

    prep_goals: List[SubGoal] = []
    prep_counter = 0

    for evidence_path, sg_ids in evidence_ref_count.items():
        if len(sg_ids) < 2:
            continue

        ev_info = next((e for e in evidence_files if e.path == evidence_path), None)
        if ev_info is None:
            continue

        prep_counter += 1
        prep_id = f"SG-P{prep_counter:03d}"

        description, task_type = _get_prep_description(ev_info)

        prep_goal = SubGoal(
            id=prep_id,
            level=SubGoalLevel.PREP,
            description=description,
            domain=ev_info.detected_type if ev_info.detected_type != "unknown" else "",
            task_type=task_type,
            inputs=[evidence_path],
            outputs=[f"{evidence_path}_prepared"],
            dependencies=[],
            tools=_get_prep_tools(ev_info),
            assigned_role="",
            estimated_minutes=_estimate_prep_time(ev_info),
            priority=1,
        )
        prep_goals.append(prep_goal)

        # Update analysis sub-goals: replace raw evidence with prep output
        for sg_id in sg_ids:
            sg = analysis_sub_goals.get(sg_id)
            if sg:
                if evidence_path in sg.inputs:
                    sg.inputs.remove(evidence_path)
                    sg.inputs.append(prep_goal.outputs[0])
                if prep_id not in sg.dependencies:
                    sg.dependencies.append(prep_id)

    return prep_goals


def _get_prep_description(ev: EvidenceInfo) -> Tuple[str, str]:
    """Get human-readable description and task type for preparing evidence."""
    name = ev.path.split("/")[-1].split("\\")[-1]
    if ev.mount_required:
        return f"挂载镜像文件: {name}", "disk_analysis"
    elif ev.is_encrypted:
        return f"解密文件: {name}", "crypto_analysis"
    elif ev.is_archive:
        return f"解压归档文件: {name}", "data_recovery"
    else:
        return f"预处理: {name}", "data_recovery"


def _get_prep_tools(ev: EvidenceInfo) -> List[str]:
    """Get recommended tools for preparing evidence."""
    if ev.mount_required:
        if ev.extension == ".e01":
            return ["ewfmount", "mount"]
        elif ev.extension in (".vmdk", ".vhd", ".vhdx"):
            return ["mount", "losetup", "qemu-img"]
        return ["mount", "losetup"]
    elif ev.is_encrypted:
        return ["gpg", "openssl"]
    elif ev.is_archive:
        if ev.extension == ".zip":
            return ["unzip", "7z"]
        elif ev.extension in (".rar",):
            return ["unrar", "7z"]
        return ["7z", "tar"]
    return ["file", "binwalk"]


def _estimate_prep_time(ev: EvidenceInfo) -> int:
    """Estimate preparation time in minutes based on file size."""
    gb = ev.size_bytes / (1024 ** 3)
    if gb > 10:
        return 30
    elif gb > 2:
        return 15
    elif gb > 0.5:
        return 5
    return 2
