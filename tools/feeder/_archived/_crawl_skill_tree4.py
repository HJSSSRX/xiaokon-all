#!/usr/bin/env python3
"""Skill tree crawler v4 - enable Network before navigation, robust capture."""
import sys, time, json, os
sys.path.insert(0, 'D:/ai')
from tools.feeder.spa_crawler import SpaCrawler

OUTPUT = 'D:/ai/tools/feeder/ctfhub_skilltree_full.json'

c = SpaCrawler()
if not c.connect('ctfhub'):
    print('FAILED')
    sys.exit(1)

all_nodes = {}
STATE_MAP = {0: 'mastered', 1: 'learning', 2: 'unlearned'}

def fresh_nav():
    """Navigate to skilltree with Network enabled BEFORE navigation."""
    # First, clear state
    while c._recv_any(0.3):
        pass
    # Enable Network
    c._send('Network.enable')
    c._send('Runtime.enable')
    time.sleep(0.3)
    while c._recv_any(0.3):
        pass
    # Navigate
    c._send('Page.navigate', {'url': 'https://www.ctfhub.com/#/skilltree'})
    time.sleep(3)
    while c._recv_any(0.3):
        pass

def intercept_responses(api_pattern='getTree', timeout=8):
    """Capture all responses matching api_pattern."""
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
            if api_pattern.lower() in url.lower():
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
    r = c.evaluate("""
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
    return r

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

# ---- Phase 1: Get root tree ----
print('=== Phase 1: Root ===')
fresh_nav()

# The Skill/getTree API call happens during initial page load
responses = intercept_responses('getTree', timeout=5)
print('Captured {} API responses'.format(len(responses)))

root = None
for url, data in responses.items():
    if isinstance(data, dict) and 'data' in data:
        node = data['data']
        print('  Got node: "{}" (id={})'.format(node.get('title'), node.get('id')))
        if node.get('id') == 1:
            root = node
        if node.get('id'):
            all_nodes[node['id']] = node

if not root:
    # Try clicking "CTF" root node and capturing
    print('Root not captured from initial load. Trying click...')
    fresh_nav()
    responses = intercept_responses('getTree', timeout=3)  # capture initial
    for url, data in responses.items():
        if isinstance(data, dict) and 'data' in data:
            n = data['data']
            if n.get('id'):
                all_nodes[n['id']] = n
            if n.get('id') == 1:
                root = n

    if not root:
        # Last resort: click CTF
        print('Clicking CTF...')
        r = click_label('CTF')
        print('  Click:', r)
        time.sleep(0.5)
        resp2 = intercept_responses('getTree', timeout=3)
        for url, data in resp2.items():
            if isinstance(data, dict) and 'data' in data:
                n = data['data']
                if n.get('id'):
                    all_nodes[n['id']] = n
                if n.get('id') == 1:
                    root = n
                print('  Click response: "{}" (id={})'.format(
                    n.get('title'), n.get('id')))

if not root:
    print('FATAL: Cannot get root tree')
    c.close()
    sys.exit(1)

print('Root: "{}" has {} children'.format(root['title'], len(root.get('children', []))))

# ---- Phase 2: Click each major category ----
print('\n=== Phase 2: Expand Categories ===')

# Get root children to see what categories exist
root_children = root.get('children', [])
print('Root children:')
for ch in root_children:
    state = STATE_MAP.get(ch.get('user_record_skill_state'), '?')
    task = '[TASK]' if ch.get('task_id') else '[CAT]'
    print('  {} {} (id={}, {})'.format(task, ch.get('title'), ch.get('id'), state))

# Collect all category labels from root children (non-task nodes)
category_labels = [ch['title'] for ch in root_children if not ch.get('task_id')]

# Also check for deeper categories
def find_all_category_titles(node):
    titles = []
    if not node.get('task_id') and node.get('title'):
        titles.append(node['title'])
    for child in node.get('children', []):
        titles.extend(find_all_category_titles(child))
    return titles

all_cat_titles = find_all_category_titles(root)
print('All category titles from initial tree: {}'.format(all_cat_titles))

# Expand each category from root
categories_to_expand = [ch for ch in root_children if not ch.get('task_id')]
print('Expanding {} root categories...'.format(len(categories_to_expand)))

for cat in categories_to_expand:
    label = cat['title']
    cat_id = cat['id']
    print('\n--- "{}" (id={}) ---'.format(label, cat_id))

    fresh_nav()
    r = click_label(label)
    print('  Click:', r)

    if 'not found' in str(r):
        print('  SKIP: not clickable')
        continue

    time.sleep(0.5)
    resp = intercept_responses('getTree', timeout=4)

    got_data = False
    for url, data in resp.items():
        if isinstance(data, dict) and 'data' in data:
            node = data['data']
            nid = node.get('id')
            title = node.get('title', '?')
            children = node.get('children', [])
            print('  Response: "{}" (id={}): {} children'.format(title, nid, len(children)))
            if nid:
                all_nodes[nid] = node
            # Print children
            for ch in children:
                state = STATE_MAP.get(ch.get('user_record_skill_state'), '?')
                task_str = ''
                if ch.get('task_id'):
                    task_str = ' [TASK id={}] "{}"'.format(
                        ch.get('task_id'), ch.get('task_title', '') or '')
                print('    - {} (id={}, {}){}'.format(
                    ch.get('title'), ch.get('id'), state, task_str))
            got_data = True

    if not got_data:
        print('  No API response captured')

    # Show visible labels after click
    labels = get_labels()
    print('  Visible after click: {}'.format(labels))

# ---- Phase 3: Deep expand - subcategories ----
print('\n=== Phase 3: Deep expand subcategories ===')

def collect_subcategories():
    """Find categories whose children are also categories (need expansion)."""
    result = []
    for nid, node in all_nodes.items():
        children = node.get('children', [])
        for ch in children:
            if ch.get('task_id'):
                continue
            ch_id = ch.get('id')
            if ch_id and ch_id in all_nodes:
                # Already have expanded data
                continue
            result.append({
                'title': ch['title'],
                'id': ch_id,
                'parent_title': node.get('title', ''),
                'parent_id': node.get('id'),
            })
    return result

for round_num in range(5):
    to_expand = collect_subcategories()
    if not to_expand:
        print('No more subcategories to expand!')
        break

    print('\nRound {}: {} subcategories to expand'.format(round_num + 1, len(to_expand)))

    for item in to_expand[:25]:
        label = item['title']
        print('  "{}" (id={}, parent="{}")...'.format(
            label, item['id'], item['parent_title']))

        fresh_nav()
        r = click_label(label)
        if 'not found' in str(r):
            print('    Not directly accessible, need parent expansion first')
            # Try expanding the parent first
            parent_label = item['parent_title']
            print('    Expanding parent "{}" first...'.format(parent_label))
            r2 = click_label(parent_label)
            time.sleep(0.5)
            parent_resp = intercept_responses('getTree', timeout=3)
            for url, data in parent_resp.items():
                if isinstance(data, dict) and 'data' in data:
                    pn = data['data']
                    if pn.get('id'):
                        all_nodes[pn['id']] = pn

            # Now try again
            time.sleep(0.3)
            r3 = click_label(label)
            time.sleep(0.5)
            resp = intercept_responses('getTree', timeout=3)
        else:
            time.sleep(0.5)
            resp = intercept_responses('getTree', timeout=3)

        for url, data in resp.items():
            if isinstance(data, dict) and 'data' in data:
                node = data['data']
                nid = node.get('id')
                children = node.get('children', [])
                task_count = sum(1 for c in children if c.get('task_id'))
                cat_count = len(children) - task_count
                print('    "{}" (id={}): {} children ({} tasks, {} cats)'.format(
                    node.get('title'), nid, len(children), task_count, cat_count))
                if nid:
                    all_nodes[nid] = node
                # Quick preview
                for ch in children[:5]:
                    s = STATE_MAP.get(ch.get('user_record_skill_state'), '?')
                    t = ' [TASK]' if ch.get('task_id') else ''
                    print('      - {} (id={}, {}){}'.format(
                        ch.get('title'), ch.get('id'), s, t))
                if len(children) > 5:
                    print('      ... and {} more'.format(len(children) - 5))

# ---- Phase 4: Collect statistics ----
print('\n=== Phase 4: Statistics ===')

def count_all(node, visited, stats, path=''):
    if node.get('id') in visited:
        return
    visited.add(node.get('id'))
    stats['total'] += 1

    title = node.get('title', '')
    current = '{}/{}'.format(path, title) if path else title

    if node.get('task_id'):
        stats['tasks'] += 1
        state = node.get('user_record_skill_state', -1)
        stats['task_by_state'][state] = stats['task_by_state'].get(state, 0) + 1
        stats['task_list'].append({
            'path': current,
            'title': title,
            'task_id': node['task_id'],
            'task_title': node.get('task_title', ''),
            'state': STATE_MAP.get(state, '?'),
            'finish_count': node.get('finish_count', 0),
        })
    else:
        stats['categories'] += 1
        state = node.get('user_record_skill_state', -1)
        stats['cat_by_state'][state] = stats['cat_by_state'].get(state, 0) + 1
        stats['cat_list'].append({
            'path': current,
            'title': title,
            'id': node['id'],
            'state': STATE_MAP.get(state, '?'),
            'children_count': len(node.get('children', [])),
        })

    for child in node.get('children', []):
        count_all(child, visited, stats, current)

stats = {
    'total': 0, 'tasks': 0, 'categories': 0,
    'task_by_state': {}, 'cat_by_state': {},
    'task_list': [], 'cat_list': [],
}
count_all(root, set(), stats)

print('Total nodes: {}'.format(stats['total']))
print('Categories: {}'.format(stats['categories']))
print('Tasks: {}'.format(stats['tasks']))
print()
print('Task by state:')
for s in sorted(stats['task_by_state'].keys()):
    print('  {}: {} tasks'.format(STATE_MAP.get(s, '?'), stats['task_by_state'][s]))
print()
print('Category by state:')
for s in sorted(stats['cat_by_state'].keys()):
    print('  {}: {} categories'.format(STATE_MAP.get(s, '?'), stats['cat_by_state'][s]))

# ---- Build full tree ----
print('\n=== Building full tree ===')

def assemble(node, visited=None):
    if visited is None:
        visited = set()
    nid = node.get('id')
    if nid in visited:
        return dict(node, _circular=True)
    visited.add(nid)

    result = dict(node)
    children = []
    for ch in node.get('children', []):
        ch_id = ch.get('id')
        if ch_id in all_nodes and ch_id != nid:
            children.append(assemble(all_nodes[ch_id], visited.copy()))
        else:
            children.append(ch)
    result['children'] = children
    return result

full_tree = assemble(root)

output = {
    'captured_at': time.strftime('%Y-%m-%d %H:%M:%S'),
    'source_route': '/skilltree',
    'api_endpoint': '/User_API/Skill/getTree',
    'full_tree': full_tree,
    'nodes_captured': len(all_nodes),
    'node_ids': sorted(all_nodes.keys()),
    'stats': stats,
    'state_map': STATE_MAP,
    'how_it_works': 'Lazy-loaded tree. Each click on a category node triggers Skill/getTree API with the node id. The response returns the clicked node with its immediate children populated.',
}

# Save
with open(OUTPUT, 'w', encoding='utf-8') as f:
    json.dump(output, f, ensure_ascii=False, indent=2)
print('Saved: {} ({:,} bytes)'.format(OUTPUT, os.path.getsize(OUTPUT)))

# Also save back to the original requested path
with open('D:/ai/tools/feeder/ctfhub_skilltree.json', 'w', encoding='utf-8') as f:
    json.dump(output, f, ensure_ascii=False, indent=2)

c.close()
print('Done!')
