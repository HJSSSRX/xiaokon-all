"""
深度搜保险柜 - 扩展关键词 + chat 上下文
"""
import sys
import io
import re
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

ROOT = Path(r"E:\ffffff-JIANCAI\2026FIC团体赛\case\mobile_extract")
chat = (ROOT / "chat_dump.txt").read_text(encoding="utf-8", errors="ignore")

# 1. 扩展关键词搜索
KW = [
    "保险柜", "保险箱", "金库", "safebox", "safe box",
    "藏起", "藏在", "存放", "存在哪", "放哪",
    "黄金存", "黄金放", "金条", "金块", "现金存",
    "银行卡密码", "保险密码",
    "编号", "号码",
    "密码是", "口令",
    "spot", "place", "where", "hide",
]

print("=" * 60)
print("=== chat_dump.txt 深度搜 ===")
print("=" * 60)
for kw in KW:
    matches = list(re.finditer(re.escape(kw), chat))
    if matches:
        print(f"\n[关键词: {kw}] 匹配 {len(matches)} 次")
        for m in matches[:5]:
            s = max(0, m.start() - 150)
            e = min(len(chat), m.end() + 250)
            ctx = chat[s:e].replace("\n", "\n  ")
            print(f"  @{m.start()}:\n  ...{ctx}...\n  {'-'*40}")

# 2. 看 chat_dump.txt 最后 500 行 (聊天最新内容)
print("\n" + "=" * 60)
print("=== chat_dump.txt 最后 5000 字符 (最新对话) ===")
print("=" * 60)
print(chat[-5000:])

# 3. 看 channels_dump.txt
print("\n" + "=" * 60)
print("=== channels_dump.txt 全部 ===")
print("=" * 60)
ch_text = (ROOT / "channels_dump.txt").read_text(encoding="utf-8", errors="ignore")
print(ch_text[:15000])  # 前 15000 字符

print("\n完成")
