#!/usr/bin/env python3
"""Get CTFHub skill tree — CDP cookie extraction + curl."""
import json
import subprocess
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

    # Get ALL cookies from browser (no URL filter)
    send("Network.getAllCookies", msg_id=2)
    resp = recv(2, 5)
    cookie_jar = {}
    if resp:
        cookies = resp.get("result", {}).get("cookies", [])
        print(f"Total cookies: {len(cookies)}")
        for c in cookies:
            domain = c.get("domain", "")
            name = c["name"]
            value = c["value"]
            print(f"  [{domain}] {name}={value[:50]}")
            if "ctfhub" in domain:
                cookie_jar[name] = value

    if not cookie_jar:
        print("\nNo ctfhub cookies found!")
        ws.close()
        sys.exit(1)

    # Build cookie string
    cookie_str = "; ".join(f"{k}={v}" for k, v in cookie_jar.items())
    print(f"\nCookie: {cookie_str[:120]}...")

    # Use curl to call API
    cmd = [
        "curl", "-s",
        "https://api.ctfhub.com/User_API/Skill/getTree",
        "-H", f"Cookie: {cookie_str}",
        "-H", "User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
        "-H", "Referer: https://www.ctfhub.com/",
        "-H", "Origin: https://www.ctfhub.com",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
    print(f"\n=== API Response ===")
    print(result.stdout[:8000])
    if result.stderr:
        print(f"STDERR: {result.stderr[:500]}")

    # Save
    with open("D:/ai/ctfhub_skill_tree.json", "w", encoding="utf-8") as f:
        f.write(result.stdout)

    ws.close()


if __name__ == "__main__":
    main()
