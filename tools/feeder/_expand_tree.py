#!/usr/bin/env python3
"""Expand skill tree nodes by clicking them to trigger lazy-load API calls."""
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

# Enable Network
c._send('Network.enable')
time.sleep(0.5)
while c._recv_any(0.3):
    pass

# Check current page
route = c.evaluate("""
    (function() {
        var app = document.querySelector('#app');
        if (app && app.__vue__ && app.__vue__.$router)
            return app.__vue__.$router.currentRoute.path;
        return '?';
    })()
""")
print('Route:', route)

# First, let's see what Vue component is rendering the skill tree
# by searching for all visible labels
labels = c.evaluate("""
    (function() {
        var labels = document.querySelectorAll('.org-tree-node-label-inner');
        var results = [];
        for (var i = 0; i < labels.length; i++) {
            var el = labels[i];
            results.push({
                text: el.innerText.trim(),
                className: el.className,
                onclick: el.onclick ? 'has onclick' : 'no onclick',
                parentClickable: el.parentElement.onclick ? 'parent has onclick' : 'parent no onclick',
                cursor: window.getComputedStyle(el).cursor,
                rect: el.getBoundingClientRect()
            });
        }
        return results;
    })()
""")
print('\nVisible labels:')
for l in labels:
    print('  "{}" class={} cursor={} ({},{})'.format(
        l['text'], l['className'], l['cursor'],
        int(l['rect']['x']), int(l['rect']['y'])))

# Try clicking the "Web" node and intercept any API call
print('\n=== Clicking on "Web" node ===')

# First, capture the click
click_result = c.evaluate("""
    (function() {
        var labels = document.querySelectorAll('.org-tree-node-label-inner');
        for (var i = 0; i < labels.length; i++) {
            if (labels[i].innerText.trim() === 'Web') {
                // Try clicking the label or its parent
                labels[i].click();
                return 'clicked label';
            }
        }
        // Try broader search
        var allEls = document.querySelectorAll('*');
        for (var i = 0; i < allEls.length; i++) {
            if (allEls[i].innerText.trim() === 'Web' && allEls[i].children.length === 0) {
                allEls[i].click();
                return 'clicked leaf: ' + allEls[i].tagName;
            }
        }
        return 'not found';
    })()
""")
print('Click result:', click_result)
time.sleep(2)

# Check if any network requests were triggered
print('Checking for new network activity...')
network_msgs = []
deadline = time.time() + 3
while time.time() < deadline:
    msg = c._recv_any(0.5)
    if msg:
        method = msg.get('method', '')
        if 'Network' in method:
            network_msgs.append(method)
            if method == 'Network.responseReceived':
                url = msg.get('params', {}).get('response', {}).get('url', '')
                if 'api' in url.lower() or 'skill' in url.lower():
                    rid = msg['params']['requestId']
                    c._send('Network.getResponseBody', {'requestId': rid})
                    print('  API response URL:', url)
            if method == 'Network.requestWillBeSent':
                url = msg.get('params', {}).get('request', {}).get('url', '')
                if 'api' in url.lower() or 'skill' in url.lower():
                    print('  API request:', url)
        if 'id' in msg and msg.get('id') and msg.get('id', 0) > 10:
            result = msg.get('result', {})
            if 'body' in result:
                body = result['body']
                print('  Response body ({} chars): {}'.format(len(body), body[:500]))

print('Network messages captured:', len(network_msgs))
for m in network_msgs:
    print('  ', m)

# Also try clicking the parent .org-tree-node-label element
print('\n=== Clicking on Web parent container ===')
click2 = c.evaluate("""
    (function() {
        var labels = document.querySelectorAll('.org-tree-node-label');
        for (var i = 0; i < labels.length; i++) {
            var inner = labels[i].querySelector('.org-tree-node-label-inner');
            if (inner && inner.innerText.trim() === 'Web') {
                labels[i].click();
                return 'clicked parent label';
            }
        }
        return 'not found';
    })()
""")
print('Click result:', click2)
time.sleep(2)

# Let's try using the Vue component directly
print('\n=== Checking Vue event handlers ===')
vue_info = c.evaluate("""
    (function() {
        var app = document.querySelector('#app');
        if (!app || !app.__vue__) return 'no vue';

        // Search ALL components for tree data
        function searchAll(vm, depth, path) {
            if (depth > 6 || !vm) return [];
            var results = [];
            var name = (vm.$options && vm.$options.name) || '';

            // Check if this component has tree-relevant data
            if (vm.$data) {
                var keys = Object.keys(vm.$data).filter(function(k) {
                    return k[0] !== '$' && k[0] !== '_';
                });
                var treeKeys = keys.filter(function(k) {
                    return /tree|node|skill|data/i.test(k);
                });
                if (treeKeys.length > 0) {
                    var snap = {name: name, path: path, depth: depth, treeKeys: treeKeys};
                    for (var i = 0; i < treeKeys.length; i++) {
                        try {
                            var val = JSON.parse(JSON.stringify(vm.$data[treeKeys[i]]));
                            snap[treeKeys[i]] = val;
                        } catch(e) {
                            snap[treeKeys[i]] = 'error: ' + e.message;
                        }
                    }
                    results.push(snap);
                }
            }

            if (vm.$children) {
                for (var i = 0; i < vm.$children.length; i++) {
                    results = results.concat(
                        searchAll(vm.$children[i], depth + 1,
                            path + (path ? '/' : '') + name)
                    );
                }
            }
            return results;
        }

        return searchAll(app.__vue__, 0, '');
    })()
""", timeout=20)

if isinstance(vue_info, list):
    for item in vue_info:
        print(json.dumps(item, ensure_ascii=False, indent=2)[:2000])
elif isinstance(vue_info, str):
    print(vue_info)

# Also try to intercept API by re-navigating and clicking immediately
print('\n=== Attempt 2: Navigate then click and intercept ===')
c._send('Page.navigate', {'url': 'https://www.ctfhub.com/#/skilltree'})
time.sleep(3)
while c._recv_any(0.3):
    pass

# Enable network again
c._send('Network.enable')
time.sleep(0.3)
while c._recv_any(0.3):
    pass

# Now try clicking Web and capture
click3 = c.evaluate("""
    (function() {
        var els = document.querySelectorAll('.org-tree-node-label-inner');
        for (var i = 0; i < els.length; i++) {
            if (els[i].innerText.trim() === 'Web') {
                els[i].click();
                return 'clicked';
            }
        }
        return 'not found';
    })()
""")
print('Click:', click3)

# Collect network responses for 3 seconds
collected = {}
request_urls = {}
deadline = time.time() + 5
while time.time() < deadline:
    msg = c._recv_any(0.5)
    if msg:
        method = msg.get('method', '')
        if method == 'Network.requestWillBeSent':
            url = msg['params']['request']['url']
            rid = msg['params']['requestId']
            request_urls[rid] = url
        elif method == 'Network.responseReceived':
            url = msg['params']['response']['url']
            rid = msg['params']['requestId']
            # Get response body
            mid = c._send('Network.getResponseBody', {'requestId': rid})
            collected[mid] = (rid, url)
        elif 'id' in msg:
            mid = msg.get('id')
            if mid in collected:
                rid, url = collected[mid]
                body = msg.get('result', {}).get('body', '')
                print('  [{}] {}'.format(url[:120], len(body)))

c.close()
print('\nDone.')
