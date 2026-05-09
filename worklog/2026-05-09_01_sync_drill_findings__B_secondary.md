# Sync Drill 发现汇报 (B_secondary → A_main)

> **日期**: 2026-05-09
> **执行机器**: `B_secondary` (`F:\cloud\DD`, Windows 11, Python 3.12.7, default GBK console)
> **任务来源**: A_main 给的"sync 三库 + 跑测试 + 验证工具齐全 + setup_machine"指令
> **完成度**: sync ✓ / 测试 9/10 (修复 1 个) / setup_machine ✓ / **3 个 bug 待 A_main 修复**

---

## 一、Sync 执行情况

### 1.1 拉取范围

```
xiaokon-all/main:  25681e0..3c88e9d  (本机收到 20 commit)
push 后 master → main: 3c88e9d..7af3572  (含本机 catch-up merge commit)
108 files changed, 13853 insertions(+), 1751 deletions(-)
```

### 1.2 6 个工具文件验证全部到位

- ✓ `tools/build_kb_index.py`
- ✓ `tools/setup_machine.py`
- ✓ `tools/sync_to_xiaokon_all.py`
- ✓ `tests/run_all.py`
- ✓ `docs/AGENT_BOOTSTRAP_PROMPT.md`
- ✓ `docs/MULTI_MACHINE_CONTRIBUTION.md`

### 1.3 网络曲折：Steam++ 加速器是 GitHub 流量瓶颈

中间多次 fetch 失败，根因不是 git 配置，是本机 **Steam++ Accelerator** 把 GitHub 域名劫持到 `127.0.0.1` 但本身不接服务（端口扫描确认 `127.0.0.1:443` 无 listener）。

```
hosts 被劫持到 127.0.0.1 的 GitHub 域名: 27 条
curl https://github.com → Trying 127.0.0.1:443 → connection refused
```

**关 Steam++ GUI 里的 GitHub 加速规则后**，hosts 自动恢复，sync 一次成功。

> **建议**：`docs/MULTI_MACHINE_CONTRIBUTION.md` 增加一节"国内网络环境注意事项"，提醒：Steam++/Watt Toolkit 即使关 GUI 也可能残留 hosts 劫持，sync 前必跑 `tools/check_net.ps1`。

---

## 二、测试套件结果：9/10（修了 1 个 Unicode bug 后）

| 子套件 | 修前 | 修后 | 备注 |
|---|---|---|---|
| `test_collab_hub.py` | ✓ | ✓ | |
| `test_hub_v04_endpoints.py` | ✓ | ✓ | |
| `test_dashboard_heartbeat.py` | ✓ | ✓ | |
| `test_ssh_helper.py` | ✓ | ✓ | |
| `test_sim_recon.py` | ✓ | ✓ | |
| `test_huoyan_adapter.py` | ✓ (50/50) | ✓ | |
| `test_parse_yaml.py` | ✓ | ✓ | |
| `test_prompt_gen.py` | ✓ | ✓ | |
| `test_multi_machine.py` | ✗ | ✓ (25/0) | 修了 build_kb_index.py Unicode |
| `test_fic_kb_search.py` | ✗ | ✗ | **架构 bug，留给 A_main**（见 §3.3） |

---

## 三、待 A_main 修复的 3 个 Bug

### 3.1 [HIGH] Unicode 字符在 Windows GBK console 全部炸（多文件）

**症状**：

```
UnicodeEncodeError: 'gbk' codec can't encode character '\u2713' in position 2:
illegal multibyte sequence
```

任何 `print('  ✓ ...')` `print('  ✗ ...')` 这类装饰字符的工具，在默认 cp936 console 都崩。

**已确认受影响文件**：
- `tools/build_kb_index.py` line 189 / 203 (`✓`)
- `tools/setup_machine.py` line 245 (`✓`)
- `tools/fic_kb_search.py` 多处（17 个测试 fail 中部分由此产生）
- 推测：所有 print 用 ✓ ✗ ⚠ → 都受影响

**复现**：

```powershell
# 在默认 cp936 console（不设 PYTHONIOENCODING）
python tools/setup_machine.py --id Test  # → UnicodeEncodeError
$env:PYTHONIOENCODING = "utf-8"
python tools/setup_machine.py --id Test  # → 正常
```

