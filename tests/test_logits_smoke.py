"""Smoke test for tools.core.logits — standalone, no KB dependency."""
import sys
sys.path.insert(0, 'D:/ai')

from tools.logits import get_capture
import json
import os

cap = get_capture()
cap.enable()

# ── Record alloc x2 ──────────────────────────────
cap.record_alloc(
    sg_id='SG-001', timestamp='2026-05-23 16:00:00.000',
    complexity_score=0.42, mode='boost', reason='复杂度<阈值',
    dimension_scores={'level': 0.6, 'domain': 0.5, 'tools': 0.3},
    weights={'level': 2.5, 'domain': 2.0, 'tools': 1.5},
    raw_weighted_sum=3.1)
cap.record_alloc(
    sg_id='SG-002', timestamp='2026-05-23 16:00:01.000',
    complexity_score=0.78, mode='focused', reason='复杂度>=阈值',
    dimension_scores={'level': 0.9, 'domain': 0.7, 'tools': 0.8},
    weights={'level': 2.5, 'domain': 2.0, 'tools': 1.5},
    raw_weighted_sum=6.2)

# ── Record boost x2 ──────────────────────────────
cap.record_boost(
    sg_id='SG-001', success=True, method='model_inference',
    confidence='single_source_high', attempts=1, temperature=0.3,
    answer='flag{test123}', kb_hit_count=2)
cap.record_boost(
    sg_id='SG-002', success=False, method='escalated',
    confidence='placeholder', attempts=3, temperature=0.7,
    validation_errors=['bad format'], kb_hit_count=0)

# ── Record model call ────────────────────────────
cap.record_model_call(
    sg_id='SG-001', temperature=0.3, prompt_chars=500, output_chars=200,
    latency_ms=1200.5, model_backend='openai_compatible')

# ── Summary ──────────────────────────────────────
s = cap.summary()
assert s['total_allocations'] == 2, f"bad allocs: {s}"
assert s['total_boosts'] == 2, f"bad boosts: {s}"
assert s['total_model_calls'] == 1, f"bad calls: {s}"
assert s['boost_success_rate'] == 0.5, f"bad rate: {s}"
assert s['modes'] == {'boost': 1, 'focused': 1}, f"bad modes: {s}"
print(f'[OK] summary: alloc={s["total_allocations"]} boost={s["total_boosts"]} calls={s["total_model_calls"]}')
print(f'     rate={s["boost_success_rate"]} modes={s["modes"]} methods={s["methods"]}')

# ── JSON ─────────────────────────────────────────
os.makedirs('D:/ai/tests', exist_ok=True)
cap.write_json('D:/ai/tests/logits_smoke_test.json')
with open('D:/ai/tests/logits_smoke_test.json', encoding='utf-8') as f:
    data = json.load(f)
assert len(data['allocations']) == 2
assert len(data['boosts']) == 2
assert len(data['model_calls']) == 1
assert data['meta']['summary']['total_allocations'] == 2
print(f'[OK] JSON: {os.path.getsize("D:/ai/tests/logits_smoke_test.json")} bytes')

# ── JSONL ────────────────────────────────────────
cap.write_jsonl('D:/ai/tests/logits_smoke.jsonl')
with open('D:/ai/tests/logits_smoke.jsonl', encoding='utf-8') as f:
    lines = f.readlines()
assert len(lines) == 5, f"expected 5 lines, got {len(lines)}"
print(f'[OK] JSONL: {len(lines)} lines')

# ── Compact TSV ──────────────────────────────────
cap.write_compact_scores('D:/ai/tests/logits_smoke_scores.tsv')
with open('D:/ai/tests/logits_smoke_scores.tsv', encoding='utf-8') as f:
    tsv = f.read()
assert 'SG-001' in tsv and 'SG-002' in tsv
print(f'[OK] TSV: {len(tsv.splitlines())} lines')
for line in tsv.strip().split('\n'):
    print(f'     {line[:120]}')

# ── Clear ────────────────────────────────────────
cap.clear()
assert cap.summary()['total_allocations'] == 0
assert cap.enabled == True  # clear doesn't disable
print('[OK] clear')

# ── Disable (records are silently dropped) ───────
cap.disable()
cap.record_alloc(sg_id='SG-099', timestamp='', complexity_score=0.99,
                 mode='focused', reason='should be ignored',
                 dimension_scores={}, weights={}, raw_weighted_sum=9.9)
assert cap.summary()['total_allocations'] == 0
print('[OK] disable drops records')

print()
print('=== ALL 10 TESTS PASSED ===')
