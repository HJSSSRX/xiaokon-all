#!/usr/bin/env python3
"""Find the click handler on org-tree nodes to navigate to challenges."""
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

    def evaluate(code, timeout=8):
        send("Runtime.evaluate", {"expression": code, "returnByValue": True, "awaitPromise": False}, msg_id=99)
        resp = recv_any(timeout)
        if resp and resp.get("id") == 99:
            return resp.get("result", {}).get("result", {}).get("value")
        return None

    send("Runtime.enable", msg_id=1)
    recv_any(2)
    send("Network.enable", msg_id=2)
    recv_any(2)
    while recv_any(0.2):
        pass

    # Navigate to skill tree first
    print("Going to skill tree...")
    evaluate("document.querySelector('#app').__vue__.$router.push('/skilltree')")
    time.sleep(2)

    # 1. Find the Vue component that owns the org-tree
    print("\n=== Find org-tree Vue component ===")
    result = evaluate("""
    (function() {
        var container = document.querySelector('.org-tree-container');
        if (!container) return 'no container';

        // Walk up to find Vue instance
        var el = container;
        while (el) {
            if (el.__vue__) {
                var vm = el.__vue__;
                var info = {
                    name: vm.$options.name || '(anon)',
                    tag: el.tagName,
                    hasListeners: !!vm.$listeners,
                    listenerKeys: vm.$listeners ? Object.keys(vm.$listeners) : [],
                    hasAttrs: !!vm.$attrs,
                    attrKeys: vm.$attrs ? Object.keys(vm.$attrs) : [],
                    methods: vm.$options.methods ? Object.keys(vm.$options.methods).slice(0, 15) : [],
                    computed: vm.$options.computed ? Object.keys(vm.$options.computed).slice(0, 10) : [],
                };
                return JSON.stringify(info);
            }
            el = el.parentElement;
        }
        return 'no vue instance found';
    })()
    """)
    print(f"Container Vue: {result}")

    # 2. Look at event listeners on the DOM
    print("\n=== Event listeners on org-tree ===")
    result = evaluate("""
    (function() {
        var result = [];
        // Check getEventListeners (Chrome DevTools API)
        if (typeof getEventListeners !== 'undefined') {
            var nodes = document.querySelectorAll('.org-tree-node-label-inner');
            for (var i = 0; i < Math.min(nodes.length, 5); i++) {
                var listeners = getEventListeners(nodes[i]);
                var keys = Object.keys(listeners);
                if (keys.length > 0) {
                    result.push({text: nodes[i].innerText.trim(), events: keys});
                }
            }
        } else {
            result.push('getEventListeners not available (need to enable DOMDebugger)');
        }
        return JSON.stringify(result);
    })()
    """)
    print(f"Listeners: {result}")

    # 3. Enable DOMDebugger to access event listeners
    send("DOMDebugger.enable", msg_id=10)
    recv_any(2)

    # Get the DOM node ID for org-tree-container
    print("\n=== Get DOM node for org-tree ===")
    send("DOM.getDocument", {"depth": -1}, msg_id=11)
    resp = recv_any(5)
    root_node_id = None
    if resp and resp.get("id") == 11:
        root = resp.get("result", {}).get("root", {})
        root_node_id = root.get("nodeId")
        print(f"Root nodeId: {root_node_id}")

    if root_node_id:
        # Find org-tree node
        send("DOM.querySelectorAll", {
            "nodeId": root_node_id,
            "selector": ".org-tree-node-label-inner"
        }, msg_id=12)
        resp = recv_any(5)
        if resp and resp.get("id") == 12:
            node_ids = resp.get("result", {}).get("nodeIds", [])
            print(f"Found {len(node_ids)} org-tree label nodes")

            # Get the first few
            for nid in node_ids[:3]:
                # Get node info
                send("DOM.resolveNode", {"nodeId": nid}, msg_id=13)
                resp = recv_any(3)
                if resp and resp.get("id") == 13:
                    obj_id = resp.get("result", {}).get("object", {}).get("objectId")
                    if obj_id:
                        # Call getEventListeners on this node
                        evaluate(f"""
                        (function() {{
                            var el = null;
                            // Find by text matching
                            var labels = document.querySelectorAll('.org-tree-node-label-inner');
                            for (var i = 0; i < labels.length; i++) {{
                                if (typeof getEventListeners !== 'undefined') {{
                                    var listeners = getEventListeners(labels[i]);
                                    if (Object.keys(listeners).length > 0) {{
                                        console.log(labels[i].innerText, Object.keys(listeners));
                                    }}
                                }}
                            }}
                            return 'checked ' + labels.length + ' labels';
                        }})()
                        """)

    # 4. Try using DOMDebugger.getEventListeners
    print("\n=== DOMDebugger getEventListeners ===")
    # First find the nodeId
    send("DOM.querySelector", {
        "nodeId": root_node_id,
        "selector": ".org-tree-node:not(.is-leaf):first-child"
    }, msg_id=20) if root_node_id else None

    resp = recv_any(5)
    if resp and resp.get("id") == 20:
        result = resp.get("result", {})
        node_id = result.get("nodeId")
        if node_id:
            print(f"First non-leaf node: {node_id}")
            send("DOMDebugger.getEventListeners", {
                "nodeId": node_id,
                "depth": 2
            }, msg_id=21)
            resp = recv_any(5)
            if resp and resp.get("id") == 21:
                listeners = resp.get("result", {}).get("listeners", [])
                print(f"Listeners: {json.dumps(listeners, ensure_ascii=False)[:1000]}")

    # 5. Alternative: use JavaScript to intercept clicks and trace
    print("\n=== Intercept clicks ===")
    result = evaluate("""
    (function() {
        // Find the Vue instance that handles skill tree
        var app = document.querySelector('#app').__vue__;

        // Search for the skill tree component
        function findSkillTreeComponent(vm, depth) {
            if (depth > 6) return null;
            if (vm.$options.name) {
                var name = vm.$options.name.toLowerCase();
                if (name.indexOf('skill') > -1 || name.indexOf('tree') > -1) {
                    return {
                        name: vm.$options.name,
                        methods: vm.$options.methods ? Object.keys(vm.$options.methods) : [],
                        props: vm.$options.props ? Object.keys(vm.$options.props) : [],
                        computed: vm.$options.computed ? Object.keys(vm.$options.computed) : [],
                        data: vm.$data ? Object.keys(vm.$data).slice(0, 20) : []
                    };
                }
            }
            if (vm.$children) {
                for (var i = 0; i < vm.$children.length; i++) {
                    var result = findSkillTreeComponent(vm.$children[i], depth + 1);
                    if (result) return result;
                }
            }
            return null;
        }

        var found = findSkillTreeComponent(app, 0);
        if (found) return JSON.stringify(found);

        // If not found by name, search for any component with 'node' or 'tree' in data
        function searchData(vm, depth) {
            if (depth > 6) return null;
            var dataKeys = vm.$data ? Object.keys(vm.$data) : [];
            var relevant = dataKeys.filter(function(k) {
                return /tree|skill|node|data|list/i.test(k);
            });
            if (relevant.length > 0) {
                return {
                    name: vm.$options.name || '(anon)',
                    depth: depth,
                    relevantData: relevant
                };
            }
            if (vm.$children) {
                for (var i = 0; i < vm.$children.length; i++) {
                    var result = searchData(vm.$children[i], depth + 1);
                    if (result) return result;
                }
            }
            return null;
        }
        var dataResult = searchData(app, 0);
        if (dataResult) return JSON.stringify(dataResult);

        return 'no skill tree component found';
    })()
    """)
    print(f"Skill tree component: {result}")

    ws.close()
    print("\nDone.")


if __name__ == "__main__":
    main()
