"""Check answer schema fill rate."""
import yaml, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

with open(r"E:\ffffff-JIANCAI\2026FIC团体赛\case\shared\answers.yaml", encoding="utf-8") as f:
    d = yaml.safe_load(f) or {}

total_a = total_p = total_q = 0
for cat, items in d.items():
    has_a = sum(1 for a in items if a.get("analysis"))
    has_p = sum(1 for a in items if a.get("evidence_path"))
    print(f"  {cat:22s} {len(items):2d} 题  analysis={has_a:2d}/{len(items)}  ev_path={has_p:2d}/{len(items)}")
    total_a += has_a
    total_p += has_p
    total_q += len(items)
print(f"  {'合计':22s} {total_q:2d} 题  analysis={total_a:2d}/{total_q}  ev_path={total_p:2d}/{total_q}")
