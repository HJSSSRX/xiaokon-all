# 多机协作贡献规则 (Multi-Machine Contribution Rules)

> **版本**: v1.0 (2026-05-09)  
> **适用**: 三库 (`xiaokon_autoforensicai` / `autoforensicai_data` / `xiaokon-all`)  
> **解决问题**: 多台机器同时跑 AI 分析, 都想往三库提交贡献, 每台贡献的内容不同, 但合并时频繁冲突.

---

## TL;DR — 一句话规则

**每台机器只往"自己专属命名空间"的文件写, 共享 INDEX 由工具自动重建, push 前先 rebase**.

---

## 一、根本痛点诊断

### 1.1 为什么以前会冲突

| 冲突类型 | 例子 | 频率 |
|---|---|---|
| 同名文件双方都新建 | A 机和 B 机都新建 `tools/check_net.ps1` | **高** |
| INDEX 集中表 | A/B 机都改 `knowledge/retrospectives/INDEX.yaml` 加自己的条目 | **极高** |
| 同一行被两边都改 | `worklog/2026-05-09.md` 同一段两边都补充 | 中 |
| 运行时状态混入 | `data/collab_hub/hub.db` 被 commit | 偶发 |

### 1.2 解决核心思路

**写入隔离 (Write Isolation)** — 让两台机器**物理上不可能写到同一个 byte**:
1. 静态贡献 → 文件名带机器 ID
2. 索引文件 → 工具自动生成, 任何手改都被 hook 拒绝
3. 运行时状态 → 严格 gitignore, 永不入仓库
4. push 前必须 rebase, 强制让冲突在本地解决

---

## 二、机器身份制 (MACHINE_ID)

### 2.1 什么是 MACHINE_ID

每台跑 ForHacker 的机器有**唯一标识**:
```
格式: <主机名缩写>_<角色用途>
例子: A_main / B_secondary / C_user1 / lab_03
```

存放位置:
- Windows: `%APPDATA%\autoforensicai\machine.txt`
- Linux/Mac: `~/.config/autoforensicai/machine.txt`

### 2.2 首次设置

任何机器**首次 clone** 后必须跑:

```bash
python tools/setup_machine.py
# 询问: 这台机器叫什么? (默认: <主机名_main>)
# 自动:
#   1. 写入 machine.txt
#   2. git config user.name = "cascade@<MACHINE_ID>"
#   3. 安装 pre-commit hook (拦截手改 INDEX, 拒绝运行时文件)
#   4. 安装 .gitignore 增量条目
```

### 2.3 commit 必带机器标签

所有 commit message **结尾**带 `[machine: <ID>]`:

```
✓ feat(huoyan): 8001 → 8477 实地修正 [machine: A_main]
✓ fix(prompt): IP 替换 [machine: B_secondary]
✗ feat(huoyan): 8001 → 8477 实地修正                ← 缺机器标签, 被 hook 拒绝
```

`tools/setup_machine.py` 装的 commit-msg hook 会**自动检查 + 自动追加** (如果你忘了, 它给你加上).

---

## 三、文件命名空间分区

### 3.1 高冲突区域: 复盘 / 笔记 / 个人产物

**强制带 `__<MACHINE_ID>` 后缀**:

```
✗ knowledge/retrospectives/20260509_C01_os_version.yaml          ← 谁都能写, 必冲突
✓ knowledge/retrospectives/20260509_C01_os_version__A_main.yaml  ← 只 A_main 写
✓ knowledge/retrospectives/20260509_C01_os_version__B_second.yaml ← B 机写另一份
```

合并时, 同一题可以有多个机器的复盘, 互相独立, **不冲突**, 而且能看到不同机的视角对比.

### 3.2 共识区: solved/ skills/ cards/

这些是"经过共识的最终答案", 不应该乱 commit. 流程:
1. 各机先把自己的初稿放在 `retrospectives/<...>__<MACHINE_ID>.yaml`
2. 主控 (designated curator) 定期合并/筛选, 提交到 `solved/`
3. 任何机器**直接改 `solved/` 必须先开 issue 讨论**, 否则 PR 不予合并

