#!/usr/bin/env python3
"""Skill tree crawler v3 - fresh navigate then click for each node."""
import sys, time, json, os
sys.path.insert(0, 'D:/ai')
from tools.feeder.spa_crawler import SpaCrawler

OUTPUT = 'D:/ai/tools/feeder/ctfhub_skilltree_full.json'

c = SpaCrawler()
if not c.connect('ctfhub'):
    print('FAILED')
    sys.exit(1)

all_nodes = {}  # id -> full node data with children

def navigate_to_skilltree():
    """Fresh navigation to skilltree page."""
    c._send('Page.navigate', {'url': 'https://www.ctfhub.com/#/skilltree'})
    time.sleep(2.5)
    while c._recv_any(0.3):
        pass
    # Enable network
    c._send('Network.enable')
    time.sleep(0.3)
    while c._recv_any(0.3):
        pass

def intercept_getTree_response(timeout=6):
    """Wait for and capture Skill/getTree API response."""
    mid_to_info = {}
    results = {}
    deadline = time.time() + timeout
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
                    results[mid_to_info[mid]] = json.loads(body)
                except:
                    results[mid_to_info[mid]] = body
    return results

def click_label(text):
    """Click a visible tree node label by text."""
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
    """Get all visible labels after a click."""
    return c.evaluate("""
        (function() {
            var labels = document.querySelectorAll('.org-tree-node-label-inner');
            var r = [];
            for (var i = 0; i < labels.length; i++)
                r.push(labels[i].innerText.trim());
            return r;
        })()
    """)

def expand_and_capture(node_label, timeout=5):
    """Navigate to skilltree, click node, capture API response.
    Returns (node_data, visible_labels_after)."""
    navigate_to_skilltree()

    r = click_label(node_label)
    if 'not found' in str(r):
        print('  SKIP: "{}" not clickable (may need parent expansion)'.format(node_label))
        # Try an alternative: find the label by traversing all elements
        alt_click = c.evaluate("""
            (function() {
                var all = document.querySelectorAll('*');
                for (var i = 0; i < all.length; i++) {
                    if (all[i].childNodes.length === 1 &&
                        all[i].childNodes[0].nodeType === 3 &&
                        all[i].childNodes[0].textContent.trim() === arguments[0]) {
                        all[i].click();
                        return 'clicked via textNode';
                    }
                }
                return 'still not found';
            })()
        """.replace('arguments[0]', json.dumps(node_label)))
        if 'not found' in str(alt_click):
            return None, []
        time.sleep(0.5)
    else:
        time.sleep(0.5)

    # Capture API
    responses = intercept_getTree_response(timeout)

    node_data = None
    for url, data in responses.items():
        if isinstance(data, dict) and 'data' in data:
            node = data['data']
            node_id = node.get('id')
            if node_id:
                all_nodes[node_id] = node
            node_data = node

    # Get visible labels
    labels = get_labels()

    return node_data, labels

# ---- Phase 1: Get root tree ----
print('=== Phase 1: Root Tree ===')
navigate_to_skilltree()
time.sleep(0.5)
root_resp = intercept_getTree_response(3)

root = None
for url, data in root_resp.items():
    if isinstance(data, dict) and 'data' in data:
        root = data['data']
        all_nodes[root['id']] = root
        print('Root: "{}" (id={})'.format(root['title'], root['id']))

if not root:
    # Click nothing - the tree is already loaded on page load
    # Try clicking the root "CTF" node
    r = click_label('CTF')
    time.sleep(0.5)
    root_resp2 = intercept_getTree_response(3)
    for url, data in root_resp2.items():
        if isinstance(data, dict) and 'data' in data:
            root = data['data']
            all_nodes[root['id']] = root
            print('Root (from click): "{}" (id={})'.format(root['title'], root['id']))

if not root:
    print('ERROR: Could not get root tree')
    c.close()
    sys.exit(1)

print('Root labels after expand:', get_labels())

# ---- Phase 2: Expand each major category ----
print('\n=== Phase 2: Major Categories ===')

# Collect all nodes we want to expand
def collect_category_ids(node, categories=None):
    if categories is None:
        categories = []
    if not node:
        return categories
    task_id = node.get('task_id', 0)
    if not task_id and node.get('id') and node['id'] != 1:  # Non-root, non-task
        categories.append({
            'id': node['id'],
            'title': node['title'],
            'level': node.get('level', 0),
            'pid': node.get('pid', 0),
        })
    for child in node.get('children', []):
        collect_category_ids(child, categories)
    return categories

categories = collect_category_ids(root)
print('Categories to expand: {}'.format(len(categories)))
for cat in categories:
    print('  {} (id={}, pid={})'.format(cat['title'], cat['id'], cat['pid']))

# ---- Phase 3: Expand each category ----
print('\n=== Phase 3: Expanding Categories ===')

STATE_MAP = {0: 'mastered', 1: 'learning', 2: 'unlearned'}
depth_stats = {}

# We'll use a BFS approach: expand all level-0 categories, then level-1, etc.
# But each expansion resets the tree view, so we need to expand one at a time

def print_children(node, indent=2):
    """Helper to print node children."""
    for ch in node.get('children', []):
        prefix = ' ' * indent
        state = STATE_MAP.get(ch.get('user_record_skill_state'), '?')
        task_str = ''
        if ch.get('task_id'):
            task_str = ' [TASK id={}]'.format(ch.get('task_id'))
            title = ch.get('task_title', '') or ''
            task_str += ' "{}"'.format(title)
        print('{}- {} (id={}, {}){}'.format(prefix, ch.get('title'), ch.get('id'), state, task_str))

