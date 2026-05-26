#!/usr/bin/env python3
"""CDP client — connect to Chrome DevTools Protocol for page interaction."""
import json
import sys
import time
import websocket

CHROME_PATH = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
CDP_URL = "http://127.0.0.1:9222"


def _fetch_json(url):
    import urllib.request
    with urllib.request.urlopen(url) as resp:
        return json.loads(resp.read().decode())


def list_tabs():
    """List all open tabs with their URLs and titles."""
    tabs = _fetch_json(f"{CDP_URL}/json")
    for i, t in enumerate(tabs):
        print(f"[{i}] {t['title'][:80]} | {t['url'][:100]}")
    return tabs


def find_tab(url_fragment):
    """Find a tab whose URL contains url_fragment."""
    tabs = _fetch_json(f"{CDP_URL}/json")
    for t in tabs:
        if url_fragment in t.get("url", ""):
            return t
    return None


def send_and_wait(ws, method, params=None, wait_for=None, timeout=8):
    """Send a CDP command and optionally wait for a specific event."""
    msg_id = getattr(send_and_wait, "_id", 0) + 1
    send_and_wait._id = msg_id

    payload = {"id": msg_id, "method": method, "params": params or {}}
    ws.send(json.dumps(payload))

    result = None
    deadline = time.time() + timeout
    while time.time() < deadline:
        ws.settimeout(deadline - time.time())
        try:
            raw = ws.recv()
        except websocket.WebSocketTimeoutException:
            break
        msg = json.loads(raw)
        if msg.get("id") == msg_id:
            result = msg.get("result", {})
        if wait_for and msg.get("method") == wait_for:
            return msg

    return result


def eval_js(ws, expression):
    """Execute JavaScript in the page and return result."""
    resp = send_and_wait(
        ws,
        "Runtime.evaluate",
        {"expression": expression, "returnByValue": True, "awaitPromise": True},
        timeout=15,
    )
    if resp and "result" in resp:
        return resp["result"].get("value")
    return resp


def extract_page_text(ws):
    """Extract readable text from page body."""
    return eval_js(ws, "document.body.innerText")


def extract_links(ws):
    """Extract all links from the page."""
    return eval_js(
        ws,
        """Array.from(document.querySelectorAll('a')).map(a => ({
            href: a.href, text: a.innerText.trim().slice(0,80)
        }))""",
    )


def extract_skill_tree(ws):
    """Attempt to extract CTFHub skill tree data from Vue/React state."""
    scripts = [
        # Vue 2
        "document.querySelector('#app')?.__vue__?.$store?.state",
        # Vue 3
        "document.querySelector('#app')?._vnode?.component?.setupState",
        # General: find any window property that looks like route data
        "JSON.stringify(window.__NUXT__ || window.__INITIAL_STATE__ || null)",
        # All localStorage
        "JSON.stringify({...localStorage})",
    ]
    for s in scripts:
        result = eval_js(ws, s)
        if result:
            print(f"State found: {str(result)[:500]}")
            return result
    return None


def click_element(ws, selector):
    """Click an element by CSS selector."""
    return eval_js(
        ws,
        f"""(() => {{
            const el = document.querySelector('{selector}');
            if (el) {{ el.click(); return 'clicked'; }}
            return 'not found';
        }})()""",
    )


def navigate(ws, url):
    """Navigate the tab to a new URL."""
    return send_and_wait(ws, "Page.navigate", {"url": url})


def click_text(ws, text):
    """Click an element containing specific text."""
    return eval_js(
        ws,
        f"""(() => {{
            const els = document.querySelectorAll('*');
            for (const el of els) {{
                if (el.innerText && el.innerText.trim() === '{text}') {{
                    el.click(); return 'clicked: ' + el.tagName;
                }}
            }}
            return 'not found';
        }})()""",
    )


