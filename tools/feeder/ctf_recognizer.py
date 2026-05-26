#!/usr/bin/env python3
"""CTF Challenge Recognition Engine.

Matches CTF challenges against vulnerability pattern database.
Integrates Apriori and FCA for technique prediction and isomorphism detection.

Pipeline: Tag→Domain → PatternDB match → Apriori predict → FCA isomorphism → Plan

Usage:
    from tools.feeder.ctf_recognizer import CTFRecognizer, recognize
    r = CTFRecognizer()
    result = r.recognize(challenge_data)
"""

import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple

from tools.feeder.ctf_patterns import (
    CATEGORY_DIFFICULTY, PatternDB, VulnerabilityPattern, get_pattern_db,
)


# ── Data Models ────────────────────────────────────────────────────────────

@dataclass
class CTFChallenge:
    challenge_id: int
    title: str
    description: str = ""
    tags: List[str] = field(default_factory=list)
    level: float = 0.0
    solve_count: int = 0
    target_url: str = ""
    extra: Dict[str, Any] = field(default_factory=dict)


@dataclass
class RecognitionResult:
    challenge: CTFChallenge
    patterns: List[Tuple[VulnerabilityPattern, float]] = field(default_factory=list)
    top_match: Optional[VulnerabilityPattern] = None
    top_match_score: float = 0.0
    predicted_techniques: List[Tuple[str, float]] = field(default_factory=list)
    isomorphic_challenges: List[Tuple[str, float]] = field(default_factory=list)
    attack_plan: List[Dict] = field(default_factory=list)
    estimated_difficulty: str = "unknown"
    estimated_time: str = "unknown"
    notes: List[str] = field(default_factory=list)

    def plan_summary(self, verbose: bool = False) -> str:
        sep = "=" * 60
        lines = [
            sep,
            f"Challenge: {self.challenge.title} (L{self.challenge.level:.1f}, {self.challenge.solve_count} solves)",
            f"Tags: {', '.join(self.challenge.tags)}",
        ]
        if self.top_match:
            lines.append(f"Top Match: {self.top_match.technique} ({self.top_match_score:.0%})")
        if self.predicted_techniques:
            pt = ", ".join(f"{t}({s:.0%})" for t, s in self.predicted_techniques[:3])
            lines.append(f"Predicted: {pt}")
        if self.isomorphic_challenges:
            lines.append("Similar to: " + ", ".join(c for c, _ in self.isomorphic_challenges[:3]))
        lines.append(f"Difficulty: {self.estimated_difficulty} | Time: {self.estimated_time}")
        if self.notes:
            lines.append("Notes: " + "; ".join(self.notes))
        if verbose and self.attack_plan:
            lines.append("Attack Plan:")
            for step in self.attack_plan:
                lines.append(f"  [{step.get('phase', '?')}] {step.get('action', '?')}: {step.get('detail', '')}")
        lines.append(sep)
        return "\n".join(lines)

    def to_dict(self) -> dict:
        return {
            "challenge_id": self.challenge.challenge_id,
            "title": self.challenge.title, "tags": self.challenge.tags,
            "level": self.challenge.level,
            "top_match": self.top_match.to_dict() if self.top_match else None,
            "top_match_score": self.top_match_score,
            "predicted_techniques": [{"technique": t, "confidence": s}
                                     for t, s in self.predicted_techniques],
            "isomorphic_challenges": [{"name": n, "similarity": s}
                                      for n, s in self.isomorphic_challenges],
            "attack_plan": self.attack_plan,
            "estimated_difficulty": self.estimated_difficulty,
            "estimated_time": self.estimated_time,
            "notes": self.notes,
        }


# ── Recognizer Engine ──────────────────────────────────────────────────────

