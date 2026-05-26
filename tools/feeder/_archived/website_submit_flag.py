#!/usr/bin/env python3
"""Submit WebsiteManger flag to CTFHub via CDP."""
import sys, time, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.path.insert(0, 'D:/ai')
from tools.feeder.spa_crawler import SpaCrawler

FLAG = "ctfhub{78acc17a373fb3f4e367b8a4}"

c = SpaCrawler()
c.connect('ctfhub')

# Navigate to challenge page
c._send('Page.navigate', {'url': 'https://www.ctfhub.com/#/challenge'})
print('Loading challenge page...')
time.sleep(3)
while c._recv_any(0.3): pass

# Wait for SPA
for i in range(6):
    body = c.evaluate('document.body ? document.body.textContent.substring(0, 200) : "no body"')
    if "We're sorry" not in str(body) and "no body" not in str(body):
        print('  SPA rendered after %d iterations' % (i+1))
        break
    if i < 5:
        print('  Waiting for SPA... (%d)' % (i+1))
        time.sleep(2)
        while c._recv_any(0.3): pass

# Find and click WebsiteManger card
result = c.evaluate(
    'var cards=document.querySelectorAll(".ant-card-hoverable");'
    'var r="not found";'
    'for(var i=0;i<cards.length;i++){'
    '  if(cards[i].textContent.indexOf("WebsiteManger")>=0){cards[i].click();r="clicked";break;}'
    '}'
    'r'
)
print('Click WebsiteManger: %s' % result)

time.sleep(2)
while c._recv_any(0.3): pass

# Check modal
modal = c.evaluate('var m=document.querySelector(".ant-modal"); m ? m.textContent.substring(0, 500) : "NO_MODAL"')
print('Modal: %s' % str(modal)[:300])

# Find flag input and fill it
fill_js = (
    'var inputs=document.querySelectorAll(".ant-modal input");'
    'var result="no flag input found";'
    'for(var i=0;i<inputs.length;i++){'
    '  var ph=inputs[i].placeholder||"";'
    '  if(ph.indexOf("Flag")>=0){'
    '    var setter=Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype,"value").set;'
    '    setter.call(inputs[i],"'+FLAG+'");'
    '    var ev=new Event("input",{bubbles:true});'
    '    inputs[i].dispatchEvent(ev);'
    '    result="filled";'
    '    break;'
    '  }'
    '}'
    'result'
)
flag_result = c.evaluate(fill_js)
print('Flag fill: %s' % flag_result)

# Click submit button
if 'filled' in str(flag_result):
    submit_js = (
        'var btns=document.querySelectorAll(".ant-modal button");'
        'var result="no submit btn";'
        'for(var i=0;i<btns.length;i++){'
        '  var t=btns[i].textContent.trim();'
        '  if(t.indexOf("提交Flag")>=0){'
        '    btns[i].click();'
        '    result="clicked: "+t;'
        '    break;'
        '  }'
        '}'
        'result'
    )
    submit_result = c.evaluate(submit_js)
    print('Submit: %s' % submit_result)
    time.sleep(3)
    while c._recv_any(0.3): pass

    # Check feedback
    fb = c.evaluate(
        'var els=document.querySelectorAll(".ant-message-notice-content,.ant-notification-notice");'
        'var r=[];'
        'for(var i=0;i<els.length;i++){r.push(els[i].textContent.trim());}'
        'r.length>0 ? JSON.stringify(r) : "no feedback visible"'
    )
    print('Feedback: %s' % fb)

print('Done!')
