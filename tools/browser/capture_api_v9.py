#!/usr/bin/env python3
"""Get CTFHub skill tree v9 — listen FIRST, then trigger, + deep Vue search."""
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

    def recv_any(timeout=0.5):
        try:
            ws.settimeout(timeout)
            return json.loads(ws.recv())
        except websocket.WebSocketTimeoutException:
            return None
        except Exception:
            return None

    # Enable domains
    send("Runtime.enable", msg_id=1)
    recv_any(2)
    send("Page.enable", msg_id=2)
    recv_any(2)
    send("Network.enable", msg_id=3)
    recv_any(2)

    # Clear pending
    while recv_any(0.2):
        pass

    # ====== APPROACH A: Network interception (set up listener FIRST) ======
    print("\n=== Approach A: Network interception ===")

    # Navigate to a DIFFERENT page first to force reload
    print("Navigating away from skill tree...")
    send("Page.navigate", {"url": "https://www.ctfhub.com/#/index"}, msg_id=10)
    recv_any(3)

    # Flush
    while recv_any(0.3):
        pass

    print("Now navigating to skill tree (listening)...")
    # Trigger skill tree view
    send("Runtime.evaluate", {
        "expression": "document.querySelector('#app').__vue__.$router.push('/skilltree')",
        "returnByValue": True,
    }, msg_id=11)

    api_data = None
    deadline = time.time() + 15
    while time.time() < deadline:
        msg = recv_any(1.0)
        if not msg:
            continue

        method = msg.get("method", "")

        # Capture the getTree response
        if method == "Network.responseReceived":
            url = msg["params"]["response"]["url"]
            if "getTree" in url:
                rid = msg["params"]["requestId"]
                print(f"  Captured response: {rid}")

                # Get response body immediately
                send("Network.getResponseBody", {"requestId": rid}, msg_id=50)
                # Wait for the body response
                body_deadline = time.time() + 5
                while time.time() < body_deadline:
                    body_msg = recv_any(1.0)
                    if body_msg and body_msg.get("id") == 50:
                        b = body_msg.get("result", {}).get("body", "")
                        if b:
                            api_data = b
                            print(f"  Got response body: {len(b)} bytes")
                        break

        # Check for our router push response
        if msg.get("id") == 11:
            print("  Router navigation complete")

        if api_data:
            break

    if api_data:
        print(f"\n=== Skill Tree Data ({len(api_data)} bytes) ===")
        print(api_data[:5000])
        with open("D:/ai/ctfhub_skill_tree.json", "w", encoding="utf-8") as f:
            f.write(api_data)
        print("Saved to D:/ai/ctfhub_skill_tree.json")
    else:
        print("No API data captured via network interception")

    # ====== APPROACH B: Deep Vue component search ======
    print("\n=== Approach B: Deep Vue component search ===")

    send("Runtime.evaluate", {
        "expression": """
        (function() {
            var appEl = document.querySelector('#app');
            if (!appEl || !appEl.__vue__) return JSON.stringify({error: 'no vue'});

            var root = appEl.__vue__;
            var results = [];

            function deepSearch(vm, path, depth) {
                if (depth > 8) return;
                if (!vm) return;

                // Check $data
                if (vm.$data) {
                    var keys = Object.keys(vm.$data);
                    var relevant = keys.filter(function(k) {
                        return /skill|tree|node|challenge|category|topic|task|problem|question/i.test(k);
                    });
                    if (relevant.length > 0) {
                        var preview = {};
                        relevant.forEach(function(k) {
                            var val = vm.$data[k];
                            if (typeof val === 'string') preview[k] = val.slice(0, 100);
                            else if (Array.isArray(val)) preview[k] = '[array len=' + val.length + ']';
                            else if (typeof val === 'object' && val !== null) preview[k] = '[object keys:' + Object.keys(val).slice(0, 5).join(',') + ']';
                            else preview[k] = String(val).slice(0, 100);
                        });
                        results.push({path: path, component: vm.$options.name || '(anon)', dataKeys: relevant, preview: preview});
                    }
                }

                // Check $options.computed for skill-related things
                if (vm.$options && vm.$options.computed) {
                    var compKeys = Object.keys(vm.$options.computed);
                    var compRel = compKeys.filter(function(k) {
                        return /skill|tree|node|challenge|category/i.test(k);
                    });
                    if (compRel.length > 0) {
                        results.push({path: path, component: vm.$options.name || '(anon)', computedKeys: compRel});
                    }
                }

                // Check for non-Vuex state (component-level)
                if (vm.$options && vm.$options.name) {
                    var name = vm.$options.name.toLowerCase();
                    if (/skill|tree|node|challenge|category/i.test(name)) {
                        results.push({path: path, componentName: vm.$options.name, hasData: !!vm.$data,
                            dataKeys: vm.$data ? Object.keys(vm.$data).slice(0, 20) : []});
                    }
                }

                // Recurse into children
                if (vm.$children) {
                    for (var i = 0; i < vm.$children.length; i++) {
                        deepSearch(vm.$children[i], path + ' > ' + (vm.$children[i].$options.name || 'c' + i), depth + 1);
                    }
                }
            }

            deepSearch(root, 'root', 0);
            return JSON.stringify(results.slice(0, 30));
        })()
        """,
        "returnByValue": True,
    }, msg_id=20)

    resp = recv_any(8)
    if resp and resp.get("id") == 20:
        result = resp.get("result", {}).get("result", {}).get("value")
        print(result[:5000] if result else "(null)")

    # ====== APPROACH C: Check all Vuex module state including dynamic ======
    print("\n=== Approach C: All Vuex modules (including dynamic) ===")

    send("Runtime.evaluate", {
        "expression": """
        (function() {
            var appEl = document.querySelector('#app');
            if (!appEl || !appEl.__vue__ || !appEl.__vue__.$store) return 'no store';

            var store = appEl.__vue__.$store;
            var modules = {};

            // Get all registered modules
            if (store._modules && store._modules.root) {
                function walk(mod, name) {
                    var info = {};
                    if (mod._rawModule) {
                        var raw = mod._rawModule;
                        if (raw._children) info.children = Object.keys(raw._children);
                        if (raw._rawModule && raw._rawModule.state) {
                            info.stateKeys = Object.keys(raw._rawModule.state);
                        }
                        if (raw._rawModule && raw._rawModule.getters) {
                            info.getters = Object.keys(raw._rawModule.getters);
                        }
                    }
                    if (mod.state) {
                        try {
                            info.statePreview = JSON.stringify(mod.state).slice(0, 500);
                        } catch(e) {}
                    }
                    if (Object.keys(info).length > 0) modules[name || 'root'] = info;

                    if (mod._children) {
                        Object.keys(mod._children).forEach(function(k) {
                            walk(mod._children[k], name ? name + '/' + k : k);
                        });
                    }
                }
                walk(store._modules.root, '');
            }

            return JSON.stringify(modules);
        })()
        """,
        "returnByValue": True,
    }, msg_id=21)

    resp = recv_any(8)
    if resp and resp.get("id") == 21:
        result = resp.get("result", {}).get("result", {}).get("value")
        if result:
            print(result[:5000])

    # ====== APPROACH D: Search window/global scope ======
    print("\n=== Approach D: Global scope search ===")

    send("Runtime.evaluate", {
        "expression": """
        (function() {
            var results = [];
            // Check all window properties for skill/tree data
            Object.keys(window).forEach(function(k) {
                if (/skill|tree|challenge|ctf/i.test(k)) {
                    var val = window[k];
                    var desc = typeof val === 'function' ? '[function]' :
                               typeof val === 'object' ? ('[object] ' + (val ? Object.keys(val).slice(0,10).join(',') : 'null')) :
                               String(val).slice(0, 100);
                    results.push({key: k, type: typeof val, desc: desc});
                }
            });
            return JSON.stringify(results);
        })()
        """,
        "returnByValue": True,
    }, msg_id=22)

    resp = recv_any(5)
    if resp and resp.get("id") == 22:
        result = resp.get("result", {}).get("result", {}).get("value")
        if result:
            print(result[:3000])

    ws.close()
    print("\nDone.")


if __name__ == "__main__":
    main()
