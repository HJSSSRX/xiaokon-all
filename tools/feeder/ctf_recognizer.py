#!/usr/bin/env python3
"""CTF Challenge Recognition Engine.

Integrates PatternDB, Apriori association rules, and Formal Concept Analysis
to automatically classify CTF challenges and generate solving plans.

Pipeline:
    1. Tag → Domain mapping (keyword + tag analysis)
    2. PatternDB matching (vulnerability type recognition)
    3. Apriori association: (tag_set) → (technique)
    4. FCA equivalence classes: find isomorphic solved challenges
    5. Plan generation: ordered attack chain with confidence

Usage:
    from tools.feeder.ctf_recognizer import CTFRecognizer, recognize

    r = CTFRecognizer(kb_root="D:/ai/knowledge")
    result = r.recognize(challenge_data)
    print(result.plan_summary())
"""

import os
import sys
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple

from tools.feeder.ctf_patterns import PatternDB, VulnerabilityPattern, get_pattern_db


# ── Data Models ────────────────────────────────────────────────────────────

@dataclass
class CTFChallenge:
    """Raw challenge data from CTFHub or similar platform."""
    challenge_id: int
    title: str
    description: str = ""
    tags: List[str] = field(default_factory=list)
    level: float = 0.0
    solve_count: int = 0
    target_url: str = ""
    extra: Dict[str, Any] = field(default_factory=dict)

    def to_transaction(self) -> Set[str]:
        """Convert to item set for Apriori mining."""
        return {t.lower() for t in self.tags}


@dataclass
class RecognitionResult:
    """Output of the recognition engine for one challenge."""
    challenge: CTFChallenge
    patterns: List[Tuple[VulnerabilityPattern, float]]  # (pattern, match_score)
    top_match: Optional[VulnerabilityPattern] = None
    top_match_score: float = 0.0

    # Apriori-based predictions
    predicted_techniques: List[Tuple[str, float]] = field(default_factory=list)

    # FCA-based isomorphism
    isomorphic_challenges: List[Tuple[str, float]] = field(default_factory=list)

    # Generated plan
    attack_plan: List[Dict] = field(default_factory=list)
    estimated_difficulty: str = "unknown"  # easy / medium / hard
    estimated_time: str = "unknown"        # fast (<5min) / medium (5-30min) / slow (>30min)
    notes: List[str] = field(default_factory=list)

    def plan_summary(self, verbose: bool = False) -> str:
        """Human-readable plan summary."""
        lines = [
            "=" * 60,
            "Challenge: %s (level %.1f, %d solves)" % (
                self.challenge.title, self.challenge.level, self.challenge.solve_count),
            "Tags: %s" % ", ".join(self.challenge.tags),
        ]

        if self.top_match:
            lines.append("Top Match: %s (%.0f%%)" % (
                self.top_match.technique, self.top_match_score * 100))

        if self.predicted_techniques:
            pt = ", ".join("%s(%.0f%%)" % (t, s*100) for t, s in self.predicted_techniques[:3])
            lines.append("Predicted: %s" % pt)

        if self.isomorphic_challenges:
            lines.append("Similar to: %s" % ", ".join(
                c for c, _ in self.isomorphic_challenges[:3]))

        lines.append("Difficulty: %s | Time: %s" % (
            self.estimated_difficulty, self.estimated_time))

        if self.notes:
            lines.append("Notes: %s" % "; ".join(self.notes))

        if verbose and self.attack_plan:
            lines.append("Attack Plan:")
            for step in self.attack_plan:
                lines.append("  [%s] %s: %s" % (
                    step.get("phase", "?"), step.get("action", "?"),
                    step.get("detail", "")))

        lines.append("=" * 60)
        return "\n".join(lines)

    def to_dict(self) -> dict:
        """Serialize to dict for JSON output."""
        return {
            "challenge_id": self.challenge.challenge_id,
            "title": self.challenge.title,
            "tags": self.challenge.tags,
            "level": self.challenge.level,
            "top_match": self.top_match.to_dict() if self.top_match else None,
            "top_match_score": self.top_match_score,
            "predicted_techniques": [
                {"technique": t, "confidence": s}
                for t, s in self.predicted_techniques
            ],
            "isomorphic_challenges": [
                {"name": n, "similarity": s}
                for n, s in self.isomorphic_challenges
            ],
            "attack_plan": self.attack_plan,
            "estimated_difficulty": self.estimated_difficulty,
            "estimated_time": self.estimated_time,
            "notes": self.notes,
        }


