"""
在 mobile_extract 中查找保险柜编号 + 密码 (computer Q9/Q10)
"""
import sqlite3
import re
from pathlib import Path

ROOT = Path(r"E:\ffffff-JIANCAI\2026FIC团体赛\case\mobile_extract")

KEYWORDS = [
    "保险", "保险柜", "保险箱", "金库", "safe", "vault",
    "编号", "密码", "password", "号码", "黄金",
    "钥匙", "口令", "锁", "code",
    "schließfach", "tresor",  # 保险柜的德语等
]


def search_db(db_path: Path):
    print(f"\n=== {db_path.name} ===")
    try:
        con = sqlite3.connect(str(db_path))
        cur = con.cursor()
        cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [r[0] for r in cur.fetchall()]
        print(f"Tables: {tables}")

        for tn in tables:
            cur.execute(f"PRAGMA table_info('{tn}')")
            cols = [c[1] for c in cur.fetchall()]
            print(f"\n[Table: {tn}] cols: {cols}")
            try:
                cur.execute(f"SELECT * FROM '{tn}' LIMIT 1000")
                rows = cur.fetchall()
                print(f"  Rows: {len(rows)}")
                # 关键词搜
                for r in rows:
                    s = " ".join(str(v) for v in r if v is not None)
                    for kw in KEYWORDS:
                        if kw in s:
                            print(f"  *** 命中 '{kw}': {s[:300]}")
                            break
            except Exception as e:
                print(f"  scan failed: {e}")
        con.close()
    except Exception as e:
        print(f"open failed: {e}")


# 1. note.db
search_db(ROOT / "note.db")

# 2. todo.db
search_db(ROOT / "todo.db")

# 3. mmssms.db (短信)
search_db(ROOT / "mmssms.db")

# 4. wechat-like wk_*.db (聊天)
for db in ROOT.glob("wk_*.db"):
    search_db(db)

# 5. chat_dump.txt
print("\n=== chat_dump.txt 关键词搜 ===")
chat = (ROOT / "chat_dump.txt").read_text(encoding="utf-8", errors="ignore")
for kw in KEYWORDS:
    for m in re.finditer(kw, chat):
        start = max(0, m.start() - 80)
        end = min(len(chat), m.end() + 200)
        snippet = chat[start:end].replace("\n", " | ")
        print(f"[{kw}] @{m.start()}: ...{snippet}...")

# 6. channels_dump.txt
print("\n=== channels_dump.txt 关键词搜 ===")
ch = (ROOT / "channels_dump.txt").read_text(encoding="utf-8", errors="ignore")
for kw in KEYWORDS:
    for m in re.finditer(kw, ch):
        start = max(0, m.start() - 80)
        end = min(len(ch), m.end() + 200)
        snippet = ch[start:end].replace("\n", " | ")
        print(f"[{kw}] @{m.start()}: ...{snippet}...")

print("\n完成")
