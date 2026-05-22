"""把 mobile_analyst 状态从 done 重置为 in_progress
反映 5 题错答的真实情况
"""
from __future__ import annotations
import sys, io, json, urllib.request

if hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

HUB = "http://127.0.0.1:8765"

def post(path, data):
    body = json.dumps(data, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        f"{HUB}{path}", data=body,
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST")
    return urllib.request.urlopen(req, timeout=5).read().decode("utf-8")


# 重置 mobile_analyst 进度
mobile_progress = {
    "status": "in_progress",
    "current_task": "重做 5 题错答 (Q1机型/Q9 AI模型/Q10飞行县/Q11多选/Q16 JS Bridge)",
    "completed": [
        "Q2 ✅ 20260606",
        "Q3 ✅ 20260414",
        "Q4 ✅ wk_xxx.db",
        "Q5 ✅ 32位hex密码",
        "Q6 ✅ TN8v...nU1 钱包",
        "Q7 ✅ 26226f",
        "Q8 ✅ 5",
        "Q12 ✅ file:///android_asset/www/index.html",
        "Q13 ✅ Base64 (修正)",
        "Q14 ✅ user_collection",
        "Q15 ✅ TXqH... 钱包",
        "Q17 ✅ backup.sp-live88.xyz:8443",
    ],
    "pending": [
        "Q1 手机型号 (你答 RedmiNote7Pro, 平台不认; 试 REDMINOTE7PRO 或 Note7Pro)",
        "Q9 本地AI模型版本 (你答 Qwen3.5-0.8B, 错; 看 .gguf 文件名)",
        "Q10 飞行县 (你答 西安市未央区, 错; 重新分析 DJI flight log GPS)",
        "Q11 多选权限 (你答 A,B,D, 错; 试 ABDE)",
        "Q16 JS Bridge 方法 (你答 getContactsList, 错; 列多个方法)",
    ],
    "blocker": "",
    "updated": "2026-05-08 21:50:00",
}

print(post("/progress/mobile_analyst", mobile_progress))

# 同时更新 session log
post("/session/log", {
    "from": "main_designer",
    "type": "decision",
    "summary": "mobile 状态重置: done → in_progress (5 题需重做)",
    "detail": "DIDCTF 平台真实显示 12/17, 之前的 5 题答错。已下发 v2 mobile prompt。",
})

print("\nmobile 状态已重置为 in_progress")
