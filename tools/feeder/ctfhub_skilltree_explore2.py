#!/usr/bin/env python3
"""Explore CTFHub skill tree via CDP and save all data to JSON.
Handles SSL interstitial bypass first."""
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

# ---- Bypass SSL interstitial if needed ----
current_url = c.evaluate('window.location.href')
print(f'Initial URL: {current_url}')
if 'chrome-error' in str(current_url):
    print('SSL interstitial detected, bypassing...')
    c.evaluate("var btn = document.querySelector('#details-button'); if(btn) btn.click();")
    time.sleep(0.8)
    c.evaluate("var link = document.querySelector('#proceed-link'); if(link) link.click();")
    time.sleep(2.5)
    print(f'New URL: {c.evaluate("window.location.href")}')

# Verify Vue app is loaded
has_app = c.evaluate('document.querySelector("#app") !== null')
print(f'Vue app loaded: {has_app}')
if not has_app:
    print('FATAL: Vue app not loaded!')
    c.close()
    sys.exit(1)

result = {
    'captured_at': time.strftime('%Y-%m-%d %H:%M:%S'),
    'url': 'https://www.ctfhub.com/#/skilltree',
}

# ============================================================
# Step 1: Navigate to /skilltree and intercept API responses
# ============================================================
print('\n=== Step 1: Navigate to /skilltree and intercept API ===')
time.sleep(0.5)

# Navigate to skilltree
c.router_push('/skilltree')
time.sleep(2.5)

# Verify we're on skilltree
current_route = c.evaluate("""
    (function() {
        var app = document.querySelector('#app');
        if (app && app.__vue__ && app.__vue__.$router) {
            return app.__vue__.$router.currentRoute.path;
        }
        return 'unknown';
    })()
""")
print(f'Current route: {current_route}')

# Intercept skilltree API
apis = c.intercept_api('ctfhub', '/skilltree', 'getTree', timeout=15)
result['api_responses'] = {}
for name, body in apis.items():
    print(f'  API captured: {name} ({len(body)} bytes)')
    try:
        result['api_responses'][name] = json.loads(body)
    except Exception:
        result['api_responses'][name] = body[:5000]

# Also intercept more broadly - any 'User_API' call
more_apis = c.intercept_api('ctfhub', '/skilltree', 'User_API', timeout=15)
for name, body in more_apis.items():
    if name not in result['api_responses']:
        print(f'  Additional API: {name} ({len(body)} bytes)')
        try:
            result['api_responses'][name] = json.loads(body)
        except Exception:
            result['api_responses'][name] = body[:5000]

# ============================================================
# Step 2: Extract Vuex state
# ============================================================
print('\n=== Step 2: Extract Vuex state ===')
state = c.extract_vuex_state()
result['vuex_state'] = state
if state:
    for key in sorted(state.keys()):
        val = state[key]
        if isinstance(val, dict):
            subkeys = sorted(val.keys())[:30]
            print(f'  state.{key} = dict with keys: {subkeys}')
        elif isinstance(val, list):
            print(f'  state.{key} = list[{len(val)}]')
        else:
            vstr = str(val)[:100]
            print(f'  state.{key} = {vstr}')
else:
    print('  No Vuex state found')

# ============================================================
# Step 3: Click around the skill tree page to trigger API calls
# ============================================================
print('\n=== Step 3: Explore skill tree nodes ===')

# Get all visible nodes/buttons
nodes_data = c.evaluate("""
    (function() {
        var results = [];
        // Look for node elements
        var allEls = document.querySelectorAll('[class*="node"], [class*="skill"], [class*="tree"], .el-tree-node, [class*="item"], [class*="card"]');
        for (var i = 0; i < allEls.length && i < 80; i++) {
            var el = allEls[i];
            var rect = el.getBoundingClientRect();
            if (rect.width > 0 && rect.height > 0 && rect.top < window.innerHeight && rect.top > 0) {
                results.push({
                    tag: el.tagName,
                    className: (el.className || '').toString().slice(0, 120),
                    text: (el.innerText || '').trim().slice(0, 150),
                    children: el.children.length
                });
            }
        }
        return results;
    })()
""")
print(f'  Visible skilltree nodes: {len(nodes_data)}')
for n in nodes_data[:15]:
    print(f'    [{n["tag"]}] class={n["className"][:80]}')
    print(f'      text={n["text"][:100]}')
result['nodes_data'] = nodes_data

# ============================================================
# Step 4: Get full page text and structure
# ============================================================
print('\n=== Step 4: Page content ===')
page_text = c.page_text(10000)
result['page_text'] = page_text
print(f'  Page text: {len(page_text)} chars')
# Print first 2000 non-blank chars
clean = ' '.join(page_text.split())[:2000]
print(f'  Preview: {clean[:500]}...')

# Get structured page info
html = c.page_html()
result['page_html'] = html[:80000]
print(f'  Page HTML: {len(html)} chars total')

