"""把 questions_meta.yaml 和 answers_official.yaml 推送到 Hub
让 dashboard 显示完整的题目矩阵 + 已确认答案
"""

from __future__ import annotations
import sys, io, json, urllib.request, pathlib, yaml

if hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

HUB = "http://127.0.0.1:8765"
ROOT = pathlib.Path(r"E:\ffffff-JIANCAI\2026FIC团体赛\case\shared")

meta = yaml.safe_load((ROOT / "questions_meta.yaml").read_text(encoding="utf-8"))
official = yaml.safe_load((ROOT / "answers_official.yaml").read_text(encoding="utf-8"))


def post(path, data):
    body = json.dumps(data, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        f"{HUB}{path}", data=body,
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST")
    try:
        return urllib.request.urlopen(req, timeout=5).read().decode("utf-8")
    except Exception as e:
        return f"ERR: {e}"


# 1. POST 题目元数据
total_q = 0
for cat, qs in meta.items():
    for qid, q in qs.items():
        data = {
            "qid": f"{cat}_{qid}",
            "category": cat,
            "qtype": q["qtype"],
            "score": q["score"],
            "question": q["question"],
            "format_hint": q["format_hint"],
            "options": q.get("options", []),
            "from": "main_designer",
        }
        r = post("/questions", data)
        total_q += 1

print(f"已 POST {total_q} 道题目到 Hub")

# 2. POST 已确认的官方答案（标记 platform_confirmed）
total_a = 0
for cat, qs in official.items():
    for qid, ans in qs.items():
        data = {
            "category": cat,
            "qid": qid,
            "answer": ans["answer"],
            "analysis": "DIDCTF 平台已确认正确答案",
            "evidence_path": "shared/answers_official.yaml",
            "source_role": "main_designer",
            "confidence": "high",
            "verification_status": "platform_confirmed",
        }
        r = post("/answers", data)
        total_a += 1

print(f"已 POST {total_a} 个官方答案到 Hub")

# 3. POST 一条 session_log 摘要
post("/session/log", {
    "from": "main_designer",
    "type": "milestone",
    "summary": f"题目导入完成: 52 题 / 22 已确认 / 26 错答 / 4 未答",
    "detail": "见 case/shared/diff_report.md。下一步: 三角色基于 todo.yaml 续战。挂载密码已知: FIC-{e404d6e66586e9460c23755afab5a872bcf78ab4}",
})

# 4. 测试 Hub
import urllib.request
r = urllib.request.urlopen(f"{HUB}/ping", timeout=3).read().decode("utf-8")
print(f"\nHub ping: {r}")
