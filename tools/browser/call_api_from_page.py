#!/usr/bin/env python3
"""Call CTFHub APIs from within the authenticated page context."""
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

    def recv(msg_id, timeout=12):
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

    def evaluate(code, timeout=12):
        send("Runtime.evaluate", {
            "expression": code,
            "returnByValue": True,
            "awaitPromise": True
        }, msg_id=99)
        resp = recv(99, timeout)
        if resp:
            result = resp.get("result", {}).get("result", {})
            value = result.get("value")
            if result.get("subtype") == "error":
                return f"ERROR: {result.get('description', '')}"
            return value
        return "TIMEOUT"

    # Find the axios/http instance used by the Vue app
    print("=== Finding HTTP service ===")
    result = evaluate("""
    (function() {
        var app = document.querySelector('#app');
        if (!app || !app.__vue__) return 'no vue app';

        var vm = app.__vue__;

        // Search for axios instance
        function findAxios(obj, path, depth) {
            if (depth > 4) return null;
            if (!obj || typeof obj !== 'object') return null;

            var keys = Object.keys(obj);
            for (var i = 0; i < keys.length; i++) {
                var k = keys[i];
                var v = obj[k];
                // Check if this is an axios instance
                if (v && typeof v === 'function' && (k === 'request' || k === 'get' || k === 'post')) {
                    // Check parent for baseURL
                    var parent = obj;
                    if (parent.defaults && parent.defaults.baseURL) {
                        return JSON.stringify({path: path, baseURL: parent.defaults.baseURL});
                    }
                }
                if (v && typeof v === 'object' && v !== null && !Array.isArray(v)) {
                    var r = findAxios(v, path ? path + '.' + k : k, depth + 1);
                    if (r) return r;
                }
            }
            return null;
        }

        var axiosResult = findAxios(vm, '', 0);
        if (axiosResult) return axiosResult;

        // Try global axios
        if (typeof axios !== 'undefined') return 'global axios found';

        // Try Vue.prototype.$http or $axios
        var proto = Object.getPrototypeOf(vm);
        if (proto) {
            var protoKeys = Object.keys(proto).filter(function(k) {
                return /http|axios|api|request/i.test(k);
            });
            if (protoKeys.length > 0) return 'Vue prototype: ' + JSON.stringify(protoKeys);
        }

        return 'no http service found. vm keys: ' + JSON.stringify(Object.keys(vm).slice(0, 15));
    })()
    """)
    print(f"HTTP service: {result}")

    # Try to call the API using Vue's internal request method
    print("\n=== Call API via Vue app's internal method ===")
    result = evaluate("""
    (async function() {
        try {
            // Try to find and use the app's request method
            var app = document.querySelector('#app').__vue__;
            if (!app) return 'no app';

            // Check if there's a global api module
            // Try using XMLHttpRequest directly (which should have cookies)
            return await new Promise(function(resolve) {
                var xhr = new XMLHttpRequest();
                xhr.open('GET', 'https://api.ctfhub.com/User_API/Challenge/getAll', true);
                xhr.withCredentials = true;
                xhr.setRequestHeader('Accept', 'application/json');
                xhr.setRequestHeader('Content-Type', 'application/json');
                xhr.onload = function() {
                    resolve('XHR status: ' + xhr.status + ', body: ' + xhr.responseText.slice(0, 1000));
                };
                xhr.onerror = function() {
                    resolve('XHR error: ' + xhr.status);
                };
                xhr.send();
            });
        } catch(e) {
            return 'Error: ' + e.message;
        }
    })()
    """)

    print(f"XHR result: {result}")

    # Let's try injecting axios and using the auth token from the store
    print("\n=== Try with store token ===")
    result = evaluate("""
    (async function() {
        try {
            var app = document.querySelector('#app').__vue__;
            var token = app.$store.state.user.token;
            if (!token) return 'no token in store';

            var resp = await fetch('https://api.ctfhub.com/User_API/Challenge/getAll', {
                method: 'GET',
                credentials: 'include',
                headers: {
                    'Accept': 'application/json',
                    'Content-Type': 'application/json',
                    'Authorization': 'Bearer ' + token
                }
            });
            var text = await resp.text();
            return 'Status: ' + resp.status + ', body: ' + text.slice(0, 1000);
        } catch(e) {
            return 'Error: ' + e.message;
        }
    })()
    """)
    print(f"Fetch result: {result}")

    ws.close()
    print("\nDone.")


if __name__ == "__main__":
    main()
