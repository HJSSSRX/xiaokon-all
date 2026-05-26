#!/usr/bin/env python3
"""Final CTFHub data capture — fresh navigation to trigger API calls + network interception."""
import json
import sys
import time
import urllib.request

import websocket

CDP = "http://127.0.0.1:9222"
SAVE_DIR = "D:/ai"


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
    send("Page.enable", msg_id=2)
    recv_any(2)
    send("Network.enable", msg_id=3)
    recv_any(2)
    while recv_any(0.2):
        pass

    # === STEP 1: Go to index (away from skill tree) ===
    print("\n--- Step 1: Navigate to index ---")
    send("Page.navigate", {"url": "https://www.ctfhub.com/#/index"}, msg_id=10)
    time.sleep(3)
    # Drain all pending messages
    while recv_any(0.3):
        pass

    # === STEP 2: Navigate to skill tree, capture getTree ===
    print("\n--- Step 2: Navigate to skill tree ---")
    send("Runtime.evaluate", {
        "expression": "document.querySelector('#app').__vue__.$router.push('/skilltree')",
        "returnByValue": True,
    }, msg_id=20)

    skill_tree = None
    deadline = time.time() + 12
    while time.time() < deadline:
        m = recv_any(1.0)
        if not m:
            continue

        method = m.get("method", "")
        if method == "Network.responseReceived":
            url = m["params"]["response"]["url"]
            if "getTree" in url:
                rid = m["params"]["requestId"]
                print(f"  getTree response received: {rid}")
                send("Network.getResponseBody", {"requestId": rid}, msg_id=81)
                body_msg = recv_any(5)
                if body_msg and body_msg.get("id") == 81:
                    body = body_msg.get("result", {}).get("body", "")
                    if body:
                        skill_tree = body
                        with open(f"{SAVE_DIR}/ctfhub_skill_tree.json", "w", encoding="utf-8") as f:
                            f.write(body)
                        print(f"  Saved skill tree ({len(body)} bytes)")

        if m.get("id") == 20:
            print("  Router navigation complete")

        if skill_tree:
            break

    # Drain remaining
    while recv_any(0.3):
        pass

    # === STEP 3: Navigate to challenge list ===
    print("\n--- Step 3: Navigate to challenge list ---")
    send("Runtime.evaluate", {
        "expression": "document.querySelector('#app').__vue__.$router.push('/challenge')",
        "returnByValue": True,
    }, msg_id=30)

    challenges = None
    hot_categories = None
    deadline = time.time() + 15
    while time.time() < deadline:
        m = recv_any(1.0)
        if not m:
            continue

        method = m.get("method", "")
        if method == "Network.responseReceived":
            url = m["params"]["response"]["url"]
            rid = m["params"]["requestId"]
            status = m["params"]["response"]["status"]

            if "getAll" in url and "Challenge" in url:
                print(f"  Challenge/getAll response: {rid}")
                send("Network.getResponseBody", {"requestId": rid}, msg_id=82)
                body_msg = recv_any(5)
                if body_msg and body_msg.get("id") == 82:
                    body = body_msg.get("result", {}).get("body", "")
                    if body:
                        challenges = body
                        with open(f"{SAVE_DIR}/ctfhub_challenges.json", "w", encoding="utf-8") as f:
                            f.write(body)
                        print(f"  Saved challenges ({len(body)} bytes)")

            if "getHotCategory" in url:
                print(f"  Challenge/getHotCategory response: {rid}")
                send("Network.getResponseBody", {"requestId": rid}, msg_id=83)
                body_msg = recv_any(5)
                if body_msg and body_msg.get("id") == 83:
                    body = body_msg.get("result", {}).get("body", "")
                    if body:
                        hot_categories = body
                        with open(f"{SAVE_DIR}/ctfhub_hot_categories.json", "w", encoding="utf-8") as f:
                            f.write(body)
                        print(f"  Saved hot categories ({len(body)} bytes)")

        if challenges and hot_categories:
            break

    # === SUMMARY ===
    print("\n" + "="*60)
    print("SUMMARY")

    if skill_tree:
        data = json.loads(skill_tree)
        if data.get("status"):
            tree = data["data"]
            def count_nodes(node):
                n = 1
                for c in node.get("children", []):
                    n += count_nodes(c)
                return n
            print(f"Skill tree: {count_nodes(tree)} nodes, root: {tree['title']}")
        else:
            print(f"Skill tree: API error - {data.get('msg')}")

    if challenges:
        data = json.loads(challenges)
        if data.get("status"):
            items = data["data"].get("items", [])
            print(f"Challenges: {len(items)} total")
            # Group by category
            cats = {}
            for item in items[:50]:
                for c in item.get("category", []):
                    name = c["title"]
                    if name not in cats:
                        cats[name] = 0
                    cats[name] += 1
            print(f"  Top categories: {dict(sorted(cats.items(), key=lambda x: -x[1])[:10])}")

    if hot_categories:
        data = json.loads(hot_categories)
        if data.get("status"):
            hot = data["data"].get("items", [])
            print(f"Hot categories: {[c['title'] for c in hot]}")

    ws.close()
    print("\nDone.")


if __name__ == "__main__":
    main()
