#!/usr/bin/env python3
"""Comprehensive skill tree crawler: click ALL nodes, capture ALL API responses.
Builds the complete tree by recursively expanding each category node."""
import sys, time, json, os
sys.path.insert(0, 'D:/ai')
from tools.feeder.spa_crawler import SpaCrawler

OUTPUT = 'D:/ai/tools/feeder/ctfhub_skilltree_full.json'

c = SpaCrawler()
if not c.connect('ctfhub'):
    print('FAILED')
    sys.exit(1)

# Navigate to skilltree
print('Loading skilltree page...')
c._send('Page.navigate', {'url': 'https://www.ctfhub.com/#/skilltree'})
time.sleep(3)
while c._recv_any(0.3):
    pass

# Capture initial tree (root node)
print('Getting root tree...')
root_data = c.intercept_api('ctfhub', '/skilltree', 'getTree', timeout=10)
initial_tree = None
for name, body in root_data.items():
    try:
        parsed = json.loads(body)
        initial_tree = parsed.get('data')
        print('Root: "{}" (id={}), {} children'.format(
            initial_tree.get('title'), initial_tree.get('id'),
            len(initial_tree.get('children', []))))
    except:
        pass

if not initial_tree:
    print('Failed to get root tree!')
    c.close()
    sys.exit(1)

# Build complete tree
all_nodes = {}  # id -> node data (including children)
all_nodes[initial_tree['id']] = initial_tree

def get_visible_labels():
    """Get text of all visible tree labels."""
    return c.evaluate("""
        (function() {
            var labels = document.querySelectorAll('.org-tree-node-label-inner');
            var results = [];
            for (var i = 0; i < labels.length; i++) {
                results.push(labels[i].innerText.trim());
            }
            return results;
        })()
    """)

def click_node(text):
    """Click a visible node by its text."""
    return c.evaluate("""
        (function() {
            var labels = document.querySelectorAll('.org-tree-node-label-inner');
            for (var i = 0; i < labels.length; i++) {
                if (labels[i].innerText.trim() === arguments[0]) {
                    labels[i].click();
                    return 'clicked: ' + arguments[0];
                }
            }
            return 'not found: ' + arguments[0];
        })()
    """.replace('arguments[0]', json.dumps(text)))

def intercept_click_response(timeout=6):
    """Wait for a Skill/getTree response after clicking."""
    collected = {}
    mid_to_info = {}
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
                url = mid_to_info[mid]
                body = msg.get('result', {}).get('body', '')
                try:
                    collected[url] = json.loads(body)
                except:
                    collected[url] = body

    return collected

# Recursive expansion
def expand_node(label, node_id, depth=0):
    """Click a node to get its children, then recursively expand those children."""
    if depth > 4:  # Safety limit
        return

    # Skip if already expanded
    if node_id in all_nodes and all_nodes[node_id].get('children'):
        existing_children = all_nodes[node_id]['children']
        if len(existing_children) > 0 and existing_children[0].get('title'):
            print('  {}[skip] "{}" already has {} children'.format(
                '  ' * depth, label, len(existing_children)))
            # Still recurse into children
            for child in existing_children:
                child_label = child.get('title', '?')
                child_id = child.get('id')
                if child_id and not child.get('task_id'):
                    expand_node(child_label, child_id, depth + 1)
            return

    # Navigate back to skilltree to reset the tree view
    if depth > 0:
        c._send('Page.navigate', {'url': 'https://www.ctfhub.com/#/skilltree'})
        time.sleep(2.5)
        while c._recv_any(0.3):
            pass
        # Re-expand the path by clicking parent nodes
        # Need to re-click ancestors... this gets complicated
        # Instead, just click the current node directly if visible

    # Click the node and intercept
    print('{}Clicking "{}" (id={})...'.format('  ' * depth, label, node_id))
    click_result = click_node(label)
    print('{}  {}'.format('  ' * depth, click_result))

    if 'not found' in str(click_result):
        print('{}  Node not clickable, skipping'.format('  ' * depth))
        return

    time.sleep(0.3)
    responses = intercept_click_response(4)

    for url, data in responses.items():
        if isinstance(data, dict) and 'data' in data:
            node = data['data']
            nid = node.get('id')
            title = node.get('title', '?')
            children = node.get('children', [])
            print('{}  Got: "{}" (id={}) with {} children'.format(
                '  ' * depth, title, nid, len(children)))

            if nid:
                all_nodes[nid] = node

            # Mark these children on our parent node
            if node_id in all_nodes:
                all_nodes[node_id]['children'] = children

            # Recurse into non-task children
            for child in children:
                child_id = child.get('id')
                child_label = child.get('title', '?')
                if child_id and not child.get('task_id'):
                    # Need to click this child - but tree is now showing these children
                    time.sleep(0.5)
                    expand_node(child_label, child_id, depth + 1)

    time.sleep(1)