# ── Tag → Domain Mapping ───────────────────────────────────────────────────

# Maps CTFHub tags to vulnerability categories (from pattern DB)
TAG_TO_CATEGORY = {
    "sql注入": "SQL注入",
    "xss": "XSS",
    "csrf": "CSRF",
    "ssrf": "SSRF",
    "rce": "RCE",
    "文件包含": "文件包含",
    "反序列化(Unserialize)": "反序列化",
    "反序列化": "反序列化",
    "unserialize": "反序列化",
    "备份文件泄露": "备份文件泄露",
    "弱类型": "弱类型",
    "ssti": "SSTI",
    "文件上传": "文件上传",
    "xxe": "XXE",
    "命令注入": "RCE",
    "php": "PHP",
    "ruby": "Ruby",
    "yii2": "SSTI",
    "流量分析": "流量分析",
}

# CTFHub category → difficulty estimate
CATEGORY_DIFFICULTY = {
    "SQL注入": "medium",
    "文件包含": "hard",
    "SSRF": "easy",
    "反序列化": "hard",
    "备份文件泄露": "easy",
    "RCE": "medium",
    "SSTI": "medium",
    "弱类型": "medium",
    "文件上传": "easy",
    "XSS": "easy",
    "XXE": "medium",
    "信息收集": "easy",
    "流量分析": "medium",
}


# ── Recognizer Engine ──────────────────────────────────────────────────────