**A_main 那边为什么不暴露**：A_main 估计有 `PYTHONIOENCODING=utf-8` 全局环境变量，或用 git bash / WSL（自带 UTF-8 stdout）。

**B_secondary 的临时修复**（已应用，未 push）：

每个工具顶部 `import sys` 后加：

```python
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
```

已临时修复 `build_kb_index.py` 和 `setup_machine.py`，让本机能跑通流程。**未 commit、未 push**，等 A_main 决定永久方案。

**建议永久修复**（择一）：
1. **每个 CLI 工具顶部加上面 3 行**（最稳，跨环境）
2. **改文档要求所有 Windows 用户设 `PYTHONIOENCODING=utf-8`**（最省，但用户容易忘）
3. **把 ✓ ✗ ⚠ 替换为 ASCII 等价**（`[OK]` `[FAIL]` `[WARN]`），不依赖环境

我倾向方案 1（最少惊讶）。

### 3.2 [HIGH] `fic_kb_search.py` 硬编码绝对路径，B 机器上完全失效

**症状**：

```python
# tools/fic_kb_search.py 第 27 行
KB_ROOT = Path(r"E:\ffffff-JIANCAI\2026FIC团体赛\case\shared\knowledge_base")
```

B_secondary 没有 `E:\ffffff-JIANCAI\` 这个目录。结果：
- `fic_kb_search.py --category computer` 退出 0 但**输出空**
- `--result incorrect` 期望 12 条结果，**实际 0**
- `--keywords maccms` `--question "..."` 抛 Traceback
- **17 个测试用例失败**

**对比**：`build_kb_index.py:38-53` 的 `find_kb_dir()` 有 fallback 链（cwd → repo-relative → 几个候选硬编码路径），所以多机能用。`fic_kb_search.py` 没有这种 fallback。

**建议修复**：

KB_ROOT 改成与 `build_kb_index.py` 一致的解析逻辑：

```python
def find_kb_root() -> Path:
    # 1. 环境变量优先
    if "FIC_KB_ROOT" in os.environ:
        return Path(os.environ["FIC_KB_ROOT"])
    # 2. repo 内（推荐：把 KB 放进 monorepo 的 knowledge/competitions/2026FIC-团体赛/）
    repo_kb = Path(__file__).resolve().parent.parent / "knowledge" / "competitions" / "2026FIC-团体赛"
    if repo_kb.is_dir():
        return repo_kb
    # 3. fallback 到 A_main 老路径（向后兼容）
    legacy = Path(r"E:\ffffff-JIANCAI\2026FIC团体赛\case\shared\knowledge_base")
    if legacy.is_dir():
        return legacy
    raise FileNotFoundError("KB not found, set FIC_KB_ROOT or move KB into repo")
```

> 配套问题：A_main 的 KB 数据 (`E:\ffffff-JIANCAI\...\knowledge_base\`) 当前**根本不在 monorepo 里**，需要决定：要不要把它迁入 `knowledge/competitions/2026FIC-团体赛/`？这是数据归属决策，B_secondary 不擅自做。

### 3.3 [MED] `setup_machine.py` 没处理 `core.hooksPath` 已设置的情况

**症状**：

```bash
$ git -C f:\cloud\DD config --get core.hooksPath
.githooks                          ← 已被 §8 collab tuning v1.1 设过

$ python tools/setup_machine.py --id B_secondary
  ✓ installed hook: commit-msg    ← 装到了 .git/hooks/，但 git 不会调用
  ✓ installed hook: pre-commit    ← 同上
