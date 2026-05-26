#!/usr/bin/env python3
"""Extract CTFHub skill tree data via CDP."""
import json
import os
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
    print("Tabs:")
    for t in tabs:
        print(f"  [{t['type']}] {t.get('title','')[:60]}")
    return None


def send(ws, method, params=None, msg_id=1):
    ws.send(json.dumps({"id": msg_id, "method": method, "params": params or {}}))


def recv(ws, msg_id, timeout=10):
    deadline = time.time() + timeout
    while time.time() < deadline:
        ws.settimeout(max(0.5, deadline - time.time()))
        try:
            msg = json.loads(ws.recv())
            if msg.get("id") == msg_id:
                return msg
        except websocket.WebSocketTimeoutException:
            break
        except Exception:
            break
    return None


def evaluate(ws, expression, timeout=10):
    send(ws, "Runtime.evaluate", {"expression": expression, "returnByValue": True}, msg_id=99)
    resp = recv(ws, 99, timeout)
    if resp:
        result = resp.get("result", {}).get("result", {})
        return result.get("value")
    return None


def main():
    os.environ["PYTHONIOENCODING"] = "utf-8"

    target = find_tab("ctfhub")
    if not target:
        print("CTFHub tab not found!")
        sys.exit(1)

    print(f"Connected: {target['title']}")
    ws = websocket.create_connection(target["webSocketDebuggerUrl"], timeout=10)

    # Init
    send(ws, "Runtime.enable", msg_id=1)
    recv(ws, 1, 3)
    send(ws, "DOM.enable", msg_id=2)
    recv(ws, 2, 3)
    send(ws, "Network.enable", msg_id=3)
    recv(ws, 3, 3)
    time.sleep(0.5)

    # 1. Extract Vue state
    vue_code = """
    (function() {
        var root = document.querySelector('#app');
        if (!root) return 'no #app';
        var vm = root.__vue__;
        if (!vm) return 'no __vue__';
        var out = {hasStore: !!vm.$store, hasRouter: !!vm.$router};
        if (vm.$store && vm.$store.state) {
            out.stateKeys = Object.keys(vm.$store.state);
            out.statePreview = JSON.stringify(vm.$store.state).slice(0, 5000);
        }
        if (vm.$router && vm.$router.options && vm.$router.options.routes) {
            out.routes = vm.$router.options.routes.map(function(r) {
                return {path: r.path, name: r.name};
            });
        }
        return JSON.stringify(out);
    })()
    """
    result = evaluate(ws, vue_code)
    print("\n=== Vue State ===")
    if result:
        with open("D:/ai/ctfhub_vue_state.json", "w", encoding="utf-8") as f:
            f.write(str(result))
        print(result[:3000])
    else:
        print("(no vue state)")

    # 2. Extract full DOM structure of skill tree
    dom_code = """
    (function() {
        var sections = [];
        // Find all major containers
        var containers = document.querySelectorAll(
            '[class*="skill"], [class*="tree"], [class*="node"], ' +
            '[class*="category"], [class*="item"], [class*="card"], ' +
            '.el-menu-item, .el-tree-node, .el-collapse-item'
        );
        containers.forEach(function(el) {
            var text = (el.innerText || el.textContent || '').trim();
            var cls = (el.className || '').replace(/\\s+/g, ' ').trim();
            if (text && text.length < 500) {
                sections.push({cls: cls.slice(0,60), text: text.slice(0,200)});
            }
        });
        if (sections.length === 0) {
            // Fallback: get all text from the main area
            var main = document.querySelector('main, .main, section, .content, [role="main"]');
            if (main) {
                sections.push({cls: 'main', text: main.innerText.slice(0, 3000)});
            }
        }
        return JSON.stringify(sections.slice(0, 50));
    })()
    """
    result = evaluate(ws, dom_code)
    print("\n=== DOM Structure ===")
    if result:
        try:
            sections = json.loads(result)
            for s in sections:
                print(f"[{s['cls'][:40]}] {s['text'][:150]}")
        except Exception:
            print(result[:2000])

    # 3. Try to get API data from localStorage/network cache
    storage_code = """
    (function() {
        var data = {};
        for (var i = 0; i < localStorage.length; i++) {
            var key = localStorage.key(i);
            var val = localStorage.getItem(key);
            if (val && val.length < 2000) {
                data[key] = val.slice(0, 500);
            }
        }
        return JSON.stringify(data);
    })()
    """
    result = evaluate(ws, storage_code)
    print("\n=== localStorage ===")
    if result:
        print(result[:2000])

    # 4. Get the full text content (better encoding this time)
    text_code = """
    (function() {
        var body = document.body;
        if (!body) return '';
        return body.innerText.slice(0, 5000);
    })()
    """
    result = evaluate(ws, text_code)
    if result:
        with open("D:/ai/ctfhub_page_text.txt", "w", encoding="utf-8") as f:
            f.write(result)
        print(f"\n=== Page text saved ({len(result)} chars) ===")

    # 5. Network requests
    net_code = """
    (function() {
        if (!window.performance || !window.performance.getEntriesByType) return 'no perf API';
        var entries = window.performance.getEntriesByType('resource');
        var urls = entries.map(function(e) { return e.name; });
        return JSON.stringify(urls);
    })()
    """
    result = evaluate(ws, net_code)
    print("\n=== Loaded Resources ===")
    if result:
        try:
            urls = json.loads(result)
            api_urls = [u for u in urls if "api" in u.lower() or "ajax" in u.lower() or "/v" in u]
            for u in api_urls[:20]:
                print(f"  API: {u[:150]}")
            other_urls = [u for u in urls if u not in api_urls]
            for u in other_urls[:10]:
                print(f"  RES: {u[:150]}")
        except Exception:
            print(result[:1000])

    ws.close()
    print("\nDone.")


if __name__ == "__main__":
    main()
