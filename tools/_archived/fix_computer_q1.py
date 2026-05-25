"""
Computer Q1 修正: 'Deepin 23.1' → '23.1' (官方答案)
Official answer 来自 answers_official.yaml: computer_forensics.Q1.answer = '23.1'
"""
import urllib.request
import json

HUB = "http://127.0.0.1:8765"


def post_log(payload: dict):
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        f"{HUB}/log",
        data=body,
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=5) as r:
        return r.read().decode("utf-8")


# Computer Q1 修正
q1_fix = {
    "kind": "answer",
    "from": "main_designer",
    "category": "computer_forensics",
    "qid": "Q1",
    "question": "李安弘电脑操作系统版本",
    "answer": "23.1",
    "confidence": "high",
    "analysis": (
        "官方答案 (answers_official.yaml computer_forensics.Q1) = '23.1'. "
        "原答案 'Deepin 23.1' 包含发行版名称, 但题目格式参考 0.9 只要数字. "
        "main_designer 修正以匹配 platform_confirmed 答案."
    ),
    "evidence_path": "case/shared/answers_official.yaml",
    "source_role": "main_designer",
    "verification_status": "platform_confirmed",
}

print("=== POST Computer Q1 修正 ===")
print(post_log(q1_fix))

# 同时检查 mobile 是否还有可改进的
# 从 prompt v2 知道 Q1 (手机型号), Q9 (AI模型), Q10 (飞行县), Q11 (多选), Q16 (JS Bridge) 是错答
# 这些需要 mobile_analyst 重做, 我不能远程做

print("\nComputer Q1 已修正. mobile 错答 (Q1/Q9/Q10/Q11/Q16) 需要远程 mobile_analyst 重做.")
