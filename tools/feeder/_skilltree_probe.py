#!/usr/bin/env python3
"""Quick probe: check login state and navigate to skilltree."""
import sys, time, json, os
sys.path.insert(0, 'D:/ai')
from tools.feeder.spa_crawler import SpaCrawler

c = SpaCrawler()
c.connect('ctfhub')

# Check login state
token = c.evaluate("""
    (function() {
        var app = document.querySelector('#app');
        if (app && app.__vue__ && app.__vue__.$store) {
            var user = app.__vue__.$store.state.user;
            return JSON.stringify({
                username: user.username,
                hasToken: !!user.token,
                nick: user.nickname
            });
        }
        return 'no store';
    })()
""")
print('Login state:', token)

# Navigate directly to skilltree
result = c.evaluate("""
    (function() {
        var app = document.querySelector('#app');
        if (app && app.__vue__ && app.__vue__.$router) {
            app.__vue__.$router.push('/skilltree');
            return 'navigating';
        }
        return 'no router';
    })()
""")
print('Router push:', result)
time.sleep(3)

# Check where we are now
route = c.evaluate("""
    (function() {
        var app = document.querySelector('#app');
        if (app && app.__vue__ && app.__vue__.$router) {
            return app.__vue__.$router.currentRoute.path;
        }
        return 'unknown';
    })()
""")
print('Current route:', route)

# Check page text
text = c.page_text(2000)
print(f'Page text ({len(text)} chars):')
# Filter printable
safe = ''.join(c if ord(c) < 128 or ord(c) > 0x4e00 else c for c in text)
print(safe[:800])

# Check for tree elements
tree_count = c.evaluate('document.querySelectorAll("[class*=tree], [class*=skill]").length')
print(f'Elements with tree/skill class: {tree_count}')

# Try intercepting API on skilltree navigation
api_data = c.intercept_api('ctfhub', '/skilltree', 'tree', timeout=15)
print(f'API responses: {len(api_data)}')
for name, body in api_data.items():
    print(f'  {name}: {len(body)} bytes')
    try:
        parsed = json.loads(body)
        print(f'  Parsed: {json.dumps(parsed, ensure_ascii=False)[:1000]}')
    except:
        print(f'  Raw: {body[:500]}')

c.close()
