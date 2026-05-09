# 远程 AI 机子接入提示词 (Agent Bootstrap Prompts)

> **用法**: 直接把对应场景的提示词贴到那台机器的 AI 对话框里. AI 会自动执行所有步骤.
>
> **三库地址** (任何机器都用这三个 URL):
> - 框架库: `https://github.com/HJSSSRX/xiaokon_autoforensicai`
> - 数据库: `https://github.com/HJSSSRX/autoforensicai_data`
> - 全量库: `https://github.com/HJSSSRX/xiaokon-all`

---

## 场景 0: 架构识别 (任何场景前必跑)

> **关键**: 不同机器可能用不同的仓库布局. 跑工具前必须先识别本机属于哪种.

```
本机第一次接触 AutoForensicAI 项目时, 先识别架构. 不要假设和别的机器一样.

# 步骤
1. 找到 AutoForensicAI 的本地 git checkout 目录 (cwd_repo).
   常见位置: e:\项目\自动化取证 / e:\xiaokon-all / f:\cloud\DD / ~/autoforensicai
2. 检查目录里是否已有 tools/detect_layout.py:
   - 有: cd <cwd_repo> && python tools/detect_layout.py
   - 没有: 说明本机版本太老, 先从 xiaokon-all 拉最新 (跳到场景 0.1)

# 输出会指出本机是以下哪种布局
- A_framework_clone: 单一 framework clone (只有 tools/tests/docs)
- A_data_clone:      单一 data clone (只有 knowledge/cases)
- A_all_clone:       单一 xiaokon-all monorepo clone (内容齐全)
- B_monorepo_multi:  monorepo 内容 + 三个 remote 都配置了 (危险, 直推 framework/data 会破坏)
- A_*_legacy / unknown: 需要清理或迁移

# 不同布局的 push 规则
- A_framework_clone → 只推 origin (framework)
- A_data_clone      → 只推 origin (data)
- A_all_clone       → 只推 origin (all). 不要在这里改代码后试图分发到 framework/data.
- B_monorepo_multi  → 只能推 xiaokon-all remote, 推 framework/data 是禁止的.

# 如果 detect_layout 输出 "DANGER" 告警
完全不要忽视. 那意味着直接 git push 会破坏远程仓库. 把完整输出贴给我, 等指示.
```

### 场景 0.1: 本机太老, 没有 detect_layout (先 sync xiaokon-all)

```
本机的工具版本比 xiaokon-all 旧, 缺 tools/detect_layout.py 等. 先 sync 上游再说.

# 步骤
1. 先看本机目录有没有未 push 的本地改动:
   git -C <cwd_repo> status
   git -C <cwd_repo> log --all --not --remotes --oneline
   有未 push 内容 → 先停下贴给我.

2. 找到指向 xiaokon-all 的 remote 名 (可能叫 all / xiaokon-all / origin):
   git -C <cwd_repo> remote -v | grep -i xiaokon-all

3. fetch + merge xiaokon-all 的最新到本地:
   git -C <cwd_repo> fetch <xiaokon-all-remote-name>
   git -C <cwd_repo> merge --no-ff <xiaokon-all-remote-name>/main -m "sync from xiaokon-all"
   有冲突 → 停下报告.

4. 验证现在 detect_layout.py 有了:
   ls <cwd_repo>/tools/detect_layout.py
   ls <cwd_repo>/tools/setup_machine.py
   ls <cwd_repo>/tools/build_kb_index.py
   ls <cwd_repo>/tools/safe_push.py
   ls <cwd_repo>/tests/run_all.py
   全有 → 跑场景 0 重新识别架构.
   缺失 → 报告 git log -5 给我.

5. 跑工具自检:
   python <cwd_repo>/tools/detect_layout.py
   python <cwd_repo>/tests/run_all.py
   测试不全绿 → 把 FAIL 的清单贴给我.
```

---

## 场景 A: 新机器首次接入 (从零 setup)

> 用于: 一台从未参与的新电脑, 想加入 AutoForensicAI 协作.

