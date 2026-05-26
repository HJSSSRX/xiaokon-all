#!/usr/bin/env python3
"""Final skill tree extraction - full data capture from CTFHub skilltree page."""
import sys, time, json, os
sys.path.insert(0, 'D:/ai')
from tools.feeder.spa_crawler import SpaCrawler

OUTPUT = 'D:/ai/tools/feeder/ctfhub_skilltree.json'
c = SpaCrawler()

if not c.connect('ctfhub'):
    print('FAILED to connect')
    sys.exit(1)

# Clear any pending messages
while c._recv_any(0.3):
    pass

# Navigate to skilltree with fresh load to intercept API
print('=== Navigating to skilltree (fresh load for API interception) ===')
c._send('Page.navigate', {'url': 'https://www.ctfhub.com/#/index'})
time.sleep(2.5)
while c._recv_any(0.3):
    pass

# Now intercept the API during navigation to skilltree
print('Intercepting skilltree APIs...')
apis = c.intercept_api('ctfhub', '/skilltree', 'getTree', timeout=20)

result = {
    'captured_at': time.strftime('%Y-%m-%d %H:%M:%S'),
    'source_url': 'https://www.ctfhub.com/#/skilltree',
    'api_responses': {},
    'vuex_state': None,
    'page_text': None,
    'processed_tree': None,
}

print(f'API responses captured: {len(apis)}')
for name, body in apis.items():
    print(f'  {name}: {len(body)} bytes')
    try:
        parsed = json.loads(body)
        result['api_responses'][name] = parsed
        # Print structure summary
        if isinstance(parsed, dict):
            print(f'    Keys: {list(parsed.keys())}')
            if 'data' in parsed:
                data = parsed['data']
                if isinstance(data, dict):
                    print(f'    data keys: {list(data.keys())}')
                    if 'children' in data:
                        print(f'    root has {len(data["children"])} children')
                elif isinstance(data, list):
                    print(f'    data is list[{len(data)}]')
    except Exception as e:
        result['api_responses'][name] = body
        print(f'    (not JSON) {body[:300]}')

# ---- Extract Vuex store ----
print('\n=== Extracting Vuex state ===')
time.sleep(1)

state = c.extract_vuex_state()
result['vuex_state'] = state

if state:
    print(f'Vuex top keys: {sorted(state.keys())}')
    for key in sorted(state.keys()):
        val = state[key]
        if isinstance(val, dict):
            sk = sorted(val.keys())[:20]
            print(f'  state.{key}: dict[{len(sk)}] keys={sk}')
            # Deep dive into skill/tree modules
            for subk in sk:
                subval = val[subk]
                if isinstance(subval, (dict, list)):
                    s = json.dumps(subval, ensure_ascii=False)
                    if len(s) > 150:
                        s = s[:150] + '...'
                    print(f'    .{subk}: {s}')
                elif isinstance(subval, str):
                    print(f'    .{subk}: "{subval[:80]}"')
                else:
                    print(f'    .{subk}: {subval}')
        elif isinstance(val, list):
            print(f'  state.{key}: list[{len(val)}]')
        else:
            print(f'  state.{key}: {str(val)[:100]}')
else:
    print('No Vuex state!')

# ---- Extract page text ----
print('\n=== Page text ===')
text = c.page_text(5000)
result['page_text'] = text
print(f'Text length: {len(text)} chars')
print(text[:1500])

# ---- Extract DOM tree structures ----
print('\n=== DOM skill tree elements ===')
tree_elements = c.evaluate("""
    (function() {
        // Find the skill tree container
        var containers = document.querySelectorAll('[class*="skill"], [class*="tree"], [class*="Skill"], [class*="Tree"]');
        var results = [];
        for (var i = 0; i < containers.length && i < 30; i++) {
            var el = containers[i];
            var rect = el.getBoundingClientRect();
            if (rect.width > 50 && rect.height > 20) {
                results.push({
                    tag: el.tagName,
                    className: (el.className || '').toString().slice(0, 150),
                    text: (el.innerText || '').trim().slice(0, 200),
                    childrenCount: el.children.length,
                    rect: {w: Math.round(rect.width), h: Math.round(rect.height)}
                });
            }
        }
        return results;
    })()
""")
print(f'Found {len(tree_elements)} skill/tree elements')
for el in tree_elements[:20]:
    print(f'  <{el["tag"]}> {el["className"][:80]}')
    print(f'    rect={el["rect"]} text={el["text"][:100]}')

