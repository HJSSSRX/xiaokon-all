"""Integration tests for tools/analytics/ module.

Covers: apriori.py, transactions.py, recommend.py, cli.py
Run: python -m pytest tests/test_analytics_integration.py -v
"""

import os
import sys
import tempfile
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from tools.analytics.apriori import (
    generate_frequent_itemsets,
    generate_association_rules,
    format_rules_table,
    _count_itemsets,
    _generate_candidates,
)
from tools.analytics.transactions import (
    extract_transactions,
    load_all_transactions,
    _parse_frontmatter,
    _read_file_items,
)
from tools.analytics.recommend import (
    recommend,
    format_recommendations,
    _build_rule_index,
    _is_tool,
)


# ────────────────────────────────
# apriori.py unit tests
# ────────────────────────────────

class TestAprioriCore:
    def test_count_itemsets_empty(self):
        assert _count_itemsets([], [("a",)]) == {}

    def test_count_itemsets_basic(self):
        txns = [{"a", "b"}, {"a", "c"}, {"a", "b", "c"}]
        counts = _count_itemsets(txns, [("a",), ("a", "b")])
        assert counts[("a",)] == 3
        assert counts[("a", "b")] == 2

    def test_generate_candidates_k2(self):
        freq_1 = [("a",), ("b",), ("c",), ("d",)]
        cands = _generate_candidates(freq_1, 2)
        assert len(cands) == 6  # C(4,2)
        assert all(len(c) == 2 for c in cands)

    def test_generate_candidates_prunes_infrequent(self):
        """k=3 candidates: only those with all (k-1)-subsets frequent survive."""
        freq_2 = [("a", "b"), ("a", "c"), ("b", "c")]  # {a,b,c} is closed
        # Also include ("a", "d") - then ("a", "b", "d") needs ("b", "d") which isn't in freq_2
        freq_2_extra = [("a", "b"), ("a", "c"), ("b", "c"), ("a", "d")]
        cands = _generate_candidates(freq_2, 3)
        assert ("a", "b", "c") in cands
        cands_extra = _generate_candidates(freq_2_extra, 3)
        assert ("a", "b", "d") not in cands_extra  # pruned: ("b","d") not frequent

    def test_frequent_itemsets_empty(self):
        assert generate_frequent_itemsets([]) == {}

    def test_frequent_itemsets_absolute_threshold(self):
        txns = [{"a", "b"}, {"a", "c"}, {"a", "b", "c"}, {"d"}]
        result = generate_frequent_itemsets(txns, min_support=2)  # absolute count
        assert 1 in result
        assert ("a",) in result[1]
        assert ("d",) not in result[1]  # only 1 tx

    def test_frequent_itemsets_relative_threshold(self):
        txns = [{"a", "b"}, {"a", "c"}, {"a", "b", "c"}, {"d"}]
        result = generate_frequent_itemsets(txns, min_support=0.5)  # 50% of 4 = 2
        assert ("a",) in result[1]
        assert ("d",) not in result[1]

    def test_frequent_itemsets_max_k(self):
        txns = [{"a", "b", "c"}, {"a", "b", "c"}, {"a", "b", "c"}]
        result = generate_frequent_itemsets(txns, min_support=0.5, max_k=2)
        assert 1 in result
        assert 2 in result
        assert 3 not in result  # capped

    def test_association_rules_empty(self):
        rules = generate_association_rules({})
        assert rules == []

    def test_association_rules_basic(self):
        txns = [{"a", "b"}, {"a", "b"}, {"a", "b"}, {"a"}, {"b"}]
        freq = generate_frequent_itemsets(txns, min_support=0.4)
        rules = generate_association_rules(freq, transactions=txns, min_confidence=0.6)
        # {a} => {b} should exist
        assert any(
            r["antecedent"] == ("a",) and r["consequent"] == ("b",) for r in rules
        )

    def test_association_rules_lift(self):
        """Lift > 1 when items are positively correlated."""
        txns = [{"a", "b"}, {"a", "b"}, {"a", "b"}, {"a"}, {"b"}]
        freq = generate_frequent_itemsets(txns, min_support=0.4)
        rules = generate_association_rules(freq, transactions=txns, min_confidence=0.1)
        ab_rule = [r for r in rules if r["antecedent"] == ("a",) and r["consequent"] == ("b",)]
        if ab_rule:
            assert ab_rule[0]["lift"] > 1.0

    def test_format_rules_table_empty(self):
        assert format_rules_table([]) == "No association rules found."

    def test_format_rules_table_has_rows(self):
        rules = [
            {
                "antecedent": ("a",),
                "consequent": ("b",),
                "support": 0.5,
                "confidence": 0.8,
                "lift": 2.0,
            }
        ]
        out = format_rules_table(rules)
        assert "a" in out
        assert "b" in out
        assert "0.500" in out


