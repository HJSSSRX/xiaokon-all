"""Quick Hub state inspector - prints findings/answers/questions in readable form."""
import urllib.request, json, sys, io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

HUB = "http://127.0.0.1:8765"


def get(path):
    return json.loads(urllib.request.urlopen(f"{HUB}{path}").read())


# ─── findings by role ───
print("=" * 70)
print("FINDINGS BY ROLE")
print("=" * 70)
for role in ["computer_analyst", "mobile_analyst", "server_analyst", "binary_analyst"]:
    findings = get(f"/findings?from={role}")
    print(f"\n--- {role}: {len(findings)} findings ---")
    for f in findings:
        print(f"\n[{f.get('id')}] {f.get('time','')[:19]} | conf={f.get('confidence','')}")
        print(f"  summary: {f.get('summary','')[:120]}")
        if f.get("details"):
            details = f.get("details", "")
            print(f"  details: {details[:200]}{'...' if len(details) > 200 else ''}")
        if f.get("source"):
            print(f"  source: {f.get('source','')}")
        if f.get("related_to"):
            print(f"  related: {f.get('related_to','')}")

# ─── answers schema check ───
print("\n" + "=" * 70)
print("ANSWERS SCHEMA CHECK (which need backfill)")
print("=" * 70)
ans = get("/answers")
for cat in ["mobile_forensics", "binary_forensics", "server_forensics", "internet_forensics", "computer_forensics"]:
    items = ans.get(cat, [])
    print(f"\n--- {cat}: {len(items)} 条 ---")
    for a in items:
        has_analysis = bool(a.get("analysis"))
        has_evpath = bool(a.get("evidence_path"))
        vs = a.get("verification_status", "MISSING")
        print(f"  {a.get('qid')}: ans={a.get('answer','')[:40]:40s} | analysis={'Y' if has_analysis else 'N'} | ev_path={'Y' if has_evpath else 'N'} | v={vs}")

# ─── questions ───
print("\n" + "=" * 70)
print("UNANSWERED QUESTIONS")
print("=" * 70)
qs = get("/questions")
for q in qs:
    if not q.get("answer"):
        print(f"\n[Q{q.get('id')}] {q.get('time','')[:19]} {q.get('from')} -> {q.get('to')}")
        print(f"  Q: {q.get('question','')}")
