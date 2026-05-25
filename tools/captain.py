"""
Captain Console — 小空 (主设计师) 主动拉取全局态势的工具 (A 方案)

设计意图:
  在 A 方案下, 远程角色只调 log_*() 一个函数, 不再被强制 POST 各种状态。
  作为 captain (小空), 我应该主动拉态势, 而不是被动等。
  此脚本一次性输出: 心跳/答案完成率/未回复 inbox/blocker/最近活动/战略建议钩子。

用法:
  python tools/captain.py                         # 一次性快照 (打印)
  python tools/captain.py --watch 30              # 每 30 秒刷新打印 (前台)
  python tools/captain.py --json                  # JSON 输出, 方便 chat 再分析
  python tools/captain.py --since 2026-05-08T15   # 只看某时间点之后的活动
  python tools/captain.py --watcher 30            # 后台监视模式: 写 brief + 自动跨角色路由
"""
import argparse
import datetime
import io
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

DEFAULT_HUB  = "http://127.0.0.1:8765"
DEFAULT_CASE = r"E:\ffffff-JIANCAI\2026FIC团体赛\case"
ROLES = ["computer_analyst", "mobile_analyst", "server_analyst", "binary_analyst"]
CATEGORIES = {
    "computer_forensics": "计算机",
    "mobile_forensics": "手机",
    "server_forensics": "服务器",
    "binary_forensics": "二进制",
    "internet_forensics": "互联网",
}


def get(hub, path):
    try:
        with urllib.request.urlopen(f"{hub}{path}", timeout=5) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        return {"_err": f"HTTP {e.code}: {e.read().decode()[:80]}"}
    except Exception as e:
        return {"_err": str(e)}


def fmt_age(t_str, now):
    try:
        t = datetime.datetime.strptime(t_str[:19], "%Y-%m-%d %H:%M:%S")
        m = (now - t).total_seconds() / 60
        if m < 1:
            return "刚才"
        if m < 60:
            return f"{m:.0f}分钟前"
        if m < 60 * 24:
            return f"{m/60:.1f}小时前"
        return f"{m/60/24:.1f}天前"
    except Exception:
        return "?"


def alive_emoji(t_str, now):
    try:
        t = datetime.datetime.strptime(t_str[:19], "%Y-%m-%d %H:%M:%S")
        m = (now - t).total_seconds() / 60
        if m < 30:
            return "🟢"
        if m < 120:
            return "🟡"
        if m < 60 * 12:
            return "🟠"
        return "🔴"
    except Exception:
        return "❓"


def _try_lint(case_dir: str) -> list[dict]:
    """尝试调 answer_format_lint.quick_lint, 失败静默返回空。"""
    try:
        tools_dir = Path(__file__).parent
        sys.path.insert(0, str(tools_dir))
        from tools.competition.answer_format_lint import quick_lint
        fails, _ = quick_lint(case_dir)
        return fails
    except Exception as e:
        return [{"_err": str(e)}]


