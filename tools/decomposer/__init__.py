"""Challenge Decomposer — automatic challenge decomposition into sub-goals.

Usage:
    from tools.decomposer import decompose, Decomposer

    # Quick decomposition from a directory
    plan = decompose("cases/2025pinghang/")

    # With full control
    dec = Decomposer(kb_root="knowledge/", recommend_tools=True)
    plan = dec.decompose("cases/2025pinghang/")
"""

from tools.decomposer.models import (
    DecompositionPlan, EvidenceInfo, SubGoal, SubGoalLevel,
)
from tools.decomposer.decomposer_engine import decompose as _decompose_engine
from tools.decomposer.evidence_classifier import classify_evidence, summarize_evidence
from tools.decomposer.parser import parse_challenge
from tools.decomposer.output_writer import (
    write_all_outputs, write_report, write_tasks_json, write_execution_plan,
    format_summary,
)


class Decomposer:
    """High-level decomposer with configurable options."""

    def __init__(
        self,
        kb_root: str = "",
        recommend_tools: bool = True,
        max_depth: int = 3,
        compute_hashes: bool = False,
    ):
        if not kb_root:
            import os
            kb_root = os.path.join(
                os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
                "knowledge"
            )
        self.kb_root = kb_root
        self.recommend_tools = recommend_tools
        self.max_depth = max_depth
        self.compute_hashes = compute_hashes

    def decompose(
        self,
        challenge_dir: str = "",
        challenge_text: str = "",
        output_dir: str = "",
    ) -> DecompositionPlan:
        """Decompose a challenge from directory or text description.

        Args:
            challenge_dir: Path to challenge directory with evidence files.
            challenge_text: Free-text challenge description.
            output_dir: Directory for output files. Uses challenge_dir if empty.

        Returns:
            DecompositionPlan ready for inspection and output.
        """
        name, description, questions, _, _ = parse_challenge(
            challenge_dir=challenge_dir or None,
            challenge_text=challenge_text or None,
        )

        evidence = []
        if challenge_dir:
            import os
            if os.path.isdir(challenge_dir):
                evidence = classify_evidence(
                    challenge_dir,
                    max_depth=self.max_depth,
                    compute_hashes=self.compute_hashes,
                )

        plan = _decompose_engine(
            evidence_files=evidence,
            challenge_name=name,
            challenge_description=description,
            questions=questions,
            kb_root=self.kb_root,
            recommend_tools=self.recommend_tools,
        )

        if output_dir or challenge_dir:
            out = output_dir or challenge_dir
            write_all_outputs(plan, out)

        return plan


def decompose(
    challenge_dir: str = "",
    challenge_text: str = "",
    output_dir: str = "",
    kb_root: str = "",
    recommend_tools: bool = True,
) -> DecompositionPlan:
    """Convenience function: decompose a challenge in one call.

    Args:
        challenge_dir: Path to challenge directory.
        challenge_text: Free-text challenge description.
        output_dir: Directory for output files.
        kb_root: Knowledge base root path.
        recommend_tools: Enable KB-based tool recommendations.

    Returns:
        DecompositionPlan.
    """
    dec = Decomposer(
        kb_root=kb_root,
        recommend_tools=recommend_tools,
    )
    return dec.decompose(
        challenge_dir=challenge_dir,
        challenge_text=challenge_text,
        output_dir=output_dir,
    )