class CTFRecognizer:
    """Main recognition engine for CTF challenges."""

    def __init__(self, kb_root: str = None, pattern_db: PatternDB = None):
        self.kb_root = kb_root or os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
            "knowledge")
        self.pattern_db = pattern_db or get_pattern_db()
        self._apriori_cache = None
        self._fca_context = None

    # ── Apriori Integration ──

    def _load_apriori(self) -> dict:
        """Load or cache Apriori rules from the knowledge base."""
        if self._apriori_cache is not None:
            return self._apriori_cache

        from tools.analytics.transactions import load_all_transactions
        from tools.analytics.apriori import (
            generate_frequent_itemsets, generate_association_rules)

        txns, fnames = load_all_transactions(self.kb_root)
        if len(txns) < 2:
            self._apriori_cache = {"rules": [], "frequent": {}}
            return self._apriori_cache

        frequent = generate_frequent_itemsets(txns, min_support=0.1, max_k=3)
        rules = generate_association_rules(frequent, txns, min_confidence=0.3, min_lift=0.5)

        self._apriori_cache = {"rules": rules, "frequent": frequent}
        return self._apriori_cache

    def get_association_rules(self) -> list:
        """Get mined association rules."""
        return self._load_apriori()["rules"]

    def predict_techniques(self, tags: Set[str]) -> List[Tuple[str, float]]:
        """Use Apriori rules to predict techniques from tags."""
        rules = self.get_association_rules()
        tags_lower = {t.lower() for t in tags}
        predictions = []

        for rule in rules:
            antecedent = set(rule["antecedent"])
            consequent = rule["consequent"]
            # Check if any antecedent item is in our tags
            if antecedent & tags_lower or any(
                any(a in t for t in tags_lower) for a in antecedent
            ):
                score = rule["confidence"] * rule.get("lift", 1.0)
                predictions.append((consequent, score))

        # Deduplicate and sort
        merged = {}
        for cons, score in predictions:
            if cons in merged:
                merged[cons] = max(merged[cons], score)
            else:
                merged[cons] = score

        return sorted(merged.items(), key=lambda x: x[1], reverse=True)

    # ── FCA Integration (Group Theory) ──

    def _build_fca(self) -> Any:
        """Build Formal Concept Analysis context from pattern DB + solved challenges."""
        if self._fca_context is not None:
            return self._fca_context

        from tools.analytics.grouptheory import FormalContext

        # Objects = challenge names, Attributes = tags
        objects = []
        attr_sets = []

        # Add pattern DB entries as "challenges"
        for p in self.pattern_db.patterns:
            if p.solved_examples:
                for example in p.solved_examples:
                    objects.append(example)
                    attr_sets.append(set(t.lower() for t in p.tags))

        # Add from KB solved challenges
        try:
            from tools.analytics.transactions import extract_transactions
            txns, fnames = extract_transactions(
                self.kb_root, item_types=("tags",), source_dirs=["solved"])
            for i, txn in enumerate(txns):
                objects.append(fnames[i])
                attr_sets.append(txn)
        except Exception:
            pass

        if len(objects) < 2 or len(set().union(*attr_sets) if attr_sets else set()) < 2:
            self._fca_context = None
            return None

        ctx = FormalContext(objects, list(set().union(*attr_sets)))
        for obj, attrs in zip(objects, attr_sets):
            for a in attrs:
                try:
                    ctx.add(obj, a)
                except Exception:
                    pass

        self._fca_context = ctx
        return ctx

    def find_isomorphic_challenges(self, tags: Set[str]) -> List[Tuple[str, float]]:
        """Find structurally similar solved challenges via FCA."""
        ctx = self._build_fca()
        if ctx is None:
            # Fallback: use pattern DB directly
            results = []
            tags_lower = {t.lower() for t in tags}
            for p in self.pattern_db.patterns:
                for example in p.solved_examples:
                    overlap = len(set(t.lower() for t in p.tags) & tags_lower)
                    if overlap > 0:
                        results.append((example, overlap / max(len(tags_lower), 1)))
            results.sort(key=lambda x: x[1], reverse=True)
            return results

        try:
            from tools.analytics.grouptheory import attribute_closure
            tags_lower = {t.lower() for t in tags}
            closure = attribute_closure(tags_lower, ctx)

            # Find objects whose attributes are subset of closure
            results = []
            for i, obj in enumerate(ctx.objects):
                obj_attrs = {a for a, v in ctx.incidence.get(obj, {}).items() if v}
                overlap = len(obj_attrs & closure)
                if overlap > 0:
                    sim = overlap / max(len(obj_attrs | closure), 1)
                    results.append((obj, sim))

            results.sort(key=lambda x: x[1], reverse=True)
            return results
        except Exception:
            return []

    # ── Main Recognition Pipeline ──

    def recognize(self, challenge: CTFChallenge) -> RecognitionResult:
        """Run full recognition pipeline on a challenge."""
        tags = set(challenge.tags)
        desc = challenge.description

        result = RecognitionResult(
            challenge=challenge,
            patterns=[],
        )

        # 1. PatternDB matching
        matches = self.pattern_db.search(tags=tags, description=desc, min_score=0.15)
        result.patterns = matches
        if matches:
            result.top_match, result.top_match_score = matches[0]

        # 2. Apriori technique prediction
        result.predicted_techniques = self.predict_techniques(tags)

        # 3. FCA isomorphism
        result.isomorphic_challenges = self.find_isomorphic_challenges(tags)

        # 4. Generate attack plan
        if result.top_match:
            result.attack_plan = list(result.top_match.attack_chain)

            # Merge in WAF bypass if applicable
            if result.top_match.waf_bypass:
                result.notes.append(
                    "WAF bypass: space=%s, AND=%s, blocked=[%s]" % (
                        result.top_match.waf_bypass.get("space", ""),
                        result.top_match.waf_bypass.get("and", ""),
                        ", ".join(result.top_match.waf_bypass.get("blocked", []))
                    ))

        # 5. Estimate difficulty
        if result.top_match:
            cat = result.top_match.subcategory
            result.estimated_difficulty = CATEGORY_DIFFICULTY.get(cat, "medium")
        elif challenge.level > 8.0:
            result.estimated_difficulty = "hard"
        elif challenge.level > 6.0:
            result.estimated_difficulty = "medium"
        else:
            result.estimated_difficulty = "easy"

        # 6. Estimate time
        techs = [t for t, _ in result.predicted_techniques]
        if any("blind" in t.lower() or "盲注" in t for t in techs):
            result.estimated_time = "slow (>30min)"
        elif result.top_match and "sqli" in result.top_match.id:
            result.estimated_time = "slow (>30min)"
        elif result.top_match and result.top_match.subcategory in ("SSRF", "备份文件泄露"):
            result.estimated_time = "fast (<5min)"
        elif result.top_match and result.top_match.subcategory == "文件包含":
            result.estimated_time = "medium (5-30min)"
        else:
            result.estimated_time = "medium (5-30min)"

        # 7. Add notes about solved examples
        if result.top_match and result.top_match.solved_examples:
            result.notes.append(
                "Solved examples: %s" % ", ".join(result.top_match.solved_examples))

        return result

    def batch_recognize(self, challenges: List[CTFChallenge]) -> List[RecognitionResult]:
        """Recognize multiple challenges at once."""
        return [self.recognize(c) for c in challenges]

    def priority_order(self, results: List[RecognitionResult]
                       ) -> List[RecognitionResult]:
        """Sort challenges by solving priority (easy/fast first, then by confidence)."""
        difficulty_order = {"easy": 0, "medium": 1, "hard": 2}
        time_order = {"fast (<5min)": 0, "medium (5-30min)": 1, "slow (>30min)": 2}

        def key(r: RecognitionResult):
            diff = difficulty_order.get(r.estimated_difficulty, 3)
            time = time_order.get(r.estimated_time, 3)
            conf = r.top_match_score if r.top_match else 0.0
            # Sort: easiest first, then highest confidence
            return (diff, time, -conf)

        return sorted(results, key=key)


