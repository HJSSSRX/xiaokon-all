# -*- coding: utf-8 -*-
"""Extract SQLite databases from E01 and analyze them"""
import sys, io, os, struct, sqlite3, tempfile
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
import pyewf

E01 = r"A:\检材 手机\24CS_Phone.E01"
OUT_DIR = r"A:\phone_dbs"

def open_e01():
    filenames = pyewf.glob(E01)
    h = pyewf.handle()
    h.open(filenames)
    return h

def read_at(h, offset, size):
    h.seek(offset)
    return h.read(size)

def extract_sqlite(h, offset, out_path, max_size=50*1024*1024):
    """Extract SQLite database from E01 at given offset"""
    # Read SQLite header to get page size and page count
    header = read_at(h, offset, 100)
    if header[:16] != b'SQLite format 3\x00':
        return False
    
    page_size = struct.unpack('>H', header[16:18])[0]
    if page_size == 1:
        page_size = 65536
    
    # Database size in pages (at offset 28)
    db_pages = struct.unpack('>I', header[28:32])[0]
    if db_pages == 0:
        # Try reading file change counter to estimate
        db_pages = 100  # default guess
    
    db_size = page_size * db_pages
    if db_size > max_size:
        db_size = max_size
    if db_size < page_size:
        db_size = page_size * 10
    
    data = read_at(h, offset, db_size)
    with open(out_path, 'wb') as f:
        f.write(data)
    return True

def analyze_db(path):
    """Get table names and row counts from SQLite database"""
    try:
        conn = sqlite3.connect(path)
        conn.text_factory = lambda b: b.decode('utf-8', 'replace')
        cur = conn.cursor()
        cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [r[0] for r in cur.fetchall()]
        
        info = {'tables': tables, 'data': {}}
        for t in tables[:20]:
            try:
                cur.execute(f'SELECT COUNT(*) FROM "{t}"')
                count = cur.fetchone()[0]
                info['data'][t] = count
            except:
                info['data'][t] = -1
        
        conn.close()
        return info
    except Exception as e:
        return {'error': str(e), 'tables': [], 'data': {}}

def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    
    h = open_e01()
    total = h.get_media_size()
    
    # Find all SQLite databases
    print("[*] Scanning for SQLite databases...")
    CHUNK = 64 * 1024 * 1024
    sqlite_magic = b'SQLite format 3\x00'
    locations = []
    
    offset = 0
    while offset < total:
        data = read_at(h, offset, CHUNK)
        if not data:
            break
        pos = 0
        while pos < len(data) - 16:
            idx = data.find(sqlite_magic, pos)
            if idx < 0:
                break
            locations.append(offset + idx)
            pos = idx + 16
        offset += CHUNK - 256
    
    print(f"[*] Found {len(locations)} SQLite databases")
    
    # Extract and analyze each
    print("[*] Extracting and analyzing...")
    results = []
    
    for i, loc in enumerate(locations):
        db_path = os.path.join(OUT_DIR, f"db_{i:03d}_0x{loc:x}.sqlite")
        try:
            extract_sqlite(h, loc, db_path)
            info = analyze_db(db_path)
            tables = info.get('tables', [])
            data = info.get('data', {})
            
            # Classify
            tags = []
            tables_lower = ' '.join(tables).lower()
            
            if any(x in tables_lower for x in ['rcontact', 'enmicromsg', 'voiceinfo', 'fts_username']):
                tags.append('WeChat-main')
            elif any(x in tables_lower for x in ['message', 'session']) and 'wechat' not in tables_lower:
                tags.append('Messaging')
            if 'contacts' in tables_lower or 'raw_contacts' in tables_lower:
                tags.append('Contacts')
            if 'sms' in tables_lower or 'mmssms' in tables_lower:
                tags.append('SMS')
            if any(x in tables_lower for x in ['bookmark', 'browser', 'history', 'searches']):
                tags.append('Browser')
            if any(x in tables_lower for x in ['amap', 'autonavi', 'gaode']):
                tags.append('AMap')
            if any(x in tables_lower for x in ['mijia', 'smarthome', 'miot']):
                tags.append('MiJia')
            if any(x in tables_lower for x in ['package', 'install']):
                tags.append('Package')
            if any(x in tables_lower for x in ['account', 'user_info', 'userinfo']):
                tags.append('Account')
            if any(x in tables_lower for x in ['gedatalk', 'geda']):
                tags.append('GeDa')
            if any(x in tables_lower for x in ['walletbill', 'wallet', 'bill']):
                tags.append('Wallet')
            if any(x in tables_lower for x in ['photo', 'image', 'media']):
                tags.append('Media')
            if any(x in tables_lower for x in ['calllog', 'calls']):
                tags.append('CallLog')
            
            result = {
                'idx': i,
                'offset': loc,
                'path': db_path,
                'tables': tables,
                'data': data,
                'tags': tags,
            }
            results.append(result)
            
            if tags:
                total_rows = sum(v for v in data.values() if v > 0)
                print(f"  DB#{i:03d} @0x{loc:x} [{','.join(tags)}] tables={len(tables)} rows~{total_rows}")
                for t in tables[:8]:
                    cnt = data.get(t, '?')
                    print(f"    {t}: {cnt} rows")
                if len(tables) > 8:
                    print(f"    ... +{len(tables)-8} more tables")
            
        except Exception as e:
            if 'encrypted' in str(e).lower() or 'file is not a database' in str(e).lower():
                results.append({'idx': i, 'offset': loc, 'tags': ['ENCRYPTED'], 'tables': []})
                print(f"  DB#{i:03d} @0x{loc:x} [ENCRYPTED/CORRUPT]")
            # Skip failed ones silently
    
    h.close()
    
    # Summary
    print(f"\n{'='*60}")
    print(f"SUMMARY: {len(results)} databases analyzed")
    tag_counts = {}
    for r in results:
        for t in r.get('tags', []):
            tag_counts[t] = tag_counts.get(t, 0) + 1
    for tag, cnt in sorted(tag_counts.items(), key=lambda x: -x[1]):
        print(f"  {tag}: {cnt}")

if __name__ == '__main__':
    main()
