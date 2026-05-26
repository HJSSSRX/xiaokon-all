#!/usr/bin/env python3
"""Get CTFHub skill tree v7 — load SPA properly, navigate via router, extract data."""
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

    def evaluate(code, timeout=12, await_promise=False):
        send("Runtime.evaluate", {
            "expression": code,
            "returnByValue": True,
            "awaitPromise": await_promise
        }, msg_id=99)
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
    send("Page.enable", msg_id=2)
    recv(2, 3)
    send("Network.enable", msg_id=3)
    recv(3, 3)

    # Step 1: Navigate to the main page to load the SPA shell
    print("\n=== Step 1: Load SPA shell ===")
    send("Page.navigate", {"url": "https://www.ctfhub.com/#/index"}, msg_id=4)
    nav_result = recv(4, 15)
    if nav_result:
        print(f"Navigation: {json.dumps(nav_result.get('result', {}), ensure_ascii=False)[:300]}")

    # Wait for page to load
    print("Waiting for SPA to load...")
    time.sleep(3)

    # Check page state
    result = evaluate("""
        (function() {
            return JSON.stringify({
                url: location.href,
                title: document.title,
                hasAppEl: !!document.querySelector('#app'),
                bodyChildren: document.body ? document.body.children.length : 0
            });
        })()
    """)
    print(f"Page state: {result}")

    # Step 2: Navigate to skill tree via Vue Router
    print("\n=== Step 2: Navigate to skill tree via Vue Router ===")
    result = evaluate("""
        (function() {
            var appEl = document.querySelector('#app');
            if (!appEl || !appEl.__vue__) return 'no vue app';
            var router = appEl.__vue__.$router;
            if (!router) return 'no router';
            router.push('/skilltree');
            return 'navigating to /skilltree';
        })()
    """)
    print(f"Router push: {result}")

    # Wait for route change and API calls
    print("Waiting for skill tree data to load...")
    time.sleep(3)

    # Step 3: Extract Vuex store state
    print("\n=== Step 3: Extract Vuex store ===")
    result = evaluate("""
        (function() {
            var appEl = document.querySelector('#app');
            if (!appEl) return JSON.stringify({error: 'no #app element'});
            var vm = appEl.__vue__;
            if (!vm) {
                // Try Vue 3
                var app = appEl._vue_app__;
                if (app) return JSON.stringify({framework: 'vue3', info: 'app found'});
                return JSON.stringify({error: 'no vue instance', keys: Object.keys(appEl).slice(0, 20)});
            }
            if (!vm.$store) return JSON.stringify({error: 'no $store', vmKeys: Object.keys(vm).slice(0, 20)});

            var state = vm.$store.state;
            // Serialize with a safe replacer
            var json = JSON.stringify(state, function(key, val) {
                if (typeof val === 'function') return undefined;
                if (val && typeof val === 'object' && val._isVue) return undefined;
                return val;
            });
            return json;
        })()
    """)
    if result:
        # Save full state
        try:
            with open("D:/ai/ctfhub_store_state.json", "w", encoding="utf-8") as f:
                f.write(str(result))
            print(f"State saved ({len(str(result))} chars)")
            # Parse and show key structure
            parsed = json.loads(str(result))
            if isinstance(parsed, dict):
                print(f"Top-level keys: {list(parsed.keys())}")
                for k, v in parsed.items():
                    if isinstance(v, dict):
                        print(f"  {k}: dict with keys {list(v.keys())[:10]}")
                    elif isinstance(v, list):
                        print(f"  {k}: list with {len(v)} items")
                    elif isinstance(v, str):
                        print(f"  {k}: str ({len(v)} chars)")
                    else:
                        print(f"  {k}: {type(v).__name__} = {str(v)[:100]}")
            elif isinstance(parsed, list):
                print(f"List with {len(parsed)} items")
            print(f"\nFirst 2000 chars of state:\n{str(result)[:2000]}")
        except Exception as e:
            print(f"Parse error: {e}")
            print(str(result)[:3000])

    # Step 4: Also try to extract skill tree specifically
    print("\n=== Step 4: Search for skill tree data in store ===")
    result = evaluate("""
        (function() {
            var appEl = document.querySelector('#app');
            if (!appEl || !appEl.__vue__ || !appEl.__vue__.$store) return 'no store';

            var state = appEl.__vue__.$store.state;
            var found = [];

            function search(obj, path, depth) {
                if (depth > 5) return;
                if (!obj || typeof obj !== 'object') return;
                if (Array.isArray(obj)) {
                    obj.forEach(function(item, i) {
                        search(item, path + '[' + i + ']', depth + 1);
                    });
                    return;
                }
                Object.keys(obj).forEach(function(key) {
                    var full = path + '.' + key;
                    if (/skill|tree|node|category|challenge|topic/i.test(key)) {
                        var preview = JSON.stringify(obj[key]).slice(0, 200);
                        found.push({path: full, preview: preview});
                    }
                    search(obj[key], full, depth + 1);
                });
            }

            search(state, 'state', 0);
            return JSON.stringify(found.slice(0, 30));
        })()
    """)
    if result:
        print(result[:3000])

    ws.close()
    print("\nDone.")


if __name__ == "__main__":
    main()
