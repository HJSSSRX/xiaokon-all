"""
Regression tests for collab_hub.py - uses an isolated temp case dir, no pollution.

Run:
  python tests/test_collab_hub.py
"""
import json
import shutil
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


def wait_ready(base, timeout=20):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            urllib.request.urlopen(f"{base}/ping", timeout=1).read()
            return True
        except Exception:
            time.sleep(0.1)
    return False


def main():
    # Setup isolated temp case dir
    tmp = Path(tempfile.mkdtemp(prefix="hub_test_"))
    (tmp / "shared").mkdir()
    port = free_port()
    base = f"http://127.0.0.1:{port}"

    # Launch hub in subprocess
    proc = subprocess.Popen(
        [sys.executable, str(HUB), "serve", str(tmp), "--port", str(port), "--bind", "127.0.0.1"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    try:
        if not wait_ready(base):
            print("[FAIL] Hub did not start within 5s")
            return 1

        results = []

        def t(name, expected, status, body):
            ok = status == expected
            mark = "OK" if ok else "FAIL"
            print(f"[{mark}] {name} -> {status}")
            if not ok:
                print(f"      body: {json.dumps(body, ensure_ascii=False)[:300]}")
            results.append(ok)
            return ok

        # Health
        t("GET /ping", 200, *call(base, "GET", "/ping"))

        # Findings
        s, b = call(base, "POST", "/findings",
                    {"from": "computer_analyst", "summary": "test1", "detail": "x"})
        t("POST /findings (C)", 201, s, b)
        assert b["id"] == "F-C001", f"expected F-C001, got {b['id']}"

        s, b = call(base, "POST", "/findings",
                    {"from": "mobile_analyst", "summary": "test2"})
        t("POST /findings (M)", 201, s, b)
        assert b["id"] == "F-M001"

        s, b = call(base, "GET", "/findings")
        t("GET /findings (all)", 200, s, b)
        assert len(b) == 2

        s, b = call(base, "GET", "/findings?from=computer_analyst")
        t("GET /findings?from=...", 200, s, b)
        assert len(b) == 1 and b[0]["from"] == "computer_analyst"

        s, b = call(base, "GET", "/findings/F-C001")
        t("GET /findings/F-C001", 200, s, b)

        s, b = call(base, "GET", "/findings/F-X999")
        t("GET /findings/F-X999 -> 404", 404, s, b)

        # Progress
        s, b = call(base, "POST", "/progress/computer_analyst",
                    {"status": "in_progress", "completed": ["Q1"]})
        t("POST /progress/computer_analyst", 200, s, b)

        s, b = call(base, "GET", "/progress")
        t("GET /progress", 200, s, b)
        assert "computer_analyst" in b

        # Answers
        s, b = call(base, "POST", "/answers",
                    {"category": "computer", "qid": "Q1", "answer": "Win10"})
        t("POST /answers Q1 (create)", 201, s, b)

        s, b = call(base, "POST", "/answers",
                    {"category": "computer", "qid": "Q1", "answer": "Win10 22H2"})
        t("POST /answers Q1 (update)", 200, s, b)

        s, b = call(base, "GET", "/answers/computer")
        t("GET /answers/computer", 200, s, b)
        assert len(b) == 1 and b[0]["answer"] == "Win10 22H2"

        # Questions
        s, b = call(base, "POST", "/questions",
                    {"from": "computer_analyst", "to": "server_analyst",
                     "question": "key path?"})
        t("POST /questions", 201, s, b)
        qid = b["id"]
        assert qid == "Q001"

        s, b = call(base, "POST", f"/questions/{qid}/reply", {"answer": "no"})
        t(f"POST /questions/{qid}/reply", 200, s, b)
        assert b["answer"] == "no"

        s, b = call(base, "GET", "/questions?to=server_analyst")
        t("GET /questions?to=server_analyst", 200, s, b)
        assert len(b) == 1

        # Session
        s, b = call(base, "POST", "/session/log",
                    {"decision": "test", "reason": "regression"})
        t("POST /session/log", 201, s, b)

        s, b = call(base, "POST", "/session/blocker",
                    {"from": "computer_analyst", "blocker": "TPM locked"})
        t("POST /session/blocker", 201, s, b)
        assert b["id"] == "B001"

        s, b = call(base, "POST", "/session/strategy",
                    {"current_phase": "test", "priorities": ["a", "b"]})
        t("POST /session/strategy", 200, s, b)

        s, b = call(base, "GET", "/session")
        t("GET /session (snapshot)", 200, s, b)
        assert "session_log" in b and "blockers" in b and "strategy" in b
        assert len(b["session_log"]) == 1
        assert len(b["blockers"]) == 1
        assert b["strategy"]["current_phase"] == "test"

        # Validation errors
        s, b = call(base, "POST", "/findings", {})
        t("POST /findings missing 'from' -> 400", 400, s, b)

        s, b = call(base, "POST", "/answers", {"qid": "Q1"})
        t("POST /answers missing 'category' -> 400", 400, s, b)

        s, b = call(base, "GET", "/nonexistent")
        t("GET /nonexistent -> 404", 404, s, b)

        # Files (whitelist)
        # Create a fake role_prompt file in temp case
        fake_prompt = tmp / "role_prompt_test.md"
        fake_prompt.write_text("hello", encoding="utf-8")
        s, b = call(base, "GET", "/files/role_prompt_test.md")
        t("GET /files/role_prompt_test.md (whitelisted)", 200, s, b)
        assert b == "hello"

        s, b = call(base, "GET", "/files/../etc/passwd")
        t("GET /files/../etc/passwd -> 403", 403, s, b)

        # Persistence: verify yaml files exist
        for f in ["findings.yaml", "progress.yaml", "answers.yaml",
                  "questions.yaml", "session_log.yaml", "blockers.yaml", "strategy.yaml"]:
            assert (tmp / "shared" / f).exists(), f"{f} not persisted"
        print("[OK] All shared yaml files persisted")
        results.append(True)

        # Summary
        total = len(results)
        ok = sum(results)
        print()
        print(f"=== {ok}/{total} tests passed ===")
        return 0 if ok == total else 1

    finally:
        proc.terminate()
        try:
            proc.wait(timeout=2)
        except subprocess.TimeoutExpired:
            proc.kill()
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
