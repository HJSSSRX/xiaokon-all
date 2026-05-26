#!/usr/bin/env python3
"""Final skill tree crawler - uses intercept_api properly for each node.

Key insight: `intercept_api` with route='/skilltree' triggers the SPA to load
the full tree via Skill/getTree API. Each node click also triggers the API.
By using intercept_api for the initial load, we get the FULL nested tree.

Then we click each category node to expand its children (which may be truncated
in the initial response for non-logged-in users).
"""
import sys, time, json, os
sys.path.insert(0, 'D:/ai')
from tools.feeder.spa_crawler import SpaCrawler

OUTPUT = 'D:/ai/tools/feeder/ctfhub_skilltree.json'
c = SpaCrawler()

if not c.connect('ctfhub'):
    print('FAILED')
    sys.exit(1)

all_nodes = {}
STATE_MAP = {0: 'mastered', 1: 'learning', 2: 'unlearned'}

# ================================================================
# Phase 1: Get initial full tree via intercept_api
# ================================================================
print('=== Phase 1: Full tree via intercept_api ===')

apis = c.intercept_api('ctfhub', '/skilltree', 'getTree', timeout=20)

root = None
for name, body in apis.items():
    try:
        data = json.loads(body)
    except:
        continue
    if isinstance(data, dict) and 'data' in data:
        node = data['data']
        nid = node.get('id')
        if nid:
            all_nodes[nid] = node
        if not root or (nid and nid < root.get('id', 9999)):
            root = node
        print('API "{}": node "{}" (id={}) with {} children'.format(
            name, node.get('title'), nid, len(node.get('children', []))))

if not root:
    print('ERROR: No root!')
    c.close()
    sys.exit(1)

# Print initial tree
def print_tree(node, indent=0, visited=None):
    if visited is None:
        visited = set()
    nid = node.get('id')
    if nid in visited:
        print('{}  (circular ref to id={})'.format('  ' * indent, nid))
        return
    visited.add(nid)

    prefix = '  ' * indent
    state = STATE_MAP.get(node.get('user_record_skill_state'), '?')
    task_id = node.get('task_id', 0)
    title = node.get('title', '?')
    children = node.get('children', [])

    if task_id:
        task_title = (node.get('task_title') or '')[:50]
        print('{}[{}] {} [TASK id={}] "{}" (solves={})'.format(
            prefix, state, title, task_id, task_title,
            node.get('finish_count', 0)))
    else:
        n_ch = len(children)
        print('{}[{}] {} (id={}, {} children)'.format(
            prefix, state, title, nid, n_ch))

    for child in children:
        if child.get('id') in all_nodes and child['id'] != nid:
            print_tree(all_nodes[child['id']], indent + 1, visited.copy())
        else:
            print_tree(child, indent + 1, visited.copy())

print('\nInitial tree:')
print_tree(root)

# ================================================================
# Phase 2: Click each category to expand children
# ================================================================

def click_label(text):
    return c.evaluate("""
        (function() {
            var labels = document.querySelectorAll('.org-tree-node-label-inner');
            for (var i = 0; i < labels.length; i++) {
                if (labels[i].innerText.trim() === arguments[0]) {
                    labels[i].click();
                    return 'clicked';
                }
            }
            return 'not found: ' + arguments[0];
        })()
    """.replace('arguments[0]', json.dumps(text)))

def get_labels():
    return c.evaluate("""
        (function() {
            var labels = document.querySelectorAll('.org-tree-node-label-inner');
            var r = [];
            for (var i = 0; i < labels.length; i++)
                r.push(labels[i].innerText.trim());
            return r;
        })()
    """)

