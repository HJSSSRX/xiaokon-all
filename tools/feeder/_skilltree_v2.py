#!/usr/bin/env python3
"""Skill tree extraction v2 - login if needed, then extract full tree data."""
import sys, time, json, os
sys.path.insert(0, 'D:/ai')
from tools.feeder.spa_crawler import SpaCrawler

OUTPUT = 'D:/ai/tools/feeder/ctfhub_skilltree.json'
c = SpaCrawler()

if not c.connect('ctfhub'):
    print('FAILED to connect')
    sys.exit(1)

# ----- Check current state -----
print('=== Current State ===')
current_url = c.evaluate('window.location.href')
print(f'URL: {current_url}')

route = c.evaluate("""
    (function() {
        var app = document.querySelector('#app');
        if (app && app.__vue__ && app.__vue__.$router) {
            return app.__vue__.$router.currentRoute.path;
        }
        return 'no router';
    })()
""")
print(f'Route: {route}')

# Check if logged in
login_state = c.evaluate("""
    (function() {
        var app = document.querySelector('#app');
        if (app && app.__vue__ && app.__vue__.$store) {
            var u = app.__vue__.$store.state.user;
            return JSON.stringify({
                loggedIn: !!u.token,
                username: u.username,
                nick: u.nickname
            });
        }
        return 'no store';
    })()
""")
print(f'Login: {login_state}')

# Extract cookies to see if there's an existing session
cookies = c.extract_cookies('ctfhub')
print(f'CTFHub cookies: {len(cookies)}')
for k, v in cookies.items():
    print(f'  {k}={v[:40]}')

# ----- Step 1: Try Page.navigate directly to skilltree -----
print('\n=== Step 1: Direct navigate to /#/skilltree ===')
c._send('Page.navigate', {'url': 'https://www.ctfhub.com/#/skilltree'})
time.sleep(4)

# Clear pending messages
while c._recv_any(0.3):
    pass

new_url = c.evaluate('window.location.href')
new_route = c.evaluate("""
    (function() {
        var app = document.querySelector('#app');
        if (app && app.__vue__ && app.__vue__.$router) {
            return app.__vue__.$router.currentRoute.path;
        }
        return '?';
    })()
""")
print(f'After navigate - URL: {new_url}, Route: {new_route}')

# Check if we see skill tree content
page_text = c.page_text(2000)
print(f'Page text ({len(page_text)} chars):')
print(page_text[:600])

# Check for skill tree elements
tree_els = c.evaluate('document.querySelectorAll("[class*=tree], [class*=Tree], [class*=skill], [class*=Skill]").length')
print(f'Elements with skill/tree class: {tree_els}')

# Check if still on login page
is_login = c.evaluate("""
    (function() {
        return document.querySelector('.login, [class*=login], [class*=Login]') !== null;
    })()
""")
print(f'Is login page: {is_login}')

# ----- If not on skilltree, try login first -----
# Let's look at the login page to understand the form
if is_login:
    print('\n=== Need to login. Analyzing login form... ===')
    form_info = c.evaluate("""
        (function() {
            var inputs = document.querySelectorAll('input');
            var info = [];
            for (var i = 0; i < inputs.length; i++) {
                info.push({
                    type: inputs[i].type,
                    name: inputs[i].name,
                    placeholder: inputs[i].placeholder,
                    id: inputs[i].id
                });
            }
            var buttons = document.querySelectorAll('button');
            var btns = [];
            for (var i = 0; i < buttons.length; i++) {
                btns.push({
                    text: buttons[i].innerText.trim().slice(0, 50),
                    type: buttons[i].type
                });
            }
            return JSON.stringify({inputs: info, buttons: btns});
        })()
    """)
    print(f'Form structure: {form_info}')

c.close()