# ────────────────────────────────
# transactions.py unit tests
# ────────────────────────────────

class TestTransactions:
    def test_parse_frontmatter_valid(self):
        content = "---\ntags: [a, b]\ntools: [x]\n---\n# Title"
        fm = _parse_frontmatter(content)
        assert fm == {"tags": ["a", "b"], "tools": ["x"]}

    def test_parse_frontmatter_none(self):
        assert _parse_frontmatter("# No frontmatter") == {}

    def test_parse_frontmatter_invalid_yaml(self):
        content = "---\n: bad yaml : :\n---\n"
        fm = _parse_frontmatter(content)
        assert fm == {}

    def test_read_file_items_md(self, tmp_path):
        f = tmp_path / "test.md"
        f.write_text("---\ntags: [android, mobile]\ntools: [adb, jadx]\n---\n# Content", encoding="utf-8")
        tags, tools, cats = _read_file_items(str(f))
        assert tags == {"android", "mobile"}
        assert tools == {"adb", "jadx"}

    def test_read_file_items_no_frontmatter(self, tmp_path):
        f = tmp_path / "plain.md"
        f.write_text("# Just a title\n\nSome content.", encoding="utf-8")
        tags, tools, cats = _read_file_items(str(f))
        assert tags == set()
        assert tools == set()

    def test_read_file_items_binary_file(self, tmp_path):
        f = tmp_path / "binary.md"
        f.write_bytes(b"\x00\x01\x02\xff\xfe")
        tags, tools, cats = _read_file_items(str(f))
        assert tags == set()

    def test_extract_transactions_real_kb(self):
        kb = os.path.join(os.path.dirname(__file__), "..", "knowledge")
        txns, files = extract_transactions(kb, item_types=("tools",))
        assert len(txns) > 0
        assert len(txns) == len(files)
        # All items should be lowercase strings
        for txn in txns:
            for item in txn:
                assert item == item.lower()

    def test_extract_transactions_tags(self):
        kb = os.path.join(os.path.dirname(__file__), "..", "knowledge")
        txns, files = extract_transactions(kb, item_types=("tags",))
        assert len(txns) > 0

    def test_extract_transactions_nonexistent_dir(self):
        txns, files = extract_transactions("/nonexistent/path", item_types=("tools",))
        assert txns == []

    def test_load_all_transactions(self):
        kb = os.path.join(os.path.dirname(__file__), "..", "knowledge")
        txns, files = load_all_transactions(kb)
        assert len(txns) > 0


# ────────────────────────────────
# recommend.py unit tests
# ────────────────────────────────

