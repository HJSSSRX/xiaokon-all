#!/usr/bin/env python3
"""CTFHub WebsiteManger solver — start sandbox and explore."""
import sys, json, time, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.path.insert(0, 'D:/ai')
from tools.feeder.spa_crawler import SpaCrawler

c = SpaCrawler()
c.connect('ctfhub')

# Navigate to challenge page
c._send('Page.navigate', {'url': 'https://www.ctfhub.com/#/challenge'})
print('Loading challenge page...')
time.sleep(5)
while c._recv_any(0.3): pass

# Check if SPA rendered
body = c.evaluate('document.body ? document.body.textContent.substring(0, 200) : "no body"')
if "We're sorry" in str(body):
    print('SPA not rendered, reloading...')
    c._send('Page.reload', {'ignoreCache': True})
    time.sleep(5)
    while c._recv_any(0.3): pass

# Find and click WebsiteManger card
result = c.evaluate(
    'var cards=document.querySelectorAll(".ant-card-hoverable");'
    'var r="not found";'
    'for(var i=0;i<cards.length;i++){'
    'if(cards[i].textContent.indexOf("WebsiteManger")>=0){cards[i].click();r="clicked WebsiteManger";break;}'
    '}'
    'r'
)
print(f'Click: {result}')

if result == 'not found':
    # Check if we need to go to next page
    page_info = c.evaluate(
        'var p=document.querySelector(".ant-pagination");'
        'p ? p.textContent : "no pagination"'
    )
    print(f'Pagination: {page_info}')
    # List visible cards
    cards = c.evaluate(
        'var cards=document.querySelectorAll(".ant-card-hoverable");'
        'var r=[];'
        'for(var i=0;i<cards.length;i++){r.push(cards[i].textContent.substring(0,60));}'
        'JSON.stringify(r)'
    )
    print(f'Visible cards: {cards}')

time.sleep(1.5)
while c._recv_any(0.3): pass

# Get modal
modal = c.evaluate('var m=document.querySelector(".ant-modal"); m ? m.textContent.substring(0, 3000) : "NO_MODAL"')
print(f'\nModal: {modal[:2000] if modal else "None"}')

# Capture API responses (especially Sandbox/getInfo)
body_requests = {}
captured = {}
deadline = time.time() + 8
while time.time() < deadline:
    msg = c._recv_any(0.5)
    if msg is None: continue
    msg_id = msg.get('id')
    method = msg.get('method', '')
    if msg_id and msg_id in body_requests:
        body = msg.get('result', {}).get('body', '')
        if body:
            short = body_requests.pop(msg_id)
            captured[short] = body
        continue
    if method == 'Network.responseReceived':
        url = msg['params']['response']['url']
        if 'api.ctfhub.com' in url:
            rid = msg['params']['requestId']
            c._msg_id += 1
            body_mid = c._msg_id
            short = url.split('User_API/')[-1].split('?')[0]
            body_requests[body_mid] = short
            c._send('Network.getResponseBody', {'requestId': rid}, msg_id=body_mid)

for name, body in captured.items():
    try:
        data = json.loads(body)
        print(f'  API {name}: {json.dumps(data, ensure_ascii=False)[:500]}')
    except:
        pass

# Click start button
start = c.evaluate(
    'var btns=document.querySelectorAll(".ant-modal button");'
    'var r="no button";'
    'for(var i=0;i<btns.length;i++){'
    'var t=btns[i].textContent.trim();'
    'if(t.indexOf("50")>=0||t.indexOf("开启")>=0||t.indexOf("启动")>=0){btns[i].click();r="clicked: "+t;break;}'
    '}'
    'r'
)
print(f'\nStart button: {start}')

# Wait for sandbox to be ready and get target
print('Waiting for sandbox...')
for i in range(8):
    time.sleep(2)
    while c._recv_any(0.3): pass
    modal2 = c.evaluate('var m=document.querySelector(".ant-modal"); m ? m.textContent : "NO_MODAL"')
    # Look for URL pattern in modal
    import re
    urls = re.findall(r'https?://[^\s]+', str(modal2))
    if urls:
        print(f'  [{i}] Found URLs: {urls}')
    # Check for target link
    links = c.evaluate(
        'var as=document.querySelectorAll(".ant-modal a");'
        'var r=[];'
        'for(var i=0;i<as.length;i++){var h=as[i].href;if(h&&h.indexOf("sandbox")>=0)r.push(h);}'
        'JSON.stringify(r)'
    )
    if links and links != '[]':
        print(f'  [{i}] Sandbox links: {links}')
        break
    # Print abbreviated modal text
    if modal2 and len(str(modal2)) > 100:
        print(f'  [{i}] Modal: {str(modal2)[:200]}')
