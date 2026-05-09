#!/usr/bin/env python3
"""
collab_hub.py - Lightweight HTTP Hub for multi-machine AI agent collaboration.

Architecture:
  Main host runs Hub. Remote IDE Agents (Windsurf/Cursor/Claude) interact via curl.
  Stateless server; all state persists in <case_dir>/shared/*.yaml.

API:
  GET  /ping
  GET  /findings              (?from=role)
  GET  /findings/{id}
  POST /findings              {from, type, summary, detail, related_to}
  GET  /progress
  POST /progress/{role}       {status, current_task, completed, pending, blocker}
  GET  /answers               (or /answers/{category})
  POST /answers               {category, qid, question, answer, confidence, source_role, evidence}
  GET  /questions             (?to=role)
  POST /questions             {from, to, question}
  POST /questions/{id}/reply  {answer}
  GET  /session               -> {session_log, blockers, strategy}
  POST /session/log           {decision, reason, related_findings}
  POST /session/blocker       {from, blocker, needs, routed_to}
  POST /session/strategy      {current_phase, priorities, deferred, notes}
  GET  /files/{name}          (whitelisted: role_prompt_*.md, shared/*.yaml)

Usage:
  python collab_hub.py serve <case_dir> [--port 8765] [--bind 0.0.0.0]

Client examples (curl):
  curl http://192.168.1.10:8765/ping
  curl -X POST http://192.168.1.10:8765/findings \
       -H "Content-Type: application/json" \
       -d '{"from":"computer_analyst","summary":"OS=Win10","detail":"reg key X"}'
"""
import argparse
import datetime
import http.server
import json
import re
import socket
import sys
import threading
from pathlib import Path
from urllib.parse import parse_qs

try:
    import yaml
except ImportError:
    import subprocess
    subprocess.run([sys.executable, "-m", "pip", "install", "pyyaml", "-q"], check=False)
    import yaml


# ─── Constants ───

ROLE_PREFIX = {
    "computer_analyst": "C",
    "mobile_analyst": "M",
    "server_analyst": "S",
    "binary_analyst": "B",
    "main_designer": "D",
}

# A 方案: role -> answer category 自动推断 (用于 /log 智能分流)
ROLE_TO_CATEGORY = {
    "computer_analyst": "computer_forensics",
    "mobile_analyst": "mobile_forensics",
    "server_analyst": "server_forensics",
    "binary_analyst": "binary_forensics",
    "internet_analyst": "internet_forensics",
}

# Whitelist for /files/ to prevent path traversal
# Allows: role_prompt_*.md, shared/*.yaml, and any TOP-LEVEL ALL-CAPS .md docs
# (deployment guides, handoff notes, etc.) but NOT arbitrary user files.
FILE_WHITELIST = re.compile(
    r"^(role_prompt_\w+\.md|shared/[\w_-]+\.(yaml|md|jsonl)|[A-Z][A-Z0-9_]+\.md|README\.md|import_[\w_]+\.py)$"
)

_lock = threading.Lock()
_hub_started_at = now_str() if False else None  # placeholder, set in cmd_serve


# ─── State helpers ───

def now_str():
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def shared_path(case_dir, name):
    return Path(case_dir) / "shared" / name


def load_yaml(path, default=None):
    if not path.exists():
        return default if default is not None else []
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if data is None:
        return default if default is not None else []
    return data


