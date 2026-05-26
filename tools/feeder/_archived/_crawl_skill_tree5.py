#!/usr/bin/env python3
"""Skill tree crawler v5 - uses proven intercept_api pattern for each node."""
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

def expand_node(node_label, parent_label=None):
    """Use intercept_api to get tree data for a node.

    The skill tree is lazy: clicking a category calls Skill/getTree with that node's ID.
    The API returns the clicked node with its immediate children populated.

    Strategy: navigate to /skilltree, click the node, capture all getTree responses.
    """
    print('  Expanding "{}"...'.format(node_label))

    # Use the proven intercept_api pattern
    # This will: connect, enable Network, navigate away, push route, capture
    apis = c.intercept_api('ctfhub', '/skilltree', 'getTree', timeout=12)

    for name, body in apis.items():
        try:
            data = json.loads(body)
        except:
            continue

        if isinstance(data, dict) and 'data' in data:
            node = data['data']
            nid = node.get('id')
            title = node.get('title', '?')
            children = node.get('children', [])
            if nid:
                all_nodes[nid] = node
            print('    API returned: "{}" (id={}): {} children'.format(
                title, nid, len(children)))

            # Print children summary
            for ch in children[:8]:
                s = STATE_MAP.get(ch.get('user_record_skill_state'), '?')
                t = ' [TASK]' if ch.get('task_id') else ' [CAT]'
                extra = ''
                if ch.get('task_id'):
                    extra = ' task="{}"'.format(ch.get('task_title', '') or '')
                print('      - {} {}(id={}, {}){}'.format(t, ch.get('title'), ch.get('id'), s, extra))
            if len(children) > 8:
                print('      ... and {} more'.format(len(children) - 8))
            return node

    return None

# ---- Phase 1: Get the initial tree ----
print('=== Phase 1: Initial tree ===')

# The intercept_api with route='/skilltree' and away_first='/index' will
# navigate to /index first, then push /skilltree, and capture the getTree API.
apis = c.intercept_api('ctfhub', '/skilltree', 'getTree', timeout=15)

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
        if nid == 1 or node.get('title') == 'CTF':
            root = node
        print('Got: "{}" (id={}) with {} children'.format(
            node.get('title'), nid, len(node.get('children', []))))

if not root:
    print('ERROR: No root tree!')
    c.close()
    sys.exit(1)

# ---- Phase 2: Expand each visible category by clicking it ----
print('\n=== Phase 2: Expand categories ===')

# Collect all non-task nodes from the current tree state
def get_visible_labels():
    """Check what labels are currently visible."""
    return c.evaluate("""
        (function() {
            var labels = document.querySelectorAll('.org-tree-node-label-inner');
            var r = [];
            for (var i = 0; i < labels.length; i++)
                r.push(labels[i].innerText.trim());
            return r;
        })()
    """)

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

# Get initial visible labels
visible = get_visible_labels()
print('Initial visible labels:', visible)

# Categories to expand (from root children, skip task nodes)
categories = [(ch['title'], ch['id']) for ch in root.get('children', [])
              if not ch.get('task_id')]
print('Root categories to expand:', [c[0] for c in categories])

for label, cat_id in categories:
    print('\n--- "{}" (id={}) ---'.format(label, cat_id))

    # Re-navigate to skilltree to reset the view
    c._send('Page.navigate', {'url': 'https://www.ctfhub.com/#/skilltree'})
    time.sleep(2.5)

    # Clear pending
    while c._recv_any(0.3):
        pass

    # Enable network
    c._send('Network.enable')
    time.sleep(0.3)
    while c._recv_any(0.3):
        pass

    # Click the category
    r = click_label(label)
    print('  Click:', r)

    if 'not found' in str(r):
        print('  SKIP')
        continue

    time.sleep(0.3)

    # Collect getTree responses
    mid_to_info = {}
    deadline = time.time() + 5
    while time.time() < deadline:
        msg = c._recv_any(0.3)
        if msg is None:
            continue
        method = msg.get('method', '')
        if method == 'Network.responseReceived':
            url = msg['params']['response']['url']
            if 'getTree' in url:
                rid = msg['params']['requestId']
                mid = c._send('Network.getResponseBody', {'requestId': rid})
                mid_to_info[mid] = url
        elif 'id' in msg:
            mid = msg.get('id')
            if mid in mid_to_info:
                body = msg.get('result', {}).get('body', '')
                try:
                    data = json.loads(body)
                    if isinstance(data, dict) and 'data' in data:
                        node = data['data']
                        nid = node.get('id')
                        title = node.get('title', '?')
                        children = node.get('children', [])
                        if nid:
                            all_nodes[nid] = node
                        print('  API: "{}" (id={}): {} children'.format(
                            title, nid, len(children)))
                        for ch in children:
                            s = STATE_MAP.get(ch.get('user_record_skill_state'), '?')
                            t = ' [TASK]' if ch.get('task_id') else ' [CAT]'
                            extra = ''
                            if ch.get('task_id'):
                                extra = ' task="{}"'.format((ch.get('task_title') or '')[:40])
                            print('    - {} {}(id={}, {}){}'.format(
                                t, ch.get('title'), ch.get('id'), s, extra))
                except:
                    pass

    # Check visible labels after click
    visible = get_visible_labels()
    print('  Labels after click:', visible[:12])