# ── Convenience ──

_default_recognizer = None


def get_recognizer(kb_root: str = None) -> CTFRecognizer:
    """Get or create the default recognizer singleton."""
    global _default_recognizer
    if _default_recognizer is None:
        _default_recognizer = CTFRecognizer(kb_root=kb_root)
    return _default_recognizer


def recognize(challenge_data: dict, kb_root: str = None) -> RecognitionResult:
    """One-shot challenge recognition from a dictionary.

    Args:
        challenge_data: {
            "id": int, "title": str, "description": str,
            "tags": [str, ...], "level": float, "solve_count": int,
            "target_url": str (optional)
        }

    Returns:
        RecognitionResult
    """
    r = get_recognizer(kb_root)
    challenge = CTFChallenge(
        challenge_id=challenge_data.get("id", 0),
        title=challenge_data.get("title", "Unknown"),
        description=challenge_data.get("description", ""),
        tags=challenge_data.get("tags", []),
        level=challenge_data.get("level", 0.0),
        solve_count=challenge_data.get("solve_count", 0),
        target_url=challenge_data.get("target_url", ""),
        extra=challenge_data.get("extra", {}),
    )
    return r.recognize(challenge)


# ── Test ──

if __name__ == "__main__":
    # Test with synthetic challenge data from CTFHub
    r = get_recognizer()

    challenges = [
        CTFChallenge(
            challenge_id=1013, title="Baby PHP",
            description="PHP unserialize vulnerability exploitation",
            tags=["Web", "PHP", "反序列化(Unserialize)"], level=8.9, solve_count=301),
        CTFChallenge(
            challenge_id=1014, title="SQL注入基础",
            description="SQL injection challenge with basic filtering",
            tags=["Web", "SQL注入"], level=7.0, solve_count=500),
        CTFChallenge(
            challenge_id=1015, title="文件上传",
            description="Upload your avatar, bypass extension filter",
            tags=["Web", "文件上传"], level=6.5, solve_count=300),
        CTFChallenge(
            challenge_id=1016, title="hidden flag",
            description="Find the hidden backup file and get the flag",
            tags=["Web", "备份文件泄露"], level=5.7, solve_count=1379),
    ]

    print("=== Challenge Recognition Results ===\n")
    for c in challenges:
        result = r.recognize(c)
        print(result.plan_summary(verbose=True))
        print()

    print("\n=== Priority Order ===")
    all_results = r.batch_recognize(challenges)
    for i, res in enumerate(r.priority_order(all_results)):
        print("%d. %s (%s, conf=%.0f%%)" % (
            i+1, res.challenge.title,
            res.estimated_difficulty, res.top_match_score * 100))