# ============================================================
# Step 5: Extract Vue components
# ============================================================
print('\n=== Step 5: Vue components ===')
c.router_push('/skilltree')
time.sleep(1.5)

for keyword in ['skill', 'tree', 'node', 'challenge']:
    comps = c.extract_vue_components(keyword)
    if comps:
        print(f'  Components matching "{keyword}": {len(comps)}')
        for comp in comps[:5]:
            print(f'    {comp["name"]} (depth={comp["depth"]}) methods={comp["methods"][:6]} dataKeys={comp["dataKeys"][:6]}')

# ============================================================
# Step 6: Extract router routes
# ============================================================
print('\n=== Step 6: Router routes ===')
routes = c.extract_router_routes()
result['router_routes'] = routes
print(f'  Routes: {len(routes)}')
for r in routes:
    children = r.get('children', [])
    if isinstance(children, list):
        print(f'    {r.get("path")} -> {r.get("redirect","")} [{len(children)} children]')
    else:
        print(f'    {r.get("path")} -> {r.get("redirect","")}')

# ============================================================
# Step 7: SPA structure discovery
# ============================================================
print('\n=== Step 7: SPA structure ===')
structure = c.discover_structure('ctfhub')
result['spa_structure'] = structure
print(f'  Vuex modules: {list(structure.get("vuex_modules", {}).keys())[:20]}')

# ============================================================
# Step 8: Comprehensive JS data extraction
# ============================================================
print('\n=== Step 8: Deep JS extraction ===')

# Try to get ALL reactive data from skilltree component
deep_data = c.evaluate("""
    (function() {
        var app = document.querySelector('#app');
        if (!app || !app.__vue__) return {error: '#app not found'};

        function walkVm(vm, depth, path) {
            if (depth > 10 || !vm) return null;
            var name = (vm.$options && vm.$options.name) || '';
            var key = path + (path ? '/' : '') + name;

            var info = { name: name, path: key, depth: depth };

            // Get component data (serializable)
            if (vm.$data) {
                var dataKeys = Object.keys(vm.$data).filter(function(k) {
                    return k[0] !== '$' && k[0] !== '_';
                });
                if (dataKeys.length > 0 && dataKeys.length < 50) {
                    var dataSnap = {};
                    for (var i = 0; i < dataKeys.length; i++) {
                        var dk = dataKeys[i];
                        try {
                            var val = vm.$data[dk];
                            var seria = JSON.parse(JSON.stringify(val));
                            dataSnap[dk] = seria;
                        } catch(e) {
                            dataSnap[dk] = '[unserializable: ' + typeof vm.$data[dk] + ']';
                        }
                    }
                    info.data = dataSnap;
                }
            }

            // Children
            if (vm.$children && vm.$children.length > 0) {
                info.children = [];
                for (var i = 0; i < vm.$children.length; i++) {
                    var child = walkVm(vm.$children[i], depth + 1, key);
                    if (child && (child.data || child.children)) {
                        info.children.push(child);
                    }
                }
                if (info.children.length === 0) delete info.children;
            }

            return info;
        }

        return walkVm(app.__vue__, 0, '');
    })()
""", timeout=30)

result['deep_component_tree'] = deep_data

# Print summary
def summarize_tree(node, indent=0):
    prefix = '  ' * indent
    if not node:
        return
    name = node.get('name', '(anon)')
    has_data = 'data' in node and node['data']
    n_children = len(node.get('children', []))
    if has_data:
        dk = sorted(node['data'].keys())
        print(f'{prefix}{name} [data:{dk}]')
    if n_children > 0:
        if not has_data:
            print(f'{prefix}{name} [{n_children} children]')
        if indent < 3:
            for child in node.get('children', [])[:5]:
                summarize_tree(child, indent + 1)
            if n_children > 5:
                print(f'{prefix}  ... and {n_children - 5} more children')

print('Component tree (showing only components with data):')
summarize_tree(deep_data)

# ============================================================
# Save
# ============================================================
print(f'\n=== Saving to {OUTPUT} ...')
with open(OUTPUT, 'w', encoding='utf-8') as f:
    json.dump(result, f, ensure_ascii=False, indent=2)
file_size = os.path.getsize(OUTPUT)
print(f'Saved: {file_size:,} bytes')

# Summary
summary = {
    'captured_at': result['captured_at'],
    'api_endpoints': list(result['api_responses'].keys()),
    'vuex_state_keys': sorted(state.keys()) if state else [],
    'node_count': len(nodes_data),
    'route_count': len(routes),
}
summary_path = OUTPUT.replace('.json', '_summary.json')
with open(summary_path, 'w', encoding='utf-8') as f:
    json.dump(summary, f, ensure_ascii=False, indent=2)
print(f'Summary: {summary_path}')

c.close()
print('\n=== Done! ===')
