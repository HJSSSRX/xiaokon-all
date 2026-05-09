"""
collab_hub v0.4 新端点集成测试: /needs, /heartbeat, /answers/{cat}/{qid}/lock|unlock

Run:
  python3 tests/test_hub_v04_endpoints.py
"""
import json
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HUB = ROOT / "tools" / "collab_hub.py"


def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def call(base, method, path, body=None):
    url = f"{base}{path}"
    data = json.dumps(body).encode("utf-8") if body else None
    headers = {"Content-Type": "application/json"} if body else {}
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            ct = r.headers.get("Content-Type", "")
            raw = r.read().decode("utf-8")
            return r.status, json.loads(raw) if ct.startswith("application/json") else raw
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode("utf-8"))


def wait_ready(base, timeout=5):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            urllib.request.urlopen(f"{base}/ping", timeout=1).read()
            return True
        except Exception:
            time.sleep(0.1)
    return False


def main():
    tmp = Path(tempfile.mkdtemp(prefix="hub_v04_test_"))
    (tmp / "shared").mkdir()
    port = free_port()
    base = f"http://127.0.0.1:{port}"

    proc = subprocess.Popen(
        [sys.executable, str(HUB), "serve", str(tmp), "--port", str(port), "--bind", "127.0.0.1"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    try:
        if not wait_ready(base):
            print("[FAIL] Hub did not start within 5s")
            return 1

        results = []

        def t(name, expected, status, body, extra_check=None):
            ok = status == expected
            if ok and extra_check:
                ok = extra_check(body)
            mark = "OK" if ok else "FAIL"
            print(f"[{mark}] {name} -> {status}")
            if not ok:
                print(f"      body: {json.dumps(body, ensure_ascii=False)[:300]}")
            results.append(ok)

        # ─── /needs ───
        print("\n=== /needs (跨检材求助队列) ===")

        # POST /needs
        s, b = call(base, "POST", "/needs", {
            "from": "computer_analyst",
            "item": "VC 容器密码 (16-32 ASCII)",
            "purpose": "解 C-Q8 勒索软件邮箱",
            "candidate_locations": ["mobile/笔记", "mobile/IM"],
            "candidate_providers": ["mobile_analyst"],
            "blocking_qids": ["C_Q8", "C_Q9", "C_Q10"],
        })
        t("POST /needs", 201, s, b,
          lambda b: b.get("id") == "N001" and b.get("status") == "open")

        # POST /log kind=need (高级 API)
        s, b = call(base, "POST", "/log", {
            "kind": "need",
            "from": "server_analyst",
            "item": "ngrok 子域名",
            "candidate_providers": ["mobile_analyst", "internet_analyst"],
        })
        t("POST /log kind=need", 201, s, b,
          lambda b: b.get("id") == "N002")

        # GET /needs
        s, b = call(base, "GET", "/needs")
        t("GET /needs (all)", 200, s, b,
          lambda b: isinstance(b, list) and len(b) == 2)

        # GET /needs?status=open
        s, b = call(base, "GET", "/needs?status=open")
        t("GET /needs?status=open", 200, s, b,
          lambda b: len(b) == 2 and all(n["status"] == "open" for n in b))

        # GET /needs?to=mobile_analyst (针对 mobile 的)
        s, b = call(base, "GET", "/needs?to=mobile_analyst")
        t("GET /needs?to=mobile_analyst", 200, s, b,
          lambda b: len(b) == 2)  # N001 直接, N002 含 mobile_analyst

        # GET /needs?to=binary_analyst (没人针对它, 但 N002 含 *)
        # 实际 N001/N002 都不含 binary_analyst, 所以应该 0
        s, b = call(base, "GET", "/needs?to=binary_analyst")
        t("GET /needs?to=binary_analyst (no match)", 200, s, b,
          lambda b: len(b) == 0)

        # GET /needs/{id}
        s, b = call(base, "GET", "/needs/N001")
        t("GET /needs/N001", 200, s, b,
          lambda b: b.get("item", "").startswith("VC"))

        # POST /needs/{id}/claim
        s, b = call(base, "POST", "/needs/N001/claim", {"by": "mobile_analyst"})
        t("POST /needs/N001/claim", 200, s, b,
          lambda b: b.get("status") == "claimed" and b.get("claimed_by") == "mobile_analyst")

        # 二次 claim 应当 409
        s, b = call(base, "POST", "/needs/N001/claim", {"by": "binary_analyst"})
        t("POST /needs/N001/claim 二次 -> 409", 409, s, b)

        # POST /needs/{id}/fulfill
        s, b = call(base, "POST", "/needs/N001/fulfill", {
            "by": "mobile_analyst",
            "value": "9ed2@99y8.com.cn",
            "evidence_path": ["mobile/笔记/我的密码本.txt:line3"],
        })
        t("POST /needs/N001/fulfill", 200, s, b,
          lambda b: b.get("status") == "fulfilled" and b.get("fulfilled_value") == "9ed2@99y8.com.cn")

        # POST /needs/{id}/abandon
        s, b = call(base, "POST", "/needs/N002/abandon", {"reason": "重复求助"})
        t("POST /needs/N002/abandon", 200, s, b,
          lambda b: b.get("status") == "abandoned")

        # 缺 item 应当 400
        s, b = call(base, "POST", "/needs", {"from": "x"})
        t("POST /needs 缺 item -> 400", 400, s, b)

        # ─── /heartbeat ───
        print("\n=== /heartbeat (探活) ===")

        # POST /heartbeat
        s, b = call(base, "POST", "/heartbeat", {
            "from": "computer_analyst",
            "current_task": "解 C-Q4",
        })
        t("POST /heartbeat", 200, s, b,
          lambda b: b.get("current_task") == "解 C-Q4")

        s, b = call(base, "POST", "/heartbeat", {
            "from": "server_analyst",
            "current_task": "查 maccms",
        })
        t("POST /heartbeat (second role)", 200, s, b)

        # GET /heartbeat
        s, b = call(base, "GET", "/heartbeat")
        t("GET /heartbeat (snapshot)", 200, s, b,
          lambda b: isinstance(b, dict)
                    and "computer_analyst" in b
                    and "server_analyst" in b
                    and b["computer_analyst"]["stale"] is False
                    and b["computer_analyst"]["age_seconds"] is not None
                    and b["computer_analyst"]["age_seconds"] < 5)

        # POST /heartbeat 缺 from -> 400
        s, b = call(base, "POST", "/heartbeat", {"current_task": "x"})
        t("POST /heartbeat 缺 from -> 400", 400, s, b)

        # ─── /answers/{cat}/{qid}/lock ───
        print("\n=== /answers 锁机制 ===")

        # POST 一个答案 (无锁, 应当成功)
        s, b = call(base, "POST", "/answers", {
            "category": "computer",
            "qid": "Q5",
            "answer": "9527",
            "source_role": "computer_analyst",
            "confidence": "self_verified_db",
        })
        t("POST /answers (no lock)", 201, s, b)

        # 第一次锁
        s, b = call(base, "POST", "/answers/computer/Q5/lock", {
            "by": "main_designer",
            "reason": "审核中",
        })
        t("POST /answers/computer/Q5/lock", 200, s, b,
          lambda b: b.get("by") == "main_designer")

        # 锁主自己 POST 应当成功
        s, b = call(base, "POST", "/answers", {
            "category": "computer",
            "qid": "Q5",
            "answer": "9527-corrected",
            "source_role": "main_designer",
            "confidence": "platform_confirmed",
        })
        t("POST /answers (locker self) -> 200", 200, s, b,
          lambda b: b.get("answer") == "9527-corrected")

        # 别人 POST 应当 409
        s, b = call(base, "POST", "/answers", {
            "category": "computer",
            "qid": "Q5",
            "answer": "wrong-answer",
            "source_role": "computer_analyst",
            "confidence": "single_source_high",
        })
        t("POST /answers (other role locked) -> 409", 409, s, b,
          lambda b: "locked" in str(b.get("error", "")).lower())

        # 别人不能 unlock (除非 force)
        s, b = call(base, "POST", "/answers/computer/Q5/unlock", {
            "by": "computer_analyst",
        })
        t("POST /unlock (other role, no force) -> 403", 403, s, b)

        # 锁主 unlock 成功
        s, b = call(base, "POST", "/answers/computer/Q5/unlock", {
            "by": "main_designer",
        })
        t("POST /unlock (locker self)", 200, s, b,
          lambda b: b.get("status") == "unlocked")

        # unlock 后别人可以 POST
        s, b = call(base, "POST", "/answers", {
            "category": "computer",
            "qid": "Q5",
            "answer": "after-unlock",
            "source_role": "computer_analyst",
            "confidence": "single_source_high",
        })
        t("POST /answers (after unlock) -> 200", 200, s, b)

        # force unlock
        s, b = call(base, "POST", "/answers/computer/Q5/lock", {"by": "X"})
        t("POST /lock (re-lock by X)", 200, s, b)
        s, b = call(base, "POST", "/answers/computer/Q5/unlock", {
            "by": "Y", "force": True,
        })
        t("POST /unlock force=true (other)", 200, s, b)

        # ─── confidence 5 级归一化 ───
        print("\n=== confidence 5 级归一化 ===")

        # 老 high → single_source_high
        s, b = call(base, "POST", "/answers", {
            "category": "computer",
            "qid": "Q6",
            "answer": "X",
            "confidence": "high",
        })
        t("POST /answers confidence=high → single_source_high", 201, s, b,
          lambda b: b.get("confidence") == "single_source_high"
                    and b.get("confidence_raw") == "high")

        # 老 medium → gui_observed
        s, b = call(base, "POST", "/answers", {
            "category": "computer",
            "qid": "Q7",
            "answer": "Y",
            "confidence": "medium",
        })
        t("POST /answers confidence=medium → gui_observed", 201, s, b,
          lambda b: b.get("confidence") == "gui_observed")

        # 5 级直传保留
        s, b = call(base, "POST", "/answers", {
            "category": "computer",
            "qid": "Q8",
            "answer": "Z",
            "confidence": "platform_confirmed",
        })
        t("POST /answers confidence=platform_confirmed (passthrough)", 201, s, b,
          lambda b: b.get("confidence") == "platform_confirmed")

        # 未知值 → placeholder (避免误评高)
        s, b = call(base, "POST", "/answers", {
            "category": "computer",
            "qid": "Q9",
            "answer": "?",
            "confidence": "garbage_value",
        })
        t("POST /answers confidence=garbage → placeholder", 201, s, b,
          lambda b: b.get("confidence") == "placeholder")

        # ─── Summary ───
        passed = sum(results)
        total = len(results)
        print()
        print("=" * 60)
        print(f"PASSED: {passed} / {total}")
        print("=" * 60)
        return 0 if passed == total else 1

    finally:
        proc.terminate()
        try:
            proc.wait(timeout=2)
        except subprocess.TimeoutExpired:
            proc.kill()
        import shutil
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
