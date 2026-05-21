# Full-Auto Training Protocol

## Purpose
Validate and improve the AutoForensicAI pipeline by solving challenges with KNOWN answers. The goal is not just to get the flag — it's to produce a high-quality, reusable solution file in knowledge/solved/.

## Workflow

### Step 1: Challenge Setup
Main receives:
- Challenge files (images, pcaps, binaries, etc.)
- Known answer/flag (for verification)
- Challenge description and category

Main creates workspace:
```
training/{date}_{challenge_name}/
├── shared/
├── challenge/          ← challenge files here
├── work/               ← solver's working directory
└── output/
    └── solution.md     ← final output
```

### Step 2: Knowledge Base Search (CRITICAL)
Before ANY solving attempt:
```bash
python tools/kb_search.py --tags {relevant_tags}
python tools/kb_search.py --text "{key_phrases}"
python tools/kb_search.py --tools {likely_tools}
```

If a relevant prior solution exists:
- Read it
- Attempt to follow the same approach
- Note whether it worked or needed adaptation
- This tests KB reusability

If no prior solution exists:
- Solve from scratch
- This fills a gap in the KB

### Step 3: Solve
The solver (single window or multiple) works through the challenge:
1. Identify challenge type
2. Apply relevant techniques from skills/
3. Execute CLI commands step by step
4. Document every command and its output
5. Find the flag

### Step 4: Verify
Compare found answer with known answer:
- Match → proceed to Step 5
- No match → log failure, analyze why, retry with different approach

### Step 5: Generate Solution File
Write to `knowledge/solved/{challenge_name}.md`:

```markdown
---
tags: [{tag1}, {tag2}, ...]
tools: [{tool1}, {tool2}, ...]
category: {category}
difficulty: {easy|medium|hard}
source: {where this challenge came from}
date: {today}
verified: true
---
# {Title}

## Problem
{Challenge description}

## Solution Steps
{Numbered steps with exact commands and expected output}

## Key Takeaways
{What's transferable to other challenges}

## Answer
{flag}
```

### Step 6: Pipeline Assessment
Log training metrics:
```yaml
# training/{date}_{name}/metrics.yaml
challenge: {name}
category: {category}
kb_search_hit: true/false     # Did KB have relevant prior art?
kb_solution_reused: true/false # Was a prior solution directly applicable?
solve_success: true/false
solve_time_seconds: {N}
tools_used: [...]
new_knowledge_generated: true  # Always true if solved
pipeline_notes: "..."          # Any issues with the pipeline itself
```

## Multi-Window Training
For efficiency, Main can set up multiple solvers working on different challenges simultaneously. Each solver is independent — they just need their own workspace directory. Main monitors progress and collects results.

```
training/batch_2026-05-05/
├── challenge_01/
│   ├── shared/
│   ├── challenge/
│   └── output/solution.md
├── challenge_02/
│   ├── shared/
│   ├── challenge/
│   └── output/solution.md
└── batch_report.md       ← Main compiles this
```

## Dual-Perspective Training (双端视角)

Training mode should explicitly connect forensics and offensive use of the same technique. For each solved challenge, answer:

```
## 双端视角

### 取证场景
{How this knowledge helps in forensics: what traces to look for, how to interpret artifacts}

### 攻防场景
{How this knowledge helps in offense: what weakness to exploit, how to bypass detection}

### 转换点
{The pivot: same technique, different direction}
```

**Example** — SQLite WAL 文件:
| | 取证 | 攻防 |
|---|---|---|
| 场景 | 从 WAL 恢复被删除的聊天记录 | 注入后覆盖 WAL 擦除操作痕迹 |
| 工具 | `sqlite3 .recover` | `PRAGMA journal_mode=OFF` |
| 转换点 | SQLite 的 WAL 即操作日志 — 谁控制了它，谁就控制了"真相" |

**Example** — inet_ntoa:
| | 取证 | 攻防 |
|---|---|---|
| 场景 | 从 `user_last_login_ip` (int) 提取真实 IP | 将攻击 IP 编码为 int 绕过 WAF IP 黑名单 |
| 转换点 | 同一转换函数 — 取证用它还原，攻击用它伪装 |

This dual perspective gets embedded in the solution file and fed back into the knowledge base, so future AI roles can pull both contexts automatically.

## What Makes Training Different from Competition
| Aspect | Training | Competition |
|---|---|---|
| Known answer | Yes | No |
| Time pressure | No | Yes |
| Goal | Build KB + validate pipeline | Find answers fast |
| KB search | Test if it helps | Use it to save time |
| Documentation | Thorough (含双端视角) | Good enough |
| Retry on failure | Yes, with analysis | Move on if stuck |
