#!/usr/bin/env python3
"""Get CTFHub skill tree v5 — intercept network response via CDP."""
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

    send("Network.enable", msg_id=1)
    deadline = time.time() + 3
    while time.time() < deadline:
        ws.settimeout(max(0.3, deadline - time.time()))
        try:
            msg = json.loads(ws.recv())
            if msg.get("id") == 1:
                break
        except Exception:
            break

    send("Runtime.enable", msg_id=2)
    deadline = time.time() + 3
    while time.time() < deadline:
        ws.settimeout(max(0.3, deadline - time.time()))
        try:
            msg = json.loads(ws.recv())
            if msg.get("id") == 2:
                break
        except Exception:
            break

    # Navigate to skill tree page to trigger API calls
    print("Navigating to skill tree page...")
    send("Page.enable", msg_id=3)
    deadline = time.time() + 3
    while time.time() < deadline:
        ws.settimeout(max(0.3, deadline - time.time()))
        try:
            msg = json.loads(ws.recv())
            if msg.get("id") == 3:
                break
        except Exception:
            break

    # Navigate to skilltree to trigger API calls
    send("Page.navigate", {"url": "https://www.ctfhub.com/skilltree"}, msg_id=4)

    # Collect request IDs for Skill/getTree
    skill_tree_requests = []
    captured_responses = []

    deadline = time.time() + 15
    while time.time() < deadline:
        ws.settimeout(max(0.3, deadline - time.time()))
        try:
            raw = ws.recv()
            msg = json.loads(raw)

            # Handle navigation result
            if msg.get("id") == 4:
                print(f"Navigation result: {json.dumps(msg.get('result',{}), ensure_ascii=False)[:200]}")

            # Capture Skill/getTree requests and responses
            method = msg.get("method", "")
            if method == "Network.requestWillBeSent":
                url = msg["params"]["request"]["url"]
                if "getTree" in url:
                    rid = msg["params"]["requestId"]
                    print(f"Captured request: {rid[:20]}... -> {url[:120]}")
                    skill_tree_requests.append(rid)
            elif method == "Network.responseReceived":
                url = msg["params"]["response"]["url"]
                if "getTree" in url:
                    rid = msg["params"]["requestId"]
                    status = msg["params"]["response"]["status"]
                    print(f"Response {status} for: {rid[:20]}...")
                    if rid in skill_tree_requests:
                        captured_responses.append(rid)

        except websocket.WebSocketTimeoutException:
            print("Timeout waiting for requests")
            break
        except Exception as e:
            print(f"Error: {e}")
            break

    print(f"\nFound {len(skill_tree_requests)} getTree requests, {len(captured_responses)} responses")

    # Get response bodies
    for rid in captured_responses[:3]:
        send("Network.getResponseBody", {"requestId": rid}, msg_id=10)
        resp = recv_with_id(ws, 10, 5)
        if resp:
            result = resp.get("result", {})
            body = result.get("body", "")
            base64 = result.get("base64Encoded", False)
            print(f"\nResponse body for {rid[:20]}... ({len(body)} chars, base64={base64}):")
            print(body[:5000])

            # Save to file
            if body:
                with open("D:/ai/ctfhub_skill_tree.json", "w", encoding="utf-8") as f:
                    f.write(body)
                print("Saved to D:/ai/ctfhub_skill_tree.json")

    ws.close()


def recv_with_id(ws, msg_id, timeout=8):
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


if __name__ == "__main__":
    main()
