#!/usr/bin/env python3
"""Extract skill tree from DOM directly - the full tree is rendered in org-tree HTML."""
import sys, time, json, os
sys.path.insert(0, 'D:/ai')
from tools.feeder.spa_crawler import SpaCrawler

OUTPUT = 'D:/ai/tools/feeder/ctfhub_skilltree.json'
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

# Enable domains
c._send('Network.enable')
c._send('Runtime.enable')
time.sleep(0.3)
while c._recv_any(0.3):
    pass

# Extract the complete DOM tree structure
print('\n=== Extracting org-tree DOM structure ===')

# 1. Get all org-tree-node-label-inner elements (the labeled nodes)
labels_data = c.evaluate("""
    (function() {
        var labels = document.querySelectorAll('.org-tree-node-label-inner');
        var results = [];
        for (var i = 0; i < labels.length; i++) {
            var el = labels[i];
            var computed = window.getComputedStyle(el);
            // Get parent node info
            var parentNode = el.closest('.org-tree-node');
            var isLeaf = parentNode ? parentNode.classList.contains('is-leaf') : false;

            results.push({
                text: el.innerText.trim(),
                className: el.className,
                isLeaf: isLeaf,
                bgColor: computed.backgroundColor,
                cursor: computed.cursor,
            });
        }
        return results;
    })()
""")
print('Labels found:', len(labels_data))
for l in labels_data:
    leaf_str = ' [LEAF]' if l.get('isLeaf') else ''
    print('  "{}" {} {}'.format(l['text'], l['className'], leaf_str))

# 2. Extract the full tree hierarchy from the DOM
# The org-tree has this structure:
# .org-tree-container > .org-tree > .org-tree-node (recursive)
# Each org-tree-node has:
#   .org-tree-node-label > .org-tree-node-label-inner (the visible label)
#   .org-tree-node-children (recursive children)

tree_hierarchy = c.evaluate("""
    (function() {
        function extractNode(el, depth) {
            if (depth > 8 || !el) return null;

            var isNode = el.classList && el.classList.contains('org-tree-node');
            if (!isNode) {
                // Check if it's the outer container
                if (el.classList && (el.classList.contains('org-tree') || el.classList.contains('org-tree-container'))) {
                    var children = [];
                    for (var i = 0; i < el.children.length; i++) {
                        var child = extractNode(el.children[i], depth);
                        if (child) children.push(child);
                    }
                    return children.length > 0 ? children : null;
                }
                return null;
            }

            // Get the label
            var labelEl = el.querySelector('.org-tree-node-label-inner');
            var label = labelEl ? labelEl.innerText.trim() : '?';
            var className = labelEl ? labelEl.className : '';
            var isLeaf = el.classList.contains('is-leaf');

            var result = {
                label: label,
                className: className,
                isLeaf: isLeaf,
                children: []
            };

            // Find children container
            var childrenContainer = el.querySelector('.org-tree-node-children');
            if (childrenContainer && !isLeaf) {
                for (var i = 0; i < childrenContainer.children.length; i++) {
                    var child = extractNode(childrenContainer.children[i], depth + 1);
                    if (child) result.children.push(child);
                }
            }

            return result;
        }

        // Start from the tree container
        var treeContainer = document.querySelector('.org-tree');
        if (!treeContainer) treeContainer = document.querySelector('.org-tree-container');
        if (!treeContainer) return {error: 'No org-tree found'};

        return extractNode(treeContainer, 0);
    })()
""", timeout=15)

print('\n=== DOM Tree Hierarchy ===')
def print_dom_tree(node, indent=0):
    if isinstance(node, list):
        for item in node:
            print_dom_tree(item, indent)
        return
    if isinstance(node, str):
        print('{}{}'.format('  ' * indent, node))
        return
    if isinstance(node, dict):
        if 'error' in node:
            print('Error:', node['error'])
            return
        prefix = '  ' * indent
        leaf = ' [LEAF]' if node.get('isLeaf') else ''
        print('{}{} {} ({})'.format(prefix, node.get('label', '?'),
                                     node.get('className', ''), leaf))
        for child in node.get('children', []):
            print_dom_tree(child, indent + 1)

print_dom_tree(tree_hierarchy)

# 3. Also extract the initial API response for node IDs and metadata
print('\n=== Capturing API data ===')

# Intercept the getTree API during navigation
c._send('Page.navigate', {'url': 'https://www.ctfhub.com/#/index'})
time.sleep(2)
while c._recv_any(0.3):
    pass

# Intercept during route push
api_data = c.intercept_api('ctfhub', '/skilltree', 'getTree', timeout=15, away_first=None)

api_tree = None
for name, body in api_data.items():
    try:
        data = json.loads(body)
        if isinstance(data, dict) and 'data' in data:
            node = data['data']
            api_tree = node
            print('API tree root: "{}" (id={})'.format(node.get('title'), node.get('id')))
    except:
        pass

# 4. Try to get ALL node data by clicking through the tree
# First, let's extract all node IDs from the API tree
print('\n=== Extracting all node IDs from API tree ===')

def extract_all_nodes(node, node_map=None):
    if node_map is None:
        node_map = {}
    nid = node.get('id')
    if nid:
        node_map[nid] = {
            'title': node.get('title'),
            'task_id': node.get('task_id'),
            'task_title': node.get('task_title'),
            'user_record_skill_state': node.get('user_record_skill_state'),
            'finish_count': node.get('finish_count'),
            'pid': node.get('pid'),
            'level': node.get('level'),
            'children_ids': [c.get('id') for c in node.get('children', [])],
        }
    for child in node.get('children', []):
        extract_all_nodes(child, node_map)
    return node_map

