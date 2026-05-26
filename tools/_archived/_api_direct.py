#!/usr/bin/env python3
"""Direct API approach: use CDP to execute fetch() calls from the SPA context,
bypassing UI clicking entirely. Gets node children by calling Skill/getTree."""
import sys, time, json, os
sys.path.insert(0, 'D:/ai')
from tools.feeder.spa_crawler import SpaCrawler

OUTPUT = 'D:/ai/tools/feeder/ctfhub_skilltree.json'
c = SpaCrawler()

if not c.connect('ctfhub'):
    print('FAILED')
    sys.exit(1)

# Navigate to skilltree first to get session cookies and CSRF tokens
print('Loading skilltree page...')
c._send('Page.navigate', {'url': 'https://www.ctfhub.com/#/skilltree'})
time.sleep(3)
while c._recv_any(0.3):
    pass

all_nodes = {}
STATE_MAP = {0: 'mastered', 1: 'learning', 2: 'unlearned'}

# Try to call the API directly via fetch in the page context
def fetch_tree_node(node_id):
    """Call Skill/getTree API via fetch() in the page context."""
    result = c.evaluate("""
        (function() {
            return fetch('/User_API/Skill/getTree', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({id: """ + str(node_id) + """})
            })
            .then(r => r.json())
            .then(data => JSON.stringify(data))
            .catch(e => JSON.stringify({error: e.message}));
        })()
    """, await_promise=True, timeout=15)
    return result

# Alternative: try GET request
def fetch_tree_get(node_id):
    """Call Skill/getTree with GET parameter."""
    result = c.evaluate("""
        (function() {
            return fetch('/User_API/Skill/getTree?id=""" + str(node_id) + """', {
                method: 'GET',
                headers: {'Content-Type': 'application/json'},
            })
            .then(r => r.json())
            .then(data => JSON.stringify(data))
            .catch(e => JSON.stringify({error: e.message}));
        })()
    """, await_promise=True, timeout=15)
    return result

# Try POST first
print('\n=== Fetching node 1 (root) ===')
resp = fetch_tree_node(1)
print('Response type:', type(resp))
if isinstance(resp, str):
    print('Response:', resp[:500])

# Try GET
print('\n=== Fetching node 1 via GET ===')
resp2 = fetch_tree_get(1)
print('Response:', str(resp2)[:500] if resp2 else 'None')

# If fetch doesn't work, try XMLHttpRequest
print('\n=== Trying XHR approach ===')
resp3 = c.evaluate("""
    (function() {
        return new Promise(function(resolve) {
            var xhr = new XMLHttpRequest();
            xhr.open('POST', '/User_API/Skill/getTree', true);
            xhr.setRequestHeader('Content-Type', 'application/json');
            xhr.onload = function() {
                resolve(xhr.responseText);
            };
            xhr.onerror = function() {
                resolve(JSON.stringify({error: 'xhr error'}));
            };
            xhr.send(JSON.stringify({id: 1}));
        });
    })()
""", await_promise=True, timeout=15)
print('XHR response:', str(resp3)[:500] if resp3 else 'None')

# Also try to use the Vue component's own API call method
print('\n=== Trying Vue component data ===')
vue_data = c.evaluate("""
    (function() {
        // Find the skill tree component and check its data
        var app = document.querySelector('#app');
        if (!app || !app.__vue__) return 'no vue';

        function findData(vm, depth) {
            if (depth > 6 || !vm) return null;
            var data = vm.$data;
            if (data) {
                var keys = Object.keys(data).filter(function(k) {
                    return k[0] !== '$' && k[0] !== '_';
                });
                var treeKeys = keys.filter(function(k) {
                    return /tree|data|node|skill|list/i.test(k);
                });
                if (treeKeys.length > 0) {
                    var snap = {name: (vm.$options && vm.$options.name) || '', treeKeys: treeKeys};
                    for (var i = 0; i < treeKeys.length; i++) {
                        try {
                            var val = JSON.parse(JSON.stringify(data[treeKeys[i]]));
                            snap[treeKeys[i]] = val;
                        } catch(e) {
                            snap[treeKeys[i]] = 'error';
                        }
                    }
                    return snap;
                }
            }
            if (vm.$children) {
                for (var i = 0; i < vm.$children.length; i++) {
                    var found = findData(vm.$children[i], depth + 1);
                    if (found) return found;
                }
            }
            return null;
        }

        return findData(app.__vue__, 0);
    })()
""", timeout=20)

