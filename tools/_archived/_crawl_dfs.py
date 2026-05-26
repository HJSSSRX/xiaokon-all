#!/usr/bin/env python3
"""DFS skill tree crawler: navigate to skilltree, click node, capture children,
click each child, capture grandchildren, etc. Depth-first search through the tree."""
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
# Get initial full tree
# ================================================================
print('=== Get full tree ===')
apis = c.intercept_api('ctfhub', '/skilltree', 'getTree', timeout=20)
for name, body in apis.items():
    try:
        data = json.loads(body)
        if isinstance(data, dict) and 'data' in data:
            node = data['data']
            nid = node.get('id')
            if nid:
                all_nodes[nid] = node
            print('Initial: "{}" (id={}) with {} children'.format(
                node.get('title'), nid, len(node.get('children', []))))
    except:
        pass

root = all_nodes.get(1)
if not root:
    print('FATAL: no root')
    c.close()
    sys.exit(1)

# ================================================================
# Helper functions
# ================================================================

def navigate_to_skilltree():
    """Reset to skilltree initial view."""
    c._send('Page.navigate', {'url': 'https://www.ctfhub.com/#/skilltree'})
    time.sleep(3)
    while c._recv_any(0.3):
        pass
    c._send('Network.enable')
    time.sleep(0.3)
    while c._recv_any(0.3):
        pass

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
            return 'not found';
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

def capture_response(timeout=4):
    """Capture getTree response after clicking."""
    mid_to_info = {}
    deadline = time.time() + timeout
    while time.time() < deadline:
        msg = c._recv_any(0.3)
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
                    d = json.loads(body)
                    if isinstance(d, dict) and 'data' in d:
                        node = d['data']
                        nid = node.get('id')
                        if nid:
                            all_nodes[nid] = node
                        return node
                except:
                    pass
    return None

# ================================================================
# DFS expansion
# ================================================================

expanded_ids = set()  # Track which node IDs we've already expanded

def expand_dfs(node_title, node_id, depth=0):
    """Depth-first: click this node, get its children, expand each child."""
    if depth > 4:
        return
    if node_id in expanded_ids:
        return

    prefix = '  ' * depth
    print('{}Expanding "{}" (id={})...'.format(prefix, node_title, node_id))

    # Navigate to skilltree to get a clean state
    navigate_to_skilltree()

    # Verify the label is visible
    visible = get_labels()
    print('{}  Visible: {}'.format(prefix, visible))

    # Click the node
    r = click_label(node_title)
    if 'not found' in str(r):
        # Maybe we need to click through the tree to get to this node
        # For now, check if this is a child of an expanded node
        print('{}  NOT FOUND in current view. Skipping.'.format(prefix))
        return
    print('{}  Clicked'.format(prefix))
    time.sleep(0.3)

    # Capture response
    node = capture_response(3)
    if not node:
        print('{}  No API response'.format(prefix))
        return

    expanded_ids.add(node_id)

    children = node.get('children', [])
    print('{}  Got: {} children'.format(prefix, len(children)))

    # Print children
    child_categories = []
    for ch in children:
        s = STATE_MAP.get(ch.get('user_record_skill_state'), '?')
        t = 'TASK' if ch.get('task_id') else 'CAT'
        extra = ''
        if ch.get('task_id'):
            extra = ' "{}"'.format((ch.get('task_title') or '')[:40])
        print('{}    [{}] {} (id={}, {}){}'.format(prefix, t, ch.get('title'), ch.get('id'), s, extra))

        if not ch.get('task_id'):
            child_categories.append((ch['title'], ch['id']))

    # Now expand each child category
    # BUT: we need to be in the parent's view to see the children
    for child_title, child_id in child_categories:
        if child_title in ('Web进阶',):  # Known empty
            continue
        expand_dfs(child_title, child_id, depth + 1)

# Start DFS from each top-level visible category
print('\n=== DFS Expansion ===')

# First, get the visible labels to see what root-level categories we have
navigate_to_skilltree()
visible = get_labels()
print('Root-level visible labels: {}'.format(visible))

# These are the major categories we want to expand
root_categories = [c for c in visible if c not in ('CTF', '基础知识', '签到')]
print('Major categories to expand: {}'.format(root_categories))

for cat in root_categories:
    # Find the node ID from our initial tree
    cat_id = None
    for nid, node in all_nodes.items():
        if node.get('title') == cat:
            cat_id = nid
            break

    if cat_id:
        print('\n--- Major category: {} (id={}) ---'.format(cat, cat_id))
        expand_dfs(cat, cat_id, depth=1)
    else:
        print('\n--- Unknown category: {} (no ID found) ---'.format(cat))

# ================================================================
# Build final tree
# ================================================================

def print_tree(node, indent=0, visited=None):
    if visited is None:
        visited = set()
    nid = node.get('id')
    if nid in visited:
        print('{}  [circular ref]'.format('  ' * indent))
        return
    visited.add(nid)

    prefix = '  ' * indent
    state = STATE_MAP.get(node.get('user_record_skill_state'), '?')
    task_id = node.get('task_id', 0)
    title = node.get('title', '?')
    children = node.get('children', [])

    if task_id and task_id > 0:
        t_title = (node.get('task_title') or '')[:50]
        print('{}[{}] {} [TASK id={}] "{}" (solves={})'.format(
            prefix, state, title, task_id, t_title,
            node.get('finish_count', 0)))
    else:
        print('{}[{}] {} (id={}, {} children)'.format(
            prefix, state, title, nid, len(children)))

    for child in children:
        ch_id = child.get('id')
        if ch_id in all_nodes and ch_id != nid:
            print_tree(all_nodes[ch_id], indent + 1, visited.copy())
        else:
            print_tree(child, indent + 1, visited.copy())

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

full_tree = assemble(all_nodes.get(1, root))

print('\n' + '=' * 60)
print('FINAL SKILL TREE')
print('=' * 60)
print_tree(full_tree)

# Stats
def count_all(node, visited, s):
    nid = node.get('id')
    if nid in visited:
        return
    visited.add(nid)
    s['total'] += 1
    if node.get('task_id') and node.get('task_id') > 0:
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
    'api_endpoint': '/User_API/Skill/getTree',
    'full_tree': full_tree,
    'nodes_captured': len(all_nodes),
    'node_ids': sorted(all_nodes.keys()),
    'expanded_ids': sorted(expanded_ids),
    'stats': s,
    'state_map': STATE_MAP,
}
with open(OUTPUT, 'w', encoding='utf-8') as f:
    json.dump(output, f, ensure_ascii=False, indent=2)
print('\nSaved: {} ({:,} bytes)'.format(OUTPUT, os.path.getsize(OUTPUT)))

c.close()
print('Done!')
