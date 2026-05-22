"""检查每个角色最后心跳时间——判断远程机是否还连着 Hub。"""
import urllib.request, json, sys, io, datetime

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

HUB = "http://127.0.0.1:8765"


def get(path):
    return json.loads(urllib.request.urlopen(f"{HUB}{path}").read())


now = datetime.datetime.now()
print(f"当前时间: {now.strftime('%Y-%m-%d %H:%M:%S')}")
print(f"Hub uptime: {get('/ping').get('started_at', '?')} — 现在")
print()

# 1. progress.updated 是角色最后一次主动 POST 的时间
print("=" * 70)
print("【角色心跳】progress.updated 时间戳")
print("=" * 70)
progress = get("/progress")
for role, p in progress.items():
    updated = p.get("updated", "")
    status = p.get("status", "?")
    task = (p.get("current_task", "") or "")[:60]
    if updated:
        try:
            t = datetime.datetime.strptime(updated, "%Y-%m-%d %H:%M:%S")
            age_min = (now - t).total_seconds() / 60
            age_label = (
                f"{age_min:.0f} 分钟前" if age_min < 60
                else f"{age_min/60:.1f} 小时前"
            )
            alive_emoji = "[OK]" if age_min < 30 else ("[?]" if age_min < 120 else "[X]")
        except Exception:
            age_label = "解析失败"
            alive_emoji = "[?]"
    else:
        age_label = "从未更新"
        alive_emoji = "[X]"
    print(f"  {alive_emoji} {role:20s} | status={status:18s} | {age_label:15s} | {task}")

# 2. 每个角色最近一条 finding 时间
print()
print("=" * 70)
print("【最近活动】每个角色最后一次 POST /findings")
print("=" * 70)
for role in ["mobile_analyst", "computer_analyst", "server_analyst", "binary_analyst"]:
    findings = get(f"/findings?from={role}")
    if not findings:
        print(f"  [X] {role:20s} | 无 finding")
        continue
    latest = max(findings, key=lambda f: f.get("time", ""))
    t_str = latest.get("time", "")
    try:
        t = datetime.datetime.strptime(t_str[:19], "%Y-%m-%d %H:%M:%S")
        age_min = (now - t).total_seconds() / 60
        age_label = (
            f"{age_min:.0f} 分钟前" if age_min < 60
            else f"{age_min/60:.1f} 小时前"
        )
        alive_emoji = "[OK]" if age_min < 30 else ("[?]" if age_min < 120 else "[X]")
    except Exception:
        age_label = "解析失败"
        alive_emoji = "[?]"
    print(f"  {alive_emoji} {role:20s} | 最后 finding {t_str[:19]} ({age_label})")
    print(f"        最新: [{latest.get('id')}] {latest.get('summary','')[:80]}")

# 3. 未回复的 inbox 排序
print()
print("=" * 70)
print("【未回复 question】按收件人分组")
print("=" * 70)
qs = get("/questions")
unanswered = [q for q in qs if not q.get("answer")]
by_to = {}
for q in unanswered:
    by_to.setdefault(q.get("to", "?"), []).append(q)

for to, items in sorted(by_to.items()):
    print(f"\n  ▶ {to} 收件箱: {len(items)} 个未回复")
    for q in items:
        t_str = q.get("time", "")[:19]
        try:
            t = datetime.datetime.strptime(t_str, "%Y-%m-%d %H:%M:%S")
            age_min = (now - t).total_seconds() / 60
            age_label = f"卡 {age_min:.0f}min" if age_min < 60 else f"卡 {age_min/60:.1f}h"
        except Exception:
            age_label = "?"
        print(f"      [Q{q.get('id')}] {age_label:8s} 来自 {q.get('from','?'):18s}: "
              f"{(q.get('question','') or '')[:60]}")
