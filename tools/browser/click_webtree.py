#!/usr/bin/env python3
"""Click on org-tree nodes to expand categories and capture API calls."""
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
    send("Network.enable", msg_id=1)
    recv_any(2)
    send("Runtime.enable", msg_id=2)
    recv_any(2)
    send("DOM.enable", msg_id=3)
    recv_any(2)

    while recv_any(0.2):
        pass

    # Ensure on skill tree
    send("Runtime.evaluate", {
        "expression": "document.querySelector('#app').__vue__.$router.push('/skilltree')",
        "returnByValue": True,
    }, msg_id=10)
    recv_any(3)
    time.sleep(2)
    while recv_any(0.2):
        pass

    # Inspect the org-tree structure more closely
    print("=== Org-tree structure ===")
    send("Runtime.evaluate", {
        "expression": """
        (function() {
            var nodes = document.querySelectorAll('.org-tree-node');
            var info = [];
            nodes.forEach(function(n) {
                var label = n.querySelector('.org-tree-node-label-inner');
                var children = n.querySelector('.org-tree-node-children');
                var expandBtn = n.querySelector('.org-tree-node-btn');
                info.push({
                    text: n.innerText.trim().slice(0, 40),
                    isLeaf: n.classList.contains('is-leaf'),
                    hasChildren: !!children,
                    hasExpandBtn: !!expandBtn,
                    labelClass: label ? label.className : '',
                    childCount: children ? children.children.length : 0
                });
            });
            return JSON.stringify(info.slice(0, 15));
        })()
        """,
        "returnByValue": True,
    }, msg_id=11)

    resp = recv_any(5)
    if resp and resp.get("id") == 11:
        result = resp.get("result", {}).get("result", {}).get("value")
        print(result[:3000] if result else "(null)")

    # Try clicking various elements
    clicks = [
        # Click org-tree-node directly
        """(function() {
            var nodes = document.querySelectorAll('.org-tree-node-label');
            for (var i = 0; i < nodes.length; i++) {
                var text = nodes[i].innerText.trim();
                if (text === 'Web' || text.indexOf('Web') === 0) {
                    nodes[i].click();
                    return 'clicked .org-tree-node-label: ' + text;
                }
            }
            return 'not found';
        })()""",

        # Click with mouse event dispatch
        """(function() {
            var nodes = document.querySelectorAll('.org-tree-node-label');
            for (var i = 0; i < nodes.length; i++) {
                var text = nodes[i].innerText.trim();
                if (text === 'Web') {
                    nodes[i].dispatchEvent(new MouseEvent('click', {bubbles: true, cancelable: true}));
                    return 'dispatched click on: ' + text;
                }
            }
            return 'not found';
        })()""",

        # Click the inner label
        """(function() {
            var labels = document.querySelectorAll('.org-tree-node-label-inner');
            for (var i = 0; i < labels.length; i++) {
                if (labels[i].innerText.trim() === 'Web') {
                    // Click parent .org-tree-node-label
                    var parent = labels[i].parentElement;
                    if (parent) {
                        parent.click();
                        return 'clicked parent of inner: ' + parent.className;
                    }
                    labels[i].click();
                    return 'clicked inner directly';
                }
            }
            return 'not found';
        })()""",

        # Try to find Vue event handlers and call them
        """(function() {
            var nodes = document.querySelectorAll('.org-tree-node');
            for (var i = 0; i < nodes.length; i++) {
                var text = nodes[i].innerText.trim();
                if (text.indexOf('Web') === 0) {
                    // Try to find Vue instance
                    var vm = nodes[i].__vue__;
                    if (vm) {
                        // Try calling any click/expand handler
                        if (vm.$listeners && vm.$listeners.click) {
                            vm.$listeners.click();
                            return 'called Vue click listener';
                        }
                        if (vm.onClick) { vm.onClick(); return 'called onClick'; }
                        if (vm.handleClick) { vm.handleClick(); return 'called handleClick'; }
                        if (vm.expand) { vm.expand(); return 'called expand'; }
                        if (vm.select) { vm.select(); return 'called select'; }
                        return 'Vue instance found but no handler: ' + JSON.stringify(Object.keys(vm).slice(0, 20));
                    }
                    return 'no Vue instance on node: ' + text;
                }
            }
            return 'Web node not found';
        })()""",

        # Try the parent org-tree-container
        """(function() {
            var containers = document.querySelectorAll('.org-tree-container, [class*="org-tree"]');
            return 'org-tree containers: ' + containers.length;
        })()""",
    ]

    for i, code in enumerate(clicks):
        print(f"\n--- Click attempt {i+1} ---")
        send("Runtime.evaluate", {"expression": code, "returnByValue": True}, msg_id=30+i)
        resp = recv_any(5)
        if resp and resp.get("id") == 30+i:
            result = resp.get("result", {}).get("result", {}).get("value")
            print(f"Result: {result}")

        # Check for API calls triggered
        time.sleep(0.8)
        while True:
            m = recv_any(0.3)
            if not m:
                break
            method = m.get("method", "")
            if method == "Network.requestWillBeSent":
                url = m["params"]["request"]["url"]
                if "api.ctfhub.com" in url:
                    print(f"  -> API call: {url[:200]}")
            elif method == "Network.responseReceived":
                url = m["params"]["response"]["url"]
                if "api.ctfhub.com" in url:
                    rid = m["params"]["requestId"]
                    status = m["params"]["response"]["status"]
                    print(f"  <- Response {status}: {url[:150]}")
                    # Try to get body
                    send("Network.getResponseBody", {"requestId": rid}, msg_id=90)
                    body_resp = recv_any(4)
                    if body_resp and body_resp.get("id") == 90:
                        body = body_resp.get("result", {}).get("body", "")
                        if body:
                            print(f"     Body ({len(body)} bytes): {body[:2000]}")
                            # Save if it looks like skill tree data
                            if "skill" in url.lower() or "getTree" in url.lower() or "getNode" in url.lower() or "challenge" in url.lower():
                                with open("D:/ai/ctfhub_skilltree_detail.json", "w", encoding="utf-8") as f:
                                    f.write(body)
                                print("     Saved to file.")

    # Final: get full page DOM to understand structure
    print("\n=== Full DOM structure for org-tree ===")
    send("Runtime.evaluate", {
        "expression": """
        (function() {
            var container = document.querySelector('[class*="org-tree"]');
            if (!container) return 'no org-tree container found';
            return container.outerHTML.slice(0, 3000);
        })()
        """,
        "returnByValue": True,
    }, msg_id=60)
    resp = recv_any(5)
    if resp and resp.get("id") == 60:
        result = resp.get("result", {}).get("result", {}).get("value")
        print(result[:3000] if result else "(null)")

    ws.close()
    print("\nDone.")


if __name__ == "__main__":
    main()
