#!/usr/bin/env python3
"""Explore CTFHub skill tree via CDP and save all data to JSON."""
import sys, time, json, os
sys.path.insert(0, 'D:/ai')
from tools.feeder.spa_crawler import SpaCrawler

OUTPUT = 'D:/ai/tools/feeder/ctfhub_skilltree.json'
c = SpaCrawler()

print('CDP Status:', c.is_ready)

if not c.connect('ctfhub'):
    print('FAILED to connect')
    c.close()
    sys.exit(1)

result = {
    'captured_at': time.strftime('%Y-%m-%d %H:%M:%S'),
    'url': 'https://www.ctfhub.com/#/skilltree',
}

# ============================================================
# Step 1: Navigate to skilltree and capture API
# ============================================================
print('Step 1: Navigating to /skilltree and capturing API...')

time.sleep(0.5)
c.router_push('/skilltree')
time.sleep(2.5)

# Now intercept the skilltree API (it should trigger on navigation)
print('Intercepting skilltree APIs...')
apis = c.intercept_api('ctfhub', '/skilltree', 'getTree', timeout=15)
result['api_responses'] = {}
for name, body in apis.items():
    print(f'  Captured API: {name} ({len(body)} bytes)')
    try:
        result['api_responses'][name] = json.loads(body)
    except Exception:
        result['api_responses'][name] = body[:5000]

# Also try intercepting more broadly
print('Intercepting any skilltree-related APIs...')
more_apis = c.intercept_api('ctfhub', '/skilltree', 'skill', timeout=15)
for name, body in more_apis.items():
    if name not in result['api_responses']:
        print(f'  Captured additional API: {name} ({len(body)} bytes)')
        try:
            result['api_responses'][name] = json.loads(body)
        except Exception:
            result['api_responses'][name] = body[:5000]

# ============================================================
# Step 2: Extract Vuex state
# ============================================================
print('\nStep 2: Extracting Vuex store state...')
state = c.extract_vuex_state()
result['vuex_state'] = state
if state:
    # Print a summary of top-level keys
    top_keys = list(state.keys())
    print(f'  Vuex top-level keys: {top_keys}')
    # Drill into skill/skilltree related modules
    for key in top_keys:
        val = state[key]
        if isinstance(val, dict):
            subkeys = list(val.keys())[:30]
            print(f'  state.{key} sub-keys: {subkeys}')
            # Deep dive into skilltree
            if 'skill' in str(key).lower() or 'tree' in str(key).lower():
                print(f'    >>> SKILLTREE DATA in state.{key}:')
                print(json.dumps(val, ensure_ascii=False, indent=2)[:3000])
        elif isinstance(val, list):
            print(f'  state.{key} is list with {len(val)} items')
        else:
            val_str = str(val)[:200]
            print(f'  state.{key} = {val_str}')

# ============================================================
# Step 3: Extract components related to skilltree
# ============================================================
print('\nStep 3: Extracting skilltree-related Vue components...')
# Navigate again to ensure we're on the right page
c.router_push('/skilltree')
time.sleep(1.5)

# Search for skilltree components
components = c.extract_vue_components('skill')
result['skilltree_components'] = components
print(f'  Found {len(components)} skilltree-related components')

# Also search for "tree" components
tree_comps = c.extract_vue_components('tree')
existing_names = {c['name'] for c in components}
for comp in tree_comps:
    if comp['name'] not in existing_names:
        components.append(comp)
result['skilltree_components'] = components
for comp in components:
    print(f'  - {comp["name"]} (depth={comp["depth"]}) methods={comp["methods"][:5]} dataKeys={comp["dataKeys"][:5]}')

# ============================================================
# Step 4: DOM inspection
# ============================================================
print('\nStep 4: DOM inspection of skilltree page...')

# Get the page HTML
html = c.page_html()
result['page_html'] = html[:50000]
print(f'  Page HTML: {len(html)} chars total, saved first 50000')

# Query the skill tree elements
tree_els = c.dom_query('.skill-tree, .skilltree, [class*="skill"], [class*="tree"]')
result['dom_skilltree_elements'] = tree_els
print(f'  Skill tree DOM elements: {len(tree_els)}')
for el in tree_els[:15]:
    print(f'    <{el["tag"]}> class="{el["cls"]}" text="{el["text"][:80]}"')

# Query for node/challenge status elements
node_els = c.dom_query('.node, [class*="node"], .challenge-item, [class*="challenge"]')
result['dom_node_elements'] = node_els[:50]
print(f'  Node elements: {len(node_els)}')
for el in node_els[:10]:
    print(f'    <{el["tag"]}> class="{el["cls"]}" text="{el["text"][:80]}"')

# Query lock/unlock indicators
lock_els = c.dom_query('.lock, .locked, .unlock, .unlocked, [class*="lock"], [class*="status"]')
result['dom_lock_elements'] = lock_els[:30]
print(f'  Lock/status elements: {len(lock_els)}')

# ============================================================
# Step 5: Try to get more detail about each node by clicking
# ============================================================
print('\nStep 5: Exploring interactive elements...')

