"""diff_answers.py — 对比 answers.yaml (我们答的) vs answers_official.yaml (平台标准答案)

输出哪些题答错了 (我们答了但平台没显示标准答案 = 错)
输出哪些题已确认 (平台显示了标准答案)
输出哪些题还没答 (我们没答, 平台也没显示)
"""

from __future__ import annotations
import sys, io, pathlib, yaml

if hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

# 同时写文件
_OUT_FILE = pathlib.Path(r"E:\ffffff-JIANCAI\2026FIC团体赛\case\shared\diff_report.md")
_lines = []
def _print(*args):
    s = " ".join(str(a) for a in args)
    print(s)
    _lines.append(s)

ROOT = pathlib.Path(r"E:\ffffff-JIANCAI\2026FIC团体赛\case\shared")

ours = yaml.safe_load((ROOT / "answers.yaml").read_text(encoding="utf-8")) or {}
official = yaml.safe_load((ROOT / "answers_official.yaml").read_text(encoding="utf-8")) or {}
meta = yaml.safe_load((ROOT / "questions_meta.yaml").read_text(encoding="utf-8")) or {}

_print("=" * 80)
_print("答案对比报告")
_print("=" * 80)

# 整合
total_ok, total_wrong, total_unanswered = 0, 0, 0
all_categories = set(meta.keys())

for cat in all_categories:
    cat_meta = meta.get(cat, {})
    cat_ours_raw = ours.get(cat, [])
    cat_official = official.get(cat, {})

    # answers.yaml 是 list[dict], 转成 dict[qid, dict] 方便查
    cat_ours = {}
    if isinstance(cat_ours_raw, list):
        for item in cat_ours_raw:
            if isinstance(item, dict) and "qid" in item:
                cat_ours[item["qid"]] = item
    elif isinstance(cat_ours_raw, dict):
        cat_ours = cat_ours_raw

    _print(f"\n## {cat}")

    for qid, q_meta in cat_meta.items():
        our = cat_ours.get(qid)
        off = cat_official.get(qid)

        # 我们答的答案
        our_ans = None
        if isinstance(our, dict):
            our_ans = our.get("answer")

        off_ans = off.get("answer") if off else None

        if off_ans is not None:
            status = "OK"
            total_ok += 1
            if our_ans and our_ans != off_ans:
                status = f"OK(updated: '{our_ans}' -> '{off_ans}')"
        elif our_ans is not None:
            status = f"WRONG (我们答: '{our_ans}')"
            total_wrong += 1
        else:
            status = "TODO (未答)"
            total_unanswered += 1

        # 显示
        q_short = q_meta["question"][:50] + ("..." if len(q_meta["question"]) > 50 else "")
        _print(f"  {qid:5s} [{q_meta['qtype']}] {q_short}")
        _print(f"        --> {status}")
        if off_ans:
            _print(f"        平台答案: {off_ans}")

_print("\n" + "=" * 80)
_print(f"总结: {total_ok} 已确认 / {total_wrong} 错答需重做 / {total_unanswered} 未答")
_print("=" * 80)
_OUT_FILE.write_text("\n".join(_lines), encoding="utf-8")
print(f"\n报告已写入: {_OUT_FILE}")