def snapshot(hub, since=None, case_dir=DEFAULT_CASE):
    """一次拉取全局态势, 返回 dict (json 模式直接 dump)。"""
    now = datetime.datetime.now()
    state = {
        "captain": "小空",
        "hub": hub,
        "case_dir": case_dir,
        "snap_at": now.strftime("%Y-%m-%d %H:%M:%S"),
        "ping": get(hub, "/ping"),
        "progress": get(hub, "/progress"),
        "answers": get(hub, "/answers"),
        "findings": get(hub, "/findings"),
        "questions": get(hub, "/questions"),
        "session": get(hub, "/session"),
    }

    # 派生指标 ===

    # 1. 各角色心跳
    state["heartbeat"] = []
    for role in ROLES:
        p = state["progress"].get(role, {}) if isinstance(state["progress"], dict) else {}
        updated = p.get("updated", "")
        state["heartbeat"].append({
            "role": role,
            "alive": alive_emoji(updated, now),
            "age": fmt_age(updated, now),
            "status": p.get("status", "?"),
            "task": (p.get("current_task") or "")[:50],
            "blocker": (p.get("blocker") or "")[:50],
        })

    # 2. 答案进度
    state["answer_stats"] = {}
    if isinstance(state["answers"], dict):
        for cat, items in state["answers"].items():
            if not isinstance(items, list):
                continue
            answered = sum(1 for a in items if a.get("answer"))
            verified = sum(1 for a in items if a.get("verification_status") == "verified")
            disputed = sum(1 for a in items if a.get("verification_status") == "disputed")
            state["answer_stats"][cat] = {
                "total": len(items),
                "answered": answered,
                "verified": verified,
                "disputed": disputed,
            }

    # 3. 未回复 inbox (按收件人分组)
    state["unanswered"] = {}
    if isinstance(state["questions"], list):
        for q in state["questions"]:
            if not isinstance(q, dict):
                continue
            if q.get("answer"):
                continue
            to = q.get("to", "?")
            state["unanswered"].setdefault(to, []).append({
                "id": q.get("id"),
                "from": q.get("from"),
                "age": fmt_age(q.get("time", ""), now),
                "question": (q.get("question") or "")[:80],
            })

    # 4. 最近 N 条 finding (since 之后或最近 10 条)
    recent = []
    if isinstance(state["findings"], list):
        for f in state["findings"][-30:]:
            if not isinstance(f, dict):
                continue
            t_str = f.get("time", "")
            if since and t_str < since:
                continue
            recent.append({
                "id": f.get("id"),
                "from": f.get("from"),
                "age": fmt_age(t_str, now),
                "summary": (f.get("summary") or "")[:80],
                "encoding_lost": f.get("_encoding_lost", False),
            })
    state["recent_findings"] = recent[-10:]

    # 5. 开放 blocker
    blockers = []
    sess = state["session"] if isinstance(state["session"], dict) else {}
    bl = sess.get("blockers", [])
    if isinstance(bl, list):
        for b in bl:
            if not isinstance(b, dict):
                continue
            if b.get("status", "open") != "open":
                continue
            blockers.append({
                "id": b.get("id"),
                "from": b.get("from"),
                "blocker": (b.get("blocker") or "")[:80],
                "needs": (b.get("needs") or "")[:80],
                "age": fmt_age(b.get("time", ""), now),
                "routed_to": b.get("routed_to") or "未路由",
            })
    state["open_blockers"] = blockers

    # 5b. 答案格式 lint (C3)
    state["lint_fails"] = _try_lint(case_dir)

    return state