# ---- Start expansion ----
print('\n=== Starting recursive expansion ===\n')

# First, expand root's children
root = initial_tree
for child in root.get('children', []):
    child_label = child.get('title', '?')
    child_id = child.get('id')
    if child_id and not child.get('task_id'):
        expand_node(child_label, child_id, depth=0)

# Also try a different approach: for each visible label, click it and collect
print('\n=== Alternative: brute force - click every visible label ===')

# Navigate fresh
c._send('Page.navigate', {'url': 'https://www.ctfhub.com/#/skilltree'})
time.sleep(3)
while c._recv_any(0.3):
    pass

# Get initial tree nodes to click
targets = [
    'Web', 'Pwn', 'Reverse', 'Crypto', 'Misc', '彩蛋', 'BlockChain',
]

for target in targets:
    print('\n--- Expanding {} ---'.format(target))
    c._send('Page.navigate', {'url': 'https://www.ctfhub.com/#/skilltree'})
    time.sleep(2.5)
    while c._recv_any(0.3):
        pass

    # Click the target
    r = click_node(target)
    print('Click: ', r)
    time.sleep(0.5)

    # Collect all getTree responses
    resp = intercept_click_response(5)
    for url, data in resp.items():
        if isinstance(data, dict) and 'data' in data:
            node = data['data']
            nid = node.get('id')
            title = node.get('title', '?')
            children = node.get('children', [])
            print('  Node "{}" (id={}): {} children'.format(title, nid, len(children)))
            if nid:
                all_nodes[nid] = node

                # Print children
                for ch in children[:10]:
                    task_str = ''
                    if ch.get('task_id'):
                        task_str = ' [TASK id={}]'.format(ch.get('task_id'))
                    print('    - {} (id={}, state={}){}'.format(
                        ch.get('title'), ch.get('id'),
                        ch.get('user_record_skill_state'), task_str))
                if len(children) > 10:
                    print('    ... and {} more'.format(len(children) - 10))

    time.sleep(1)

    # Now check visible children to expand further
    visible = get_visible_labels()
    print('  Visible after expand:', visible[:20])

    # Click each visible subcategory that's not already collected
    for sub_label in visible:
        # Skip known root-level categories
        if sub_label in ('CTF', '基础知识', '签到', 'Web', 'Pwn', 'Reverse', 'Crypto', 'Misc', '彩蛋', 'BlockChain'):
            continue
        # Skip if we already have this
        known = False
        for nid, node in all_nodes.items():
            if node.get('title') == sub_label and node.get('children') and len(node['children']) > 0:
                known = True
                break
        if known:
            continue

        print('  Expanding sub: {}'.format(sub_label))
        time.sleep(0.3)
        r = click_node(sub_label)
        time.sleep(0.3)
        sub_resp = intercept_click_response(4)
        for url2, data2 in sub_resp.items():
            if isinstance(data2, dict) and 'data' in data2:
                node2 = data2['data']
                nid2 = node2.get('id')
                children2 = node2.get('children', [])
                print('    Sub-Node "{}" (id={}): {} children'.format(
                    node2.get('title'), nid2, len(children2)))
                if nid2:
                    all_nodes[nid2] = node2
                for ch2 in children2[:8]:
                    task_str2 = ''
                    if ch2.get('task_id'):
                        task_str2 = ' [TASK id={}]'.format(ch2.get('task_id'))
                    print('      - {} (id={}, state={}){}'.format(
                        ch2.get('title'), ch2.get('id'),
                        ch2.get('user_record_skill_state'), task_str2))

# ---- Save ----
print('\n=== Saving complete tree ===')

# Build the assembled tree
def assemble_tree(node_id):
    node = all_nodes.get(node_id)
    if not node:
        return {'id': node_id, 'error': 'not found'}
    result = dict(node)
    children = node.get('children', [])
    assembled_children = []
    for child in children:
        child_id = child.get('id')
        if child_id and child_id in all_nodes and all_nodes[child_id].get('children') is not None:
            # Use our expanded version
            assembled_children.append(assemble_tree(child_id))
        else:
            assembled_children.append(child)
    result['children'] = assembled_children
    return result

full_tree = assemble_tree(initial_tree['id'])

output_data = {
    'captured_at': time.strftime('%Y-%m-%d %H:%M:%S'),
    'full_tree': full_tree,
    'node_count': len(all_nodes),
    'all_nodes': {str(k): v for k, v in all_nodes.items()},
}

with open(OUTPUT, 'w', encoding='utf-8') as f:
    json.dump(output_data, f, ensure_ascii=False, indent=2)

file_size = os.path.getsize(OUTPUT)
print('Saved to {}: {:,} bytes'.format(OUTPUT, file_size))
print('Total nodes captured:', len(all_nodes))

c.close()
print('Done!')