class CTFRecognizer:
    """Challenge recognition via pattern matching + optional Apriori/FCA."""

    def __init__(self, kb_root: str = None, pattern_db: PatternDB = None,
                 use_apriori: bool = True, use_fca: bool = False):
        if kb_root is None:
            kb_root = os.path.join(
                os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                "knowledge")
        self.kb_root = kb_root
        self.pattern_db = pattern_db or get_pattern_db()
        self.use_apriori = use_apriori
        self.use_fca = use_fca
        self._apriori_cache = None
        self._fca_cache = None

    # ── Apriori (lazy) ──

    def _load_apriori(self) -> dict:
        if self._apriori_cache is not None:
            return self._apriori_cache
        try:
            from tools.analytics.transactions import load_all_transactions
            from tools.analytics.apriori import (generate_frequent_itemsets,
                                                  generate_association_rules)
            txns, _ = load_all_transactions(self.kb_root)
            if len(txns) < 2:
                self._apriori_cache = {"rules": [], "frequent": {}}
                return self._apriori_cache
            frequent = generate_frequent_itemsets(txns, min_support=0.1, max_k=3)
            rules = generate_association_rules(frequent, txns, min_confidence=0.3, min_lift=0.5)
            self._apriori_cache = {"rules": rules, "frequent": frequent}
        except Exception:
            self._apriori_cache = {"rules": [], "frequent": {}}
        return self._apriori_cache

    def _predict_from_rules(self, tags: Set[str]) -> List[Tuple[str, float]]:
        if not self.use_apriori:
            return []
        rules = self._load_apriori()["rules"]
        tags_lower = {t.lower() for t in tags}
        merged = {}
        for rule in rules:
            antecedent = set(rule["antecedent"])
            consequent = rule["consequent"]
            if antecedent & tags_lower or any(
                any(a in t for t in tags_lower) for a in antecedent
            ):
                score = rule["confidence"] * rule.get("lift", 1.0)
                if consequent in merged:
                    merged[consequent] = max(merged[consequent], score)
                else:
                    merged[consequent] = score
        return sorted(merged.items(), key=lambda x: x[1], reverse=True)

    # ── FCA Isomorphism (lazy) ──

    def _find_isomorphic_fca(self, tags: Set[str]) -> List[Tuple[str, float]]:
        if not self.use_fca:
            return self._find_isomorphic_fallback(tags)
        try:
            from tools.analytics.grouptheory import FormalContext
            from tools.analytics.transactions import extract_transactions

            if self._fca_cache is None:
                objects, attr_sets = [], []
                for p in self.pattern_db.patterns:
                    for example in p.solved_examples:
                        objects.append(example)
                        attr_sets.append(set(t.lower() for t in p.tags))
                try:
                    txns, fnames = extract_transactions(
                        self.kb_root, item_types=("tags",), source_dirs=["solved"])
                    for i, txn in enumerate(txns):
                        objects.append(fnames[i])
                        attr_sets.append(txn)
                except Exception:
                    pass
                if len(objects) >= 2:
                    all_attrs = list(set().union(*attr_sets))
                    ctx = FormalContext(objects, all_attrs)
                    for obj, attrs in zip(objects, attr_sets):
                        for a in attrs:
                            try:
                                ctx.add(obj, a)
                            except Exception:
                                pass
                    self._fca_cache = ctx
                else:
                    self._fca_cache = None

            if self._fca_cache is None:
                return self._find_isomorphic_fallback(tags)
            from tools.analytics.grouptheory import attribute_closure
            tags_lower = {t.lower() for t in tags}
            closure = attribute_closure(tags_lower, self._fca_cache)
            results = []
            for obj in self._fca_cache.objects:
                obj_attrs = {a for a, v in self._fca_cache.incidence.get(obj, {}).items() if v}
                overlap = len(obj_attrs & closure)
                if overlap > 0:
                    results.append((obj, overlap / max(len(obj_attrs | closure), 1)))
            results.sort(key=lambda x: x[1], reverse=True)
            return results
        except Exception:
            return self._find_isomorphic_fallback(tags)

    def _find_isomorphic_fallback(self, tags: Set[str]) -> List[Tuple[str, float]]:
        tags_lower = {t.lower() for t in tags}
        results = []
        for p in self.pattern_db.patterns:
            for example in p.solved_examples:
                overlap = len(set(t.lower() for t in p.tags) & tags_lower)
                if overlap > 0:
                    results.append((example, overlap / max(len(tags_lower), 1)))
        results.sort(key=lambda x: x[1], reverse=True)
        return results

    # ── Recognition Pipeline ──

    def recognize(self, challenge: CTFChallenge) -> RecognitionResult:
        tags = set(challenge.tags)
        result = RecognitionResult(challenge=challenge)

        # 1. Pattern match
        matches = self.pattern_db.search(tags=tags, description=challenge.description, min_score=0.15)
        result.patterns = matches
        if matches:
            result.top_match, result.top_match_score = matches[0]

        # 2. Apriori prediction
        result.predicted_techniques = self._predict_from_rules(tags)

        # 3. Isomorphic challenges
        result.isomorphic_challenges = self._find_isomorphic_fca(tags)

        # 4. Attack plan
        if result.top_match:
            result.attack_plan = list(result.top_match.attack_chain)
            if result.top_match.waf_bypass:
                wb = result.top_match.waf_bypass
                result.notes.append(
                    f"WAF: space={wb.get('space','')}, AND={wb.get('and','')}, "
                    f"blocked=[{','.join(wb.get('blocked',[]))}]")
            if result.top_match.solved_examples:
                result.notes.append("Solved: " + ", ".join(result.top_match.solved_examples))

        # 5. Difficulty / time
        if result.top_match:
            result.estimated_difficulty = CATEGORY_DIFFICULTY.get(
                result.top_match.subcategory, "medium")
        else:
            result.estimated_difficulty = "hard" if challenge.level > 8.0 else (
                "medium" if challenge.level > 6.0 else "easy")

        techs = [t for t, _ in result.predicted_techniques]
        if any("blind" in t.lower() or "盲注" in t for t in techs) or (
            result.top_match and "sqli" in result.top_match.id):
            result.estimated_time = "slow (>30min)"
        elif result.top_match and result.top_match.subcategory in ("SSRF", "备份文件泄露"):
            result.estimated_time = "fast (<5min)"
        elif result.top_match and result.top_match.subcategory == "文件包含":
            result.estimated_time = "medium (5-30min)"
        else:
            result.estimated_time = "medium (5-30min)"

        return result

    def batch_recognize(self, challenges: List[CTFChallenge]) -> List[RecognitionResult]:
        return [self.recognize(c) for c in challenges]

    def priority_order(self, results: List[RecognitionResult]) -> List[RecognitionResult]:
        diff_order = {"easy": 0, "medium": 1, "hard": 2}
        time_order = {"fast (<5min)": 0, "medium (5-30min)": 1, "slow (>30min)": 2}
        return sorted(results, key=lambda r: (
            diff_order.get(r.estimated_difficulty, 3),
            time_order.get(r.estimated_time, 3),
            -(r.top_match_score if r.top_match else 0),
        ))


# ── Convenience ──

_default_recognizer = None


def get_recognizer(kb_root: str = None) -> CTFRecognizer:
    global _default_recognizer
    if _default_recognizer is None:
        _default_recognizer = CTFRecognizer(kb_root=kb_root)
    return _default_recognizer


def recognize(challenge_data: dict, kb_root: str = None) -> RecognitionResult:
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
    r = get_recognizer()
    tests = [
        ("Web,SQL注入", "SQL injection challenge", 7.0),
        ("Web,SSRF", "Website alive checker with curl", 7.8),
        ("Web,反序列化(Unserialize),PHP", "PHP unserialize pop chain", 8.9),
    ]
    for tags_str, desc, level in tests:
        challenge = CTFChallenge(
            challenge_id=0, title="Test", description=desc,
            tags=[t.strip() for t in tags_str.split(",")], level=level)
        result = r.recognize(challenge)
        print(result.plan_summary(verbose=True))
        print()
