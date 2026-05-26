#!/usr/bin/env python3
"""Submit flag to CTFHub EasyCleanup."""
import sys, json, time, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.path.insert(0, 'D:/ai')
from tools.feeder.spa_crawler import SpaCrawler

c = SpaCrawler()
c.connect('ctfhub')

# Navigate to challenge - first go to about:blank to clear state
c._send('Page.navigate', {'url': 'about:blank'})
time.sleep(1)
while c._recv_any(0.3): pass

c._send('Page.navigate', {'url': 'https://www.ctfhub.com/#/challenge'})
time.sleep(5)
while c._recv_any(0.3): pass

# Force a reload if SPA didn't render
c._send('Page.reload', {'ignoreCache': True})
time.sleep(5)
while c._recv_any(0.3): pass

# Verify we're on the right page
page_url = c.evaluate('document.location.href')
print(f'Current URL: {page_url}')

# Debug page state - wait longer for SPA to render
print('Waiting for SPA to render...')
for i in range(10):
    time.sleep(2)
    while c._recv_any(0.3): pass
    body_text = c.evaluate('document.body ? document.body.textContent.substring(0, 200) : "no body"')
    has_vue = 'We\'re sorry' not in (body_text or '')
    print(f'  [{i}] hasVue={has_vue}')
    if has_vue:
        break

page_title = c.evaluate('document.title')
print(f'Page title: {page_title}')

body_text = c.evaluate('document.body ? document.body.textContent.substring(0, 500) : "no body"')
print(f'Body text: {body_text}')

# Check for various card selectors
for sel in ['.ant-card', '.ant-card-hoverable', '.challenge-card', '.card', '[class*=card]']:
    count = c.evaluate(f'document.querySelectorAll("{sel}").length')
    print(f'{sel}: {count} elements')

# Click EasyCleanup
c.evaluate(
    'var cards=document.querySelectorAll(".ant-card-hoverable");'
    'var r="not found";'
    'for(var i=0;i<cards.length;i++){'
    'if(cards[i].textContent.indexOf("EasyCleanup")>=0){cards[i].click();r="clicked";break;}'
    '}'
    'r'
)
time.sleep(1.5)
while c._recv_any(0.3): pass

# Check modal state
modal = c.evaluate('var m=document.querySelector(".ant-modal"); m ? m.textContent.substring(0, 1000) : "NO_MODAL"')
print(f'Modal: {modal[:500] if modal else "None"}')

# Dump ALL form elements in modal
form_info = c.evaluate(
    'var m=document.querySelector(".ant-modal");'
    'var r={};'
    'if(!m){r.error="no modal";} else {'
    'r.inputs=[];'
    'var inputs=m.querySelectorAll("input,textarea");'
    'for(var i=0;i<inputs.length;i++){'
    'r.inputs.push({tag:inputs[i].tagName,type:inputs[i].type,placeholder:inputs[i].placeholder,className:inputs[i].className.substring(0,100)});'
    '}'
    'r.buttons=[];'
    'var btns=m.querySelectorAll("button");'
    'for(var i=0;i<btns.length;i++){'
    'r.buttons.push({text:btns[i].textContent.trim().substring(0,50),className:btns[i].className.substring(0,100)});'
    '}'
    '}'
    'JSON.stringify(r)'
)
print(f'Form elements: {form_info}')

# Type the flag into the input
# First find the right input - look for flag submission input
c.evaluate(
    'var m=document.querySelector(".ant-modal");'
    'var r="no input";'
    'if(m){'
    'var inputs=m.querySelectorAll("input,textarea");'
    'for(var i=0;i<inputs.length;i++){'
    'var inp=inputs[i];'
    'var nativeInputValueSetter=Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype,"value").set;'
    'nativeInputValueSetter.call(inp,"ctfhub{0846d9d27bf0089a8e204d02}");'
    'inp.dispatchEvent(new Event("input",{bubbles:true}));'
    'inp.dispatchEvent(new Event("change",{bubbles:true}));'
    'r="filled input "+i+": type="+inp.type+" placeholder="+inp.placeholder;'
    '}'
    '}'
    'r'
)
time.sleep(0.5)

# Click submit - try all likely buttons
c.evaluate(
    'var m=document.querySelector(".ant-modal");'
    'var r="no button";'
    'if(m){'
    'var btns=m.querySelectorAll("button");'
    'for(var i=0;i<btns.length;i++){'
    'var t=btns[i].textContent.trim();'
    'if(t.indexOf("提交")>=0||t.indexOf("submit")>=0||t.indexOf("Submit")>=0||t.indexOf("Flag")>=0||t.indexOf("flag")>=0){btns[i].click();r="clicked button: "+t;break;}'
    '}'
    '}'
    'r'
)
time.sleep(2)
while c._recv_any(0.3): pass

# Check messages
msg = c.evaluate('var m=document.querySelector(".ant-message"); m ? m.textContent : "no message"')
print(f'Message: {msg}')
modal2 = c.evaluate('var m=document.querySelector(".ant-modal"); m ? m.textContent.substring(0, 500) : "NO_MODAL"')
print(f'Modal after: {modal2[:300] if modal2 else "None"}')