# ---- Phase 3: Expand subcategories ----
print('\n=== Phase 3: Subcategories ===')

# Collect nodes that need expansion (categories whose children contain other categories)
def collect_unexpanded():
    result = []
    for nid, node in all_nodes.items():
        for ch in node.get('children', []):
            if ch.get('task_id'):
                continue  # Tasks don't need expansion
            ch_id = ch.get('id')
            if ch_id in all_nodes:
                continue  # Already expanded
            result.append({
                'title': ch['title'],
                'id': ch_id,
                'parent': node.get('title', ''),
            })
    return result

for round_num in range(10):
    to_expand = collect_unexpanded()
    if not to_expand:
        print('No more nodes to expand!')
        break

    print('\nRound {}: {} nodes to expand'.format(round_num + 1, len(to_expand)))

    for item in to_expand[:20]:
        label = item['title']
        print('  "{}" (id={}, parent="{}")'.format(label, item['id'], item['parent']))

        # Navigate to skilltree and click
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
            # May need parent expanded first in this view
            # Try clicking parent then child
            parent = item['parent']
            print('    Not directly clickable. Clicking parent "{}" first...'.format(parent))
            r2 = click_label(parent)
            time.sleep(0.5)
            # Capture parent's response
            mid_to_info = {}
            deadline = time.time() + 3
            while time.time() < deadline:
                msg = c._recv_any(0.3)
                if msg is None:
                    continue
                method = msg.get('method', '')
                if method == 'Network.responseReceived':
                    url = msg['params']['response']['url']
                    if 'getTree' in url:
                        rid = msg['params']['requestId']
                        mid = c._send('Network.getResponseBody', {'requestId': rid})
                        mid_to_info[mid] = url
                elif 'id' in msg:
                    mid = msg.get('id')
                    if mid in mid_to_info:
                        body = msg.get('result', {}).get('body', '')
                        try:
                            d = json.loads(body)
                            if isinstance(d, dict) and 'data' in d:
                                pn = d['data']
                                if pn.get('id'):
                                    all_nodes[pn['id']] = pn
                                print('    Parent: "{}": {} children'.format(
                                    pn.get('title'), len(pn.get('children', []))))
                        except:
                            pass

            # Now click the child
            time.sleep(0.3)
            r3 = click_label(label)
            print('    Child click:', r3)
            time.sleep(0.3)
        else:
            time.sleep(0.3)

        # Capture response
        mid_to_info = {}
        deadline = time.time() + 4
        while time.time() < deadline:
            msg = c._recv_any(0.3)
            if msg is None:
                continue
            method = msg.get('method', '')
            if method == 'Network.responseReceived':
                url = msg['params']['response']['url']
                if 'getTree' in url:
                    rid = msg['params']['requestId']
                    mid = c._send('Network.getResponseBody', {'requestId': rid})
                    mid_to_info[mid] = url
            elif 'id' in msg:
                mid = msg.get('id')
                if mid in mid_to_info:
                    body = msg.get('result', {}).get('body', '')
                    try:
                        d = json.loads(body)
                        if isinstance(d, dict) and 'data' in d:
                            node = d['data']
                            nid = node.get('id')
                            children = node.get('children', [])
                            if nid:
                                all_nodes[nid] = node
                            task_count = sum(1 for c in children if c.get('task_id'))
                            print('    Got: "{}" (id={}): {} children ({} tasks)'.format(
                                node.get('title'), nid, len(children), task_count))
                            for ch in children[:4]:
                                s = STATE_MAP.get(ch.get('user_record_skill_state'), '?')
                                t = 'T' if ch.get('task_id') else 'C'
                                extra = ''
                                if ch.get('task_id'):
                                    extra = ' "{}"'.format((ch.get('task_title') or '')[:30])
                                print('      [{}] {} (id={}, {}){}'.format(
                                    t, ch.get('title'), ch.get('id'), s, extra))
                    except:
                        pass

