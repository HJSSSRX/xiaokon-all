"""
深查 todo.db 全部 + chat_dump.txt 关键场景 + sqlcipher
"""
import sys
import io
import re
import sqlite3
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

ROOT = Path(r"E:\ffffff-JIANCAI\2026FIC团体赛\case\mobile_extract")

# 1. todo.db 全部
print("=" * 60)
print("=== todo.db 完整 ===")
print("=" * 60)
con = sqlite3.connect(str(ROOT / "todo.db"))
cur = con.cursor()
cur.execute("SELECT id, content, plain_text, snippet, is_finish, create_time, expire_time, label, category FROM todo ORDER BY id")
for r in cur.fetchall():
    print(f"\nid={r[0]} finish={r[4]} create={r[5]} expire={r[6]} cat={r[8]} label={r[7]}")
    print(f"  content: {r[1]!r}")
    print(f"  plain_text: {r[2]!r}")
    print(f"  snippet: {r[3]!r}")
con.close()

# 2. chat_dump.txt 黄金/挖矿/搬/藏/号码 上下文
print("\n" + "=" * 60)
print("=== chat 关键剧情(挖矿/搬/号码)上下文 ===")
print("=" * 60)
chat = (ROOT / "chat_dump.txt").read_text(encoding="utf-8", errors="ignore")

# LHA 1247 黄金对话上下文 (前 50 后 100 条)
PATTERNS = [
    r"\[1[12]\d\d\]\[(LHA|OTHER)\][^[]*",  # 1100-1299
    r"\[1[34]\d\d\]\[(LHA|OTHER)\][^[]*",  # 1300-1499
    r"\[1[56]\d\d\]\[(LHA|OTHER)\][^[]*",  # 1500-1699
]

# 直接显示 chat 关键段
for keyword in ["黄金", "挖矿", "搬", "号", "藏", "金条", "锁码"]:
    matches = list(re.finditer(keyword, chat))
    if matches:
        print(f"\n--- 关键词 '{keyword}' (匹配 {len(matches)} 次) ---")
        for m in matches:
            s = max(0, m.start() - 100)
            e = min(len(chat), m.end() + 200)
            ctx = chat[s:e]
            print(f"@{m.start()}: ...{ctx}...")
            print()

# 3. 显示 chat 末尾 (1200-1254 全部)
print("\n" + "=" * 60)
print("=== chat 1200-1254 (最后剧情) ===")
print("=" * 60)
m1200 = chat.find("[1200]")
m1255 = chat.find("[1255]")
if m1200 > 0:
    end = m1255 if m1255 > 0 else len(chat)
    print(chat[m1200:end])

# 4. 看 chat 1246-1252 详细
print("\n" + "=" * 60)
print("=== 关键: 1246-1253 (黄金/挖矿) ===")
print("=" * 60)
for i in range(1245, 1255):
    pat = rf"\[{i}\]\[(LHA|OTHER)\]\[ts=\d+\][^[]*"
    m = re.search(pat, chat)
    if m:
        print(f"  {m.group(0)}")

# 5. wk_*.db 试 sqlcipher
print("\n" + "=" * 60)
print("=== wk_*.db 状态 ===")
print("=" * 60)
import shutil
for db in ROOT.glob("wk_*.db"):
    print(f"\n文件: {db.name}, 大小: {db.stat().st_size}")
    with db.open("rb") as f:
        head = f.read(16)
    print(f"前 16 字节: {head.hex()}")
    if head[:6] == b"SQLite":
        print("  -> 普通 SQLite (不加密)")
    else:
        print("  -> 不是普通 SQLite (可能 sqlcipher 加密)")

print("\n完成")
