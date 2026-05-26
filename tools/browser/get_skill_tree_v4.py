#!/usr/bin/env python3
"""Get CTFHub skill tree v4 — comprehensive cookie extraction + in-browser fetch."""
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

    def recv(msg_id, timeout=8):
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

    send("Network.enable", msg_id=1)
    recv(1, 3)
    send("Runtime.enable", msg_id=2)
    recv(2, 3)

    # 1. Get ALL cookies (no filtering)
    send("Network.getAllCookies", msg_id=3)
    resp = recv(3, 5)
    all_cookies = resp.get("result", {}).get("cookies", []) if resp else []
    print(f"\nAll browser cookies ({len(all_cookies)}):")
    for c in all_cookies:
        print(f"  [{c.get('domain','')}] {c['name']}={c['value'][:60]}")
        for k, v in c.items():
            if k not in ("name", "value", "domain"):
                print(f"      {k}: {v}")

    # 2. Get cookies specifically for www.ctfhub.com
    ctfhub_cookies = {}
    for c in all_cookies:
        domain = c.get("domain", "")
        if "ctfhub" in domain:
            ctfhub_cookies[c["name"]] = c["value"]

    print(f"\nCTFHub cookies: {list(ctfhub_cookies.keys())}")

    # 3. Try in-browser fetch (from page context, which may include implicit auth)
    print("\n=== Method A: In-browser fetch from page ===")
    fetch_code = """
    (async function() {
        try {
            var resp = await fetch('https://api.ctfhub.com/User_API/Skill/getTree', {
                method: 'GET',
                credentials: 'include',
                headers: {
                    'Accept': 'application/json',
                    'Referer': 'https://www.ctfhub.com/',
                    'Origin': 'https://www.ctfhub.com'
                }
            });
            var text = await resp.text();
            return JSON.stringify({status: resp.status, ok: resp.ok, body: text.slice(0, 5000)});
        } catch(e) {
            return JSON.stringify({error: e.message});
        }
    })()
    """
    send("Runtime.evaluate", {"expression": fetch_code, "returnByValue": True, "awaitPromise": True}, msg_id=4)
    resp = recv(4, 15)
    if resp:
        result = resp.get("result", {}).get("result", {}).get("value")
        print(f"Fetch result: {str(result)[:3000]}")

    # 4. Try with XMLHttpRequest from page
    print("\n=== Method B: XHR from page ===")
    xhr_code = """
    (function() {
        return new Promise(function(resolve) {
            var xhr = new XMLHttpRequest();
            xhr.open('GET', 'https://api.ctfhub.com/User_API/Skill/getTree', true);
            xhr.withCredentials = true;
            xhr.setRequestHeader('Accept', 'application/json');
            xhr.onload = function() {
                resolve(JSON.stringify({status: xhr.status, body: xhr.responseText.slice(0, 5000)}));
            };
            xhr.onerror = function() {
                resolve(JSON.stringify({error: 'XHR failed'}));
            };
            xhr.send();
        });
    })()
    """
    send("Runtime.evaluate", {"expression": xhr_code, "returnByValue": True, "awaitPromise": True}, msg_id=5)
    resp = recv(5, 15)
    if resp:
        result = resp.get("result", {}).get("result", {}).get("value")
        print(f"XHR result: {str(result)[:3000]}")

    # 5. Check what original page requests looked like (via performance API)
    print("\n=== Method C: Check performance entries for API calls ===")
    perf_code = """
    (function() {
        var entries = performance.getEntriesByType('resource');
        var apiCalls = entries.filter(function(e) {
            return e.name.indexOf('api.ctfhub.com') > -1;
        }).map(function(e) {
            return {
                url: e.name,
                type: e.initiatorType,
                duration: e.duration,
                transferSize: e.transferSize
            };
        });
        return JSON.stringify(apiCalls);
    })()
    """
    send("Runtime.evaluate", {"expression": perf_code, "returnByValue": True}, msg_id=6)
    resp = recv(6, 5)
    if resp:
        result = resp.get("result", {}).get("result", {}).get("value")
        print(f"Performance entries: {str(result)[:2000]}")

    # 6. Check sessionStorage too
    print("\n=== Method D: sessionStorage ===")
    ss_code = """
    (function() {
        var data = {};
        for (var i = 0; i < sessionStorage.length; i++) {
            var key = sessionStorage.key(i);
            data[key] = sessionStorage.getItem(key).slice(0, 200);
        }
        return JSON.stringify(data);
    })()
    """
    send("Runtime.evaluate", {"expression": ss_code, "returnByValue": True}, msg_id=7)
    resp = recv(7, 5)
    if resp:
        result = resp.get("result", {}).get("result", {}).get("value")
        print(f"sessionStorage: {str(result)[:1000]}")

    ws.close()


if __name__ == "__main__":
    main()
