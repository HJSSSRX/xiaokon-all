"""Inspect raw YAML to diagnose encoding state of findings."""
import yaml, sys, io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

with open(r"E:\ffffff-JIANCAI\2026FIC团体赛\case\shared\findings.yaml", encoding="utf-8") as f:
    fs = yaml.safe_load(f) or []

print(f"total findings in yaml: {len(fs)}")

m_findings = [x for x in fs if str(x.get("id", "")).startswith("F-M")]
s_findings = [x for x in fs if str(x.get("id", "")).startswith("F-S")]
b_findings = [x for x in fs if str(x.get("id", "")).startswith("F-B")]
c_findings = [x for x in fs if str(x.get("id", "")).startswith("F-C")]

print(f"mobile: {len(m_findings)} | server: {len(s_findings)} | binary: {len(b_findings)} | computer: {len(c_findings)}")
print()

print("=" * 70)
print("mobile_analyst — encoding check")
print("=" * 70)
for x in m_findings:
    s = x.get("summary", "") or ""
    has_cjk = any("\u4e00" <= c <= "\u9fff" for c in s)
    has_q = s.startswith("?") or s.count("?") > 3
    flag = "OK_CJK" if has_cjk and not has_q else ("LOST" if has_q else "ASCII")
    print(f"  {x.get('id'):8s} [{flag:7s}] {s[:80]}")

print()
print("=" * 70)
print("server_analyst — encoding check (诊断 F-S006 起的乱码)")
print("=" * 70)
for x in s_findings:
    s = x.get("summary", "") or ""
    has_cjk = any("\u4e00" <= c <= "\u9fff" for c in s)
    has_q = s.startswith("?") or s.count("?") > 3
    flag = "OK_CJK" if has_cjk and not has_q else ("LOST" if has_q else "ASCII")
    print(f"  {x.get('id'):8s} [{flag:7s}] {s[:80]}")

print()
print("=" * 70)
print("Details 字段分布")
print("=" * 70)
for label, lst in [("mobile", m_findings), ("server", s_findings),
                   ("binary", b_findings), ("computer", c_findings)]:
    has_d = sum(1 for x in lst if x.get("details"))
    has_src = sum(1 for x in lst if x.get("source"))
    print(f"  {label}: {len(lst)} findings, has_details={has_d}, has_source={has_src}")