```

**结果**：B_secondary 上 `[machine: B_secondary]` 的自动追加**没有生效**，因为 git 只会调用 `.githooks/` 里的 hook（仓库已设 `core.hooksPath`）。`setup_machine --status` 显示 "installed" 是误报，它只检查文件存在，没检查 git 是否真的会调用。

**两个 hook 系统的来源**：
- `.githooks/pre-commit` 来自 `PROPOSAL_local_collab_tuning_v1.md §8`（user.name 防呆）
- `.git/hooks/{commit-msg, pre-commit}` 来自 `setup_machine.py`（machine 标签 + INDEX 防呆）

**建议修复**：

`setup_machine.py` 安装 hook 前检查 `core.hooksPath`：

```python
hooks_path = subprocess.check_output(
    ["git", "-C", str(REPO), "config", "--get", "core.hooksPath"],
    text=True
).strip() or ".git/hooks"
target_dir = Path(REPO) / hooks_path
# 如果已存在 hook，合并而不是覆盖（或至少警告）
if (target_dir / "pre-commit").exists():
    # merge logic / append / fail-loud
```

或者：`setup_machine.py` 安装时直接把内容追加到 `.githooks/pre-commit`（如果它存在），并 `chmod +x`。

---

## 四、本机当前状态（截至本反馈写完时）

### 4.1 改动的文件（未 push、未 commit）

```
M  tools/build_kb_index.py    — 顶部加 3 行 sys.stdout.reconfigure
M  tools/setup_machine.py     — 顶部加 3 行 sys.stdout.reconfigure
?? worklog/2026-05-09_01_sync_drill_findings__B_secondary.md   ← 这份反馈
?? tools/diag_windsurf.ps1                                       ← 之前 Windsurf 故障诊断工具
?? tools/launch_windsurf.ps1                                     ← Windsurf bypass-list 启动包装
?? cases/2026FIC/diag/                                           ← Windsurf 故障基线快照（16 文件）
?? cases/_drill_2026-05-09/                                      ← Hub 实测目录
?? .tmp_*.{py,sh,jpg}  (33 个)                                   ← 历史 2026FIC 调试残留
?? .tmp_repro_build.ps1                                          ← 本次复现 Unicode bug 用
```

### 4.2 setup_machine 配置

```
MACHINE_ID:    B_secondary
config file:   C:\Users\MXM\AppData\Roaming\autoforensicai\machine.txt
repo:          F:\cloud\DD
git user.name: cascade@B_secondary
hook commit-msg:    installed (但因 core.hooksPath=.githooks 不被 git 调用，见 §3.3)
hook pre-commit:    installed (同上)
```

### 4.3 git 状态对比

```
xiaokon-all/main HEAD: 7af3572 (本机 push 上去的 catch-up merge)
master HEAD:           7af3572
master..xiaokon-all/main:  empty
xiaokon-all/main..master:  empty
```

---

## 五、建议接下来的处理顺序

按严重性：

1. **修 §3.1 Unicode**（影响所有 Windows + 默认 GBK 用户的工具调用）
2. **修 §3.2 fic_kb_search.py 硬编码 + 决策 KB 数据归属**（影响所有非 A_main 机器的知识库使用）
3. **修 §3.3 hook 冲突**（当前 `[machine: ID]` 标签未自动加，所有 commit 需手工加，否则 push 时会发现没标签）

修完后建议再发布一轮 A_main → xiaokon-all sync，B_secondary 再次 sync 验证 10/10。

---

## 六、本机 stash & 临时文件清理建议

如果 A_main 准备好永久修复版本：

```powershell
# 1. 撤销 B_secondary 的临时 Unicode 修复
git -C f:\cloud\DD checkout -- tools/build_kb_index.py tools/setup_machine.py

# 2. 拉新版
pwsh f:\cloud\DD\tools\sync_xiaokon-all.ps1 -NoPush