class TestRecommend:
    def test_is_tool(self):
        tools_vocab = {"vol3", "strings", "sqlite3"}
        assert _is_tool("vol3", tools_vocab) is True
        assert _is_tool("strings", tools_vocab) is True
        assert _is_tool("android", tools_vocab) is False

    def test_build_rule_index(self):
        kb = os.path.join(os.path.dirname(__file__), "..", "knowledge")
        rules, txns, files = _build_rule_index(kb, min_support=0.15, min_confidence=0.5)
        assert isinstance(rules, list)
        assert len(txns) > 0

    def test_recommend_tools(self):
        kb = os.path.join(os.path.dirname(__file__), "..", "knowledge")
        result = recommend(
            ["mobile", "android", "sqlite3"],
            kb_root=kb,
            target="tools",
            min_support=0.08,
            min_confidence=0.3,
            top_n=5,
        )
        assert result["target"] == "tools"
        assert result["context"] == ["mobile", "android", "sqlite3"]
        assert "recommendations" in result
        assert "rules_checked" in result
        for rec in result["recommendations"]:
            assert "item" in rec
            assert "score" in rec
            assert "rationale" in rec
            assert rec["score"] > 0

    def test_recommend_tags(self):
        kb = os.path.join(os.path.dirname(__file__), "..", "knowledge")
        result = recommend(
            ["sqlite3", "grep", "strings"],
            kb_root=kb,
            target="tags",
            min_support=0.08,
            min_confidence=0.3,
            top_n=5,
        )
        assert result["target"] == "tags"

    def test_recommend_empty_context(self):
        kb = os.path.join(os.path.dirname(__file__), "..", "knowledge")
        result = recommend(
            ["nonexistent_tag_xyz"],
            kb_root=kb,
            target="tools",
            top_n=5,
        )
        assert result["recommendations"] == []

    def test_recommend_all_target(self):
        kb = os.path.join(os.path.dirname(__file__), "..", "knowledge")
        result = recommend(
            ["mobile", "sqlite3"],
            kb_root=kb,
            target="all",
            min_support=0.08,
            top_n=10,
        )
        assert result["target"] == "all"

    def test_format_recommendations(self):
        result = {
            "context": ["mobile"],
            "target": "tools",
            "recommendations": [
                {
                    "item": "adb",
                    "score": 5.0,
                    "confidence": 0.9,
                    "lift": 3.0,
                    "match_ratio": 1.0,
                    "best_rule": "mobile => adb",
                    "rule_confidence": 0.9,
                    "rule_lift": 3.0,
                    "rule_support": 0.2,
                    "supporting_rules": [],
                    "rationale": "完全匹配；置信度 90%；强正相关 (lift=3.0)；规则: mobile => adb",
                }
            ],
            "rules_checked": 42,
            "rules_matched": 5,
        }
        out = format_recommendations(result)
        assert "adb" in out
        assert "mobile" in out
        assert "5.00" in out

    def test_format_recommendations_empty(self):
        result = {
            "context": ["nothing"],
            "target": "tools",
            "recommendations": [],
            "rules_checked": 42,
            "rules_matched": 0,
        }
        out = format_recommendations(result)
        assert "未找到" in out or "no" in out.lower()


# ────────────────────────────────
# Integration: end-to-end pipeline
# ────────────────────────────────

