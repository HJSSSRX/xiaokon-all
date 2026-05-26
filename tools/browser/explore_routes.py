#!/usr/bin/env python3
"""Explore Vue Router routes and navigate to challenge pages."""
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

    send("Runtime.enable", msg_id=1)
    recv_any(2)
    send("Network.enable", msg_id=2)
    recv_any(2)
    while recv_any(0.2):
        pass

    # 1. Get all routes from Vue Router
    print("=== Vue Router Routes ===")
    send("Runtime.evaluate", {
        "expression": """
        (function() {
            var app = document.querySelector('#app');
            if (!app || !app.__vue__ || !app.__vue__.$router) return 'no router';
            var router = app.__vue__.$router;
            var routes = router.options.routes || [];
            var info = routes.map(function(r) {
                return {
                    path: r.path,
                    name: r.name,
                    hasComponent: !!r.component,
                    hasChildren: !!(r.children && r.children.length > 0),
                    childrenPaths: r.children ? r.children.map(function(c) { return c.path; }) : [],
                    redirect: r.redirect
                };
            });
            return JSON.stringify(info, null, 2);
        })()
        """,
        "returnByValue": True,
    }, msg_id=10)

    resp = recv_any(5)
    if resp and resp.get("id") == 10:
        result = resp.get("result", {}).get("result", {}).get("value")
        print(result[:5000] if result else "(null)")

    # 2. Try clicking on "Pwn" via the DOM and observe what happens
    print("\n=== Click 'Pwn' and monitor ===")
    # First observe current URL
    send("Runtime.evaluate", {
        "expression": "location.href",
        "returnByValue": True,
    }, msg_id=11)
    resp = recv_any(3)
    if resp and resp.get("id") == 11:
        result = resp.get("result", {}).get("result", {}).get("value")
        print(f"Current URL: {result}")

    # Try clicking using various methods
    click_code = """
    (function() {
        // Find org-tree-node-label-inner containing "Pwn"
        var labels = document.querySelectorAll('.org-tree-node-label-inner');
        for (var i = 0; i < labels.length; i++) {
            if (labels[i].innerText.trim() === 'Pwn') {
                var node = labels[i].closest('.org-tree-node');
                if (node) {
                    // Try clicking the whole node
                    node.click();
                    // Also try Vue event
                    var vm = node.__vue__;
                    if (vm) {
                        return 'clicked node, has vue: ' + Object.keys(vm).slice(0,10).join(',');
                    }
                    return 'clicked node, no vue';
                }
                return 'no parent node found';
            }
        }
        return 'Pwn label not found';
    })()
    """
    send("Runtime.evaluate", {"expression": click_code, "returnByValue": True}, msg_id=12)
    resp = recv_any(3)
    if resp and resp.get("id") == 12:
        result = resp.get("result", {}).get("result", {}).get("value")
        print(f"Click result: {result}")

    time.sleep(1)

    # Check if URL changed
    send("Runtime.evaluate", {
        "expression": "location.href",
        "returnByValue": True,
    }, msg_id=13)
    resp = recv_any(3)
    if resp and resp.get("id") == 13:
        result = resp.get("result", {}).get("result", {}).get("value")
        print(f"URL after click: {result}")

    # Check for API calls
    while True:
        m = recv_any(0.3)
        if not m:
            break
        method = m.get("method", "")
        if method == "Network.requestWillBeSent":
            url = m["params"]["request"]["url"]
            if "api.ctfhub.com" in url:
                print(f"  API: {url[:200]}")
                # Get response body
                rid = m["params"]["requestId"]
                send("Network.getResponseBody", {"requestId": rid}, msg_id=80)

    # Check for body responses
    while True:
        m = recv_any(0.3)
        if not m:
            break
        if m.get("id") == 80:
            body = m.get("result", {}).get("body", "")
            if body:
                print(f"  Body: {body[:2000]}")

    # 3. Try navigating to challenge page for the "签到" task
    print("\n=== Try navigating to challenge ===")
    send("Runtime.evaluate", {
        "expression": """
        (function() {
            var router = document.querySelector('#app').__vue__.$router;
            // Try common route patterns
            var routes = router.options.routes;
            return JSON.stringify(routes.map(function(r) { return r.path; }));
        })()
        """,
        "returnByValue": True,
    }, msg_id=14)

    resp = recv_any(5)
    if resp and resp.get("id") == 14:
        result = resp.get("result", {}).get("result", {}).get("value")
        print(f"All route paths: {result}")

    # 4. Try to find the challenge component
    print("\n=== Search for challenge-related components ===")
    send("Runtime.evaluate", {
        "expression": """
        (function() {
            var app = document.querySelector('#app').__vue__;
            var results = [];

            // Search all components in the tree
            function search(vm, depth) {
                if (depth > 6) return;
                if (vm.$options && vm.$options.name) {
                    var name = vm.$options.name;
                    if (/challenge|task|problem|skill/i.test(name)) {
                        results.push({
                            name: name,
                            depth: depth,
                            dataKeys: vm.$data ? Object.keys(vm.$data).slice(0, 10) : [],
                            computedKeys: vm.$options.computed ? Object.keys(vm.$options.computed).slice(0, 10) : []
                        });
                    }
                }
                if (vm.$children) {
                    vm.$children.forEach(function(c) { search(c, depth + 1); });
                }
            }
            search(app, 0);
            return JSON.stringify(results);
        })()
        """,
        "returnByValue": True,
    }, msg_id=15)

    resp = recv_any(5)
    if resp and resp.get("id") == 15:
        result = resp.get("result", {}).get("result", {}).get("value")
        print(result[:3000] if result else "(null)")

    ws.close()
    print("\nDone.")


if __name__ == "__main__":
    main()
