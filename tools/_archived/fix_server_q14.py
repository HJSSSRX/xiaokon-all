"""
Q14 修正: 2026/04/15 → 2026/4/15 (题目参考格式 2000/1/1 不补 0)
顺便给 Q1 备选答案做记录, 以及 server 状态总结
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


# Q14 修正
q14_fix = {
    "kind": "answer",
    "from": "main_designer",
    "category": "server_forensics",
    "qid": "Q14",
    "question": "新注册用户数量最多的日期",
    "answer": "2026/4/15",
    "confidence": "high",
    "analysis": (
        "ZFS 池 (db/tidb dataset 4.84G, 46543 objects) strings 扫描时间戳统计: "
        "2026-04-15: 31217 次 (绝对最多) / 2026-04-16: 12118 / 2026-04-13: 5358. "
        "题目格式 2000/1/1 不补 0, 故由 2026/04/15 修正为 2026/4/15. "
        "main_designer 修正 (原答案 2026/04/15 月日补 0 不符合参考格式)."
    ),
    "evidence_path": "case/server/zfs_strings/all.strings.txt + zfs_analyzed.txt",
    "source_role": "main_designer",
    "verification_status": "unverified",
}

# Q1 当前 = 13. 13.0 已被拒. 备选 trixie. 写到 finding 提醒
q1_finding = {
    "kind": "finding",
    "from": "main_designer",
    "summary": "[Q1 服务器 OS 版本] 当前 unverified=13, 13.0 已被拒. 候选: trixie / 13.0.0",
    "detail": (
        "/etc/os-release 内容:\n"
        "VERSION_ID=\"13\"\n"
        "VERSION_CODENAME=trixie\n"
        "DEBIAN_VERSION_FULL=13.0\n"
        "/etc/debian_version: 13.0\n"
        "题目格式 0.9 暗示 X.Y, 但 13.0 已拒.\n"
        "候选优先级:\n"
        "1. trixie (codename, 唯一字符串答案)\n"
        "2. 13.0.0 (full semver, 部分发行版用)\n"
        "3. 13 (current 答案, 保留)"
    ),
    "type": "instruction",
    "target_roles": ["server_analyst", "main_designer"],
}

# server 总结 finding (给 captain_brief 用)
server_summary = {
    "kind": "finding",
    "from": "main_designer",
    "summary": "[server 状态] 17/17 已答, main_designer 修正 Q5/Q12/Q14, Q1/Q15 confidence 中等待平台验证",
    "detail": (
        "已修正:\n"
        "- Q5: admin1.php (物理不存在) → user.php (源码 ENTRANCE='admin')\n"
        "- Q12: docker → lxc (TiDB mytidb 容器在 LXC, 不是 docker)\n"
        "- Q14: 2026/04/15 → 2026/4/15 (题目格式不补 0)\n\n"
        "待平台验证:\n"
        "- Q1=13 (13.0 已拒, 备选 trixie)\n"
        "- Q15=192.168.226.1 (从 nginx access.log 推断, ZFS 池里 mac_user 行数据无法直接读出)\n\n"
        "ZFS 状态: db/tidb dataset 4.84G + 46543 objects, 但 WSL 内核 (6.6.87.2-microsoft-standard-WSL2) 缺 ZFS 模块, "
        "无法 zpool import 实际挂载. 用 zdb -e + strings 拿到关键 schema/版本但拿不到行级数据."
    ),
    "type": "summary",
}

print("=== POST Q14 修正 ===")
print(post_log(q14_fix))
print()
print("=== POST Q1 备选 finding ===")
print(post_log(q1_finding))
print()
print("=== POST server 总结 ===")
print(post_log(server_summary))
print()
print("完成. 等 watcher cycle.")