```
你现在要把这台机器接入 AutoForensicAI 多机协作 (v0.5.3+).

# 任务
1. 给这台机器分配一个唯一 MACHINE_ID, 格式 <主机名缩写>_<用途>
   推荐: B_secondary / C_lab1 / D_user1 (主控机已占用 A_main, 不要重复)
2. 把三个仓库 clone 到本地:
   - 框架库 → e:\xiaokon_autoforensicai (或 ~/xiaokon_autoforensicai)
   - 数据库 → e:\autoforensicai_data
   - 全量库 → e:\xiaokon-all
3. 在框架库目录跑 setup_machine.py 完成初始化:
   - 写入 MACHINE_ID 到 ~/AppData/Roaming/autoforensicai/machine.txt
   - git config user.name = "cascade@<MACHINE_ID>"
   - 安装 commit-msg / pre-commit hooks
   - 增量更新 .gitignore
4. 验证 setup 成功:
   - tests/run_all.py 必须 10/10 全绿
   - tools/build_kb_index.py 不报错
5. 输出一个简报: 我的 MACHINE_ID 是什么、装在哪几个路径、第一次跑测试的结果

# 命令模板
git clone https://github.com/HJSSSRX/xiaokon_autoforensicai.git e:\xiaokon_autoforensicai
git clone https://github.com/HJSSSRX/autoforensicai_data.git    e:\autoforensicai_data
git clone https://github.com/HJSSSRX/xiaokon-all.git            e:\xiaokon-all
cd e:\xiaokon_autoforensicai
python tools/setup_machine.py --id <你选的 ID>
python tests/run_all.py

# 强制规则
- MACHINE_ID 必须在 docs/MULTI_MACHINE_CONTRIBUTION.md 看不到的范围内 (避免冲突)
- 不要直接 push 到任何远程, 先做本次 setup, 等待主控指派任务
- 如果 setup 失败, 把完整报错贴给我, 不要自己 force push 或绕过 hook
```

---

## 场景 B: 日常更新 (sync 上游最新)

> 用于: 已经接入的机器, 准备开工前先拉所有最新贡献.

```
请把本机的三个仓库都同步到上游最新, 然后跑测试确认无回归.

# 步骤
1. 框架库: cd <framework_path> && git pull --ff-only origin main
2. 数据库: cd <data_path> && git pull --ff-only origin main
3. 全量库: cd <all_path> && git pull --ff-only origin main
4. 重建本地 INDEX (因为别人可能新增了复盘):
   python <framework_path>/tools/build_kb_index.py --dir <data_path>
5. 跑测试套件: python <framework_path>/tests/run_all.py
6. 看 git log 最近 3 条 commit 都来自哪台机器, 输出报告

# 报告格式
最新 commit:
- framework: <hash> <subject> [machine: ?]
- data:      <hash> <subject> [machine: ?]
- all:       <hash> <subject> [machine: ?]

测试: <PASSED>/<TOTAL>
新增的别机贡献:
- <file>: 来自 [machine: B_xxx], 主题 ...

# 如果 ff-only 拉不下来 (上游不能 fast-forward)
说明本地有 commit 没 push. 不要 merge, 先用 safe_push 把自己的改动 push 上去, 再重新 pull.
```

---

## 场景 C: 提交贡献 (push 自己的工作)

> 用于: 已经做了一些工作 (复盘 / 工具改进 / 文档), 准备提交到三库.

