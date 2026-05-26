#!/usr/bin/env python3
"""Get CTFHub skill tree v6 — extract from Vuex store directly."""
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

    print(f"Tab: {target['title']}")
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

    send("Runtime.enable", msg_id=1)
    recv(1, 3)

    # Try multiple ways to extract the skill tree from the running Vue app

    checks = [
        # 1. Vue 2 __vue__ on #app
        ("Vue2 on #app",
         "JSON.stringify(document.querySelector('#app').__vue__.$store.state)"),

        # 2. Vue 2 __vue__ on any element
        ("Vue2 search all",
         """(function(){
             var el = document.querySelector('#app');
             var data = null;
             function walk(el, depth) {
                 if (depth > 3) return;
                 if (el.__vue__ && el.__vue__.$store && el.__vue__.$store.state) {
                     data = el.__vue__.$store.state;
                     return;
                 }
                 for (var i = 0; i < el.children.length; i++) {
                     walk(el.children[i], depth + 1);
                     if (data) return;
                 }
             }
             walk(el, 0);
             return JSON.stringify(data);
         })()"""),

        # 3. Vue 3 _vnode
        ("Vue3 _vnode",
         "JSON.stringify(document.querySelector('#app')._vnode?.component?.setupState)"),

        # 4. Vue devtools hook
        ("Vue devtools",
         """(function(){
             var devtoolHook = window.__VUE_DEVTOOLS_GLOBAL_HOOK__;
             if (!devtoolHook) return 'no devtools hook';
             var apps = devtoolHook.apps || [];
             return 'apps: ' + apps.length;
         })()"""),

        # 5. All window keys that might have data
        ("window keys (state-like)",
         """(function(){
             var keys = Object.keys(window).filter(function(k) {
                 return /state|store|data|vue|app/i.test(k);
             });
             return JSON.stringify(keys);
         })()"""),

        # 6. VueRouter - current route matched
        ("Vue router routes",
         """(function(){
             var app = document.querySelector('#app').__vue__;
             if (app && app.$router && app.$router.options && app.$router.options.routes) {
                 return JSON.stringify(app.$router.options.routes);
             }
             return 'no router';
         })()"""),

        # 7. Try to call the getTree function that the page uses
        ("Window globals (API-related)",
         """(function(){
             var keys = Object.keys(window).filter(function(k) {
                 return /api|request|http|fetch|axios/i.test(k);
             });
             return JSON.stringify(keys.slice(0, 20));
         })()"""),

        # 8. Check all Vue component instances
        ("Vue component search",
         """(function(){
             var app = document.querySelector('#app').__vue__;
             if (!app) return 'no vue app';
             // Search $children for any component with skill/tree data
             function search(vm, depth) {
                 if (depth > 4) return null;
                 var keys = Object.keys(vm);
                 var relevant = keys.filter(function(k) {
                     return /skill|tree|node|category|challenge/i.test(k);
                 });
                 if (relevant.length > 0) {
                     var data = {};
                     relevant.forEach(function(k) {
                         data[k] = typeof vm[k] === 'object' ? '[object]' : String(vm[k]).slice(0, 200);
                     });
                     return JSON.stringify(data);
                 }
                 if (vm.$children) {
                     for (var i = 0; i < vm.$children.length; i++) {
                         var r = search(vm.$children[i], depth + 1);
                         if (r) return r;
                     }
                 }
                 return null;
             }
             var found = search(app, 0);
             return found || 'no skill data found in component tree';
         })()"""),

        # 9. Dump all module names from Vuex store
        ("Vuex modules",
         """(function(){
             var app = document.querySelector('#app').__vue__;
             if (!app || !app.$store) return 'no store';
             var modules = app.$store._modules;
             if (!modules) return 'no modules';
             var names = [];
             function walk(mod, path) {
                 if (mod._children) {
                     Object.keys(mod._children).forEach(function(k) {
                         names.push((path ? path + '/' : '') + k);
                         walk(mod._children[k], (path ? path + '/' : '') + k);
                     });
                 }
             }
             walk(modules.root, '');
             return JSON.stringify(names);
         })()"""),

        # 10. Serialize the full store state (carefully, avoiding circular refs)
        ("Full store state (deep)",
         """(function(){
             try {
                 var state = document.querySelector('#app').__vue__.$store.state;
                 return JSON.stringify(state, function(key, val) {
                     if (typeof val === 'function') return '[function]';
                     return val;
                 });
             } catch(e) {
                 return 'Error: ' + e.message;
             }
         })()"""),
    ]

    for label, code in checks:
        send("Runtime.evaluate", {"expression": code, "returnByValue": True, "awaitPromise": False}, msg_id=50)
        resp = recv(50, 8)
        if resp:
            result = resp.get("result", {}).get("result", {})
            value = result.get("value")
            subtype = result.get("subtype")
            err = result.get("description")
            print(f"\n--- {label} ---")
            if subtype == "error" or err:
                print(f"  ERROR: {err[:200] if err else subtype}")
            elif value is not None:
                print(f"  {str(value)[:3000]}")
            else:
                print(f"  (null/undefined)")
        else:
            print(f"\n--- {label} ---\n  TIMEOUT")

    ws.close()


if __name__ == "__main__":
    main()