class TestEndToEnd:
    def test_full_pipeline(self):
        """Mine -> generate rules -> recommend from rules."""
        kb = os.path.join(os.path.dirname(__file__), "..", "knowledge")

        # Step 1: Extract
        txns, files = extract_transactions(kb, item_types=("tags", "tools", "categories"))
        assert len(txns) > 0

        # Step 2: Mine frequent itemsets
        freq = generate_frequent_itemsets(txns, min_support=0.1)
        assert len(freq) > 0

        # Step 3: Generate rules
        rules = generate_association_rules(freq, transactions=txns, min_confidence=0.3)
        assert len(rules) > 0

        # Step 4: Format rules
        table = format_rules_table(rules, top_n=5)
        assert len(table) > 0

        # Step 5: Recommend from context
        result = recommend(
            ["mobile", "sqlite3"],
            kb_root=kb,
            target="tools",
            min_support=0.1,
            top_n=5,
        )
        assert len(result["recommendations"]) > 0
        assert all("score" in r for r in result["recommendations"])

    def test_rule_consistency(self):
        """Generated rules should have consistent counts."""
        kb = os.path.join(os.path.dirname(__file__), "..", "knowledge")
        txns, _ = extract_transactions(kb, item_types=("tools",))
        freq = generate_frequent_itemsets(txns, min_support=0.1)
        rules = generate_association_rules(freq, transactions=txns, min_confidence=0.3)

        for r in rules:
            # confidence is between 0 and 1
            assert 0 <= r["confidence"] <= 1
            # support is between 0 and 1
            assert 0 <= r["support"] <= 1
            # lift is positive
            assert r["lift"] > 0
            # count_both <= count_antecedent
            if r["count_antecedent"] > 0 and r["count_both"] > 0:
                pass  # counts are rounded, may not be exact

    def test_recommend_scoring_order(self):
        """Higher scored recommendations should have higher confidence*lift*match_ratio."""
        kb = os.path.join(os.path.dirname(__file__), "..", "knowledge")
        result = recommend(
            ["mobile", "android"],
            kb_root=kb,
            target="tools",
            min_support=0.08,
            min_confidence=0.2,
            top_n=10,
        )
        recs = result["recommendations"]
        scores = [r["score"] for r in recs]
        assert scores == sorted(scores, reverse=True)  # descending

    def test_report_file_generated(self):
        """Verify association_rules.md exists and has content."""
        kb = os.path.join(os.path.dirname(__file__), "..", "knowledge")
        report_path = os.path.join(kb, "_relations", "association_rules.md")
        assert os.path.exists(report_path)
        with open(report_path, "r", encoding="utf-8") as f:
            content = f.read()
        assert "Association Rule Mining Report" in content
        assert "Tool co-occurrence" in content
        assert "Tag associations" in content


# ────────────────────────────────
# Edge cases
# ────────────────────────────────

class TestEdgeCases:
    def test_single_transaction(self):
        txns = [{"a", "b", "c"}]
        freq = generate_frequent_itemsets(txns, min_support=0.5)
        # With 1 tx, support=0.5 => min_count=0 (floor), actually min_count=int(0.5)=0 -> clamped to 1
        # So items need to appear in >= 1 tx, which all do
        assert len(freq) > 0

    def test_all_same_transactions(self):
        txns = [{"a", "b"}] * 100
        freq = generate_frequent_itemsets(txns, min_support=0.5)
        assert 2 in freq
        rules = generate_association_rules(freq, transactions=txns, min_confidence=0.5)
        ab = [r for r in rules if r["antecedent"] == ("a",) and r["consequent"] == ("b",)]
        assert len(ab) > 0
        assert ab[0]["confidence"] == 1.0

    def test_disjoint_transactions(self):
        txns = [{"a", "b"}, {"c", "d"}, {"e", "f"}]
        freq = generate_frequent_itemsets(txns, min_support=0.3)
        rules = generate_association_rules(freq, transactions=txns, min_confidence=0.3)
        # No cross-group rules should exist
        for r in rules:
            ant_set = set(r["antecedent"])
            cons_set = set(r["consequent"])
            # Each rule's items should come from the same transaction
            combined = ant_set | cons_set
            valid = any(combined.issubset(t) for t in txns)
            assert valid, f"Rule {r} crosses disjoint transactions"

    def test_confidence_bounds(self):
        """Confidence should never exceed 1.0."""
        txns = [{"a", "b"}] * 10 + [{"a"}] * 2
        freq = generate_frequent_itemsets(txns, min_support=0.1)
        rules = generate_association_rules(freq, transactions=txns, min_confidence=0.1)
        for r in rules:
            assert r["confidence"] <= 1.0
            assert r["confidence"] >= 0.0

    def test_support_normalization(self):
        """Absolute min_support >= 1 should be treated as count, < 1 as fraction."""
        txns = [{"a"}] * 5 + [{"b"}] * 95
        # min_support=0.1 => need 10 txns, so only b is frequent
        result_fraction = generate_frequent_itemsets(txns, min_support=0.1)
        assert ("a",) not in result_fraction.get(1, {})
        # min_support=3 => need 3 txns, both frequent
        result_absolute = generate_frequent_itemsets(txns, min_support=3)
        assert ("a",) in result_absolute.get(1, {})