# ---- Final Statistics ----
print('\n' + '=' * 60)
print('FINAL STATISTICS')
print('=' * 60)

def print_tree(node, indent=0, visited=None):
    if visited is None:
        visited = set()
    nid = node.get('id')
    if nid in visited:
        return
    visited.add(nid)

    prefix = '  ' * indent
    state = STATE_MAP.get(node.get('user_record_skill_state'), '?')
    task_id = node.get('task_id', 0)
    title = node.get('title', '?')

    if task_id:
        task_title = node.get('task_title', '') or ''
        print('{}[{}] {} [TASK id={}] "{}" (solves={})'.format(
            prefix, state, title, task_id, task_title[:50],
            node.get('finish_count', 0)))
    else:
        n_children = len(node.get('children', []))
        print('{}[{}] {} (id={}, {} children)'.format(
            prefix, state, title, nid, n_children))

        for child in node.get('children', []):
            if child.get('id') in all_nodes:
                print_tree(all_nodes[child['id']], indent + 1, visited.copy())
            else:
                # Use the child data directly
                ch_state = STATE_MAP.get(child.get('user_record_skill_state'), '?')
                ch_task = child.get('task_id', 0)
                if ch_task:
                    print('{}  [{}] {} [TASK id={}]'.format(
                        prefix, ch_state, child.get('title'), ch_task))
                else:
                    print('{}  [{}] {} (id={}) [unexpanded]'.format(
                        prefix, ch_state, child.get('title'), child.get('id')))

print('\nComplete skill tree:')
print_tree(root)

# Count
def count_all(node, visited, s):
    nid = node.get('id')
    if nid in visited:
        return
    visited.add(nid)
    s['total'] += 1
    if node.get('task_id'):
        s['tasks'] += 1
        st = node.get('user_record_skill_state', -1)
        s['task_states'][st] = s['task_states'].get(st, 0) + 1
    else:
        s['cats'] += 1
        st = node.get('user_record_skill_state', -1)
        s['cat_states'][st] = s['cat_states'].get(st, 0) + 1
    for child in node.get('children', []):
        if child.get('id') in all_nodes:
            count_all(all_nodes[child['id']], visited, s)
        else:
            s['total'] += 1
            if child.get('task_id'):
                s['tasks'] += 1
                st = child.get('user_record_skill_state', -1)
                s['task_states'][st] = s['task_states'].get(st, 0) + 1
            else:
                s['cats'] += 1
                st = child.get('user_record_skill_state', -1)
                s['cat_states'][st] = s['cat_states'].get(st, 0) + 1

s = {'total': 0, 'tasks': 0, 'cats': 0, 'task_states': {}, 'cat_states': {}}
count_all(root, set(), s)

print('\nCounts:')
print('  Total nodes: {}'.format(s['total']))
print('  Categories: {}'.format(s['cats']))
print('  Tasks: {}'.format(s['tasks']))
print('  Task states:')
for st in sorted(s['task_states'].keys()):
    print('    {}: {}'.format(STATE_MAP.get(st, '?'), s['task_states'][st]))
print('  Category states:')
for st in sorted(s['cat_states'].keys()):
    print('    {}: {}'.format(STATE_MAP.get(st, '?'), s['cat_states'][st]))

# Save
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

output = {
    'captured_at': time.strftime('%Y-%m-%d %H:%M:%S'),
    'full_tree': assemble(root),
    'nodes_captured': len(all_nodes),
    'stats': s,
    'state_map': STATE_MAP,
}

with open(OUTPUT, 'w', encoding='utf-8') as f:
    json.dump(output, f, ensure_ascii=False, indent=2)

print('\nSaved: {} ({:,} bytes)'.format(OUTPUT, os.path.getsize(OUTPUT)))
c.close()
print('Done!')