# Get all clickable elements in the skill tree
clickable_info = c.evaluate("""
    (function() {
        var treeArea = document.querySelector('.skill-tree, .skilltree, [class*="skill-tree"], [class*="skillTree"]');
        if (!treeArea) {
            // Try to find the main content area
            treeArea = document.querySelector('.main, .content, [class*="main"], [class*="content"]');
        }
        if (!treeArea) treeArea = document.body;

        var clickables = treeArea.querySelectorAll('a, button, [role="button"], .node, [class*="node"], [class*="clickable"], [class*="cursor-pointer"]');
        var results = [];
        for (var i = 0; i < clickables.length && i < 50; i++) {
            var el = clickables[i];
            var rect = el.getBoundingClientRect();
            if (rect.width > 0 && rect.height > 0 && rect.top < window.innerHeight) {
                results.push({
                    tag: el.tagName,
                    className: (el.className || '').toString().slice(0, 80),
                    text: (el.innerText || '').trim().slice(0, 100),
                    rect: {x: Math.round(rect.x), y: Math.round(rect.y), w: Math.round(rect.width), h: Math.round(rect.height)},
                    href: el.getAttribute('href') || '',
                });
            }
        }
        return results;
    })()
""")
result['clickable_elements'] = clickable_info
print(f'  Found {len(clickable_info)} clickable elements in viewport')
for el in clickable_info[:20]:
    print(f'    <{el["tag"]}> class="{el["className"][:60]}" text="{el["text"][:60]}" href="{el["href"]}')

# ============================================================
# Step 6: Try to extract detailed tree structure via JS
# ============================================================
print('\nStep 6: Extracting detailed tree structure via JS...')

tree_structure = c.evaluate("""
    (function() {
        // Try multiple approaches to get tree data

        // Approach 1: Check for a treeData or skillTreeData in the component
        var app = document.querySelector('#app');
        if (app && app.__vue__) {
            // Walk the component tree to find skilltree component
            function findSkillTree(vm, depth) {
                if (depth > 8 || !vm) return null;
                var name = (vm.$options && vm.$options.name) || '';
                if (name.toLowerCase().indexOf('skill') > -1 || name.toLowerCase().indexOf('tree') > -1) {
                    // Found it, get its data
                    var data = {};
                    if (vm.treeData) data.treeData = vm.treeData;
                    if (vm.skillTree) data.skillTree = vm.skillTree;
                    if (vm.nodes) data.nodes = vm.nodes;
                    if (vm.$data) {
                        // Get serializable data keys
                        var keys = Object.keys(vm.$data).filter(function(k) { return k[0] !== '$' && k[0] !== '_'; });
                        for (var i = 0; i < keys.length; i++) {
                            var key = keys[i];
                            try {
                                var val = JSON.parse(JSON.stringify(vm.$data[key]));
                                data[key] = val;
                            } catch(e) {}
                        }
                    }
                    return data;
                }
                if (vm.$children) {
                    for (var i = 0; i < vm.$children.length; i++) {
                        var found = findSkillTree(vm.$children[i], depth + 1);
                        if (found) return found;
                    }
                }
                return null;
            }
            var treeData = findSkillTree(app.__vue__, 0);
            if (treeData) return treeData;
        }

        // Approach 2: Check DOM for data attributes
        var dataElements = document.querySelectorAll('[data-tree], [data-nodes], [data-skill]');
        if (dataElements.length > 0) {
            var attrs = {};
            for (var i = 0; i < Math.min(dataElements.length, 10); i++) {
                var el = dataElements[i];
                attrs['el' + i] = {
                    tag: el.tagName,
                    dataset: JSON.parse(JSON.stringify(el.dataset))
                };
            }
            return {dataElements: attrs};
        }

        return {error: 'No tree data found in component or DOM'};
    })()
""", timeout=15)
result['tree_structure_js'] = tree_structure
print(f'  JS tree extraction result: {json.dumps(tree_structure, ensure_ascii=False)[:2000]}')

# ============================================================
# Step 7: Extract router and full SPA structure
# ============================================================
print('\nStep 7: Extracting full SPA structure...')
structure = c.discover_structure('ctfhub')
result['spa_structure'] = structure
print(f'  Routes: {len(structure.get("routes", []))}')
print(f'  Vuex modules: {list(structure.get("vuex_modules", {}).keys())}')
print(f'  Components: {len(structure.get("components", []))}')

# ============================================================
# Save everything
# ============================================================
print(f'\n=== Saving to {OUTPUT} ...')
with open(OUTPUT, 'w', encoding='utf-8') as f:
    json.dump(result, f, ensure_ascii=False, indent=2)
file_size = os.path.getsize(OUTPUT)
print(f'Saved: {file_size:,} bytes')

# Also save a compact summary
summary = {
    'captured_at': result['captured_at'],
    'vuex_top_keys': list(state.keys()) if state else [],
    'vuex_skilltree_data': {},
    'api_endpoints': list(result['api_responses'].keys()),
    'component_count': len(result.get('skilltree_components', [])),
    'dom_skilltree_element_count': len(result.get('dom_skilltree_elements', [])),
    'dom_node_element_count': len(result.get('dom_node_elements', [])),
    'clickable_count': len(result.get('clickable_elements', [])),
    'route_count': len(structure.get('routes', [])),
}

# Extract skilltree-specific data from vuex
if state:
    for key, val in state.items():
        if 'skill' in str(key).lower() or 'tree' in str(key).lower():
            if isinstance(val, dict):
                summary['vuex_skilltree_data'][key] = {
                    'keys': list(val.keys())[:50],
                    'type': 'dict'
                }
            elif isinstance(val, list):
                summary['vuex_skilltree_data'][key] = {
                    'length': len(val),
                    'type': 'list',
                    'sample': val[:3] if len(val) > 0 else []
                }
            else:
                summary['vuex_skilltree_data'][key] = str(val)[:200]

summary_path = OUTPUT.replace('.json', '_summary.json')
with open(summary_path, 'w', encoding='utf-8') as f:
    json.dump(summary, f, ensure_ascii=False, indent=2)
print(f'Summary saved: {summary_path}')

c.close()
print('\n=== Done! ===')