# 3. 重测
python f:\cloud\DD\tests\run_all.py  # 期望 10/10
```

`__B_secondary` 后缀已正确应用到本反馈文件名，符合 §3.1 of `MULTI_MACHINE_CONTRIBUTION.md`。

— B_secondary, 2026-05-09 18:00

---

## 七、第二轮 (v2) — 按 A_main 永久 fix 验证复盘

> **时间**: 2026-05-09 18:30
> **上游 fix commit**: `6585ca9 sync: framework@2d6c93c + data@3bd6844`
> **本机 HEAD**: `22a56f1 Merge xiaokon-all/main (auto-sync 2026-05-09 18:11)`

A_main 在 §一 写完后很快推送了永久 fix，本 v2 章节记录按她 6 阶段验证计划跑下来的结果与新发现的一个 Windows-specific bug。

### 7.1 验证矩阵

| 阶段 | 指令 | 结果 |
|---|---|---|
| 1 | `git checkout -- tools/build_kb_index.py tools/setup_machine.py` + sync -NoPush | ✓ 拉到 `6585ca9`；108 files changed; `detect_layout.py`/`safe_push.py`/`build_kb_index.py`/`setup_machine.py`/`fic_kb_search.py`/`sync_to_xiaokon_all.py` 全部升级 |
| 2 | `setup_machine.py --status` → `--id B_secondary` | ✓ `hooks dir: F:\cloud\DD\.githooks`，原 `.githooks/pre-commit` 被 `pre-commit.bak` 备份并 merged 进 combined hook；head 是 `Auto-installed by tools/setup_machine.py`，tail 保留原 user.name guard 完整（含 `History lesson 5ce84eb` 注释 + `GIT_BYPASS_AUTHOR=1` 机制） |
| 3 Bug1 | `detect_layout.py` | ✓ 不再 UnicodeEncodeError；输出 `LAYOUT: B_monorepo_multi` + 完整 remote 安全建议（严禁 `push framework/data`，仅允许 `push xiaokon-all`） |
| 3 Bug2 | `fic_kb_search.py --all` | ✓ 不再硬 crash；友好错误 `[fic_kb_search] 找不到 KB 根目录. 候选搜索路径全部失败. 解决: 用 --kb-dir <path> 或 export AUTOFORENSICAI_KB=<path>` |
| 3 Bug3 | `git commit -m "..."` | ⚠ 最初 silent exit 1 失败，修了**新 bug §7.2** 后 ✓，commit message 自动变为 `hook_v4 [machine: B_secondary]` |
| 4 | `tests/run_all.py` | PASSED=9 / FAILED=1；唯一 fail 是 `test_fic_kb_search.py` 内部 4/27，根因见 §7.3 |

### 7.2 [HIGH] 新 bug — Windows 11 Microsoft Store Python3 stub 让 `commit-msg` hook silent fail

**症状**：commit-msg hook 每次 silent exit 49，git 中止 commit 且**没有任何 stderr 输出**。用户看到的是 git 啥都不说就 exit 1。

**根因**：`.githooks/commit-msg` 第 29 行 `python3 -c "..."`。Windows 10/11 默认在 PATH 头部装 **App Execution Alias** stub：

```
which python3  →  /c/Users/MXM/AppData/Local/Microsoft/WindowsApps/python3.exe
python3 --version  →  (空输出, exit 49)
```

这个 stub 不是 Python，是个点击跳转 Microsoft Store 的空壳。非交互执行时：
- silent exit 49
- 没 stdout/stderr
- 没修改 `.git/COMMIT_EDITMSG`

commit-msg hook 的 `python3 -c "..."` 是**最后一条命令**，shell 退出码等于它的退出码 → 49 → git 认为 hook 拒绝 commit → 整个 commit 被中止，但用户看不到任何原因。

**复现**：

```bash
# 在 git for windows 的 mingw bash 里（不是 WSL）
echo "fake" > /tmp/msg.txt
bash .githooks/commit-msg /tmp/msg.txt
echo "exit=$?"   # → 49
cat /tmp/msg.txt  # → fake  (没加 [machine: ID])
```

**A_main 那边为什么不暴露**：
- A_main 可能用 `py` launcher 而非直调 `python3`
- A_main 可能已禁用 Microsoft Store App Execution Aliases (Settings > Apps > Advanced > App execution aliases)
- A_main 可能装了真 `python3.exe` 在 PATH 头部覆盖 stub

**B_secondary 本机 hotfix**（已应用到 `.githooks/commit-msg`，**未 push**）：

```bash
# Auto-append [machine: ID] to last non-empty line
# B_secondary local hotfix: 'python3' on Windows 11 may resolve to a Microsoft
# Store App Execution Alias stub at /c/.../WindowsApps/python3 that silent-exits 49.
# Skip any stub path; prefer real 'python' on Windows.
PYTHON_CMD=""
for cand in python3 python; do
    p=$(command -v "$cand" 2>/dev/null) || continue
    case "$p" in
        */WindowsApps/*) continue ;;  # Microsoft Store stub
    esac
    PYTHON_CMD="$p"
    break
done
if [ -z "$PYTHON_CMD" ]; then
    echo "[commit-msg] no real Python found (only Microsoft Store stubs?)" >&2
    exit 1
fi
"$PYTHON_CMD" -c "..."
```

**建议永久修复**：把这段 hotfix 合并进 `setup_machine.py` 生成 commit-msg hook 的模板即可。所有 Windows 用户都需要这个 stub 过滤。

### 7.3 [MED] `test_fic_kb_search.py` 应 skip 而非 FAIL 当 KB 数据缺失

**症状**：`fic_kb_search.py` 工具本身（A_main 已修）正确返回友好错误 + 非零退出码。但 `test_fic_kb_search.py` 里的测试断言仍假设 KB 数据存在：

```
[FAIL] --category computer 退出码 0
[FAIL] --category computer 输出非空
[FAIL] --category computer 输出含 FIC2026
[FAIL] --result incorrect 含 12 个错答 (实际 0)
[FAIL] keywords maccms 退出码 0  [fic_kb_search] 找不到 KB 根目录. ...
...
PASSED: 4  FAILED: 27
```

B_secondary 没 KB 数据 → 工具正确"找不到 KB" → 测试期望"有 12 条错答"→ FAIL。

**这不是工具 bug**，是**测试设计对环境不敏感**。合规的 skip 逻辑：

```python
def setUp(self):
    from pathlib import Path
    kb = Path.cwd() / "knowledge" / "competitions" / "2026FIC-团体赛"
    if not kb.is_dir() and not os.environ.get("AUTOFORENSICAI_KB"):
        self.skipTest(f"KB not available on this machine (set AUTOFORENSICAI_KB or populate {kb})")
```

或者用 `pytest.mark.skipif` / `unittest.skip` 装饰器。

**当前影响**：`run_all.py` 在任何没 KB 数据的机器上都会报 9/10。不影响代码正确性，但影响 CI 绿灯判断。

### 7.4 本机当前状态（v2 结束时）

```
HEAD = 22a56f1  (Merge xiaokon-all/main 2026-05-09 18:11)
master sync with xiaokon-all/main

改动：
 M .githooks/pre-commit      ← setup_machine 生成 combined，不 commit
?? .githooks/commit-msg      ← setup_machine 生成 + v2 加 stub 过滤 hotfix，不 commit
?? worklog/2026-05-09_01_sync_drill_findings__B_secondary.md  ← 本文，v2 后会 commit+push

MACHINE_ID = B_secondary
git user.name = cascade@B_secondary
core.hooksPath = .githooks
```

### 7.5 对 A_main 的下一步请求

按优先级：

1. **[HIGH] 修 §7.2 python3 stub bug** — 影响所有 Windows 10/11 协作者（默认有 App Execution Alias），他们用 `setup_machine.py` 装好 hook 后会发现 `[machine: ID]` 标签根本不自动加但又没错误信息。可选方案：
   - A. 改 commit-msg 模板加 stub 过滤（最稳）
   - B. 改 `setup_machine.py` 在 Windows 上自动 `reg delete` 掉 App Execution Alias（需用户确认，破坏性）
   - C. 在 `docs/MULTI_MACHINE_CONTRIBUTION.md` 增加一节"Windows 11 首次 setup 必须手动关 App Execution Alias"（最便宜）

2. **[MED] 修 §7.3 test_fic_kb_search.py skip 逻辑** — 让 `run_all.py` 在没 KB 数据的机器上变 10/10。一行 `skipTest()` 能解决。

3. **[LOW] Steam++ 残留 proxy 预检** — 上轮 §1.3 提过。我已经在 `tools/check_net.ps1` 加了 Stage 0（registry ProxyServer 指向 127.0.0.1 就警告）—— 这个改动在本机但**未 push**。你看要不要合入。

修完 §7.2 + §7.3 后，B_secondary 跑 `git checkout -- .githooks/commit-msg` 撤销 hotfix，再 sync 一次，期望 run_all 到 10/10。

— B_secondary, 2026-05-09 18:30 (v2)
