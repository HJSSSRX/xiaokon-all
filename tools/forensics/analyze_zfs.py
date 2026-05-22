"""
分析 ZFS strings 输出, 提取 Q13/Q14/Q15 的精确答案
"""
import re
from collections import Counter
from pathlib import Path

ZFS_STRINGS = Path("/mnt/e/ffffff-JIANCAI/2026FIC团体赛/case/server/zfs_strings/all.strings.txt")
# Windows path 等价
ZFS_STRINGS_WIN = Path(r"E:\ffffff-JIANCAI\2026FIC团体赛\case\server\zfs_strings\all.strings.txt")

if ZFS_STRINGS_WIN.exists():
    p = ZFS_STRINGS_WIN
elif ZFS_STRINGS.exists():
    p = ZFS_STRINGS
else:
    raise FileNotFoundError("strings file not found")

print(f"读取 {p} ({p.stat().st_size/1024/1024:.1f} MB)")

# Q14: 注册日期最多 — 找所有 yyyy-mm-dd 形式时间戳 + 是否在 user_reg 上下文
date_re = re.compile(r"(2026-04-\d{2})\s\d{2}:\d{2}:\d{2}")
ip_re = re.compile(r"(?:^|[^\d.])((?:192\.168|10\.0)\.\d{1,3}\.\d{1,3})(?:[^\d.]|$)")
mahui_keywords = ["马慧美", "mahuimei", "ma_hui_mei", "huimei", "mahui"]

dates = Counter()
ips = Counter()
mahui_lines = []
tidb_versions = set()

with p.open("r", encoding="utf-8", errors="ignore") as f:
    for ln in f:
        # Q14: 注册日期
        for m in date_re.finditer(ln):
            d = m.group(1)
            dates[d] += 1
        # IP 收集
        for m in ip_re.finditer(ln):
            ip = m.group(1)
            ips[ip] += 1
        # 马慧美相关行
        for kw in mahui_keywords:
            if kw in ln:
                mahui_lines.append(ln.strip()[:200])
                break
        # TiDB 版本
        for ver_re in [r"Release Version:\s+(v?\d+\.\d+\.\d+)", r'"Release Version"=(v\d+\.\d+\.\d+)']:
            for m in re.finditer(ver_re, ln):
                tidb_versions.add(m.group(1))

print("\n=== Q13 TiDB 版本 ===")
for v in sorted(tidb_versions):
    print(f"  {v}")

print("\n=== Q14 注册日期统计 (Top 10) ===")
for d, cnt in dates.most_common(10):
    print(f"  {d}: {cnt}")

print("\n=== IP 统计 (Top 20) ===")
for ip, cnt in ips.most_common(20):
    print(f"  {ip}: {cnt}")

print(f"\n=== 马慧美关键词命中行数: {len(mahui_lines)} ===")
for ln in mahui_lines[:30]:
    print(f"  {ln}")

# 写到 case 目录
out = Path(r"E:\ffffff-JIANCAI\2026FIC团体赛\case\server\zfs_analyzed.txt")
out.write_text(
    f"=== Q13 TiDB 版本 ===\n"
    + "\n".join(sorted(tidb_versions))
    + "\n\n=== Q14 注册日期统计 (Top 10) ===\n"
    + "\n".join(f"{d}: {cnt}" for d, cnt in dates.most_common(10))
    + "\n\n=== IP 统计 (Top 30) ===\n"
    + "\n".join(f"{ip}: {cnt}" for ip, cnt in ips.most_common(30))
    + f"\n\n=== 马慧美命中 {len(mahui_lines)} 行 ===\n"
    + "\n".join(mahui_lines[:50]),
    encoding="utf-8"
)
print(f"\n写入: {out}")