### 3.3 索引文件: INDEX 由工具生成

```
knowledge/retrospectives/INDEX.yaml  ← 自动生成, 不要手改
knowledge/wp_index/INDEX.md          ← 自动生成
knowledge/INDEX.yaml                 ← 顶层索引, 自动生成
```

任何 commit 包含 INDEX 文件**手动改动**, pre-commit hook 拒绝.

正确做法:
```bash
# 添加新复盘后
python tools/build_kb_index.py    # 自动扫目录重建所有 INDEX
git add .
git commit -m "..."
```

---

## 四、运行时状态严格隔离

### 4.1 .gitignore 必含

```gitignore
# 运行时状态 (collab_hub / role_log)
data/collab_hub/*.db
data/collab_hub/*.db-journal
data/collab_hub/needs_*.json
data/collab_hub/role_status_*.json

# 个人笔记 / 进度
progress.txt
worklog/personal_*.md
*.draft.md

# 缓存
.cache/
__pycache__/
*.pyc

# 机器配置 (在 ~/.config 不在仓库, 但兜底)
machine.txt
.machine_id

# 测试产物
tests/output/
htmlcov/

# IDE
.vscode/settings.json
.idea/
```

### 4.2 已经误提交怎么办

```bash
git rm --cached <path>
git commit -m "chore: gitignore 运行时状态 [machine: ...]"
```

---

## 五、push 流程: safe_push 工具

### 5.1 一键 push 三库

每个想 push 的机器跑:

```bash
python tools/safe_push.py
```

工具自动做:
1. **网络检查**: `tools/check_net.ps1` 确保不被代理劫持
2. **工作树检查**: 必须 `git status` 干净
3. **fetch 三库**: `origin` (框架) + `data` (数据) + `all` (全量)
4. **重建 INDEX**: 跑 `tools/build_kb_index.py`
5. **rebase 自己的 commits** 到最新 `origin/main`
6. **跑测试**: `tests/run_all.py` 必须全绿
7. **push 三库**:
   - 框架内容 → `origin`
   - 知识库内容 → `data`
   - 整个项目 → `all`
8. 任何步骤失败 → **自动 abort + 回滚**

### 5.2 选项

```bash
python tools/safe_push.py --dry-run   # 不真推, 看会做什么
python tools/safe_push.py --no-test   # 跳过跑测试 (不推荐)
python tools/safe_push.py --only data # 只推数据库
```

### 5.3 冲突场景的标准 SOP

如果 rebase 时撞冲突:

1. 先看冲突文件, 是不是命名空间分区违规导致
   - 是 → 改成带 `__<MACHINE_ID>` 后缀, 重 add
   - 不是 (真的有逻辑冲突) → 手动解 + 跑测试 + 继续
2. `git rebase --continue`
3. `python tools/safe_push.py --resume`

**绝不**用 `git push --force`, 永远 rebase.

---

## 六、各库职责边界 (Routing Rules)

| 内容类型 | 路径 | 应该 push 到 |
|---|---|---|
| Python/Shell 工具代码 | `tools/*.py` `tools/*.sh` | **框架库** + 全量库 |
| 测试 | `tests/*.py` | **框架库** + 全量库 |
| 设计文档 / 用户手册 | `docs/*.md` | **框架库** + 全量库 |
| 工作日志 (主线) | `worklog/2026-*.md` | **框架库** + 全量库 |
| CHANGELOG | `CHANGELOG.md` | **框架库** + 全量库 |
| 题解 / 复盘 / 技巧卡 | `knowledge/**/*.{md,yaml}` | **数据库** + 全量库 |
| 案件特化产物 | `cases/<比赛>/*` | **数据库** + 全量库 |
| 题目索引 | `knowledge/wp_index/*` | **数据库** + 全量库 |
| 运行时状态 | `data/collab_hub/*` | **不入任何仓库** |

`safe_push.py` 自动按这表分发.

---

## 七、贡献者上手指南

### 7.1 全新机器从零部署 (推荐用 xiaokon-all 全量库)

