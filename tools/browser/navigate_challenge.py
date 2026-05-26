#!/usr/bin/env python3
"""Navigate to CTFHub challenge page and capture API calls."""
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

    # Navigate to challenge page for task 264 (签到/Check-in)
    # Try different URL patterns
    print("=== Navigating to challenge page ===")

    url_patterns = [
        "/challenge",
        "/challenge/264",
        "/challenge?id=264",
        "/challenge/skill_basic_check_in",
    ]

    for pattern in url_patterns:
        print(f"\n--- Trying: {pattern} ---")
        send("Runtime.evaluate", {
            "expression": f"document.querySelector('#app').__vue__.$router.push('{pattern}')",
            "returnByValue": True,
        }, msg_id=20)

        time.sleep(2)

        # Check URL
        send("Runtime.evaluate", {
            "expression": "location.href",
            "returnByValue": True,
        }, msg_id=21)

        resp = recv_any(3)
        if resp and resp.get("id") == 21:
            result = resp.get("result", {}).get("result", {}).get("value")
            print(f"URL: {result}")

        # Check page content
        send("Runtime.evaluate", {
            "expression": "document.body ? document.body.innerText.slice(0, 500) : 'no body'",
            "returnByValue": True,
        }, msg_id=22)

        resp = recv_any(3)
        if resp and resp.get("id") == 22:
            result = resp.get("result", {}).get("result", {}).get("value")
            if result and result != "no body":
                print(f"Page text: {result[:300]}")

        # Collect API calls
        api_calls = []
        while True:
            m = recv_any(0.3)
            if not m:
                break
            method = m.get("method", "")
            if method == "Network.requestWillBeSent":
                url = m["params"]["request"]["url"]
                if "api.ctfhub.com" in url:
                    api_calls.append({"url": url, "rid": m["params"]["requestId"]})
                    print(f"  API call: {url[:180]}")
            elif method == "Network.responseReceived":
                url = m["params"]["response"]["url"]
                if "api.ctfhub.com" in url:
                    print(f"  Response: {m['params']['response']['status']} for {url[:120]}")

        # Get response bodies
        for call in api_calls:
            rid = call["rid"]
            send("Network.getResponseBody", {"requestId": rid}, msg_id=50)
            body_resp = recv_any(4)
            if body_resp and body_resp.get("id") == 50:
                result = body_resp.get("result", {})
                body = result.get("body", "")
                if body and len(body) > 10:
                    print(f"  Body for {call['url'].split('/')[-1][:60]}: {body[:1500]}")
                    # Save all API responses
                    fname = call["url"].split("User_API/")[-1].replace("/", "_") if "User_API/" in call["url"] else "response"
                    fname = fname.split("?")[0][:60]
                    with open(f"D:/ai/ctfhub_api_{fname}.json", "w", encoding="utf-8") as f:
                        f.write(body)

        # If we found a working challenge page, stop
        send("Runtime.evaluate", {
            "expression": "location.href.indexOf('challenge') > -1",
            "returnByValue": True,
        }, msg_id=30)
        resp = recv_any(3)
        if resp and resp.get("id") == 30:
            result = resp.get("result", {}).get("result", {}).get("value")
            if result:
                print("  *** On challenge page! ***")
                break

    ws.close()
    print("\nDone.")


if __name__ == "__main__":
    main()
