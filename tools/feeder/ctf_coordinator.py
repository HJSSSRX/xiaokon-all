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

import json
import os
import re
import sys
import time
import traceback
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from tools.feeder.ctf_patterns import PatternDB, get_pattern_db
from tools.feeder.ctf_recognizer import (
    CTFRecognizer, CTFChallenge, RecognitionResult, get_recognizer,
)
from tools.feeder.ctf_scanner import quick_recon, scan_ssrf, scan_lfi, scan_backup, scan_sqli


# ── Constants ──────────────────────────────────────────────────────────────

CTFHUB_API = "https://api.ctfhub.com/User_API/"
CTFHUB_URL = "https://www.ctfhub.com/#/challenge"


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
        """Fetch challenge list from CTFHub API via CDP network interception."""
        print("[Gather] Fetching challenges from CTFHub...")

        try:
            self.spa._send('Page.navigate', {'url': CTFHUB_URL})
            time.sleep(4)
            while self.spa._recv_any(0.3):
                pass

            for i in range(8):
                body = self.spa.evaluate(
                    'document.body ? document.body.textContent.substring(0, 200) : "no body"')
                if "We're sorry" not in str(body) and "no body" not in str(body):
                    break
                time.sleep(2)
                while self.spa._recv_any(0.3):
                    pass

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

            for i in range(10):
                time.sleep(2)
                while self.spa._recv_any(0.3):
                    pass
                modal = self.spa.evaluate(
                    'var m=document.querySelector(".ant-modal");'
                    'm ? m.textContent : "NO_MODAL"')
                urls = re.findall(r'https?://[^\s\x00-\x1f]+', str(modal))
                for url in urls:
                    if 'sandbox' in url and 'ctfhub' in url:
                        print("[Sandbox] Target: %s" % url)
                        return url
                if i == 5:
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
            if skip_solved and c.extra.get('state') == 0:
                continue
            if c.level > max_level:
                continue
            r = self.recognizer.recognize(c)
            results.append((c, r))

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

    # ── Phases 4-5: Explore & Solve ─────────────────────────────────────

    def try_solve(self, challenge: CTFChallenge,
                  recognition: RecognitionResult,
                  target_url: str = None) -> SolveResult:
        """Attempt to solve a challenge using ctf_scanner functions."""
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

        # Phase 4: Explore target with quick_recon
        print("[Solve] Exploring target: %s" % target_url)
        recon = quick_recon(target_url)
        result.exploration_data = recon

        if recon.get('endpoints'):
            print("[Solve] Found endpoints: %s" % recon['endpoints'])

        # Phase 5: Run auto-exploit based on pattern
        flag = None
        findings = []

        if recognition.top_match:
            subcat = recognition.top_match.subcategory
            print("[Solve] Running scanner for subcategory: %s" % subcat)

            if subcat == "SSRF":
                flag, findings = scan_ssrf(target_url,
                                           forms=recon.get('forms', []),
                                           endpoints=recon.get('endpoints', []))
            elif subcat == "备份文件泄露":
                flag, findings = scan_backup(target_url)
            elif subcat == "文件包含":
                flag, findings = scan_lfi(target_url)
            elif subcat == "SQL注入":
                flag, findings = scan_sqli(target_url,
                                           forms=recon.get('forms', []),
                                           endpoints=recon.get('endpoints', []))

        if flag:
            result.flag = flag
            result.solved = True
            print("[Solve] FLAG FOUND: %s" % flag)
        else:
            if findings:
                print("[Solve] Findings: %d items (no flag)" % len(findings))
            print("[Solve] Auto-exploit unsuccessful — manual analysis needed")
            self._print_solve_hints(recognition, recon)

        result.elapsed_seconds = time.time() - start_time
        return result

    def _print_solve_hints(self, recognition: RecognitionResult, recon: Dict):
        """Print detailed hints for manual solving."""
        print("[Hints] ---")
        if recognition.top_match:
            print("[Hints] Attack plan:")
            for step in recognition.top_match.attack_chain:
                print("[Hints]   [%s] %s" % (step.get('phase', '?'), step.get('detail', '')))

        if recon.get('endpoints'):
            print("[Hints] Discovered endpoints: %s" % recon['endpoints'])
        if recon.get('forms'):
            print("[Hints] Discovered forms: %s" % recon['forms'])

    # ── Phase 6: Record ─────────────────────────────────────────────────

    def record_solution(self, result: SolveResult):
        """Record a solved challenge to the knowledge base."""
        if not result.solved:
            return

        solution_dir = os.path.join(self.kb_root, "solved", "ctfhub")
        os.makedirs(solution_dir, exist_ok=True)

        slug = re.sub(r'[^a-z0-9]+', '_', result.challenge.title.lower()).strip('_')
        if not slug:
            slug = "challenge_%d" % result.challenge.challenge_id
        filepath = os.path.join(solution_dir, "%s.md" % slug)

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
        from tools.feeder.ctfhub_flag_submit import submit_flag

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

            result = self.try_solve(c, r, target_url)
            self.results.append(result)

            if result.solved and result.flag:
                ok, msg = submit_flag(c.title, result.flag)
                print("[Submit] %s -> %s: %s" % (c.title, ok, msg))
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