def save_yaml(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        yaml.dump(data, f, allow_unicode=True, default_flow_style=False, sort_keys=False)


def _next_seq_id(items, prefix, key="id"):
    pat = re.compile(rf"^{prefix}(\d+)$")
    nums = []
    for it in items:
        if isinstance(it, dict):
            m = pat.match(str(it.get(key, "")))
            if m:
                nums.append(int(m.group(1)))
    return f"{prefix}{max(nums, default=0) + 1:03d}"


def next_finding_id(findings, role):
    p = ROLE_PREFIX.get(role, "X")
    return _next_seq_id(findings, f"F-{p}")


def next_question_id(questions):
    return _next_seq_id(questions, "Q")


def next_blocker_id(blockers):
    return _next_seq_id(blockers, "B")


def next_need_id(needs):
    return _next_seq_id(needs, "N")


# /needs allowed values
NEED_STATUS = ("open", "claimed", "fulfilled", "abandoned")
NEED_CONFIDENCE_5 = (
    "platform_confirmed",   # 10 分稳: 平台已确认
    "self_verified_db",      # 8-9 分: 直接 SQL/文件读到
    "cross_source_high",     # 6-7 分: 多源交叉验证
    "single_source_high",    # 3-5 分: 单源, 无验证
    "gui_observed",          # 2-3 分: 仅看 GUI, 未翻底层
    "placeholder",           # 0-2 分: 占位, 未做
)
# 兼容旧 3 级
NEED_CONFIDENCE_LEGACY = ("high", "medium", "low")


def normalize_confidence(c: str) -> str:
    """老 3 级 → 5 级映射. 未知值返回 'placeholder' 避免误评高."""
    c = (c or "").strip().lower()
    if c in NEED_CONFIDENCE_5:
        return c
    legacy_map = {
        "high": "single_source_high",   # 老 high 实际只是单源高信心
        "medium": "gui_observed",
        "low": "placeholder",
    }
    return legacy_map.get(c, "placeholder")


# ─── HTTP Handler ───

class Handler(http.server.BaseHTTPRequestHandler):
    case_dir = None

    def log_message(self, fmt, *args):
        ts = datetime.datetime.now().strftime("%H:%M:%S")
        sys.stderr.write(f"[{ts}] {self.address_string()} {fmt % args}\n")

    def _send(self, status, body=None, content_type="application/json; charset=utf-8"):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        if body is not None:
            if isinstance(body, (dict, list)):
                payload = json.dumps(body, ensure_ascii=False, indent=2).encode("utf-8")
            elif isinstance(body, bytes):
                payload = body
            else:
                payload = str(body).encode("utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
        else:
            self.send_header("Content-Length", "0")
            self.end_headers()

    def _err(self, status, msg):
        self._send(status, {"error": msg, "code": status})

    def _read_json(self):
        length = int(self.headers.get("Content-Length", 0))
        if length == 0:
            return {}
        try:
            raw = self.rfile.read(length).decode("utf-8")
            return json.loads(raw)
        except Exception as e:
            return None

    def _split_path(self):
        if "?" in self.path:
            path, qs = self.path.split("?", 1)
            query = {k: v[0] for k, v in parse_qs(qs).items()}
        else:
            path, query = self.path, {}
        path = path.rstrip("/") or "/"
        return path, query

    def do_OPTIONS(self):
        self._send(204)

    def do_GET(self):
        path, query = self._split_path()

        # Health
        if path == "/ping":
            return self._send(200, {
                "status": "ok",
                "version": "v3.1",
                "time": now_str(),
                "started_at": _hub_started_at,
            })

        # Dashboard (live web UI) - no-cache headers to defeat browser caching
        if path in ("/", "/dashboard"):
            dash_path = Path(__file__).resolve().parent / "dashboard.html"
            if dash_path.exists():
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
                self.send_header("Pragma", "no-cache")
                self.send_header("Expires", "0")
                self.send_header("Access-Control-Allow-Origin", "*")
                payload = dash_path.read_bytes()
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)
                return
            return self._err(404, "dashboard.html not found in tools/")

        # Findings
        if path == "/findings":
            findings = load_yaml(shared_path(self.case_dir, "findings.yaml"), [])
            if "from" in query:
                findings = [f for f in findings if isinstance(f, dict) and f.get("from") == query["from"]]
            return self._send(200, findings)

        m = re.match(r"^/findings/(F-[A-Z]\d+)$", path)
        if m:
            findings = load_yaml(shared_path(self.case_dir, "findings.yaml"), [])
            for f in findings:
                if isinstance(f, dict) and f.get("id") == m.group(1):
                    return self._send(200, f)
            return self._err(404, f"Finding {m.group(1)} not found")

        # Progress
        if path == "/progress":
            return self._send(200, load_yaml(shared_path(self.case_dir, "progress.yaml"), {}))

        # Answers
        if path == "/answers":
            return self._send(200, load_yaml(shared_path(self.case_dir, "answers.yaml"), {}))

        m = re.match(r"^/answers/(\w+)$", path)
        if m:
            answers = load_yaml(shared_path(self.case_dir, "answers.yaml"), {})
            return self._send(200, answers.get(m.group(1), []) if isinstance(answers, dict) else [])

        # Questions
        if path == "/questions":
            questions = load_yaml(shared_path(self.case_dir, "questions.yaml"), [])
            if "to" in query:
                questions = [q for q in questions if isinstance(q, dict) and q.get("to") == query["to"]]
            if "from" in query:
                questions = [q for q in questions if isinstance(q, dict) and q.get("from") == query["from"]]
            return self._send(200, questions)

        # Session (recovery snapshot)
        if path == "/session":
            return self._send(200, {
                "session_log": load_yaml(shared_path(self.case_dir, "session_log.yaml"), []),
                "blockers": load_yaml(shared_path(self.case_dir, "blockers.yaml"), []),
                "strategy": load_yaml(shared_path(self.case_dir, "strategy.yaml"), {}),
            })

        # /needs - 跨检材求助队列 (修复 #1)
        # 用法:
        #   GET  /needs                  -> 全部 (含已完成)
        #   GET  /needs?status=open      -> 仅未满足
        #   GET  /needs?to=mobile_analyst -> 别人对 mobile 的请求
        #   GET  /needs?from=computer_analyst -> computer 发出的请求
        if path == "/needs":
            needs = load_yaml(shared_path(self.case_dir, "needs.yaml"), [])
            if "status" in query:
                needs = [n for n in needs if isinstance(n, dict) and n.get("status") == query["status"]]
            if "to" in query:
                # candidate_providers 含 to 的 / 或 to == "*" (任何角色)
                tgt = query["to"]
                needs = [n for n in needs if isinstance(n, dict) and (
                    tgt in (n.get("candidate_providers") or []) or
                    "*" in (n.get("candidate_providers") or [])
                )]
            if "from" in query:
                needs = [n for n in needs if isinstance(n, dict) and n.get("from") == query["from"]]
            return self._send(200, needs)

        m = re.match(r"^/needs/(N\d+)$", path)
        if m:
            needs = load_yaml(shared_path(self.case_dir, "needs.yaml"), [])
            for n in needs:
                if isinstance(n, dict) and n.get("id") == m.group(1):
                    return self._send(200, n)
            return self._err(404, f"Need {m.group(1)} not found")

        # /heartbeat - 角色探活 (修复 REMOTE-FAIL-06 静默失败)
        # GET /heartbeat - 列出所有角色心跳 + 是否过期 (>5 分钟无心跳 = stale)
        if path == "/heartbeat":
            beats = load_yaml(shared_path(self.case_dir, "heartbeat.yaml"), {})
            if not isinstance(beats, dict):
                beats = {}
            now = datetime.datetime.now()
            result = {}
            for role, info in beats.items():
                last = info.get("last") if isinstance(info, dict) else None
                stale = True
                age_seconds = None
                if last:
                    try:
                        last_dt = datetime.datetime.strptime(last, "%Y-%m-%d %H:%M:%S")
                        age_seconds = int((now - last_dt).total_seconds())
                        stale = age_seconds > 300  # 5 分钟阈值
                    except Exception:
                        pass
                result[role] = {
                    "last": last,
                    "age_seconds": age_seconds,
                    "stale": stale,
                    "current_task": info.get("current_task", "") if isinstance(info, dict) else "",
                }
            return self._send(200, result)

        # Files (whitelisted)
        m = re.match(r"^/files/(.+)$", path)
        if m:
            fname = m.group(1)
            if not FILE_WHITELIST.match(fname):
                return self._err(403, f"File '{fname}' not in whitelist")
            fpath = Path(self.case_dir) / fname
            if not fpath.exists():
                return self._err(404, f"File '{fname}' not found")
            return self._send(200, fpath.read_bytes(), content_type="text/plain; charset=utf-8")

        return self._err(404, f"No route for GET {path}")

    def do_POST(self):
        path, _ = self._split_path()
        body = self._read_json()
        if body is None:
            return self._err(400, "Invalid JSON body")

        with _lock:
            return self._dispatch_post(path, body)

    def _dispatch_post(self, path, body):
        # ─── A 方案: POST /log — 极简协作端点 ───
        # 远程角色只用一个端点。Hub 根据 kind 自动分流。
        # Body: {kind: answer|finding|blocker|question|progress, from: <role>, ...}
        if path == "/log":
            kind = (body.get("kind") or "").strip().lower()
            role = (body.get("from") or "").strip()
            if not kind or not role:
                return self._err(400, "Missing 'kind' or 'from' field")

            if kind == "answer":
                # 自动从 role 推断 category（除非显式指定）
                category = body.get("category") or ROLE_TO_CATEGORY.get(role, "")
                if not category:
                    return self._err(400, f"Cannot infer category from role '{role}'; pass 'category' explicitly")
                forwarded = {
                    "category": category,
                    "qid": body.get("qid", ""),
                    "question": body.get("question", ""),
                    "answer": body.get("answer", ""),
                    "confidence": body.get("confidence", "medium"),
                    "source_role": role,
                    "evidence": body.get("evidence", ""),
                    "analysis": body.get("analysis", ""),
                    "evidence_path": body.get("evidence_path", []),
                }
                return self._dispatch_post("/answers", forwarded)

            if kind == "finding":
                forwarded = {
                    "from": role,
                    "type": body.get("type", "evidence"),
                    "summary": body.get("summary", ""),
                    "detail": body.get("detail", ""),
                    "related_to": body.get("related_to", []),
                }
                return self._dispatch_post("/findings", forwarded)

            if kind == "blocker":
                forwarded = {
                    "from": role,
                    "blocker": body.get("blocker", ""),
                    "needs": body.get("needs", ""),
                    "routed_to": body.get("routed_to", ""),
                }
                return self._dispatch_post("/session/blocker", forwarded)

            if kind == "question":
                forwarded = {
                    "from": role,
                    "to": body.get("to", "main_designer"),
                    "question": body.get("question", ""),
                    "context": body.get("context", ""),
                }
                return self._dispatch_post("/questions", forwarded)

            if kind == "progress":
                forwarded = {
                    "status": body.get("status", "in_progress"),
                    "current_task": body.get("current_task", ""),
                    "completed": body.get("completed", []),
                    "pending": body.get("pending", []),
                    "blocker": body.get("blocker", ""),
                }
                return self._dispatch_post(f"/progress/{role}", forwarded)

            # 修复 #1: kind=need 走 /needs (跨检材求助队列)
            if kind == "need":
                forwarded = {
                    "from": role,
                    "item": body.get("item", ""),
                    "purpose": body.get("purpose", ""),
                    "candidate_locations": body.get("candidate_locations", []),
                    "candidate_providers": body.get("candidate_providers", ["*"]),
                    "blocking_qids": body.get("blocking_qids", []),
                    "deadline_hours": body.get("deadline_hours"),
                }
                return self._dispatch_post("/needs", forwarded)

            return self._err(400, f"Unknown kind: '{kind}'. Valid: answer/finding/blocker/question/progress/need")

        # POST /findings
        if path == "/findings":
            role = body.get("from", "").strip()
            if not role:
                return self._err(400, "Missing 'from' field")
            fpath = shared_path(self.case_dir, "findings.yaml")
            findings = load_yaml(fpath, [])
            entry = {
                "id": next_finding_id(findings, role),
                "time": now_str(),
                "from": role,
                "type": body.get("type", "evidence"),
                "summary": body.get("summary", ""),
                "detail": body.get("detail", ""),
                "related_to": body.get("related_to", []),
            }
            findings.append(entry)
            save_yaml(fpath, findings)
            return self._send(201, entry)

        # POST /progress/{role}
        m = re.match(r"^/progress/(\w+)$", path)
        if m:
            role = m.group(1)
            fpath = shared_path(self.case_dir, "progress.yaml")
            progress = load_yaml(fpath, {})
            if not isinstance(progress, dict):
                progress = {}
            progress[role] = {
                "status": body.get("status", "idle"),
                "current_task": body.get("current_task", ""),
                "completed": body.get("completed", []),
                "pending": body.get("pending", []),
                "blocker": body.get("blocker", ""),
                "updated": now_str(),
            }
            save_yaml(fpath, progress)
            return self._send(200, progress[role])

        # POST /answers
        # Extended schema (v3.1): adds analysis / evidence_path / verification_status
        # Backward-compat: any field omitted falls back to "" or [] / "unverified"
        if path == "/answers":
            category = body.get("category", "").strip()
            if not category:
                return self._err(400, "Missing 'category' field")
            fpath = shared_path(self.case_dir, "answers.yaml")
            answers = load_yaml(fpath, {})
            if not isinstance(answers, dict):
                answers = {}
            answers.setdefault(category, [])

            # Preserve existing verification fields when re-POSTing same qid
            qid = body.get("qid", "")
            existing = None
            for a in answers[category]:
                if isinstance(a, dict) and a.get("qid") == qid and qid:
                    existing = a
                    break

            # 修复 REMOTE-FAIL-09: 锁检查 — 答案被别人锁了, 拒绝写入
            if qid:
                lock_path = shared_path(self.case_dir, "answer_locks.yaml")
                locks = load_yaml(lock_path, {})
                if isinstance(locks, dict):
                    lock_key = f"{category}/{qid}"
                    existing_lock = locks.get(lock_key)
                    if existing_lock and isinstance(existing_lock, dict):
                        try:
                            locked_at = datetime.datetime.strptime(
                                existing_lock.get("locked_at", ""), "%Y-%m-%d %H:%M:%S")
                            age = (datetime.datetime.now() - locked_at).total_seconds()
                            poster = body.get("source_role", "") or body.get("from", "")
                            # 锁未过期 + 不是锁主 → 拒绝
                            if age < 300 and existing_lock.get("by") != poster:
                                return self._err(409, {
                                    "error": f"Answer {lock_key} locked by {existing_lock.get('by')}",
                                    "locked_by": existing_lock.get("by"),
                                    "locked_at": existing_lock.get("locked_at"),
                                    "your_role": poster,
                                    "hint": "POST /answers/{cat}/{qid}/lock first or wait for expiry",
                                })
                        except Exception:
                            pass

            # Normalize evidence_path: accept str or list
            ev_path = body.get("evidence_path", [])
            if isinstance(ev_path, str):
                ev_path = [ev_path] if ev_path else []
            elif not isinstance(ev_path, list):
                ev_path = []

            # 修复 #4: 5 级 confidence 强制规范化 (老 high/medium/low → 5 级)
            raw_conf = body.get("confidence", "")
            normalized_conf = normalize_confidence(raw_conf)

            entry = {
                "qid": qid,
                "question": body.get("question", "") or (existing.get("question", "") if existing else ""),
                "answer": body.get("answer", ""),
                "confidence": normalized_conf,
                "confidence_raw": raw_conf,  # 保留原始值用于审计
                "source_role": body.get("source_role", ""),
                "evidence": body.get("evidence", ""),                  # finding ID
                "analysis": body.get("analysis", "") or (existing.get("analysis", "") if existing else ""),
                "evidence_path": ev_path or (existing.get("evidence_path", []) if existing else []),
                "verification_status": body.get("verification_status",
                    existing.get("verification_status", "unverified") if existing else "unverified"),
                "verified_by": existing.get("verified_by", "") if existing else "",
                "verified_at": existing.get("verified_at", "") if existing else "",
                "verify_note": existing.get("verify_note", "") if existing else "",
                "updated": now_str(),
            }
            updated = False
            for i, a in enumerate(answers[category]):
                if isinstance(a, dict) and a.get("qid") == entry["qid"] and entry["qid"]:
                    answers[category][i] = entry
                    updated = True
                    break
            if not updated:
                answers[category].append(entry)
            save_yaml(fpath, answers)
            return self._send(200 if updated else 201, entry)

        # POST /answers/{category}/{qid}/verify - flip verification status
        # body: {verification_status, verified_by, verify_note}
        m = re.match(r"^/answers/(\w+)/(\w+)/verify$", path)
        if m:
            category, qid = m.group(1), m.group(2)
            fpath = shared_path(self.case_dir, "answers.yaml")
            answers = load_yaml(fpath, {})
            if not isinstance(answers, dict) or category not in answers:
                return self._err(404, f"Category '{category}' not found")
            target = None
            for a in answers[category]:
                if isinstance(a, dict) and a.get("qid") == qid:
                    target = a
                    break
            if not target:
                return self._err(404, f"Answer {category}/{qid} not found")
            new_status = body.get("verification_status", "verified").strip()
            valid = ("unverified", "verified", "disputed", "failed")
            if new_status not in valid:
                return self._err(400, f"verification_status must be one of {valid}")
            target["verification_status"] = new_status
            target["verified_by"] = body.get("verified_by", "main_designer")
            target["verified_at"] = now_str()
            target["verify_note"] = body.get("verify_note", "")
            target["updated"] = now_str()
            save_yaml(fpath, answers)
            return self._send(200, target)

        # POST /questions
        if path == "/questions":
            fpath = shared_path(self.case_dir, "questions.yaml")
            questions = load_yaml(fpath, [])
            entry = {
                "id": next_question_id(questions),
                "time": now_str(),
                "from": body.get("from", ""),
                "to": body.get("to", ""),
                "question": body.get("question", ""),
                "answer": "",
                "answered_at": "",
            }
            questions.append(entry)
            save_yaml(fpath, questions)
            return self._send(201, entry)

        # POST /questions/{id}/reply
        m = re.match(r"^/questions/(Q\d+)/reply$", path)
        if m:
            qid = m.group(1)
            fpath = shared_path(self.case_dir, "questions.yaml")
            questions = load_yaml(fpath, [])
            for q in questions:
                if isinstance(q, dict) and q.get("id") == qid:
                    q["answer"] = body.get("answer", "")
                    q["answered_at"] = now_str()
                    save_yaml(fpath, questions)
                    return self._send(200, q)
            return self._err(404, f"Question {qid} not found")

        # POST /session/log
        if path == "/session/log":
            fpath = shared_path(self.case_dir, "session_log.yaml")
            log = load_yaml(fpath, [])
            entry = {
                "time": now_str(),
                "decision": body.get("decision", ""),
                "reason": body.get("reason", ""),
                "related_findings": body.get("related_findings", []),
            }
            log.append(entry)
            save_yaml(fpath, log)
            return self._send(201, entry)

        # POST /session/blocker
        if path == "/session/blocker":
            fpath = shared_path(self.case_dir, "blockers.yaml")
            blockers = load_yaml(fpath, [])
            entry = {
                "id": next_blocker_id(blockers),
                "time": now_str(),
                "from": body.get("from", ""),
                "blocker": body.get("blocker", ""),
                "needs": body.get("needs", ""),
                "status": body.get("status", "open"),
                "routed_to": body.get("routed_to", ""),
            }
            blockers.append(entry)
            save_yaml(fpath, blockers)
            return self._send(201, entry)

        # POST /session/strategy (replace)
        if path == "/session/strategy":
            fpath = shared_path(self.case_dir, "strategy.yaml")
            strategy = dict(body)
            strategy["updated"] = now_str()
            save_yaml(fpath, strategy)
            return self._send(200, strategy)

        # ─── /needs (修复 #1: 跨检材求助队列) ───
        # POST /needs - 发布求助
        # body: {from, item, purpose, candidate_locations, candidate_providers, blocking_qids, deadline_hours}
        if path == "/needs":
            role = body.get("from", "").strip()
            if not role:
                return self._err(400, "Missing 'from' field")
            item = body.get("item", "").strip()
            if not item:
                return self._err(400, "Missing 'item' field (what do you need?)")
            fpath = shared_path(self.case_dir, "needs.yaml")
            needs = load_yaml(fpath, [])
            entry = {
                "id": next_need_id(needs),
                "time": now_str(),
                "from": role,
                "item": item,
                "purpose": body.get("purpose", ""),
                "candidate_locations": body.get("candidate_locations", []),
                "candidate_providers": body.get("candidate_providers", ["*"]),
                "blocking_qids": body.get("blocking_qids", []),
                "deadline_hours": body.get("deadline_hours"),
                "status": "open",
                "claimed_by": "",
                "fulfilled_by": "",
                "fulfilled_value": "",
                "fulfilled_at": "",
                "updated": now_str(),
            }
            needs.append(entry)
            save_yaml(fpath, needs)
            return self._send(201, entry)

        # POST /needs/{id}/claim - 角色认领 (告诉队列我去找)
        # body: {by}
        m = re.match(r"^/needs/(N\d+)/claim$", path)
        if m:
            need_id = m.group(1)
            fpath = shared_path(self.case_dir, "needs.yaml")
            needs = load_yaml(fpath, [])
            for n in needs:
                if isinstance(n, dict) and n.get("id") == need_id:
                    if n.get("status") != "open":
                        return self._err(409, f"Need {need_id} status={n.get('status')}, cannot claim")
                    n["status"] = "claimed"
                    n["claimed_by"] = body.get("by", "")
                    n["updated"] = now_str()
                    save_yaml(fpath, needs)
                    return self._send(200, n)
            return self._err(404, f"Need {need_id} not found")

        # POST /needs/{id}/fulfill - 满足需求 (我找到了)
        # body: {by, value, evidence_path}
        m = re.match(r"^/needs/(N\d+)/fulfill$", path)
        if m:
            need_id = m.group(1)
            fpath = shared_path(self.case_dir, "needs.yaml")
            needs = load_yaml(fpath, [])
            for n in needs:
                if isinstance(n, dict) and n.get("id") == need_id:
                    n["status"] = "fulfilled"
                    n["fulfilled_by"] = body.get("by", "")
                    n["fulfilled_value"] = body.get("value", "")
                    n["fulfilled_evidence_path"] = body.get("evidence_path", [])
                    n["fulfilled_at"] = now_str()
                    n["updated"] = now_str()
                    save_yaml(fpath, needs)
                    return self._send(200, n)
            return self._err(404, f"Need {need_id} not found")

        # POST /needs/{id}/abandon - 放弃 (找不到 / 不需要了)
        m = re.match(r"^/needs/(N\d+)/abandon$", path)
        if m:
            need_id = m.group(1)
            fpath = shared_path(self.case_dir, "needs.yaml")
            needs = load_yaml(fpath, [])
            for n in needs:
                if isinstance(n, dict) and n.get("id") == need_id:
                    n["status"] = "abandoned"
                    n["abandon_reason"] = body.get("reason", "")
                    n["updated"] = now_str()
                    save_yaml(fpath, needs)
                    return self._send(200, n)
            return self._err(404, f"Need {need_id} not found")

        # POST /heartbeat - 角色心跳上报 (修复 REMOTE-FAIL-06)
        # body: {from, current_task}
        if path == "/heartbeat":
            role = body.get("from", "").strip()
            if not role:
                return self._err(400, "Missing 'from' field")
            fpath = shared_path(self.case_dir, "heartbeat.yaml")
            beats = load_yaml(fpath, {})
            if not isinstance(beats, dict):
                beats = {}
            beats[role] = {
                "last": now_str(),
                "current_task": body.get("current_task", ""),
            }
            save_yaml(fpath, beats)
            return self._send(200, beats[role])

        # POST /answers/{cat}/{qid}/lock - 答案锁 (修复 REMOTE-FAIL-09 并发覆盖)
        # body: {by, reason}
        # 锁超过 5 分钟自动过期
        m = re.match(r"^/answers/(\w+)/(\w+)/lock$", path)
        if m:
            category, qid = m.group(1), m.group(2)
            fpath = shared_path(self.case_dir, "answer_locks.yaml")
            locks = load_yaml(fpath, {})
            if not isinstance(locks, dict):
                locks = {}
            key = f"{category}/{qid}"
            now = datetime.datetime.now()
            existing = locks.get(key)
            if existing and isinstance(existing, dict):
                # 检查是否过期
                try:
                    locked_at = datetime.datetime.strptime(existing.get("locked_at", ""),
                                                           "%Y-%m-%d %H:%M:%S")
                    age = (now - locked_at).total_seconds()
                    if age < 300 and existing.get("by") != body.get("by"):
                        return self._err(409, {
                            "error": f"Answer {key} locked by {existing.get('by')}",
                            "locked_by": existing.get("by"),
                            "locked_at": existing.get("locked_at"),
                            "age_seconds": int(age),
                        })
                except Exception:
                    pass
            entry = {
                "by": body.get("by", ""),
                "reason": body.get("reason", ""),
                "locked_at": now_str(),
            }
            locks[key] = entry
            save_yaml(fpath, locks)
            return self._send(200, entry)

        # POST /answers/{cat}/{qid}/unlock - 显式释放锁
        m = re.match(r"^/answers/(\w+)/(\w+)/unlock$", path)
        if m:
            category, qid = m.group(1), m.group(2)
            fpath = shared_path(self.case_dir, "answer_locks.yaml")
            locks = load_yaml(fpath, {})
            if not isinstance(locks, dict):
                locks = {}
            key = f"{category}/{qid}"
            existing = locks.get(key)
            if not existing:
                return self._send(200, {"status": "no-op", "key": key})
            # 只有锁主才能解锁 (除非 force)
            by = body.get("by", "")
            force = body.get("force", False)
            if not force and existing.get("by") != by:
                return self._err(403, {
                    "error": f"Lock owned by {existing.get('by')}, not {by}. Use force=true to override.",
                })
            del locks[key]
            save_yaml(fpath, locks)
            return self._send(200, {"status": "unlocked", "key": key})

        return self._err(404, f"No route for POST {path}")


# ─── Server bootstrap ───

def get_local_ips():
    ips = set()
    try:
        hostname = socket.gethostname()
        for info in socket.getaddrinfo(hostname, None, socket.AF_INET):
            ips.add(info[4][0])
    except Exception:
        pass
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ips.add(s.getsockname()[0])
        s.close()
    except Exception:
        pass
    return sorted(ips)


def init_shared_files(case_dir):
    """Ensure all required shared YAML files exist (do not overwrite)."""
    sd = Path(case_dir) / "shared"
    sd.mkdir(parents=True, exist_ok=True)
    defaults = {
        "findings.yaml": [],
        "progress.yaml": {},
        "answers.yaml": {},
        "questions.yaml": [],
        "timeline.yaml": [],
        "session_log.yaml": [],
        "blockers.yaml": [],
        "strategy.yaml": {},
    }
    for fname, default in defaults.items():
        fpath = sd / fname
        if not fpath.exists():
            save_yaml(fpath, default)


def cmd_serve(args):
    global _hub_started_at
    case_dir = Path(args.case_dir).resolve()
    if not case_dir.exists():
        print(f"[!] Case directory not found: {case_dir}")
        sys.exit(1)

    init_shared_files(case_dir)
    Handler.case_dir = case_dir
    _hub_started_at = now_str()

    server = http.server.ThreadingHTTPServer((args.bind, args.port), Handler)

    print()
    print("=" * 60)
    print(f"  Collaboration Hub v3  -  port {args.port}")
    print("=" * 60)
    print(f"  Case dir:  {case_dir}")
    print(f"  Bind:      {args.bind}:{args.port}")
    print()
    print("  Remote machines connect via:")
    for ip in get_local_ips():
        if not ip.startswith("127."):
            print(f"    curl http://{ip}:{args.port}/ping")
    print()
    print("  Endpoints:")
    print("    GET  /ping")
    print("    GET  /findings | POST /findings | GET /findings/{id}")
    print("    GET  /progress | POST /progress/{role}")
    print("    GET  /answers  | POST /answers  | GET /answers/{category}")
    print("    GET  /questions| POST /questions| POST /questions/{id}/reply")
    print("    GET  /session  | POST /session/log | /session/blocker | /session/strategy")
    print("    GET  /files/{name}  (whitelisted)")
    print()
    print("  Press Ctrl+C to stop.")
    print()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[+] Hub stopped.")


def main():
    parser = argparse.ArgumentParser(description="AutoForensicAI Collaboration Hub v3")
    sub = parser.add_subparsers(dest="command")

    p = sub.add_parser("serve", help="Start the Hub")
    p.add_argument("case_dir", help="Path to case directory")
    p.add_argument("--port", type=int, default=8765)
    p.add_argument("--bind", default="0.0.0.0")

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        return

    if args.command == "serve":
        cmd_serve(args)


if __name__ == "__main__":
    main()