```bash
# 1. 拉全量库
git clone https://github.com/HJSSSRX/xiaokon-all.git e:\xiaokon-all
cd e:\xiaokon-all

# 2. 首次 setup
python tools/setup_machine.py
# 询问: 你的机器叫什么? (输入 C_user1)

# 3. 看你能做什么 (5 个 AI 角色 prompt)
ls case/role_prompt_*_v5.md
```

### 7.2 已有框架库, 要拉数据库

```bash
git clone https://github.com/HJSSSRX/autoforensicai_data.git e:\autoforensicai_data

# 加 remote 到框架库, 用 safe_push 时它会同时 push 数据库
git -C e:\项目\自动化取证 remote add data file://e:/autoforensicai_data
```

### 7.3 提交贡献 (复盘新经验)

```bash
# 1. 写新复盘 (必须带机器 ID 后缀)
$MACHINE_ID = (Get-Content $env:APPDATA\autoforensicai\machine.txt).Trim()
$f = "knowledge/retrospectives/20260510_X02_my_finding__$MACHINE_ID.yaml"

@"
title: 某种新发现
machine: $MACHINE_ID
date: 2026-05-10
context: |
  ...
lesson: |
  ...
"@ | Set-Content $f

# 2. 一键 push 三库
python tools/safe_push.py
```

### 7.4 反向流程: 从远程拉别人新增的复盘

```bash
git pull origin main      # 框架更新 (代码/文档)
git pull data main        # 数据更新 (其他机的复盘)
python tools/build_kb_index.py  # 重建本地 INDEX
```

---

## 八、违规处理

为保护协作秩序, 三库的 GitHub Actions 钩子检查:

| 检查 | 违规 | 处理 |
|---|---|---|
| commit message 缺 `[machine: ...]` | 拒绝 | 必须修改后再 push |
| 修改了 INDEX 但没跑 build_kb_index | 警告 | 提示但不拒绝 |
| 提交了 `*.db` `progress.txt` | 拒绝 | 必须 `git rm --cached` |
| 提交了 `solved/` 的文件但 PR 描述空 | 警告 | 鼓励先开 issue |
| `__<MACHINE_ID>` 后缀的文件被多个机器修改 | 拒绝 | 命名违规 |

未来扩展: 我们可以加 `tools/check_contribution_rules.py` 在 CI 跑.

---

## 九、版本历史

- **v1.0** (2026-05-09): 首版, 基于 5 月 9 日多机协作复盘提炼.

---

## 附录: FAQ

### Q1. 为什么不用 monorepo (一个仓库) 而要三库?

**框架** 是工具代码, 比赛中很少改 (改了重启). **数据** 比赛中频繁追加 (每解一题就有复盘). **全量** 是新人快速部署用的镜像. 分开后:
- 代码库 commit 历史清爽
- 数据库可以独立增长, 不污染代码 history
- 全量库给新人一次拉到位

### Q2. MACHINE_ID 我换了机器怎么办?

直接换. 系统不强制 ID 唯一, 只要你**自己机器内部一致**即可. 切换:
```bash
python tools/setup_machine.py --rename A_main A_main_renamed
```

### Q3. 我有"半成品"想保存又不想 push 给别人看?

**不要** commit 到主分支. 用本地 branch:
```bash
git checkout -b A_main_wip
# ... 工作 ...
git checkout main  # 切回时不影响主分支
```

或者放在 `worklog/personal_*.md` (已 gitignore).

### Q4. 多机的复盘视角不同, 怎么 reconcile 成最终 solved?

主控 (curator) 周期性做:
1. 列出同一题的所有 `__*.yaml`
2. 综合提炼成 `knowledge/solved/<比赛>_<题号>.md`
3. 老的 `__*.yaml` 留着不删 (历史档案)

未来可以加 `tools/curate_solved.py` 半自动化.

### Q5. CI/CD 会跑吗?

当前 v1.0 **没有** CI 自动化. 是手动 `safe_push.py` 验证. v1.1 会加 GitHub Actions:
- pre-receive hook 检查 commit message
- post-receive hook 自动重建 INDEX
- 失败给 maintainer 邮件