# ---- Extract nested skill tree from DOM ----
print('\n=== Extract tree from DOM ===')
dom_tree = c.evaluate("""
    (function() {
        // Look for the tree container
        var treeContainer = document.querySelector('.skill-tree, .tree-container, [class*="tree-view"], [class*="TreeView"]');
        if (!treeContainer) {
            // Try to find the main tree by looking at page structure
            var allText = document.body.innerText;
            // Find the element with most mentions of 'Web', 'Pwn', etc
            var divs = document.querySelectorAll('div');
            var bestMatch = null;
            var bestScore = 0;
            for (var i = 0; i < divs.length; i++) {
                var div = divs[i];
                if (div.children.length >= 5 && div.children.length <= 50) {
                    var txt = div.innerText || '';
                    var score = (txt.match(/Web|Pwn|Reverse|Crypto|Misc|BlockChain|签到|彩蛋/g) || []).length;
                    if (score > bestScore) {
                        bestScore = score;
                        bestMatch = div;
                    }
                }
            }
            if (bestMatch) {
                // Extract children recursively
                function extractNode(el, depth) {
                    if (depth > 5 || !el) return null;
                    var text = (el.innerText || '').trim().slice(0, 200);
                    // Skip text-only leaf nodes
                    if (el.children.length === 0 && text.length < 200) {
                        return text;
                    }
                    var node = {
                        tag: el.tagName,
                        className: (el.className || '').toString().slice(0, 100),
                        children: []
                    };
                    // Add meaningful text from this node directly
                    var directText = '';
                    for (var c = 0; c < el.childNodes.length; c++) {
                        if (el.childNodes[c].nodeType === 3) { // Text node
                            directText += el.childNodes[c].textContent.trim();
                        }
                    }
                    if (directText) node.text = directText.slice(0, 80);

                    for (var c = 0; c < Math.min(el.children.length, 30); c++) {
                        var child = extractNode(el.children[c], depth + 1);
                        if (child) node.children.push(child);
                    }
                    return node;
                }
                return extractNode(bestMatch, 0);
            }
        }
        return {error: 'No tree container found'};
    })()
""", timeout=20)
result['dom_tree'] = dom_tree
print(json.dumps(dom_tree, ensure_ascii=False)[:3000])

# ---- Extract all task/challenge IDs from the page ----
print('\n=== Extract task IDs and links ===')
task_data = c.evaluate("""
    (function() {
        var allData = [];
        // Look for data attributes
        var elementsWithData = document.querySelectorAll('[data-id], [data-task], [data-task-id], [data-node-id]');
        for (var i = 0; i < elementsWithData.length && i < 100; i++) {
            var el = elementsWithData[i];
            allData.push({
                tag: el.tagName,
                dataset: JSON.parse(JSON.stringify(el.dataset)),
                text: (el.innerText || '').trim().slice(0, 60)
            });
        }
        return allData;
    })()
""")
print(f'Elements with data attributes: {len(task_data)}')
for td in task_data[:20]:
    print(f'  {td}')

# ---- Look for Vue devtools data or __vue__ component data ----
print('\n=== Vue component data search ===')
# Search for skilltree component in Vue tree
skilltree_vue = c.evaluate("""
    (function() {
        var app = document.querySelector('#app');
        if (!app || !app.__vue__) return {error: 'no vue'};

        function findByName(vm, depth, name) {
            if (depth > 8 || !vm) return null;
            var cname = (vm.$options && vm.$options.name) || '';
            if (cname.toLowerCase().indexOf(name) > -1) {
                var info = {name: cname, depth: depth};
                if (vm.$data) {
                    var dataKeys = Object.keys(vm.$data).filter(function(k) {
                        return k[0] !== '$' && k[0] !== '_';
                    });
                    if (dataKeys.length > 0) {
                        var snap = {};
                        for (var i = 0; i < dataKeys.length; i++) {
                            try {
                                snap[dataKeys[i]] = JSON.parse(JSON.stringify(vm.$data[dataKeys[i]]));
                            } catch(e) {
                                snap[dataKeys[i]] = '[unserializable]';
                            }
                        }
                        info.data = snap;
                    }
                }
                return info;
            }
            if (vm.$children) {
                for (var i = 0; i < vm.$children.length; i++) {
                    var found = findByName(vm.$children[i], depth + 1, name);
                    if (found) return found;
                }
            }
            return null;
        }

        var results = {};
        var keywords = ['skill', 'tree', 'progress', 'node', 'category'];
        for (var i = 0; i < keywords.length; i++) {
            var found = findByName(app.__vue__, 0, keywords[i]);
            if (found) results[keywords[i]] = found;
        }
        return results;
    })()
""", timeout=25)

result['vue_component_data'] = skilltree_vue
print(json.dumps(skilltree_vue, ensure_ascii=False, indent=2)[:4000])

# ---- Save everything ----
print(f'\n=== Saving to {OUTPUT} ===')
with open(OUTPUT, 'w', encoding='utf-8') as f:
    json.dump(result, f, ensure_ascii=False, indent=2)

file_size = os.path.getsize(OUTPUT)
print(f'Saved: {file_size:,} bytes')

# Create summary
summary = {
    'captured_at': result['captured_at'],
    'api_endpoints': list(result['api_responses'].keys()),
    'vuex_keys': sorted(state.keys()) if state else [],
    'has_skill_tree_data': bool(result['api_responses']),
}

# Process API response into readable tree if available
for name, resp in result['api_responses'].items():
    if isinstance(resp, dict):
        if 'data' in resp:
            summary['api_data_root_keys'] = list(resp['data'].keys()) if isinstance(resp['data'], dict) else 'list'
            summary['api_status'] = resp.get('status')
            summary['api_msg'] = resp.get('msg', '')

summary_path = OUTPUT.replace('.json', '_summary.json')
with open(summary_path, 'w', encoding='utf-8') as f:
    json.dump(summary, f, ensure_ascii=False, indent=2)
print(f'Summary: {summary_path}')

c.close()
print('\n=== Done! ===')
