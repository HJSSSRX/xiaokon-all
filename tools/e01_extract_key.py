# -*- coding: utf-8 -*-
"""Extract key databases and query them for mobile forensic answers"""
import sys, io, struct, os, sqlite3
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
import pyewf

E01 = r"A:\检材 手机\24CS_Phone.E01"
OUT_DIR = r"F:\phone_extracted"
os.makedirs(OUT_DIR, exist_ok=True)

def open_e01():
    filenames = pyewf.glob(E01)
    h = pyewf.handle()
    h.open(filenames)
    return h

def read_at(h, offset, size):
    h.seek(offset)
    return h.read(size)

def extract_db(h, offset, name, size=2*1024*1024):
    """Extract database with generous size"""
    path = os.path.join(OUT_DIR, name)
    # Read header first to determine actual size
    header = read_at(h, offset, 100)
    if header[:16] != b'SQLite format 3\x00':
        print(f"  WARNING: Not SQLite at 0x{offset:x}")
        return None
    page_size = struct.unpack('>H', header[16:18])[0]
    if page_size == 1:
        page_size = 65536
    db_pages = struct.unpack('>I', header[28:32])[0]
    if db_pages > 0:
        actual_size = page_size * db_pages
        if actual_size < 100 * 1024 * 1024:  # cap at 100MB
            size = actual_size
    
    data = read_at(h, offset, size)
    with open(path, 'wb') as f:
        f.write(data)
    return path

def query_db(path, sql, max_rows=50):
    """Execute SQL on a database"""
    try:
        conn = sqlite3.connect(path)
        conn.text_factory = lambda b: b.decode('utf-8', 'replace')
        cur = conn.cursor()
        cur.execute(sql)
        rows = cur.fetchmany(max_rows)
        cols = [d[0] for d in cur.description] if cur.description else []
        conn.close()
        return cols, rows
    except Exception as e:
        return [], [('ERROR', str(e))]

def show_query(path, sql, label="", max_rows=20):
    cols, rows = query_db(path, sql, max_rows)
    if label:
        print(f"  [{label}]")
    if cols:
        print(f"  Columns: {cols}")
    for r in rows:
        print(f"    {r}")
    return rows

def main():
    h = open_e01()
    
    # Key databases to extract based on scan results:
    key_dbs = {
        'sms_608.db': 0x112799000,       # SMS with 51 messages
        'contacts_610.db': 0x1137e6000,   # Contacts with 177 contacts
        'browser_486.db': 0x10b1f6098,    # Browser bookmarks/history
        'telegram_1141.db': 0x28a4c8000,  # Telegram-style messaging (83 msgs, 25 dialogs)
        'messaging_1164.db': 0x28c24a000, # Messaging with user_info
        'account_986.db': 0x2134d5000,    # Account with userinfo/fileinfo
        'messaging_453.db': 0x9b222098,   # Messaging with accounts/topics/users
        'account_267.db': 0x891be098,     # Account with userinfo/auth
        'media_866.db': 0x209fea000,      # Media/account with documents/images
        'wechat_finder_821.db': 0x2083ca000, # WeChat Finder
        'messaging_442.db': 0x8f5b1204,   # Messaging with shareuserrecord
    }
    
    print("[*] Extracting key databases...")
    paths = {}
    for name, offset in key_dbs.items():
        path = extract_db(h, offset, name)
        if path:
            paths[name] = path
            fsize = os.path.getsize(path)
            print(f"  {name}: {fsize/1024:.0f} KB")
    
    h.close()
    
    # === Analyze each database ===
    
    # Q01: WeChat ID - check messaging databases for user info
    print("\n" + "="*60)
    print("Q01: WeChat ID")
    if 'messaging_1164.db' in paths:
        show_query(paths['messaging_1164.db'], "SELECT * FROM user_info", "user_info")
        show_query(paths['messaging_1164.db'], "SELECT * FROM recent_session", "recent_session")
    if 'account_267.db' in paths:
        show_query(paths['account_267.db'], "SELECT * FROM userinfo", "userinfo_267")
        show_query(paths['account_267.db'], "SELECT * FROM auth", "auth_267")
    if 'account_986.db' in paths:
        show_query(paths['account_986.db'], "SELECT * FROM userinfo", "userinfo_986")
    if 'messaging_442.db' in paths:
        show_query(paths['messaging_442.db'], "SELECT * FROM shareuserrecord", "shareuserrecord")
    
    # Q02: SMS - 宝塔验证码
    print("\n" + "="*60)
    print("Q02: 宝塔面板验证码 (SMS)")
    if 'sms_608.db' in paths:
        show_query(paths['sms_608.db'], 
            "SELECT address, date, body FROM sms ORDER BY date DESC LIMIT 30", "all_sms")
    
    # Q05: 高德地图 - check account databases
    print("\n" + "="*60)
    print("Q05: 高德地图 login ID")
    if 'media_866.db' in paths:
        show_query(paths['media_866.db'], "SELECT * FROM accounts", "accounts_866")
        show_query(paths['media_866.db'], "SELECT * FROM documents LIMIT 5", "documents_866")
    
    # Q10/Q11: Contacts
    print("\n" + "="*60)
    print("Q10/Q11: Contacts analysis")
    if 'contacts_610.db' in paths:
        show_query(paths['contacts_610.db'], 
            "SELECT name FROM sqlite_master WHERE type='table'", "tables")
        show_query(paths['contacts_610.db'],
            "SELECT * FROM accounts", "accounts")
        # Try to get contact names and numbers
        show_query(paths['contacts_610.db'],
            """SELECT display_name FROM contacts WHERE display_name IS NOT NULL 
               ORDER BY display_name LIMIT 20""", "contacts_sample")
    
    # Q13: 即时通讯 server IP (check telegram/messaging databases)
    print("\n" + "="*60)
    print("Q13: 即时通讯 server IP")
    if 'telegram_1141.db' in paths:
        show_query(paths['telegram_1141.db'], 
            "SELECT name FROM sqlite_master WHERE type='table'", "telegram_tables")
        show_query(paths['telegram_1141.db'],
            "SELECT * FROM dialogs LIMIT 10", "telegram_dialogs")
    if 'messaging_453.db' in paths:
        show_query(paths['messaging_453.db'],
            "SELECT * FROM accounts", "messaging_accounts")
        show_query(paths['messaging_453.db'],
            "SELECT * FROM users LIMIT 10", "messaging_users")
    
    # Q15: Browser - 双色球
    print("\n" + "="*60)
    print("Q15: Browser bookmarks/history (双色球)")
    if 'browser_486.db' in paths:
        show_query(paths['browser_486.db'],
            "SELECT * FROM bookmarks", "bookmarks")
        show_query(paths['browser_486.db'],
            "SELECT * FROM history", "history")
    
    # General: List all table schemas for unmatched databases
    print("\n" + "="*60)
    print("SCHEMAS of key databases:")
    for name, path in paths.items():
        cols, rows = query_db(path, "SELECT name, sql FROM sqlite_master WHERE type='table'")
        print(f"\n--- {name} ---")
        for r in rows:
            print(f"  {r[0]}: {str(r[1])[:120] if r[1] else 'no schema'}")

if __name__ == '__main__':
    main()
