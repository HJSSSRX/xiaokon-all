"""
修正 server_analyst 的 Q5 和 Q12 错答
- Q5: admin1.php → user.php (物理文件存在, ENTRANCE='admin')
- Q12: docker → lxc (TiDB 在 LXC 容器 mytidb)
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


# Q5 修正: user.php
q5_fix = {
    "kind": "answer",
    "from": "main_designer",
    "category": "server_forensics",
    "qid": "Q5",
    "question": "网站后台管理入口对应的文件名",
    "answer": "user.php",
    "confidence": "high",
    "analysis": (
        "通过 WSL 挂载 server 根分区 (md0 raid0+btrfs subvol=@rootfs) 直接读源码: "
        "/var/www/html/maccms10/user.php 中 define('ENTRANCE', 'admin'), "
        "且代码注释明确写 'please rename the background entry file admin.php' — "
        "即 user.php 就是 admin.php 改名后的物理文件. "
        "nginx access.log 显示 16/Apr 起所有后台 POST 登录都走 /user.php/admin/index/login.html. "
        "admin1.php 物理文件不存在 (历史 13~14/Apr 用过, 16/Apr 改成 user.php). "
        "main_designer 修正 (原答案 admin1.php 物理文件不存在)."
    ),
    "evidence_path": "case/server/maccms_files/user.php (ENTRANCE='admin')",
    "source_role": "main_designer",
    "verification_status": "unverified",
}

# Q12 修正: lxc
q12_fix = {
    "kind": "answer",
    "from": "main_designer",
    "category": "server_forensics",
    "qid": "Q12",
    "question": "网站数据库使用了哪一类容器技术",
    "answer": "lxc",
    "confidence": "high",
    "analysis": (
        "网站 maccms10 的 database.php hostname='mytidb', 端口 3306, 用户 'aa'. "
        "/etc/hosts 解析: 10.0.3.100 mytidb (Q11 已确认). "
        "10.0.3.0/24 是 lxcbr0 网段 (USE_LXC_BRIDGE='true' in /etc/default/lxc-net). "
        "/var/lib/lxc/mytidb/config 显示 lxc.uts.name=mytidb, lxc.rootfs.path=dir:/db/tidb. "
        "另有 1 个 docker 容器 u24 (image=u22) 但与网站数据库无关. "
        "main_designer 修正 (原答案 docker - 网站数据库实际在 LXC 容器内)."
    ),
    "evidence_path": "case/server/maccms_files/database.php + /var/lib/lxc/mytidb/config",
    "source_role": "main_designer",
    "verification_status": "unverified",
}

# Q1 修正候选: 13.0 已被拒, 试 trixie
# 备选: trixie 是 Debian 13 的 codename
q1_alt = {
    "kind": "finding",
    "from": "main_designer",
    "summary": "[Q1 候选] OS 版本 13.0 已被拒, 备选: trixie (Debian 13 codename) 或 13",
    "detail": (
        "/etc/os-release: VERSION_ID=\"13\" VERSION_CODENAME=trixie DEBIAN_VERSION_FULL=13.0\n"
        "/etc/debian_version: 13.0\n"
        "platform 已拒 13.0, 候选: trixie / 13\n"
        "题目格式 0.9 暗示 X.Y 版本号, 但 13.0 已拒 → 出题人期望 codename trixie 或纯数字 13"
    ),
    "type": "instruction",
    "target_roles": ["server_analyst"],
}

print("=== POST Q5 修正 ===")
print(post_log(q5_fix))
print()
print("=== POST Q12 修正 ===")
print(post_log(q12_fix))
print()
print("=== POST Q1 备选提醒 (finding) ===")
print(post_log(q1_alt))
print()
print("修正完成. 等 watcher 30s 内 cycle 看到新答案.")
