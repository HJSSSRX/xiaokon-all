#!/usr/bin/env python3
"""Capture all CTFHub data: skill tree + challenge list via page navigation + network interception."""
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
    send("Network.enable", msg_id=2)
    recv_any(2)
    while recv_any(0.2):
        pass

    all_responses = {}

    def navigate_and_capture(route, label):
        """Navigate to a route and capture all API responses."""
        print(f"\n=== {label}: navigating to {route} ===")

        # Navigate via Vue Router
        send("Runtime.evaluate", {
            "expression": f"document.querySelector('#app').__vue__.$router.push('{route}')",
            "returnByValue": True,
        }, msg_id=50)

        time.sleep(0.5)

        # Listen for API responses
        captured = {}
        deadline = time.time() + 10
        while time.time() < deadline:
            m = recv_any(1.0)
            if not m:
                continue

            method = m.get("method", "")

            if method == "Network.responseReceived":
                url = m["params"]["response"]["url"]
                if "api.ctfhub.com" in url:
                    rid = m["params"]["requestId"]
                    short_name = url.split("User_API/")[-1].split("?")[0] if "User_API/" in url else url.split("/")[-1]
                    status = m["params"]["response"]["status"]

                    # Get body
                    send("Network.getResponseBody", {"requestId": rid}, msg_id=80)
                    body_resp = recv_any(4)
                    if body_resp and body_resp.get("id") == 80:
                        body = body_resp.get("result", {}).get("body", "")
                        if body:
                            print(f"  [{status}] {short_name} ({len(body)} bytes)")
                            captured[short_name] = body
                            # Save to file
                            fname = short_name.replace("/", "_")[:60]
                            with open(f"D:/ai/ctfhub_{fname}.json", "w", encoding="utf-8") as f:
                                f.write(body)

            # Stop when we see our navigate response
            if m.get("id") == 50:
                pass  # Navigation triggered

        all_responses[label] = captured
        return captured

    # 1. Skill tree page
    send("Page.navigate", {"url": "https://www.ctfhub.com/#/index"}, msg_id=10)
    time.sleep(2)
    while recv_any(0.2):
        pass

    skill_data = navigate_and_capture("/skilltree", "Skill Tree")
    time.sleep(2)

    # 2. Challenge list page
    challenge_data = navigate_and_capture("/challenge", "Challenge List")

    # 3. Summary
    print("\n" + "="*50)
    print("=== CAPTURED DATA SUMMARY ===")
    for label, data in all_responses.items():
        print(f"\n{label}:")
        for name, body in data.items():
            try:
                parsed = json.loads(body)
                if parsed.get("status"):
                    d = parsed["data"]
                    if isinstance(d, dict):
                        if "items" in d:
                            print(f"  {name}: {len(d['items'])} items")
                        else:
                            keys = list(d.keys())[:5]
                            print(f"  {name}: dict keys={keys}")
                    elif isinstance(d, list):
                        print(f"  {name}: list({len(d)})")
                    else:
                        print(f"  {name}: {type(d).__name__}")
                else:
                    print(f"  {name}: API returned status=false: {parsed.get('msg','')}")
            except:
                print(f"  {name}: {len(body)} bytes (non-JSON)")

    ws.close()
    print("\nDone.")


if __name__ == "__main__":
    main()