def render_human(state):
    """漂亮的人类可读输出 (给 captain 自己看)。"""
    lines = []
    p = state["ping"]
    if isinstance(p, dict) and "version" in p:
        lines.append(f"Hub {p.get('version','?')}  uptime since {p.get('started_at','?')}")
    else:
        lines.append(f"Hub error: {p.get('_err','?')}")
        return "\n".join(lines)

    lines.append(f"快照: {state['snap_at']}")
    lines.append("")

    # 心跳
    lines.append("=" * 70)
    lines.append("【角色心跳】")
    lines.append("=" * 70)
    for h in state["heartbeat"]:
        lines.append(f"  {h['alive']} {h['role']:18s} | {h['status']:12s} | {h['age']:10s}")
        if h["task"]:
            lines.append(f"      └ 任务: {h['task']}")
        if h["blocker"]:
            lines.append(f"      └ 卡点: {h['blocker']}")

    # 答案进度
    lines.append("")
    lines.append("=" * 70)
    lines.append("【答案进度】")
    lines.append("=" * 70)
    total = answered = verified = disputed = 0
    for cat, st in state["answer_stats"].items():
        label = CATEGORIES.get(cat, cat)
        pct = (st["answered"] * 100 // st["total"]) if st["total"] else 0
        lines.append(
            f"  {label:6s} {st['answered']:2d}/{st['total']:2d} ({pct:3d}%) "
            f"verified={st['verified']:2d}  disputed={st['disputed']:2d}"
        )
        total += st["total"]
        answered += st["answered"]
        verified += st["verified"]
        disputed += st["disputed"]
    if total:
        lines.append(
            f"  {'合计':6s} {answered:2d}/{total:2d} ({answered*100//total:3d}%) "
            f"verified={verified}  disputed={disputed}"
        )
        if answered == total:
            import winsound
            winsound.PlaySound("SystemExclamation", winsound.SND_ALIAS)

    # 未回复 inbox
    lines.append("")
    lines.append("=" * 70)
    lines.append("【未回复 inbox】")
    lines.append("=" * 70)
    if not state["unanswered"]:
        lines.append("  无未回复消息")
    else:
        for to, items in state["unanswered"].items():
            lines.append(f"  ▶ {to} ({len(items)} 条):")
            for q in items[:5]:
                lines.append(
                    f"      [{q['id']}] {q['age']:10s} 来自 {q['from']:18s}: {q['question']}"
                )

    # blocker
    lines.append("")
    lines.append("=" * 70)
    lines.append("【开放 blocker】(需要 captain 路由)")
    lines.append("=" * 70)
    if not state["open_blockers"]:
        lines.append("  无 open blocker")
    else:
        for b in state["open_blockers"]:
            lines.append(
                f"  • {b['from']:18s} ({b['age']:10s})"
                f" → 路由到: {b['routed_to']}"
            )
            lines.append(f"    blocker: {b['blocker']}")
            lines.append(f"    needs:   {b['needs']}")

    # 最近 finding
    lines.append("")
    lines.append("=" * 70)
    lines.append("【最近 10 条 finding】")
    lines.append("=" * 70)
    if not state["recent_findings"]:
        lines.append("  无最新 finding")
    else:
        for f in state["recent_findings"]:
            mark = "⚠️" if f.get("encoding_lost") else " "
            lines.append(f"  {mark} [{f['id']}] {f['from']:18s} {f['age']:10s}: {f['summary']}")

    # 格式 lint (C3)
    lint_fails = state.get("lint_fails", [])
    real_fails = [f for f in lint_fails if "_err" not in f]
    if real_fails:
        lines.append("")
        lines.append("=" * 70)
        lines.append("【格式 Lint — 疑似答案格式错误】(C3)")
        lines.append("=" * 70)
        for f in real_fails[:10]:
            lines.append(
                f"  ❌ [{f['cat'][:20]:20s}] {f['qid']:4s}: {(f['answer'] or '')[:40]}"
            )
            lines.append(f"     期望: {f.get('ref_format','')}  ({f.get('reason','')})")

    # 战略提示 (captain 该干的事)
    lines.append("")
    lines.append("=" * 70)
    lines.append("【captain 行动建议】")
    lines.append("=" * 70)

    suggestions = []
    # 格式 lint 失败
    if real_fails:
        suggestions.append(f"  • {len(real_fails)} 个答案格式疑似不符 — 跑 python tools/answer_format_lint.py --fix 自动标 disputed")
    # 长时间心跳缺失
    for h in state["heartbeat"]:
        if h["alive"] in ("🔴", "🟠"):
            suggestions.append(f"  • {h['role']} 心跳 {h['age']} 无更新 — 提醒用户那个窗口的 AI 是否还活着")
    # 未路由的 blocker
    for b in state["open_blockers"]:
        if b["routed_to"] == "未路由":
            suggestions.append(f"  • blocker '{b['from']}/{b['blocker'][:30]}' 未路由, 你应该选一个角色推过去")
    # disputed 答案
    for cat, st in state["answer_stats"].items():
        if st["disputed"] > 0:
            suggestions.append(f"  • {cat} 有 {st['disputed']} 个 disputed 答案, 需要复核")
    # 进度低且未 verify
    for cat, st in state["answer_stats"].items():
        if st["answered"] > 0 and st["verified"] < st["answered"] // 2:
            suggestions.append(f"  • {cat} {st['answered']} 题已答但仅 {st['verified']} 已验证, 优先复核")

    if not suggestions:
        lines.append("  (态势良好, 无紧急动作建议)")
    else:
        lines.extend(suggestions)

    return "\n".join(lines)


# ============================================================
# Watcher 模式: 后台跑, 自动 routing + 写 brief
# ============================================================

# 跨角色自动路由规则: 当 (category, qid) 出现确认答案时, 自动通知相关角色
ROUTING_RULES = [
    # binary 出密码 → 解锁 computer Q9/Q10 + binary Q4/Q5
    {
        "trigger_cat": "binary_forensics",
        "trigger_qid": "Q3",
        "broadcast_to": ["computer_analyst", "binary_analyst"],
        "summary": "🔓 vc 容器密码已解出, 立即解 computer Q9/Q10 (保险柜编号+密码) 和 binary Q4/Q5 (后缀+收款金额)",
    },
    # server 网站后台入口 → 通知 internet
    {
        "trigger_cat": "server_forensics",
        "trigger_qid": "Q5",
        "broadcast_to": ["internet_analyst", "computer_analyst"],
        "summary": "📌 网站后台管理入口已找到, 可能与 computer Q4 (apk下载链接来源) 相关",
    },
    # mobile USDT 钱包 → 通知 server 查 wallet 表
    {
        "trigger_cat": "mobile_forensics",
        "trigger_qid": "Q15",
        "broadcast_to": ["server_analyst"],
        "summary": "💰 mobile 已找到 USDT 钱包, server 可在 wallet 表/数据库中关联查询",
    },
    # server LV 解密成功 (Q1 OS 出现意味着挂上了) → 解锁 server 全部
    {
        "trigger_cat": "server_forensics",
        "trigger_qid": "Q1",
        "broadcast_to": ["server_analyst"],
        "summary": "✅ LV root 已挂载成功, 立即并行解 Q2/Q4/Q5/Q6/Q7/Q8/Q9/Q10",
    },
    # computer AI 软件路径找到 → 解锁 Q6/Q7
    {
        "trigger_cat": "computer_forensics",
        "trigger_qid": "Q6",
        "broadcast_to": ["computer_analyst"],
        "summary": "AI 软件已识别, 立即解 Q7 (apiKey)",
    },
]


def post_to_hub(hub: str, path: str, data: dict) -> str:
    body = json.dumps(data, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        f"{hub}{path}", data=body,
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST")
    try:
        return urllib.request.urlopen(req, timeout=5).read().decode("utf-8")
    except Exception as e:
        return f"ERR: {e}"


def detect_new_answers(prev_answers: dict, curr_answers: dict) -> list[tuple[str, str, str]]:
    """对比前后两次 answers 快照, 返回新出现/更新的答案 (cat, qid, answer)"""
    changes = []
    if not isinstance(curr_answers, dict):
        return changes
    for cat, items in curr_answers.items():
        if not isinstance(items, list):
            continue
        prev_cat = prev_answers.get(cat, []) if isinstance(prev_answers, dict) else []
        prev_map = {a.get("qid"): a.get("answer") for a in prev_cat if isinstance(a, dict)}
        for a in items:
            if not isinstance(a, dict):
                continue
            qid = a.get("qid")
            ans = a.get("answer")
            if not qid or not ans:
                continue
            if prev_map.get(qid) != ans:
                changes.append((cat, qid, ans))
    return changes


def detect_stalled(state: dict, threshold_min: int = 30) -> list[str]:
    """检测超过 N 分钟无心跳的角色"""
    stalled = []
    for h in state.get("heartbeat", []):
        if h["alive"] in ("🔴", "🟠"):
            stalled.append(f"{h['role']} ({h['age']})")
    return stalled


def render_brief_md(state: dict, recent_routing_events: list, stalled: list) -> str:
    """生成 captain_brief.md (Markdown 格式, 给 dashboard / 用户读)"""
    now = state["snap_at"]
    lines = [
        "# 🎯 Captain Brief — 2026FIC 实时总览",
        "",
        f"_生成时间: {now}_",
        "",
        "## 答案进度",
        "",
        "| 分类 | 已答/总数 | verified | disputed |",
        "|---|---|---|---|",
    ]
    total_a, total_t, total_v = 0, 0, 0
    for cat, st in state.get("answer_stats", {}).items():
        label = CATEGORIES.get(cat, cat)
        lines.append(f"| {label} | {st['answered']}/{st['total']} | {st['verified']} | {st['disputed']} |")
        total_a += st["answered"]; total_t += st["total"]; total_v += st["verified"]
    lines.append(f"| **合计** | **{total_a}/{total_t}** | **{total_v}** | — |")

    lines += ["", "## 角色心跳", ""]
    for h in state.get("heartbeat", []):
        lines.append(f"- {h['alive']} **{h['role']}** [{h['status']}] {h['age']} — {h['task']}")

    if stalled:
        lines += ["", "## ⚠️ 沉默角色 (>30min 无心跳)", ""]
        for s in stalled:
            lines.append(f"- {s}")

    lines += ["", "## 最近 10 条 finding", ""]
    for f in state.get("recent_findings", []):
        lines.append(f"- `{f['id']}` **{f['from']}** {f['age']}: {f['summary']}")

    lines += ["", "## 开放 blocker", ""]
    if not state.get("open_blockers"):
        lines.append("_无_")
    else:
        for b in state["open_blockers"]:
            lines.append(f"- **{b['from']}** ({b['age']}): {b['blocker']} → 需要 {b['needs']}")

    if recent_routing_events:
        lines += ["", "## 🚨 最近自动路由事件", ""]
        for e in recent_routing_events[-10:]:
            lines.append(f"- `{e['time']}` {e['summary']} → broadcast 给 {e['to']}")

    real_fails = [f for f in state.get("lint_fails", []) if "_err" not in f]
    if real_fails:
        lines += ["", "## ❌ 格式错误", ""]
        for f in real_fails[:10]:
            lines.append(f"- [{f['cat']}] {f['qid']}: `{(f['answer'] or '')[:30]}` (期望: {f.get('ref_format','')})")

    return "\n".join(lines) + "\n"


def watcher_loop(hub: str, case_dir: str, interval: int):
    """后台监视循环: 拉态势 + 自动 routing + 写 brief"""
    brief_path = Path(case_dir) / "shared" / "captain_brief.md"
    events_path = Path(case_dir) / "shared" / "captain_events.jsonl"
    state_path = Path(case_dir) / "shared" / "captain_state.json"
    brief_path.parent.mkdir(parents=True, exist_ok=True)

    print(f"[watcher] 启动. brief={brief_path}, interval={interval}s")

    # 路由触发去重: 记录已触发过的 (cat, qid) 组合, 持久化避免重启重复广播
    triggered_keys = set()
    if state_path.exists():
        try:
            saved = json.loads(state_path.read_text(encoding="utf-8"))
            triggered_keys = set(saved.get("triggered_keys", []))
            print(f"[watcher] 已加载历史触发记录: {len(triggered_keys)} 个 key")
        except Exception:
            pass

    # 启动基线: 把当前所有已答的 key 直接计入 triggered_keys, 避免首次循环全量误触发
    try:
        baseline = snapshot(hub, case_dir=case_dir)
        baseline_answers = baseline.get("answers", {})
        if isinstance(baseline_answers, dict):
            for cat, items in baseline_answers.items():
                if not isinstance(items, list):
                    continue
                for a in items:
                    if isinstance(a, dict) and a.get("answer"):
                        triggered_keys.add(f"{cat}/{a.get('qid')}")
        prev_answers = baseline_answers
        print(f"[watcher] 已建立基线 (跳过 {len(triggered_keys)} 个现有答案的 routing)")
    except Exception as e:
        print(f"[watcher] 基线建立失败: {e}")
        prev_answers = {}

    routing_events = []

    cycle = 0
    while True:
        cycle += 1
        try:
            state = snapshot(hub, case_dir=case_dir)
            curr_answers = state.get("answers", {})

            # 检测新答案 + 触发路由
            changes = detect_new_answers(prev_answers, curr_answers)
            for cat, qid, ans in changes:
                key = f"{cat}/{qid}"
                # 去重: 已触发过的 key 跳过
                if key in triggered_keys:
                    continue
                # 找匹配规则
                for rule in ROUTING_RULES:
                    if rule["trigger_cat"] == cat and rule["trigger_qid"] == qid:
                        print(f"[watcher] 触发路由: {key} -> {rule['broadcast_to']}")
                        broadcast = {
                            "from": "main_designer",
                            "type": "instruction",
                            "summary": f"[CAPTAIN AUTO] {rule['summary']}",
                            "detail": f"触发: {key} = {ans}\n目标角色: {','.join(rule['broadcast_to'])}",
                            "target_roles": rule["broadcast_to"],
                        }
                        post_to_hub(hub, "/findings", broadcast)
                        evt = {
                            "time": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                            "type": "auto_route",
                            "trigger": key,
                            "to": ",".join(rule["broadcast_to"]),
                            "summary": rule["summary"],
                        }
                        routing_events.append(evt)
                        try:
                            with events_path.open("a", encoding="utf-8") as fh:
                                fh.write(json.dumps(evt, ensure_ascii=False) + "\n")
                        except Exception:
                            pass
                # 标记此 key 已处理 (即使没匹配规则)
                triggered_keys.add(key)
                # 持久化
                try:
                    state_path.write_text(
                        json.dumps({"triggered_keys": sorted(triggered_keys)}, ensure_ascii=False, indent=2),
                        encoding="utf-8")
                except Exception:
                    pass

            # 检测 stalled
            stalled = detect_stalled(state, threshold_min=30)

            # 写 brief
            brief = render_brief_md(state, routing_events, stalled)
            brief_path.write_text(brief, encoding="utf-8")

            print(f"[watcher] cycle {cycle:4d} OK | 新答案 {len(changes)} | 路由 {len([e for e in routing_events if e.get('time','')>state['snap_at'][:10]])} | stalled {len(stalled)}")

        except KeyboardInterrupt:
            print("[watcher] 中断, 退出")
            break
        except Exception as e:
            print(f"[watcher] cycle {cycle} ERROR: {e}")

        prev_answers = curr_answers
        time.sleep(interval)


def main():
    p = argparse.ArgumentParser(description="Captain Console — 小空主动态势板")
    p.add_argument("--hub",   default=DEFAULT_HUB,  help="Hub URL")
    p.add_argument("--case",  default=DEFAULT_CASE, help="case 目录 (用于格式 lint)")
    p.add_argument("--json",  action="store_true",  help="JSON 输出")
    p.add_argument("--watch", type=int, default=0,  help="N 秒刷新打印 (前台)")
    p.add_argument("--watcher", type=int, default=0,  help="N 秒后台监视 + 自动路由 + 写 brief")
    p.add_argument("--since", help="只看 ISO timestamp 之后的活动 (例: 2026-05-08T14)")
    p.add_argument("--no-lint", action="store_true", help="跳过格式 lint (加快速度)")
    args = p.parse_args()

    # watcher 后台模式
    if args.watcher > 0:
        watcher_loop(args.hub, args.case, args.watcher)
        return

    # 一次性 / watch 前台模式
    while True:
        state = snapshot(args.hub, since=args.since, case_dir=args.case)
        if args.no_lint:
            state["lint_fails"] = []
        if args.json:
            print(json.dumps(state, ensure_ascii=False, indent=2))
        else:
            print(render_human(state))
        if args.watch <= 0:
            break
        print(f"\n(刷新中, {args.watch}s 后...)\n")
        time.sleep(args.watch)


if __name__ == "__main__":
    main()