if api_tree:
    node_map = extract_all_nodes(api_tree)
    print('Nodes from API:', len(node_map))
else:
    node_map = {}
    print('No API tree data')

# 5. Map DOM labels to API node IDs
# We need this to know which DOM element corresponds to which API node
print('\n=== Building label-to-ID mapping ===')

# Build a mapping from the API tree
def build_label_id_map(node, label_map=None):
    if label_map is None:
        label_map = {}
    title = node.get('title')
    nid = node.get('id')
    if title and nid:
        if title not in label_map:
            label_map[title] = nid
        # Prefer the non-task node ID for categories
        elif not node.get('task_id') and label_map.get(title):
            pass  # Keep the first mapping
    for child in node.get('children', []):
        build_label_id_map(child, label_map)
    return label_map

label_id_map = {}
if api_tree:
    label_id_map = build_label_id_map(api_tree)
    print('Label-to-ID mapping:', label_id_map)

# 6. Click each major category to get detailed children
# We'll navigate to skilltree, click a category, capture the response, reset
print('\n=== Clicking categories to expand ===')

def navigate_and_wait():
    c._send('Page.navigate', {'url': 'https://www.ctfhub.com/#/skilltree'})
    time.sleep(3)
    while c._recv_any(0.3):
        pass

def click_and_capture(label, nid=None):
    """Navigate to skilltree, click label, capture getTree response."""
    navigate_and_wait()
    c._send('Network.enable')
    time.sleep(0.3)
    while c._recv_any(0.3):
        pass

    # Click
    r = c.evaluate("""
        (function() {
            var labels = document.querySelectorAll('.org-tree-node-label-inner');
            for (var i = 0; i < labels.length; i++) {
                if (labels[i].innerText.trim() === arguments[0]) {
                    labels[i].click();
                    return true;
                }
            }
            return false;
        })()
    """.replace('arguments[0]', json.dumps(label)))

    if not r:
        return None, []

    time.sleep(0.4)

    # Capture
    mid_to_info = {}
    result_node = None
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
                mid_to_info[mid] = True
        elif 'id' in msg:
            mid = msg.get('id')
            if mid in mid_to_info:
                body = msg.get('result', {}).get('body', '')
                try:
                    d = json.loads(body)
                    if isinstance(d, dict) and 'data' in d:
                        result_node = d['data']
                except:
                    pass

    # Get visible labels
    labels = c.evaluate("""
        (function() {
            var labels = document.querySelectorAll('.org-tree-node-label-inner');
            var r = [];
            for (var i = 0; i < labels.length; i++)
                r.push(labels[i].innerText.trim());
            return r;
        })()
    """)

    return result_node, labels

STATE_MAP = {0: 'mastered', 1: 'learning', 2: 'unlearned'}

# Categories we know are visible (from DOM)
categories = ['Web', 'Pwn', 'Reverse', 'Crypto', 'Misc', '彩蛋', 'BlockChain']

all_expanded = {}
all_labels_seen = {}

for cat in categories:
    print('\n--- "{}" ---'.format(cat))
    node, labels = click_and_capture(cat)

    if node:
        nid = node.get('id')
        children = node.get('children', [])
        print('  API returned: "{}" (id={}) with {} children'.format(
            node.get('title'), nid, len(children)))
        if nid:
            all_expanded[nid] = node
        for ch in children:
            s = STATE_MAP.get(ch.get('user_record_skill_state', -1), '?')
            t = '[TASK]' if ch.get('task_id') else '[CAT]'
            print('    {} {} (id={}, {})'.format(t, ch.get('title'), ch.get('id'), s))
    else:
        print('  No API response')

    print('  DOM labels:', labels[:15])
    all_labels_seen[cat] = labels

# ================================================================
# Save everything
# ================================================================

output = {
    'captured_at': time.strftime('%Y-%m-%d %H:%M:%S'),
    'source': 'CTFHub /#/skilltree via CDP (DOM extraction + API capture)',
    'api_endpoint': '/User_API/Skill/getTree',

    # Full DOM tree hierarchy (all visible nodes)
    'dom_tree': tree_hierarchy,

    # API tree (initial load - may be shallow for non-logged-in)
    'api_tree': api_tree,

    # Node metadata from API
    'node_map': node_map,

    # Expanded nodes (from clicking categories)
    'expanded_nodes': {str(k): v for k, v in all_expanded.items()},

    # Labels seen when clicking each category
    'category_labels': all_labels_seen,

    # Label to ID mapping
    'label_id_map': label_id_map,

    # Statistics
    'stats': {
        'dom_labels_count': len(labels_data),
        'api_nodes_count': len(node_map),
        'expanded_nodes_count': len(all_expanded),
        'categories_clicked': len(categories),
    },
}

with open(OUTPUT, 'w', encoding='utf-8') as f:
    json.dump(output, f, ensure_ascii=False, indent=2)

fsize = os.path.getsize(OUTPUT)
print('\nSaved: {} ({:,} bytes)'.format(OUTPUT, fsize))

# Summary
print('\n=== Summary ===')
print('DOM tree labels:')
print_dom_tree(tree_hierarchy)

if api_tree:
    print('\nAPI tree structure:')
    def print_api_tree(node, indent=0):
        prefix = '  ' * indent
        state = STATE_MAP.get(node.get('user_record_skill_state'), '?')
        task = ''
        if node.get('task_id'):
            task = ' [TASK id={}]'.format(node.get('task_id'))
        print('{}[{}] {}{} (id={}, {} children)'.format(
            prefix, state, node.get('title'), task,
            node.get('id'), len(node.get('children', []))))
        for child in node.get('children', []):
            print_api_tree(child, indent + 1)
    print_api_tree(api_tree)

c.close()
print('\nDone!')
