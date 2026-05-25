---
tags: [email_forensics, deepin, foxmail, eml, sqlite, rsa, attachment, computer_forensics]
tools: [python, sqlite3, grep, find, email_module]
category: computer_forensics
difficulty: medium
source: fic2026
date: 2026-05-05
verified: true
---

# Title: Deepin-mail / Foxmail 邮件取证

## Problem
从 UOS/Deepin Linux 系统中提取邮件内容、附件、联系方式等。

## Solution Steps

1. 定位邮件数据
   ```
   # deepin-mail
   ~/.local/share/deepin/deepin-mail/
   ├── mail/db/deepin_mail.V.2.0.db    ← SQLite 元数据
   └── imap.<server>/<account>/imap/
       └── <folder_id>/mail.eml         ← 原始邮件

   # Foxmail
   ~/Foxmail 7.2/Storage/<account>/
   ├── Inbox/   (*.emlx 或 *.box)
   └── Cache/
   ```

2. 查询邮件数据库
   ```bash
   sqlite3 deepin_mail.V.2.0.db ".tables"
   sqlite3 deepin_mail.V.2.0.db \
     "SELECT subject, sender, hasAttachment FROM MailMeta WHERE hasAttachment=1;"
   ```

3. **建全量索引（核心步骤）**
   ```python
   from email import policy
   from email.parser import BytesParser
   from pathlib import Path
   import re, html

   base = Path('/path/to/imap/')
   for p in sorted(base.glob('*/mail.eml')):
       raw = p.read_bytes()
       msg = BytesParser(policy=policy.default).parsebytes(raw)
       subj = msg.get('subject', '')
       frm = msg.get('from', '')
       date = msg.get('date', '')
       atts = [part.get_filename() for part in msg.walk() if part.get_filename()]
       texts = []
       for part in msg.walk():
           if part.get_content_type() in ('text/plain', 'text/html'):
               try: t = part.get_content()
               except: t = ''
               t = html.unescape(re.sub('<[^>]+>', ' ', str(t)))
               texts.append(t[:500])
       print(f"FROM: {frm}\nDATE: {date}\nSUBJ: {subj}")
       print(f"ATTS: {atts}\nBODY: {' '.join(texts)[:200]}\n---")
   ```

4. 关键词搜索
   ```python
   keywords = ['黄金', '收购', '换现金', '推广设计图', '解密', '私钥',
               '公钥', '勒索', '联系方式', '保险柜', '编号', '密码',
               'token', '钓鱼', 'http', '@']
   ```

5. 处理加密附件
   ```bash
   # 全盘搜索 RSA 私钥
   grep -rl 'BEGIN RSA PRIVATE\|BEGIN PRIVATE' /tmp/pc_data/ 2>/dev/null
   ```

## Key Takeaways
- **先建索引再搜** — 不要逐个 eml 手动看
- deepin-mail 附件缓存在 `att/` 子目录
- 注意编码: deepin-mail 可能是 quoted-printable + GB18030
- RSA 解密题: 找到 `public.txt` 后立刻全盘搜私钥特征串
- 搜索命令:
  ```bash
  find /tmp/pc_data -name 'mail.eml' -o -name '*.eml' -o -name '*.emlx'
  find /tmp/pc_data -name 'deepin_mail*' -o -name '*.db' | xargs -I{} sqlite3 {} ".tables"
  ```
