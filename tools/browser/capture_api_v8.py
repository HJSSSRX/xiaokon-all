#!/usr/bin/env python3
"""Capture CTFHub Skill/getTree API response by watching network events."""
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

    def recv_raw(timeout=0.5):
        try:
            ws.settimeout(timeout)
            return json.loads(ws.recv())
        except websocket.WebSocketTimeoutException:
            return None
        except Exception:
            return None

    # Enable domains
    send("Runtime.enable", msg_id=1)
    time.sleep(0.5)
    send("Page.enable", msg_id=2)
    time.sleep(0.5)
    send("Network.enable", msg_id=3)
    time.sleep(0.5)

    # Flush any pending messages
    while recv_raw(0.3):
        pass

    # Navigate to main page first to load SPA
    print("Navigating to SPA shell...")
    send("Page.navigate", {"url": "https://www.ctfhub.com/#/index"}, msg_id=10)

    # Wait for navigation to complete
    deadline = time.time() + 10
    nav_done = False
    while time.time() < deadline and not nav_done:
        msg = recv_raw(0.5)
        if msg and msg.get("id") == 10:
            print(f"SPA loaded: {msg.get('result',{}).get('loaderId','')[:20]}...")
            nav_done = True

    time.sleep(2)

    # Now navigate to skill tree via router
    print("Navigating to skill tree...")
    send("Runtime.evaluate", {
        "expression": "document.querySelector('#app').__vue__.$router.push('/skilltree')",
        "returnByValue": True,
    }, msg_id=11)

    time.sleep(0.5)
    # Flush
    while recv_raw(0.2):
        pass

    # Now listen for Skill/getTree requests and capture response body
    print("Listening for API calls...")
    api_request_ids = []

    deadline = time.time() + 15
    while time.time() < deadline:
        msg = recv_raw(1.0)
        if not msg:
            print("  (no more messages)")
            break

        method = msg.get("method", "")
        msg_id = msg.get("id")

        # Handle our evaluate response
        if msg_id == 11:
            print(f"  Router navigation: {json.dumps(msg.get('result',{}), ensure_ascii=False)[:200]}")

        # Capture requestWillBeSent for getTree
        if method == "Network.requestWillBeSent":
            url = msg["params"]["request"]["url"]
            rid = msg["params"]["requestId"]
            if "getTree" in url:
                print(f"  REQUEST: {rid} -> {url}")
                # Also capture request headers
                headers = msg["params"]["request"]["headers"]
                print(f"    Headers: {json.dumps(headers, ensure_ascii=False)[:300]}")
                api_request_ids.append(rid)

        # Capture response for getTree
        if method == "Network.responseReceived":
            url = msg["params"]["response"]["url"]
            rid = msg["params"]["requestId"]
            if "getTree" in url:
                status = msg["params"]["response"]["status"]
                resp_headers = msg["params"]["response"].get("headers", {})
                print(f"  RESPONSE: {rid} -> {status}")
                print(f"    Response headers: {json.dumps(resp_headers, ensure_ascii=False)[:300]}")
                api_request_ids.append(rid)

        # Handle our msg_id responses
        if msg_id and msg_id >= 10:
            continue

    print(f"\nCaptured {len(api_request_ids)} getTree-related IDs")

    # Try to get response body for each
    for rid in set(api_request_ids):
        send("Network.getResponseBody", {"requestId": rid}, msg_id=20)
        resp = recv_raw(5)
        if resp and resp.get("id") == 20:
            result = resp.get("result", {})
            body = result.get("body", "")
            base64 = result.get("base64Encoded", False)
            if body:
                print(f"\n=== Response body for {rid} ({len(body)} bytes) ===")
                print(body[:5000])
                with open("D:/ai/ctfhub_skill_tree.json", "w", encoding="utf-8") as f:
                    f.write(body)
                print("Saved to D:/ai/ctfhub_skill_tree.json")
            else:
                print(f"  No body for {rid}: {json.dumps(result, ensure_ascii=False)[:200]}")
        else:
            print(f"  Timeout/no response for getResponseBody({rid})")

    ws.close()
    print("\nDone.")


if __name__ == "__main__":
    main()
