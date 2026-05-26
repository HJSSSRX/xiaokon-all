#!/usr/bin/env python3
"""Expand a CTFHub skill tree category and capture the API calls."""
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
    send("DOM.enable", msg_id=2)
    recv_any(2)
    send("Network.enable", msg_id=3)
    recv_any(2)

    while recv_any(0.2):
        pass

    # First: inspect the DOM to understand the tree structure
    print("\n=== DOM Inspection ===")
    send("Runtime.evaluate", {
        "expression": """
        (function() {
            var info = {};

            // Find Element UI tree
            var treeEls = document.querySelectorAll('.el-tree, .el-tree-node, .el-collapse, .el-collapse-item');
            info.treeCount = treeEls.length;

            // Get all tree nodes
            var nodes = document.querySelectorAll('.el-tree-node');
            var nodeInfo = [];
            nodes.forEach(function(n) {
                var text = n.innerText.trim().slice(0, 60);
                var cls = n.className;
                var expanded = cls.indexOf('is-expanded') > -1;
                var expandable = cls.indexOf('is-leaf') === -1;
                var content = n.querySelector('.el-tree-node__content');
                var label = content ? content.innerText.trim().slice(0, 50) : text;
                nodeInfo.push({
                    text: text,
                    expanded: expanded,
                    expandable: expandable,
                    label: label,
                    hasExpandIcon: !!n.querySelector('.el-tree-node__expand-icon')
                });
            });
            info.nodes = nodeInfo.slice(0, 15);

            // Also check for collapse items
            var collapseItems = document.querySelectorAll('.el-collapse-item');
            var collapseInfo = [];
            collapseItems.forEach(function(c) {
                collapseInfo.push({
                    header: (c.querySelector('.el-collapse-item__header') || {}).innerText,
                    content: (c.querySelector('.el-collapse-item__content') || {}).innerText
                });
            });
            info.collapseItems = collapseInfo.slice(0, 10);

            // Get all clickable elements with skill/tree related text
            var allEls = document.querySelectorAll('*');
            var clickable = [];
            allEls.forEach(function(el) {
                if (el.innerText && (el.innerText.trim() === 'Web' || el.innerText.trim() === 'Pwn' ||
                    el.innerText.trim() === 'Reverse' || el.innerText.trim() === 'Crypto' ||
                    el.innerText.trim() === 'Misc')) {
                    clickable.push({
                        tag: el.tagName,
                        cls: (el.className || '').slice(0, 80),
                        text: el.innerText.trim().slice(0, 40),
                        hasClick: !!el.onclick || !!el.__vue__
                    });
                }
            });
            info.clickableWebElements = clickable;

            return JSON.stringify(info, null, 2);
        })()
        """,
        "returnByValue": True,
    }, msg_id=10)

    resp = recv_any(5)
    if resp and resp.get("id") == 10:
        result = resp.get("result", {}).get("result", {}).get("value")
        print(result[:5000] if result else "(null)")
    else:
        print("No DOM info - page might need to be on skill tree view")

    # Ensure on skill tree view
    print("\n=== Ensuring skill tree view ===")
    send("Runtime.evaluate", {
        "expression": """
        (function() {
            var app = document.querySelector('#app');
            if (!app || !app.__vue__) return 'no vue';
            var router = app.__vue__.$router;
            if (!router) return 'no router';

            // Check current route
            var current = router.currentRoute || router.history.current;
            return JSON.stringify({current: current ? current.path : '?', fullPath: current ? current.fullPath : '?'});
        })()
        """,
        "returnByValue": True,
    }, msg_id=11)

    resp = recv_any(3)
    if resp and resp.get("id") == 11:
        result = resp.get("result", {}).get("result", {}).get("value")
        print(f"Current route: {result}")

    # Navigate to skill tree if not there
    send("Runtime.evaluate", {
        "expression": "document.querySelector('#app').__vue__.$router.push('/skilltree')",
        "returnByValue": True,
    }, msg_id=12)

    time.sleep(2)
    while recv_any(0.3):
        pass

    # Now try to find expandable elements and click them
    print("\n=== Finding and clicking expandable elements ===")

    # Try various selectors to find and click on "Web" category
    click_attempts = [
        # Click the first el-tree-node__expand-icon
        """(function() {
            var icons = document.querySelectorAll('.el-tree-node__expand-icon');
            if (icons.length > 0) {
                icons[0].click();
                return 'clicked first expand icon';
            }
            return 'no expand icons found';
        })()""",

        # Click on an element containing "Web" that's inside a tree node
        """(function() {
            var nodes = document.querySelectorAll('.el-tree-node__content');
            for (var i = 0; i < nodes.length; i++) {
                if (nodes[i].innerText.indexOf('Web') > -1 && nodes[i].innerText.indexOf('Web进阶') === -1) {
                    nodes[i].click();
                    return 'clicked Web node';
                }
            }
            return 'Web node not found';
        })()""",

        # Try clicking the collapse-item header for Web
        """(function() {
            var headers = document.querySelectorAll('.el-collapse-item__header');
            for (var i = 0; i < headers.length; i++) {
                if (headers[i].innerText.indexOf('Web') > -1) {
                    headers[i].click();
                    return 'clicked collapse header for Web';
                }
            }
            return 'no collapse header for Web';
        })()""",

        # Try any element that shows "Web" as text
        """(function() {
            var els = document.querySelectorAll('*');
            for (var i = 0; i < els.length; i++) {
                if (els[i].children.length === 0 && els[i].innerText.trim() === 'Web') {
                    var parent = els[i].parentElement;
                    if (parent) { parent.click(); return 'clicked parent of Web text: ' + parent.tagName; }
                    els[i].click(); return 'clicked Web element directly: ' + els[i].tagName;
                }
            }
            return 'no exact Web element found';
        })()""",
    ]

    for i, code in enumerate(click_attempts):
        print(f"\nAttempt {i+1}:")
        send("Runtime.evaluate", {"expression": code, "returnByValue": True}, msg_id=20)
        resp = recv_any(3)
        if resp and resp.get("id") == 20:
            result = resp.get("result", {}).get("result", {}).get("value")
            print(f"  Result: {result}")
            # Check for any API requests triggered
            time.sleep(1)
            api_msgs = []
            while True:
                m = recv_any(0.3)
                if not m:
                    break
                method = m.get("method", "")
                if method == "Network.requestWillBeSent":
                    url = m["params"]["request"]["url"]
                    if "api.ctfhub.com" in url:
                        api_msgs.append(url)
                        print(f"  API: {url[:150]}")
        else:
            print("  (timeout)")

    ws.close()
    print("\nDone.")


if __name__ == "__main__":
    main()
