# -*- coding: utf-8 -*-
"""Pass 2: Deep query extracted databases + targeted raw searches"""
import sys, io, struct, os, sqlite3, re
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
import pyewf

E01 = r"A:\检材 手机\24CS_Phone.E01"
DB_DIR = r"F:\phone_extracted"

def open_e01():
    filenames = pyewf.glob(E01)
    h = pyewf.handle()
    h.open(filenames)
    return h

def read_at(h, offset, size):
    h.seek(offset)
    return h.read(size)

def query_db(dbname, sql, max_rows=100):
    path = os.path.join(DB_DIR, dbname)
    if not os.path.exists(path):
        return [], []
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

def show(dbname, sql, label="", max_rows=30):
    cols, rows = query_db(dbname, sql, max_rows)
    if label:
        print(f"  [{label}]")
    if cols:
        print(f"  Cols: {cols}")
    for r in rows[:max_rows]:
        print(f"    {r}")
    return rows

def main():
    h = open_e01()
    total = h.get_media_size()
    
    # === Q01: Search for wxid_ in raw image (limited scan around known WeChat areas) ===
    print("="*60)
    print("Q01: WeChat ID - raw search for wxid_")
    
    # Search in chunks around known WeChat database offsets
    # WeChat Finder at 0x2083ca000, messaging at various locations
    # Also do a broader but bounded search
    wxids = set()
    CHUNK = 32 * 1024 * 1024
    
    # Scan key regions where WeChat data likely resides
    regions = [
        (0x10e00000, 0x11000000),   # ~32MB around WeChat area
        (0x18800000, 0x19400000),   # Another WeChat region
        (0x20800000, 0x21200000),   # WeChat Finder region
        (0x28a00000, 0x28d00000),   # Telegram/messaging region
    ]
    
    for start, end in regions:
        offset = start
        while offset < end and offset < total:
            sz = min(CHUNK, end - offset)
            data = read_at(h, offset, sz)
            pos = 0
            while pos < len(data):
                idx = data.find(b'wxid_', pos)
                if idx < 0:
                    break
                # Extract the full wxid
                end_idx = idx + 5
                while end_idx < len(data) and end_idx < idx + 30:
                    c = data[end_idx]
                    if c in range(ord('a'), ord('z')+1) or c in range(ord('A'), ord('Z')+1) or c in range(ord('0'), ord('9')+1) or c == ord('_'):
                        end_idx += 1
                    else:
                        break
                wxid = data[idx:end_idx].decode('ascii', 'replace')
                if len(wxid) > 8:
                    wxids.add(wxid)
                pos = end_idx
            offset += sz
    
    print(f"  Found {len(wxids)} unique wxid values:")
    for w in sorted(wxids):
        print(f"    {w}")
    
    # === Q05: 高德地图 - search for amap user config ===
    print("\n" + "="*60)
    print("Q05: 高德地图 login ID - raw search")
    
    amap_patterns = [b'amap_userid', b'user_id', b'userId']
    amap_region = (0xd000000, 0xe000000)  # Region where AMap DB was found
    data = read_at(h, amap_region[0], amap_region[1] - amap_region[0])
    
    for pattern in [b'com.autonavi.minimap']:
        idx = 0
        count = 0
        while count < 5:
            idx = data.find(pattern, idx)
            if idx < 0:
                break
            ctx = data[max(0,idx-50):idx+200].decode('utf-8', 'replace')
            safe = ''.join(c if c.isprintable() else '.' for c in ctx)
            print(f"  @+0x{idx:x}: {safe[:200]}")
            idx += len(pattern)
            count += 1
    
    # === Q10/Q11: Contacts - get all names and numbers ===
    print("\n" + "="*60)
    print("Q10/Q11: Contact names and numbers")
    
    # Get raw_contacts display name
    show('contacts_610.db', 
         """SELECT rc._id, rc.display_name, rc.display_name_alt 
            FROM raw_contacts rc WHERE rc.display_name IS NOT NULL 
            ORDER BY rc._id LIMIT 30""", "raw_contacts names")
    
    # Get phone numbers from data table (mimetype_id for phone is usually 5)
    show('contacts_610.db',
         """SELECT d.raw_contact_id, d.data1, d.data2 
            FROM data d WHERE d.mimetype_id = 5 
            ORDER BY d.raw_contact_id LIMIT 30""", "phone numbers")
    
    # Search for 季令柏
    show('contacts_610.db',
         """SELECT rc._id, rc.display_name FROM raw_contacts rc 
            WHERE rc.display_name LIKE '%季%' OR rc.display_name LIKE '%令%'""",
         "search 季令柏")
    
    # === Q13: 即时通讯 server IP (messaging_453 = Tinode/鸽哒?) ===
    print("\n" + "="*60)
    print("Q13: 鸽哒/即时通讯 - messaging_453")
    show('messaging_453.db', "SELECT * FROM accounts", "accounts")
    
    # === Telegram data for Q03 (鸽哒 might actually be Telegram fork?) ===
    print("\n" + "="*60)
    print("Telegram users and messages")
    show('telegram_1141.db', "SELECT uid, name, status FROM users LIMIT 20", "users")
    show('telegram_1141.db', 
         """SELECT mid, uid, date, out, send_state FROM messages_v2 
            ORDER BY date DESC LIMIT 10""", "recent messages")
    show('telegram_1141.db', "SELECT * FROM params", "params")
    
    # === messaging_442 (smart home messaging?) ===
    print("\n" + "="*60)
    print("messaging_442 (homeId/homeName -> 米家?)")
    show('messaging_442.db', 
         """SELECT name FROM sqlite_master WHERE type='table'""", "tables")
    # Try to query messagerecord with schema
    show('messaging_442.db',
         """SELECT * FROM messagerecord LIMIT 5""", "messagerecord")
    show('messaging_442.db',
         """SELECT * FROM shareuserrecord LIMIT 5""", "shareuserrecord")
    
    # === Q07: WeChat bill zip password - search for the zip file reference ===
    print("\n" + "="*60)
    print("Q07: WeChat bill password - search in raw image")
    # The zip password is usually sent via WeChat message or shown in the app
    # Search for '20220207' or 'zipPassword' or '解压密码' in known WeChat regions
    for start, end in [(0x10e00000, 0x11200000), (0x18800000, 0x19400000), (0x20800000, 0x21200000)]:
        data = read_at(h, start, end - start)
        for pattern in [b'20220207', b'\xe8\xa7\xa3\xe5\x8e\x8b\xe5\xaf\x86\xe7\xa0\x81']:
            idx = 0
            while True:
                idx = data.find(pattern, idx)
                if idx < 0:
                    break
                ctx = data[max(0,idx-100):idx+300].decode('utf-8', 'replace')
                safe = ''.join(c if c.isprintable() else '.' for c in ctx)
                if len(safe.strip('.')) > 20:
                    print(f"  @0x{start+idx:x}: {safe[:250]}")
                idx += len(pattern)
    
    h.close()
    print("\n[*] Pass 2 done.")

if __name__ == '__main__':
    main()
