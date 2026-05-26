#!/usr/bin/env python3
"""CTFHub challenge solver — launch sandbox and solve."""
import sys, json, time, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.path.insert(0, 'D:/ai')
from tools.feeder.spa_crawler import SpaCrawler

c = SpaCrawler()
c.connect('ctfhub')

# Navigate to challenge list
c._send('Page.navigate', {'url': 'https://www.ctfhub.com/#/challenge'})
time.sleep(2)
while c._recv_any(0.3):
    pass

# Click lemminx card to open modal
c.evaluate('''
(function(){
    var cards = document.querySelectorAll(".ant-card-hoverable");
    for(var i = 0; i < cards.length; i++){
        if(cards[i].textContent.indexOf("lemminx") >= 0){
            cards[i].click();
            return "clicked card";
        }
    }
    return "not found";
})()
''')
time.sleep(1.5)

# Drain
while c._recv_any(0.3):
    pass

# Find all buttons in modal
btns = c.evaluate(
    'JSON.stringify(Array.from(document.querySelectorAll(".ant-modal button")).map(function(b){return {text:b.textContent.trim(),cls:b.className};}))'
)
print('Modal buttons:', btns)

# Click the start button (with text '50' or '开启题目')
c.evaluate('''
(function(){
    var btns = document.querySelectorAll(".ant-modal button");
    for(var i = 0; i < btns.length; i++){
        var t = btns[i].textContent.trim();
        if(t.indexOf("50") >= 0 || t.indexOf("开启") >= 0){
            btns[i].click();
            return "clicked: " + t;
        }
    }
    return "not found";
})()
''')
time.sleep(1.5)

# Capture API responses
body_requests = {}
captured = {}
deadline = time.time() + 5
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

print(f'\nAPIs captured ({len(captured)}):')
for name, body in captured.items():
    data = json.loads(body)
    s = json.dumps(data, ensure_ascii=False)
    print(f'  {name}: {s[:500]}')
    # Save for analysis
    fname = f'D:/ai/ctfhub_solve_{name.replace("/", "_")}.json'
    with open(fname, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

# Check modal state
modal_text = c.evaluate(
    'var m=document.querySelector(".ant-modal"); return m ? m.textContent.substring(0, 500) : "no modal";'
)
print(f'\nModal: {modal_text}')