```
请把本机的工作提交到三库. 严格按以下流程, 不要跳步.

# 前置确认
1. 我的 MACHINE_ID 是: <从 ~/.config/autoforensicai/machine.txt 读取>
2. 列出我新增/修改的文件 (git status), 按归属分类:
   - tools/ tests/ docs/ worklog/ → 框架库
   - knowledge/ cases/ → 数据库
   - .gitignore CHANGELOG.md README.md → 框架库
   不允许有 framework 路径以外的 tools/ 或 data 路径以外的 knowledge/, 跨库写入会报错.

# 命名空间硬规则
- 任何复盘文件 (knowledge/retrospectives/*.yaml) 必须带 __<MACHINE_ID> 后缀
  ✓ 20260510_X02_my_finding__B_secondary.yaml
  ✗ 20260510_X02_my_finding.yaml  (会被 hook 拒绝)
- INDEX 文件不要手改, 用 tools/build_kb_index.py 重建

# 提交流程
## 1) 框架库 (如有 tools/tests/docs 改动)
cd <framework_path>
git add tools/ tests/ docs/ worklog/ CHANGELOG.md README.md .gitignore  # 只 add 该归属的
git status  # 确认没有 knowledge/ 或 cases/ 被加进来
git commit -m "feat(xxx): <主题>"  # commit-msg hook 自动加 [machine: <ID>]
git pull --rebase origin main
python tests/run_all.py  # 必须 10/10 全绿
git push origin main

## 2) 数据库 (如有 knowledge/cases 改动)
cd <data_path>
python <framework_path>/tools/build_kb_index.py --dir .  # 自动重建 INDEX
git add -A
git status  # 确认 INDEX 已自动更新
git commit -m "feat(data): <主题>"  # 在 data 仓库不需要 hook, 但建议手动加 [machine: <ID>]
git pull --rebase origin main
git push origin main

## 3) 全量库 (合并 framework + data 到 monorepo)
cd <framework_path>
python tools/sync_to_xiaokon_all.py  # 自动拉两边最新, 合并, commit, push 到 all

# 验证完成
- 框架库 GitHub 显示我的 commit, hash 和本地一致
- 数据库 GitHub 显示我的 commit
- 全量库 GitHub 最新 commit 是 sync(monorepo) ...

# 失败兜底
- 如果 commit-msg hook 拒绝 (machine.txt 不存在): 跑 python tools/setup_machine.py 修复
- 如果 pre-commit hook 拒绝 (改了 INDEX): 跑 python tools/build_kb_index.py 重建后重 add
- 如果 rebase 撞冲突: 不要 force push, 看冲突文件名
  - 同名 .yaml 复盘冲突 → 命名违规, 改成带 __<MACHINE_ID> 后缀重 add
  - 真逻辑冲突 → 手动解 + 跑测试 + git rebase --continue
```

---

## 场景 D: 一键 sync + 提交 (推荐日常使用)

> 用于: 老用户, 信任工具, 一句话搞定.

```
我刚做完一些工作, 帮我提交到三库. 步骤:

1. 在 <framework_path> 跑 python tools/safe_push.py
   工具会: fetch + rebase + 重建 INDEX + 跑测试 + push 框架库
2. 在 <data_path> 跑 git pull --rebase + push (如果有 knowledge/cases 改动)
3. 在 <framework_path> 跑 python tools/sync_to_xiaokon_all.py 同步到全量库

如果任何步骤失败, 立刻停下, 把完整报错贴给我, 不要自己 force push.

我的 MACHINE_ID: <自动从 machine.txt 读>
```

---

## 场景 B-multi: 单仓 + 多 remote 机器的提交流程

> **用于**: detect_layout 显示 `B_monorepo_multi` 的机器 (单一 working tree, 配了 framework/data/all 三个 remote).
>
> **核心规则**: **只推 xiaokon-all**, **绝不直推 framework/data** (会污染那两个仓库).

