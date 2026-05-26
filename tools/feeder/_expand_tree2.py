#!/usr/bin/env python3
"""Expand skill tree nodes - fixed version."""
import sys, time, json, os
sys.path.insert(0, 'D:/ai')
from tools.feeder.spa_crawler import SpaCrawler

c = SpaCrawler()

if not c.connect('ctfhub'):
    print('FAILED')
    sys.exit(1)

# Navigate to skilltree
print('Navigating to skilltree...')
c._send('Page.navigate', {'url': 'https://www.ctfhub.com/#/skilltree'})
time.sleep(3)
while c._recv_any(0.3):
    pass

# Show visible labels
labels = c.evaluate("""
    (function() {
        var labels = document.querySelectorAll('.org-tree-node-label-inner');
        var results = [];
        for (var i = 0; i < labels.length; i++) {
            var el = labels[i];
            var rect = el.getBoundingClientRect();
            results.push({
                text: el.innerText.trim(),
                className: el.className,
                cursor: window.getComputedStyle(el).cursor,
                rect: {left: Math.round(rect.left), top: Math.round(rect.top), w: Math.round(rect.width), h: Math.round(rect.height)}
            });
        }
        return results;
    })()
""")
print('\nVisible labels:')
for l in labels:
    print('  "{}" class={} cursor={} pos=({},{})'.format(
        l['text'], l['className'], l['cursor'], l['rect']['left'], l['rect']['top']))

# Now try to intercept API when clicking
# We'll do a fresh navigation, enable Network, click, and capture

print('\n=== Fresh load + click + intercept ===')
c._send('Page.navigate', {'url': 'https://www.ctfhub.com/#/skilltree'})
time.sleep(3)
while c._recv_any(0.3):
    pass

# Enable Network and clear pending
c._send('Network.enable')
c._send('Runtime.enable')
time.sleep(0.5)
while c._recv_any(0.3):
    pass

# Click Web node
click = c.evaluate("""
    (function() {
        var els = document.querySelectorAll('.org-tree-node-label-inner');
        for (var i = 0; i < els.length; i++) {
            if (els[i].innerText.trim() === 'Web') {
                els[i].click();
                return 'clicked Web at ' + i;
            }
        }
        // Try clicking by text content
        var all = document.querySelectorAll('*');
        for (var j = 0; j < all.length; j++) {
            if (all[j].innerText.trim() === 'Web' && all[j].children.length === 0) {
                all[j].click();
                return 'clicked Web leaf at ' + j;
            }
        }
        return 'not found';
    })()
""")
print('Click result:', click)

# Wait and collect ALL network responses
time.sleep(1)

collected_bodies = {}
mid_to_info = {}

deadline = time.time() + 5
while time.time() < deadline:
    msg = c._recv_any(0.3)
    if msg is None:
        continue

    method = msg.get('method', '')

    if method == 'Network.requestWillBeSent':
        url = msg['params']['request']['url']
        rid = msg['params']['requestId']
        if 'api' in url.lower() or 'skill' in url.lower() or 'tree' in url.lower() or 'node' in url.lower():
            print('  REQ:', url[:150])

    elif method == 'Network.responseReceived':
        url = msg['params']['response']['url']
        rid = msg['params']['requestId']
        if 'api' in url.lower() or 'skill' in url.lower() or 'tree' in url.lower() or 'node' in url.lower():
            mid = c._send('Network.getResponseBody', {'requestId': rid})
            mid_to_info[mid] = (url, rid)

    elif 'id' in msg:
        mid = msg.get('id')
        if mid in mid_to_info:
            url, rid = mid_to_info[mid]
            body = msg.get('result', {}).get('body', '')
            collected_bodies[url] = body
            print('  RESP {}: {} bytes'.format(url[:120], len(body)))
            if body:
                try:
                    parsed = json.loads(body)
                    print('    Parsed:', json.dumps(parsed, ensure_ascii=False)[:300])
                except:
                    print('    Raw:', body[:200])

print('\n=== Collected {} API responses ==='.format(len(collected_bodies)))

# Also check if the page state changed after clicking
print('\n=== Post-click DOM state ===')
labels2 = c.evaluate("""
    (function() {
        var labels = document.querySelectorAll('.org-tree-node-label-inner');
        var results = [];
        for (var i = 0; i < labels.length; i++) {
            results.push(labels[i].innerText.trim());
        }
        return results;
    })()
""")
print('Labels after click:', labels2)

# Check URL/route
route = c.evaluate("""
    (function() {
        var app = document.querySelector('#app');
        if (app && app.__vue__ && app.__vue__.$router)
            return app.__vue__.$router.currentRoute.path;
        return '?';
    })()
""")
print('Route after click:', route)

# Now try the other approach - maybe clicking navigates to a detail/child page
# Check if any router navigation happened
url = c.evaluate('window.location.href')
print('Full URL:', url)

# Try clicking on "Pwn" or another unexpanded node
print('\n=== Click on "Pwn" node ===')
c._send('Page.navigate', {'url': 'https://www.ctfhub.com/#/skilltree'})
time.sleep(3)
while c._recv_any(0.3):
    pass

# Try clicking more broadly - maybe the org-tree-node container handles the click
click_pwn = c.evaluate("""
    (function() {
        // Find the org-tree-node that contains Pwn
        var nodes = document.querySelectorAll('.org-tree-node');
        for (var i = 0; i < nodes.length; i++) {
            var inner = nodes[i].querySelector('.org-tree-node-label-inner');
            if (inner && inner.innerText.trim() === 'Pwn') {
                nodes[i].click();
                return 'clicked org-tree-node containing Pwn';
            }
        }
        // Try the full node including children
        var containers = document.querySelectorAll('.org-tree-node-label');
        for (var j = 0; j < containers.length; j++) {
            var inner2 = containers[j].querySelector('.org-tree-node-label-inner');
            if (inner2 && inner2.innerText.trim() === 'Pwn') {
                containers[j].click();
                return 'clicked org-tree-node-label containing Pwn';
            }
        }
        return 'not found';
    })()
""")
print('Click Pwn result:', click_pwn)
time.sleep(2)

# Check for any URL/route changes
route2 = c.evaluate("""
    (function() {
        var app = document.querySelector('#app');
        if (app && app.__vue__ && app.__vue__.$router)
            return app.__vue__.$router.currentRoute.path;
        return '?';
    })()
""")
print('Route after Pwn click:', route2)
url2 = c.evaluate('window.location.href')
print('URL after Pwn click:', url2)

c.close()
print('\nDone.')