def intercept_network(timeout=5):
    """Capture Skill/getTree API responses from the network."""
    mid_to_info = {}
    results = {}
    deadline = time.time() + timeout
    while time.time() < deadline:
        remaining = deadline - time.time()
        if remaining <= 0:
            break
        msg = c._recv_any(min(1.0, remaining))
        if msg is None:
            continue
        method = msg.get('method', '')
        if method == 'Network.responseReceived':
            url = msg['params']['response']['url']
            if 'getTree' in url or 'Skill' in url:
                rid = msg['params']['requestId']
                mid = c._send('Network.getResponseBody', {'requestId': rid})
                mid_to_info[mid] = url
        elif 'id' in msg:
            mid = msg.get('id')
            if mid in mid_to_info:
                body = msg.get('result', {}).get('body', '')
                try:
                    results[mid_to_info[mid]] = json.loads(body)
                except:
                    results[mid_to_info[mid]] = body
    return results

print('\n=== Phase 2: Expand categories ===')

# Collect all visible category nodes that might have hidden children
def find_categories(node, cats=None):
    if cats is None:
        cats = []
    if not node.get('task_id'):
        cats.append(node['title'])
    for child in node.get('children', []):
        find_categories(child, cats)
    return cats

all_cats = find_categories(root)
print('All category titles from initial tree:', all_cats)

# For each top-level category, try expanding to get more children
# The initial tree for non-logged-in may show only shallow structure
# We need to click categories to load their full children

# Strategy: Navigate to skilltree, click each category, capture response
categories_to_try = [
    # From DOM, these were visible: Web, Pwn, Reverse, Crypto, Misc, 彩蛋, BlockChain
    'Web', 'Pwn', 'Reverse', 'Crypto', 'Misc', '彩蛋', 'BlockChain',
    '基础知识', '签到',
]

for label in categories_to_try:
    print('\n--- Expanding "{}" ---'.format(label))

    # Navigate to skilltree to reset
    c._send('Page.navigate', {'url': 'https://www.ctfhub.com/#/skilltree'})
    time.sleep(2.5)
    while c._recv_any(0.3):
        pass
    c._send('Network.enable')
    time.sleep(0.3)
    while c._recv_any(0.3):
        pass

    r = click_label(label)
    print('  Click:', r)
    if 'not found' in str(r):
        # Try clicking parent first then this
        print('  Trying parent...')
        # The DOM showed these labels initially: CTF, 基础知识, 签到, Web, Pwn, etc.
        # So we need to ensure we're at the right level
        continue

    time.sleep(0.3)
    resp = intercept_network(4)

    got_any = False
    for url, data in resp.items():
        if isinstance(data, dict) and 'data' in data:
            node = data['data']
            nid = node.get('id')
            title = node.get('title', '?')
            children = node.get('children', [])
            print('  API: "{}" (id={}): {} children'.format(title, nid, len(children)))
            if nid:
                all_nodes[nid] = node
            got_any = True

            for ch in children:
                s = STATE_MAP.get(ch.get('user_record_skill_state'), '?')
                t = 'TASK' if ch.get('task_id') else 'CAT'
                extra = ''
                if ch.get('task_id'):
                    extra = ' "{}"'.format((ch.get('task_title') or '')[:40])
                print('    [{}] {} (id={}, {}){}'.format(t, ch.get('title'), ch.get('id'), s, extra))

    if not got_any:
        print('  No API response captured')

    labels = get_labels()
    print('  Labels after click:', labels[:15])

# ================================================================
# Phase 3: Deep expand subcategories
# ================================================================
print('\n=== Phase 3: Deep expand ===')

def collect_unexpanded():
    """Find categories whose children need expansion."""
    result = []
    for nid, node in all_nodes.items():
        for ch in node.get('children', []):
            if ch.get('task_id'):
                continue
            ch_id = ch.get('id')
            if ch_id in all_nodes:
                continue
            # Check if this child has its own children (implying more data)
            if ch.get('children') and len(ch.get('children', [])) > 0:
                result.append({'title': ch['title'], 'id': ch_id})
    return result

