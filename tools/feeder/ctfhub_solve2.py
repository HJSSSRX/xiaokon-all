#!/usr/bin/env python3
"""CTFHub solver — find challenge attachment/target link."""
import sys, json, time, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.path.insert(0, 'D:/ai')
from tools.feeder.spa_crawler import SpaCrawler

c = SpaCrawler()
c.connect('ctfhub')

# Navigate and open lemminx modal
c._send('Page.navigate', {'url': 'https://www.ctfhub.com/#/challenge'})
time.sleep(2)
while c._recv_any(0.3):
    pass

# Click lemminx card
c.evaluate('''
(function(){
    var cards = document.querySelectorAll(".ant-card-hoverable");
    for(var i = 0; i < cards.length; i++){
        if(cards[i].textContent.indexOf("lemminx") >= 0){
            cards[i].click();
            return "clicked";
        }
    }
    return "not found";
})()
''')
time.sleep(1.5)
while c._recv_any(0.3):
    pass

# Dump modal content
modal_html = c.evaluate(
    'var m=document.querySelector(".ant-modal"); '
    'if(!m) return "NO_MODAL"; '
    'return m.innerHTML.substring(0, 3000);'
)
print('=== Modal HTML ===')
print(modal_html)

# Also dump full text
modal_text = c.evaluate(
    'var m=document.querySelector(".ant-modal"); '
    'if(!m) return "NO_MODAL"; '
    'return m.textContent;'
)
print('\n=== Modal Text ===')
print(modal_text[:1500] if modal_text else 'NO_MODAL')

# Capture all API responses
body_requests = {}
captured = {}
deadline = time.time() + 4
while time.time() < deadline:
    msg = c._recv_any(0.5)
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

print('\n=== APIs Captured ===')
for name, body in captured.items():
    data = json.loads(body)
    s = json.dumps(data, ensure_ascii=False)
    print(f'  {name}: {s[:600]}')
    with open(f'D:/ai/ctfhub_{name.replace("/", "_")}.json', 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