# Expand first batch of top-level categories
first_batch = ['Web', 'Pwn', 'Reverse', 'Crypto', 'Misc', '彩蛋', 'BlockChain', '基础知识']

for label in first_batch:
    print('\n--- Expanding "{}" ---'.format(label))
    node, labels = expand_and_capture(label)

    if node:
        children = node.get('children', [])
        print('  Node "{}" (id={}, state={}): {} children'.format(
            node.get('title'), node.get('id'),
            STATE_MAP.get(node.get('user_record_skill_state'), '?'),
            len(children)))
        print_children(node)
        print('  Labels now visible:', labels[:15])
    else:
        print('  FAILED to expand')

# ---- Phase 4: Expand deeper nodes ----
print('\n=== Phase 4: Deep expansion ===')

# Collect all newly discovered subcategories
def collect_unexpanded():
    """Find nodes that are categories (no task_id) but have empty/unexpanded children."""
    result = []
    for nid, node in all_nodes.items():
        if node.get('task_id'):
            continue  # Skip task nodes
        children = node.get('children', [])
        if len(children) == 0:
            continue  # No children
        # Check if children look like task nodes (have task_ids) vs categories
        has_subcategories = any(
            not ch.get('task_id') for ch in children
        )
        if has_subcategories:
            # These children might themselves need expansion
            for ch in children:
                if not ch.get('task_id'):
                    # Check if we already have this child expanded
                    child_id = ch.get('id')
                    existing = all_nodes.get(child_id, {})
                    existing_children = existing.get('children', [])
                    if not existing_children or len(existing_children) == 0:
                        result.append({
                            'title': ch['title'],
                            'id': child_id,
                            'parent': node.get('title'),
                        })
    return result

# Do multiple rounds of expansion
for round_num in range(4):
    to_expand = collect_unexpanded()
    if not to_expand:
        print('No more nodes to expand!')
        break

    print('\nRound {}: {} nodes to expand'.format(round_num + 1, len(to_expand)))

    for item in to_expand[:30]:  # Limit per round
        label = item['title']
        if label in ('Web进阶',):  # Known empty nodes
            print('  SKIP "{}" (known empty)'.format(label))
            continue

        print('  Expanding "{}" (id={}, parent="{}")'.format(
            label, item['id'], item['parent']))

        node, labels = expand_and_capture(label)

        if node:
            children = node.get('children', [])
            print('    Got: {} children'.format(len(children)))
            print_children(node, indent=6)

            # Track depth stats
            depth = node.get('level', 0)
            if depth not in depth_stats:
                depth_stats[depth] = 0
            depth_stats[depth] += 1
        else:
            print('    FAILED - may need parent expansion first')

    if len(to_expand) == 0:
        break

# ---- Save ----
print('\n=== Saving ===')

def assemble_tree(node_id, visited=None):
    if visited is None:
        visited = set()
    if node_id in visited:
        return {'id': node_id, '_circular': True}
    visited.add(node_id)

    node = all_nodes.get(node_id)
    if not node:
        return {'id': node_id, 'error': 'not found'}

    result = dict(node)
    children = node.get('children', [])
    assembled_children = []
    for child in children:
        child_id = child.get('id')
        if child_id and child_id in all_nodes:
            # Use our expanded version (recursively)
            expanded = assemble_tree(child_id, visited.copy())
            assembled_children.append(expanded)
        else:
            assembled_children.append(child)
    result['children'] = assembled_children
    return result

full_tree = assemble_tree(root['id'])

# Collect statistics
def count_nodes(node, stats):
    stats['total'] += 1
    if node.get('task_id'):
        stats['tasks'] += 1
        state = node.get('user_record_skill_state', -1)
        stats['task_states'][state] = stats['task_states'].get(state, 0) + 1
    else:
        stats['categories'] += 1
        state = node.get('user_record_skill_state', -1)
        stats['cat_states'][state] = stats['cat_states'].get(state, 0) + 1
    for child in node.get('children', []):
        count_nodes(child, stats)

stats = {'total': 0, 'tasks': 0, 'categories': 0, 'task_states': {}, 'cat_states': {}}
count_nodes(full_tree, stats)

output = {
    'captured_at': time.strftime('%Y-%m-%d %H:%M:%S'),
    'full_tree': full_tree,
    'total_nodes_captured': len(all_nodes),
    'stats': stats,
    'state_map': STATE_MAP,
}

with open(OUTPUT, 'w', encoding='utf-8') as f:
    json.dump(output, f, ensure_ascii=False, indent=2)

fsize = os.path.getsize(OUTPUT)
print('Saved: {} ({:,} bytes)'.format(OUTPUT, fsize))
print()
print('Stats:')
print('  Total nodes in tree: {}'.format(stats['total']))
print('  Categories: {}'.format(stats['categories']))
print('  Tasks: {}'.format(stats['tasks']))
print('  Task states:')
for state in sorted(stats['task_states'].keys()):
    print('    {}: {}'.format(STATE_MAP.get(state, '?'), stats['task_states'][state]))
print('  Category states:')
for state in sorted(stats['cat_states'].keys()):
    print('    {}: {}'.format(STATE_MAP.get(state, '?'), stats['cat_states'][state]))

c.close()
print('\nDone!')
