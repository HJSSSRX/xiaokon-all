#!/usr/bin/env python3
"""CTFHub EasyCleanup solver — file inclusion challenge."""
import sys, json, time, io, socket, requests
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.path.insert(0, 'D:/ai')
from tools.feeder.spa_crawler import SpaCrawler

c = SpaCrawler()
c.connect('ctfhub')

# Navigate to challenge page
c._send('Page.navigate', {'url': 'https://www.ctfhub.com/#/challenge'})
time.sleep(2)
while c._recv_any(0.3):
    pass

# Find and click EasyCleanup card
result = c.evaluate(
    'var cards=document.querySelectorAll(".ant-card-hoverable");'
    'var r="not found";'
    'for(var i=0;i<cards.length;i++){'
    'if(cards[i].textContent.indexOf("EasyCleanup")>=0){cards[i].click();r="clicked";break;}'
    '}'
    'r'
)
print(f'Click: {result}')
time.sleep(1.5)
while c._recv_any(0.3):
    pass

# Click start
c.evaluate(
    'var btns=document.querySelectorAll(".ant-modal button");'
    'var r="not found";'
    'for(var i=0;i<btns.length;i++){'
    'var t=btns[i].textContent.trim();'
    'if(t.indexOf("开启")>=0||t.indexOf("50")>=0){btns[i].click();r="clicked: "+t;break;}'
    '}'
    'r'
)
print('Started sandbox, waiting for it to be ready...')

# Poll for sandbox info — intercept API
body_requests = {}
captured = {}
deadline = time.time() + 30
while time.time() < deadline:
    msg = c._recv_any(1)
    if msg is None:
        continue
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

print(f'\nCaptured APIs: {list(captured.keys())}')
sandbox_info = None
for name, body in captured.items():
    try:
        data = json.loads(body)
        s = json.dumps(data, ensure_ascii=False)
        print(f'  {name}: {s[:500]}')
        if 'getInfo' in name:
            sandbox_info = data
    except:
        pass

# Read modal for target info
modal = c.evaluate(
    'var m=document.querySelector(".ant-modal"); m ? m.textContent : "NO_MODAL"'
)
print(f'\nModal text: {modal[:2000] if modal else "None"}')

# Find links
links = c.evaluate(
    'var as=document.querySelectorAll(".ant-modal a");'
    'var r=[];'
    'for(var i=0;i<as.length;i++){r.push(as[i].href+" | "+as[i].textContent.trim());}'
    'JSON.stringify(r)'
)
print(f'Links: {links}')