```
本机 layout = B_monorepo_multi. 这意味着:
- 本地 working tree 是 monorepo (含 knowledge/cases + tools/tests/docs)
- 配了 3 个 remote: framework / data / xiaokon-all (具体名字看 git remote -v)
- 直推 framework remote → 会把 knowledge/cases 注入框架库, 污染
- 直推 data remote      → 会把 tools/tests/docs 注入数据库, 污染
- 只有推 xiaokon-all 是安全的

# 提交流程

1. 跑 detect_layout 确认架构:
   python <cwd_repo>/tools/detect_layout.py
   必须看到 LAYOUT: B_monorepo_multi, 否则停下用别的场景.

2. 跑 setup_machine (首次或换 ID 时):
   python <cwd_repo>/tools/setup_machine.py --id <你的 ID>
   不要用 A_main, 它是主控. 推荐 B_secondary / C_lab1 / D_user1 等.

3. 写新内容:
   - 复盘 → <cwd_repo>/knowledge/retrospectives/<日期>_<编号>__<MACHINE_ID>.yaml
   - 工具改进 → <cwd_repo>/tools/*.py (谨慎, 主控可能也在改)
   - worklog → <cwd_repo>/worklog/<日期>_<主题>__<MACHINE_ID>.md

4. 重建 INDEX (如果改了 retrospectives/):
   python <cwd_repo>/tools/build_kb_index.py --dir <cwd_repo>

5. 跑测试 (必须 10/10 全绿):
   python <cwd_repo>/tests/run_all.py

6. commit (commit-msg hook 自动加 [machine: <ID>]):
   cd <cwd_repo>
   git add -A
   git status     # 确认没有 .db / progress.txt / *.draft.md 这种被加进来
   git commit -m "feat(xxx): <主题>"

7. 推到 xiaokon-all (注意: 本地分支可能是 master, 远程是 main, 要做 mapping):
   找出 xiaokon-all remote 的实际名字 (可能叫 all / xiaokon-all):
   git remote -v | grep xiaokon-all  → 假设是 "xiaokon-all"
   
   推送命令:
   git push <xiaokon-all-remote-name> master:main
   # 如果本地分支已经叫 main: git push <xiaokon-all-remote-name> main
   
   不要执行下面的命令, 它们会污染远程:
   ✗ git push framework master:main   # framework 仓库会混入 knowledge/cases
   ✗ git push data master:main        # data 仓库会混入 tools/tests/docs

8. 让主控 (A_main) 把 xiaokon-all 上的新内容 split 到 framework + data:
   贴一条消息: "我 push 了 commit <hash> 到 xiaokon-all, 包含 X/Y/Z, 请主控 split."
   主控会跑: 
   git -C e:\xiaokon-all pull
   # 然后 cherry-pick 或手动 copy 到 e:\项目\自动化取证 + e:\autoforensicai_data, 再分别 push

# 失败兜底
- detect_layout 输出 layout != B_monorepo_multi → 你不在这个场景, 停下问主控.
- safe_push.py 在你这运行也会自动检测并拒推 framework/data, 这是设计.
- 如果非要用 safe_push.py, 加 --only all 参数: python tools/safe_push.py --only all
```

---

## 场景 E: 应急 — 接手别人未完的工作

> 用于: 主控离开了, 你要看看上一台机器做到哪、补上缺的部分.

```
1. cd <framework_path> && git log --all --oneline -20
   找出最近 commit, 看每条 [machine: ...] 标签来自谁
2. 列出最近 7 天有 commit 的所有 MACHINE_ID, 哪些是我没见过的新机器
3. 看 worklog/ 最新的 .md 文件, 总结:
   - 上一台机器在做什么板块 (computer / mobile / server / network / binary)
   - 是否在题目卡填到一半 (knowledge/problems/<板块>/*.yaml 检查 status 字段)
   - 是否留下 TODO 或 progress.txt
4. 如果有未完成的 problem 卡 (status: in_progress 或缺 our_answer 字段),
   按 v5 prompt 流程接手, 命名复盘时用我自己的 __<我的 MACHINE_ID>.yaml
5. 不要覆盖别人的 __<其他 ID>.yaml 文件, 我们是同题不同视角共存
```

---

## 附录: 各路径占位符对照表

| 占位符 | 默认值 (Windows) | 默认值 (Linux/Mac) |
|---|---|---|
| `<framework_path>` | `e:\xiaokon_autoforensicai` 或 `e:\项目\自动化取证` | `~/xiaokon_autoforensicai` |
| `<data_path>` | `e:\autoforensicai_data` | `~/autoforensicai_data` |
| `<all_path>` | `e:\xiaokon-all` | `~/xiaokon-all` |
| `<MACHINE_ID>` | 从 `%APPDATA%\autoforensicai\machine.txt` 读取 | 从 `~/.config/autoforensicai/machine.txt` 读取 |

---

## 给主控 (A_main) 的批量分配建议

如果有多台机器同时接入, 分配 MACHINE_ID 建议:

| ID | 角色定位 | 主要负责 |
|---|---|---|
| `A_main` | 主控 (本台) | 框架代码 / 全局协调 / curate solved/ |
| `B_secondary` | 第二主力 | 跟主控并行, 算力高的板块 |
| `C_user1` `C_user2` | 用户机 | 单板块深耕, 追加复盘到 retrospectives |
| `lab_NN` | 实验机 / 自动化 | 跑大规模批量任务 |

主控可定期跑:
```bash
# 列出每台机器最近 30 天的贡献
git -C <data_path> log --since="30 days ago" --format="%an" | sort | uniq -c | sort -rn
```