for round_num in range(6):
    to_expand = collect_unexpanded()
    if not to_expand:
        print('No more nodes to expand!')
        break

    print('\nRound {}: {} nodes'.format(round_num + 1, len(to_expand)))

    for item in to_expand[:15]:
        label = item['title']
        print('  "{}" (id={})...'.format(label, item['id']))

        c._send('Page.navigate', {'url': 'https://www.ctfhub.com/#/skilltree'})
        time.sleep(2.5)
        while c._recv_any(0.3):
            pass
        c._send('Network.enable')
        time.sleep(0.3)
        while c._recv_any(0.3):
            pass

        r = click_label(label)
        if 'not found' in str(r):
            print('    Not accessible directly')
            continue

        time.sleep(0.3)
        resp = intercept_network(3)

        for url, data in resp.items():
            if isinstance(data, dict) and 'data' in data:
                node = data['data']
                nid = node.get('id')
                children = node.get('children', [])
                if nid:
                    all_nodes[nid] = node
                t_count = sum(1 for c in children if c.get('task_id'))
                print('    "{}": {} children ({} tasks)'.format(
                    node.get('title'), len(children), t_count))

# ================================================================
# Final: assemble and save
# ================================================================
print('\n' + '=' * 60)
print('FINAL TREE')
print('=' * 60)

def assemble(node, visited=None):
    if visited is None:
        visited = set()
    nid = node.get('id')
    if nid in visited:
        return dict(node, _circular=True)
    visited.add(nid)
    result = dict(node)
    result['children'] = []
    for ch in node.get('children', []):
        ch_id = ch.get('id')
        if ch_id in all_nodes and ch_id != nid:
            result['children'].append(assemble(all_nodes[ch_id], visited.copy()))
        else:
            result['children'].append(ch)
    return result

full_tree = assemble(root)
print_tree(full_tree)

def count_all(node, visited, s):
    nid = node.get('id')
    if nid in visited:
        return
    visited.add(nid)
    s['total'] += 1
    if node.get('task_id'):
        s['tasks'] += 1
        st = node.get('user_record_skill_state', -1)
        s['t_states'][st] = s['t_states'].get(st, 0) + 1
    else:
        s['cats'] += 1
        st = node.get('user_record_skill_state', -1)
        s['c_states'][st] = s['c_states'].get(st, 0) + 1
    for child in node.get('children', []):
        count_all(child, visited, s)

s = {'total': 0, 'tasks': 0, 'cats': 0, 't_states': {}, 'c_states': {}}
count_all(full_tree, set(), s)

print('\nStats:')
print('  Total nodes:', s['total'])
print('  Categories:', s['cats'])
print('  Tasks:', s['tasks'])
print('  Task states:')
for st in sorted(s['t_states'].keys()):
    print('    {}: {}'.format(STATE_MAP.get(st, '?'), s['t_states'][st]))
print('  Cat states:')
for st in sorted(s['c_states'].keys()):
    print('    {}: {}'.format(STATE_MAP.get(st, '?'), s['c_states'][st]))

output = {
    'captured_at': time.strftime('%Y-%m-%d %H:%M:%S'),
    'source': 'CTFHub /#/skilltree via CDP',
    'api_endpoint': '/User_API/Skill/getTree',
    'full_tree': full_tree,
    'total_nodes_captured': len(all_nodes),
    'stats': s,
    'state_map': STATE_MAP,
    'how_it_works': (
        'Lazy-loaded org-tree. Initial page load calls Skill/getTree (no id) '
        'returning the full nested tree. Clicking a category calls Skill/getTree(id=X) '
        'focusing on that node and returning its children. '
        'Nodes have user_record_skill_state: 0=mastered, 1=learning, 2=unlearned. '
        'Tasks have task_id linking to specific challenges on CTFHub. '
        'Categories group tasks into knowledge domains (Web, Pwn, Reverse, etc).'
    ),
}

with open(OUTPUT, 'w', encoding='utf-8') as f:
    json.dump(output, f, ensure_ascii=False, indent=2)
print('\nSaved: {} ({:,} bytes)'.format(OUTPUT, os.path.getsize(OUTPUT)))

c.close()
print('Done!')
