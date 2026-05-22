"""
_test_suite.py — 一次性验证脚本 (用完可删)
测试: C2 parse_questions / C3 answer_format_lint / 知识库检索
"""
import io, sys, pathlib, json, tempfile

# 锁定当前 stdout，防止被子模块的 TextIOWrapper 重包装后丢失
_stdout = sys.stdout

ROOT = pathlib.Path(__file__).parent.parent

PASS = "[PASS]"
FAIL = "[FAIL]"

results = []

def check(name, ok, detail=""):
    tag = PASS if ok else FAIL
    results.append((tag, name, detail))
    msg = f"{tag} {name}" + (f"\n       {detail}" if detail else "")
    _stdout.write(msg + "\n")
    _stdout.flush()

# ══════════════════════════════════════════════════════════════
# 1. 知识库
# ══════════════════════════════════════════════════════════════
_stdout.write("\n=== 1. 知识库 ===\n"); _stdout.flush()
solved = list(ROOT.glob("knowledge/solved/**/*.yaml"))
check("solved YAML 数量 >= 50", len(solved) >= 50, f"实际: {len(solved)} 条")

skills = list(ROOT.glob("knowledge/skills/**/*.md"))
check("skills MD 数量 >= 10", len(skills) >= 10, f"实际: {len(skills)} 个")

for role in ["binary", "server", "computer", "mobile"]:
    p = ROOT / "knowledge" / "skills" / role / "quick_reference.md"
    check(f"skills/{role}/quick_reference.md 存在", p.exists())

# ══════════════════════════════════════════════════════════════
# 2. C2 — parse_questions
# ══════════════════════════════════════════════════════════════
_stdout.write("\n=== 2. C2 parse_questions ===\n"); _stdout.flush()
sys.path.insert(0, str(ROOT / "tools"))
try:
    from tools.competition.parse_questions import parse_markdown, group_by_cat, gen_dashboard_questions_js, gen_questions_meta_yaml

    sample = """
### 手机取证-1（简答，10分）
该手机的型号是什么？
> 参考格式: HUAWEIP90

### 手机取证-2（简答，10分）
该手机的 IMEI 是多少？
> 参考格式: 861234567890123

### 二进制取证-1（简答，10分）
SampleVC.exe 的 MD5 是多少？
> 参考格式: c4ca4238a0b923820dcc509a6f75849b

### 二进制取证-2（简答，10分）
该程序的编译日期是？
> 参考格式: 2025-06-06
"""
    items = parse_markdown(sample)
    check("解析 4 题", len(items) == 4, f"实际: {len(items)} 题")

    cats = set(it["cat"] for it in items)
    check("识别 mobile + binary 两类", "mobile_forensics" in cats and "binary_forensics" in cats,
          f"识别到: {cats}")

    fmts = [it["ref_format"] for it in items]
    check("全部提取到参考格式", all(fmts), f"格式列表: {fmts}")

    grouped = group_by_cat(items)
    js = gen_dashboard_questions_js(grouped)
    check("JS 代码块含 mobile_forensics", "mobile_forensics" in js)
    check("JS 代码块含 binary_forensics", "binary_forensics" in js)

    yaml_out = gen_questions_meta_yaml(grouped)
    check("YAML 输出非空", bool(yaml_out.strip()))

    # 测试 JSON 格式输入
    from tools.competition.parse_questions import parse_json
    json_data = {"data": [
        {"id": 1, "title": "服务器操作系统版本", "answer_format": "12.5", "score": 10, "category": "服务器取证"},
        {"id": 2, "title": "硬盘 UUID", "answer_format": "a1b2c3d4-e5f6", "score": 10, "category": "服务器取证"},
    ]}
    j_items = parse_json(json_data)
    check("JSON 解析 2 题", len(j_items) == 2, f"实际: {len(j_items)}")
    check("JSON 识别 server 分类", j_items[0]["cat"] == "server_forensics",
          f"实际: {j_items[0]['cat']}")

