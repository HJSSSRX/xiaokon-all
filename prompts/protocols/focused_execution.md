# Focused Execution Protocol (聚焦执行协议)

You are in **focused execution mode**. Your attention is on ONE sub-goal at a time.
No multitasking. No jumping ahead. Deep focus.

## Core Principle

Before running ANY tool, you do **关联性分析** (correlation analysis):
- What does the KB already know about this?
- What have previous sub-goals found that connects here?
- Which evidence files are relevant and why?
- What is my hypothesis?

Only THEN do you execute tools.

---

## Phase 1: ENTER FOCUS (进入聚焦)

**Action**: Run the CLI to get the next ready sub-goal and its context:

```powershell
python -m tools.cli executor next --case-dir {case_dir}
```

This outputs a JSON context dict. Parse it.

**Mode check** — the context now always includes `allocation_mode`:
- If `allocation_mode == "boost"`: This sub-goal is simple. **Switch protocol** — load `prompts/protocols/weak_model_boost.md` and run `python -m tools.cli executor boost --sg-id {sg_id} --case-dir {case_dir}`. Skip Phases 2-5 below.
- If `allocation_mode == "focused"`: Continue with Phases 2-5 below.

Tell the user:

```
当前聚焦: {sg_id} [{level_name}] {description}
模式: {allocation_mode} | 角色: {assigned_role} | 预估: {estimated_minutes}min | 依赖: {dependencies}
```

**If status = "all_complete"**: Print "全部完成!" and exit focused mode.
**If status = "all_blocked"**: Print the blocked items and their reasons. Ask the user how to proceed.
**If status = "no_ready"**: Print status and ask user to check manually.

---

## Phase 2: CORRELATE (关联性分析) — DO NOT SKIP

This is the core phase. You must complete ALL 5 sub-steps before running any tool.

### Step 2a: Read the Context

From the context dict, note:
- `domain` and `task_type` — what forensic domain this is
- `tools` — recommended tools
- `inputs` — evidence files to analyze
- `dep_findings` — findings from completed dependencies (CRITICAL: these are your leads)

### Step 2b: KB Search

Search the knowledge base for prior solutions matching this sub-goal:

```powershell
python -m tools.cli kb search --tags {kb_search_terms[0]} {kb_search_terms[1]} ...
```

Or use the consultant mode for natural language:
```powershell
python tools/kb_search.py --ask "{description}"
```

Read any matching results. Ask: "Has this kind of problem been solved before? What tools and techniques were used?"

### Step 2c: Cross-Reference Dependency Findings

Read `dep_findings` from the context. For each completed dependency:
- What evidence did they find?
- Does their finding relate to my sub-goal?
- Example: "SG-001 found that evidence file X is a Windows 10 memory dump. I need this for my memory analysis."

Identify **concrete connections** between their findings and your task.

### Step 2d: Evidence Identification

For each file in `inputs`:
- What type of evidence is it? (from evidence_classifier)
- What does its filename/size/magic bytes tell us?
- Is it already prepared (mounted/extracted/decrypted) by a dependency?

### Step 2e: Hypothesis Formation

State explicitly:
```
我的假设: 基于 {KB发现/依赖发现/证据类型}, 我预期在 {evidence} 中找到 {expected_finding}
```

Example: "Based on prior Windows memory forensics solutions, I expect to find the attacker's process in the memory dump's process list, likely with an abnormal parent process."

### Step 2f: Tool Plan

List the recommended tools and explain WHY each is appropriate:
```
工具计划:
1. volatility3 → 分析进程列表，查找异常进程
2. strings → 提取内存中的可读字符串，搜索IP/URL/命令
3. grep → 过滤特定模式
```

If the recommended tools seem wrong for the task, suggest alternatives and explain why.

**After completing all 6 sub-steps, ask the user:**
```
关联性分析完成。是否继续执行工具？[Y/n]
```

---

## Phase 3: EXECUTE (执行工具)

Run tools one at a time, sequentially. For each tool:

1. **Print the command** before running
2. **Run it** and capture stdout/stderr/returncode
3. **Summarize output** — don't dump raw output unless it's short. Extract the key findings.
4. **Check for errors** — if returncode != 0, note the error. Retry once with different args if appropriate.
5. **Handle timeout** — if a tool runs > 120s, kill it and move on.

**Tool execution pattern** (use existing infrastructure):
```python
from tools.core.tool_pool import run_tool_with_retry
result = run_tool_with_retry("tool_name", "arg1", "arg2", timeout=120, retries=1)
# result = {tool, args, return_code, stdout, stderr, success}
```

**If all tools fail**: Move to Phase 4 and mark the sub-goal as blocked.

---

## Phase 4: RECORD (记录结果)

For each significant finding, log it:

```python
from tools.hub.role_log import log_finding
log_finding(
    summary="简短摘要",
    detail="详细发现：命令 + 关键输出 + 解读",
    related_to=["SG-001"]  # 关联的依赖子目标
)
```

If this is a QUESTION-level sub-goal (level=3), extract the answer and log it:

```python
from tools.hub.role_log import log_answer
log_answer(
    qid="{question_qid}",
    answer="提取的答案",
    analysis="推导过程...",
    evidence_path=["证据路径"],
    confidence="medium"
)
```

Then mark the sub-goal complete:

```powershell
python -m tools.cli executor complete --sg-id {sg_id} --case-dir {case_dir} --findings '<json_findings_list>'
```

The `--findings` value is a JSON array of finding dicts:
```json
[{"tool": "volatility3", "finding": "发现可疑进程 svchost.exe PID 4396", "evidence": "memory.dmp", "related_to": ["SG-001"]}]
```

---

## Phase 5: TRANSITION (切换目标)

Print completion status:

```
✓ {sg_id} 完成! ({completed_count}/{total_count} 子目标已完成)
  记录了 {n} 个发现
  解封了: {unblocked_list}
```

Check what's next:

```powershell
python -m tools.cli executor status --case-dir {case_dir}
```

If there are ready sub-goals:
```
下一个就绪: {list_of_ready_ids}
继续下一个? [Y/n]
```

If user confirms, loop back to Phase 1 with `executor next`.
If user says no, save and exit: "会话已保存，随时可以恢复。"

---

## Error Handling

| Situation | Response |
|-----------|----------|
| Tool not found | Note in findings, try next tool, do not block |
| Tool timeout (>120s) | Kill, note partial output, try next tool |
| All tools failed | Mark sub-goal as blocked with reason |
| Evidence file missing | Log finding: "evidence X not found", proceed with remaining files |
| KB search returns nothing | Note "no prior art", proceed from first principles |
| Hub unreachable for logging | Save findings locally, retry at end of session |
| User interrupts during execution | Save session immediately, exit gracefully |

---

## Completion

When `executor next` returns `{"status": "all_complete"}`:

```
═══════════════════════════════════
  聚焦执行完成!
  题目: {challenge_name}
  子目标: {total_count} 个全部完成
  用时: {duration}
═══════════════════════════════════
```

Run final status:
```powershell
python -m tools.cli executor status --case-dir {case_dir}
```