def watch_requests(ws, duration=5):
    """Capture network requests for a few seconds."""
    send_and_wait(ws, "Network.enable")
    requests = []

    def on_msg(ws, raw):
        try:
            msg = json.loads(raw)
            if msg.get("method") == "Network.responseReceived":
                url = msg["params"]["response"]["url"]
                status = msg["params"]["response"]["status"]
                requests.append(f"{status} {url[:120]}")
        except Exception:
            pass

    ws._orig_recv = ws.recv

    import threading

    stop = threading.Event()

    def listen():
        while not stop.is_set():
            try:
                ws.settimeout(0.5)
                raw = ws._orig_recv()
                on_msg(ws, raw)
            except websocket.WebSocketTimeoutException:
                continue
            except Exception:
                break

    t = threading.Thread(target=listen, daemon=True)
    t.start()
    time.sleep(duration)
    stop.set()
    t.join(timeout=2)

    return requests


# ── CLI ──────────────────────────────────────────────────────────


def cmd_list():
    list_tabs()


def cmd_extract(url_fragment="ctfhub"):
    """Connect to a tab and extract content."""
    tab = find_tab(url_fragment)
    if not tab:
        print(f"No tab found matching '{url_fragment}'")
        print("Open tabs:")
        list_tabs()
        sys.exit(1)

    print(f"Connecting to: {tab['title'][:80]}")
    ws_url = tab["webSocketDebuggerUrl"]
    ws = websocket.create_connection(ws_url, timeout=10)

    # Enable runtime for JS execution
    send_and_wait(ws, "Runtime.enable")
    send_and_wait(ws, "Page.enable")
    send_and_wait(ws, "DOM.enable")

    # Wait for page to be ready
    time.sleep(1)

    # Extract content
    print("\n=== PAGE TEXT ===")
    text = extract_page_text(ws)
    if text:
        print(text[:3000])

    print("\n=== LINKS ===")
    links = extract_links(ws)
    if links:
        for l in links[:30]:
            print(f"  {l['text'][:60]:<60s}  {l['href'][:80]}")

    print("\n=== STATE DUMP ===")
    extract_skill_tree(ws)

    ws.close()


def cmd_repl(url_fragment="ctfhub"):
    """Interactive REPL — type JS expressions to eval in page."""
    tab = find_tab(url_fragment)
    if not tab:
        print(f"No tab found matching '{url_fragment}'")
        sys.exit(1)

    ws = websocket.create_connection(tab["webSocketDebuggerUrl"], timeout=10)
    send_and_wait(ws, "Runtime.enable")

    print("CDP REPL — type JS or :q to quit")
    while True:
        try:
            cmd = input(">>> ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not cmd:
            continue
        if cmd in (":q", ":quit", "exit"):
            break
        if cmd == ":t":
            print(extract_page_text(ws)[:2000])
            continue
        if cmd == ":l":
            for l in extract_links(ws) or []:
                print(f"  {l['text'][:60]}  {l['href'][:80]}")
            continue
        result = eval_js(ws, cmd)
        print(json.dumps(result, indent=2, ensure_ascii=False)[:2000])

    ws.close()


def cmd_watch(url_fragment="ctfhub", duration=5):
    """Watch network requests for a tab."""
    tab = find_tab(url_fragment)
    if not tab:
        print(f"No tab found matching '{url_fragment}'")
        sys.exit(1)

    ws = websocket.create_connection(tab["webSocketDebuggerUrl"], timeout=10)
    send_and_wait(ws, "Runtime.enable")

    print(f"Watching requests for {duration}s... (click around in the browser)")
    reqs = watch_requests(ws, duration=duration)
    for r in reqs:
        print(r)

    ws.close()


if __name__ == "__main__":
    import argparse

    p = argparse.ArgumentParser()
    sp = p.add_subparsers(dest="cmd")

    sp.add_parser("list", help="List open tabs")

    ep = sp.add_parser("extract", help="Extract page content")
    ep.add_argument("--tab", default="ctfhub", help="URL fragment to match")

    rp = sp.add_parser("repl", help="Interactive JS REPL")
    rp.add_argument("--tab", default="ctfhub")

    wp = sp.add_parser("watch", help="Watch network requests")
    wp.add_argument("--tab", default="ctfhub")
    wp.add_argument("--duration", type=int, default=5)

    args = p.parse_args()
    if args.cmd == "list":
        cmd_list()
    elif args.cmd == "extract":
        cmd_extract(args.tab)
    elif args.cmd == "repl":
        cmd_repl(args.tab)
    elif args.cmd == "watch":
        cmd_watch(args.tab, args.duration)
    else:
        p.print_help()