except Exception as e:
    check("C2 import/运行", False, str(e))

# ══════════════════════════════════════════════════════════════
# 3. C3 — answer_format_lint
# ══════════════════════════════════════════════════════════════
_stdout.write("\n=== 3. C3 answer_format_lint ===\n"); _stdout.flush()
try:
    from answer_format_lint import check_answer, infer_rule, FORMAT_RULES

    check("FORMAT_RULES 规则数 >= 20", len(FORMAT_RULES) >= 20, f"实际: {len(FORMAT_RULES)} 条")

    # 正确答案
    tests_ok = [
        ("HUAWEIP90",                          None),   # 无规则 → 不报错
        ("c4ca4238a0b923820dcc509a6f75849b",   "md5"),
        ("2025-06-06",                          "date_iso"),
        ("192.168.1.1",                         "ip"),
        ("443",                                 "port"),
        ("12.5",                                "version_xy"),
        ("20260101",                            "date_ymd8"),
    ]
    for val, rule in tests_ok:
        ok, reason = check_answer(val, rule) if rule else (True, "")
        check(f"OK  {val[:30]:30s} rule={rule}", ok, reason)

    # 错误答案
    tests_fail = [
        ("not-a-md5-hash",  "md5"),
        ("999.999.999.999", "ip"),
        ("hello",           "date_iso"),
    ]
    for val, rule in tests_fail:
        ok, reason = check_answer(val, rule)
        check(f"ERR {val:30s} rule={rule}", not ok, reason)

    # infer_rule 推断
    cases = [
        ("c4ca4238a0b923820dcc509a6f75849b", "md5"),
        ("192.168.1.1",                       "ip"),
        ("2025-06-06",                         "date_iso"),
        ("20260101",                           "date_ymd8"),
        ("v7.5.2",                             "version_vxyz"),
        ("http://abc.com/path",                "url_http"),
    ]
    for ref, expected in cases:
        got = infer_rule(ref)
        check(f"infer_rule({ref[:20]}) = {expected}", got == expected, f"实际: {got}")

    # 无 meta 时 lint 不崩溃
    from answer_format_lint import lint_answers
    results_lint = lint_answers(str(ROOT.parent / "ffffff-JIANCAI" / "2026FIC团体赛" / "case"))
    check("lint_answers 不崩溃", True, f"返回 {len(results_lint)} 条记录")

except Exception as e:
    check("C3 import/运行", False, str(e))

# ══════════════════════════════════════════════════════════════
# 4. v4 prompt 关键约束检查
# ══════════════════════════════════════════════════════════════
_stdout.write("\n=== 4. v4 Prompt 约束检查 ===\n"); _stdout.flush()
case_dir = pathlib.Path(r"E:\ffffff-JIANCAI\2026FIC团体赛\case")
for role, keyword in [
    ("computer", "disk_map"),
    ("server",   "architecture_map"),
    ("binary",   "log_answer"),
    ("mobile",   "log_answer"),
]:
    f = case_dir / f"role_prompt_{role}_v4.md"
    if f.exists():
        text = f.read_text(encoding="utf-8")
        check(f"{role}_v4 含 '{keyword}'", keyword in text)
    else:
        check(f"{role}_v4 文件存在", False, str(f))

# ══════════════════════════════════════════════════════════════
# 汇总
# ══════════════════════════════════════════════════════════════
_stdout.write("\n" + "=" * 60 + "\n"); _stdout.flush()
passed = sum(1 for r in results if r[0] == PASS)
failed = sum(1 for r in results if r[0] == FAIL)
_stdout.write(f"总计: {passed} PASS  {failed} FAIL  ({passed}/{passed+failed})\n"); _stdout.flush()
if failed:
    _stdout.write("\n失败项:\n")
    for tag, name, detail in results:
        if tag == FAIL:
            _stdout.write(f"  {name}: {detail}\n")
    _stdout.flush()