print('Vue component data:')
if isinstance(vue_data, dict):
    print(json.dumps(vue_data, ensure_ascii=False, indent=2)[:3000])
else:
    print(str(vue_data)[:2000])

# ---- Use the proven intercept_api approach for the full tree ----
print('\n=== Using intercept_api to get full tree ===')
# Navigate to index first, then push skilltree
c._send('Page.navigate', {'url': 'https://www.ctfhub.com/#/index'})
time.sleep(2)
while c._recv_any(0.3):
    pass

# Now intercept the getTree call during route push
c._send('Network.enable')
time.sleep(0.3)
while c._recv_any(0.3):
    pass

c._send('Page.navigate', {'url': 'https://www.ctfhub.com/#/skilltree'})
time.sleep(3)

# Collect ALL network responses, not just getTree
mid_to_info = {}
responses = {}
deadline = time.time() + 8
while time.time() < deadline:
    msg = c._recv_any(0.3)
    if msg is None:
        continue
    method = msg.get('method', '')
    if method == 'Network.responseReceived':
        url = msg['params']['response']['url']
        status = msg['params']['response']['status']
        # Capture all API calls
        if 'api' in url.lower() or 'User_API' in url or 'Skill' in url:
            rid = msg['params']['requestId']
            mid = c._send('Network.getResponseBody', {'requestId': rid})
            mid_to_info[mid] = url
            print('  Response: {} (status={})'.format(url[:120], status))
    elif method == 'Network.requestWillBeSent':
        url = msg['params']['request']['url']
        if 'api' in url.lower() or 'User_API' in url or 'Skill' in url:
            print('  Request: {}'.format(url[:120]))
    elif 'id' in msg:
        mid = msg.get('id')
        if mid in mid_to_info:
            body = msg.get('result', {}).get('body', '')
            url = mid_to_info[mid]
            try:
                responses[url] = json.loads(body)
            except:
                responses[url] = body
            print('  Body for {}: {} bytes'.format(url.split('/')[-1][:40], len(body)))

print('\nAll API responses:')
root = None
for url, data in responses.items():
    if isinstance(data, dict):
        print('  {} -> keys: {}'.format(url.split('/')[-1][:40], list(data.keys())[:5]))
        if 'data' in data:
            node = data['data']
            nid = node.get('id')
            title = node.get('title', '?')
            children = node.get('children', [])
            print('    Node: "{}" (id={}) with {} children'.format(title, nid, len(children)))
            if nid:
                all_nodes[nid] = node
            if nid == 1:
                root = node
    else:
        print('  {} -> raw ({} chars)'.format(url.split('/')[-1][:40], len(str(data))))

if not root:
    print('\nNo root found. Trying alternate approach...')
    # The API call might have different params
    # Let me check what requests were actually made
    print('Checking all network requests...')
    # Re-navigate and capture ALL requests
    c._send('Page.navigate', {'url': 'https://www.ctfhub.com/#/index'})
    time.sleep(2)
    while c._recv_any(0.3):
        pass
    c._send('Page.navigate', {'url': 'https://www.ctfhub.com/#/skilltree'})
    time.sleep(4)
    # Print all requests
    deadline = time.time() + 5
    while time.time() < deadline:
        msg = c._recv_any(0.2)
        if msg and msg.get('method') == 'Network.requestWillBeSent':
            url = msg['params']['request']['url']
            print('  REQ:', url[:150])
        elif msg and msg.get('method') == 'Network.responseReceived':
            url = msg['params']['response']['url']
            print('  RESP:', url[:150])

# Save what we have
if all_nodes:
    print('\n=== Saving partial data ===')
    output = {
        'captured_at': time.strftime('%Y-%m-%d %H:%M:%S'),
        'nodes': {str(k): v for k, v in all_nodes.items()},
        'root': root,
        'api_responses': {k: v for k, v in responses.items() if isinstance(v, dict)},
    }
    with open(OUTPUT, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print('Saved:', os.path.getsize(OUTPUT), 'bytes')

c.close()
print('Done!')
