#!/usr/bin/env python3
"""Diagnose CTFHub page structure — find framework, DOM, data location."""
import json
import sys
import time
import urllib.request

import websocket

CDP = "http://127.0.0.1:9222"


def find_tab(fragment):
    tabs = json.loads(urllib.request.urlopen(f"{CDP}/json").read())
    for t in tabs:
        if t["type"] == "page" and fragment in t.get("url", "").lower():
            return t
    return None


def main():
    target = find_tab("ctfhub")
    if not target:
        print("CTFHub tab not found!")
        # List all tabs
        tabs = json.loads(urllib.request.urlopen(f"{CDP}/json").read())
        for t in tabs:
            print(f"  [{t['type']}] {t.get('title','')[:80]} | {t.get('url','')[:100]}")
        sys.exit(1)

    print(f"Tab: {target['title']} | {target['url']}")
    ws = websocket.create_connection(target["webSocketDebuggerUrl"], timeout=10)

    def send(method, params=None, msg_id=1):
        ws.send(json.dumps(dict(id=msg_id, method=method, params=params or {})))

    def recv(msg_id, timeout=10):
        deadline = time.time() + timeout
        while time.time() < deadline:
            ws.settimeout(max(0.3, deadline - time.time()))
            try:
                msg = json.loads(ws.recv())
                if msg.get("id") == msg_id:
                    return msg
            except websocket.WebSocketTimeoutException:
                break
            except Exception:
                break
        return None

    def evaluate(code, timeout=10):
        send("Runtime.evaluate", {"expression": code, "returnByValue": True, "awaitPromise": False}, msg_id=99)
        resp = recv(99, timeout)
        if resp:
            result = resp.get("result", {}).get("result", {})
            value = result.get("value")
            if result.get("subtype") == "error" or result.get("description"):
                return f"ERROR: {result.get('description', '')}"
            return value
        return "TIMEOUT"

    send("Runtime.enable", msg_id=1)
    recv(1, 3)
    send("DOM.enable", msg_id=2)
    recv(2, 3)

    # 1. Basic DOM structure
    print("\n=== 1. DOM Structure ===")
    result = evaluate("""
        (function() {
            var info = {
                url: location.href,
                title: document.title,
                bodyChildCount: document.body ? document.body.children.length : 0,
                rootDivs: []
            };
            // Find all root-level divs with id or class
            var roots = document.querySelectorAll('body > div[id], body > div[class], body > main, body > section');
            for (var i = 0; i < Math.min(roots.length, 15); i++) {
                var r = roots[i];
                info.rootDivs.push({
                    tag: r.tagName,
                    id: r.id,
                    cls: (r.className || '').slice(0, 80),
                    childCount: r.children.length
                });
            }
            return JSON.stringify(info, null, 2);
        })()
    """)
    print(result)

    # 2. Vue/React framework detection
    print("\n=== 2. Framework Detection ===")
    result = evaluate("""
        (function() {
            var info = {
                hasVue: typeof Vue !== 'undefined',
                hasVue2: false,
                hasVue3: false,
                hasReact: typeof React !== 'undefined',
                hasAngular: typeof angular !== 'undefined',
                vueVersion: null,
                reactVersion: null
            };
            if (info.hasVue && Vue.version) info.vueVersion = Vue.version;
            if (info.hasReact && React.version) info.reactVersion = React.version;

            // Check Vue 3 app
            var appEl = document.querySelector('#app');
            if (appEl) {
                info.hasAppEl = true;
                info.appElKeys = Object.keys(appEl).filter(function(k) {
                    return k.startsWith('__') || k.startsWith('_');
                });
            } else {
                info.hasAppEl = false;
            }

            // Check for Vue app instances via all elements
            var vueEls = [];
            var all = document.querySelectorAll('*');
            for (var i = 0; i < Math.min(all.length, 100); i++) {
                var keys = Object.keys(all[i]);
                var vueKeys = keys.filter(function(k) { return k === '__vue__' || k === '__vue_app__'; });
                if (vueKeys.length > 0) {
                    vueEls.push({
                        tag: all[i].tagName,
                        id: all[i].id,
                        cls: (all[i].className || '').slice(0, 60),
                        vueKeys: vueKeys
                    });
                }
            }
            info.vueElements = vueEls;

            return JSON.stringify(info, null, 2);
        })()
    """)
    print(result)

    # 3. Check for data in DOM (e.g. data attributes, JSON script tags)
    print("\n=== 3. Data in DOM ===")
    result = evaluate("""
        (function() {
            var info = {
                dataAttrs: [],
                jsonScripts: []
            };
            // Check for data- attributes on root
            var roots = document.querySelectorAll('body > *, [data-*]');
            roots.forEach(function(r) {
                var attrs = [];
                for (var i = 0; i < r.attributes.length; i++) {
                    var a = r.attributes[i];
                    if (a.name.startsWith('data-') || a.name === 'v-bind' || a.name.startsWith('v-')) {
                        attrs.push(a.name + '=' + a.value.slice(0, 80));
                    }
                }
                if (attrs.length > 0) info.dataAttrs.push({tag: r.tagName, id: r.id, attrs: attrs});
            });

            // Check for JSON in script tags
            var scripts = document.querySelectorAll('script[type="application/json"], script[type="application/ld+json"]');
            scripts.forEach(function(s) {
                info.jsonScripts.push({id: s.id, text: s.textContent.slice(0, 500)});
            });

            // Check for __NUXT__, __INITIAL_STATE__, etc.
            if (window.__NUXT__) info.nuxt = 'present';
            if (window.__INITIAL_STATE__) info.initial = 'present';

            return JSON.stringify(info, null, 2);
        })()
    """)
    print(result)

    # 4. Try to intercept a new API call by clicking around
    print("\n=== 4. Try XHR interception ===")
    result = evaluate("""
        (function() {
            var origOpen = XMLHttpRequest.prototype.open;
            var calls = [];
            XMLHttpRequest.prototype.open = function(method, url) {
                calls.push(method + ' ' + url);
            };
            var origSend = XMLHttpRequest.prototype.send;
            XMLHttpRequest.prototype.send = function(body) {
                this.addEventListener('load', function() {
                    // can't easily capture response here
                });
                return origSend.apply(this, arguments);
            };
            // Return captured calls after clicking something
            setTimeout(function() {
                // click on a skill tree item
                var items = document.querySelectorAll('[class*="skill"], [class*="tree"], [class*="node"], .el-tree-node');
                if (items.length > 0) {
                    items[0].click();
                }
            }, 500);
            return 'XHR interceptor installed, found ' + document.querySelectorAll('[class*="skill"], [class*="tree"], [class*="node"], .el-tree-node').length + ' potential elements';
        })()
    """)
    print(result)

    # 5. Get all text content from the page
    print("\n=== 5. Page Text (first 2000 chars) ===")
    result = evaluate("document.body ? document.body.innerText.slice(0, 2000) : 'no body'")
    if result:
        print(result)

    ws.close()


if __name__ == "__main__":
    main()
