"""
读 note.db 全部笔记内容 (UTF-8 输出)
"""
import sqlite3
import sys
import io
from pathlib import Path

# 让 stdout 使用 UTF-8 (避免 gbk encoding 错误)
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

DB = Path(r"E:\ffffff-JIANCAI\2026FIC团体赛\case\mobile_extract\note.db")

con = sqlite3.connect(str(DB))
cur = con.cursor()

# note 表
print("=" * 60)
print("=== note 表全部行 ===")
print("=" * 60)
cur.execute("SELECT _id, parent_id, created_date, modified_date, snippet, type, subject, title, plain_text, mind_content_plain_text FROM note")
rows = cur.fetchall()
for r in rows:
    nid, pid, cd, md, snippet, t, subj, title, plain, mind = r
    print(f"\n--- _id={nid}, type={t}, parent={pid} ---")
    print(f"created_date={cd}")
    print(f"modified_date={md}")
    print(f"title={title!r}")
    print(f"subject={subj!r}")
    print(f"snippet={snippet!r}")
    print(f"plain_text={plain!r}")
    print(f"mind_content_plain_text={mind!r}")

# data 表 (附件/富文本)
print("\n" + "=" * 60)
print("=== data 表全部行 ===")
print("=" * 60)
cur.execute("SELECT _id, mime_type, note_id, content, data1, data2 FROM data")
for r in cur.fetchall():
    print(f"\nrow: {r}")

con.close()
print("\n完成")
