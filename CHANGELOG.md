# AutoForensicAI 变更日志

> 项目: 自动化电子取证 (5 角色 AI 协作框架)
> 用途: 记录每轮迭代的具体改动, 让用户和未来的 AI 能看到"现在系统是什么 + 这次改了什么"
> 维护规则: 每次改动后**立即**更新本文件, 然后跑自测确保不破坏。

---

## 目录结构 (项目当前状态)

```
e:\项目\自动化取证\
├── CHANGELOG.md                  ← 本文件
├── tools/                        ← 核心工具 (角色启动 + Hub + 协作)
│   ├── collab_hub.py             ← 协作 Hub (HTTP 服务, /findings, /answers, /needs, ...)
│   ├── role_log.py               ← 角色日志库 (log_answer/finding/blocker/need)
│   ├── generate_role_prompts_v5.py  ← v5 角色 prompt 生成器
│   ├── ssh_helper.py             ← SSH 助手 (NEW v0.4) — 仿真服务器/容器直连
│   ├── sim_recon.py              ← 仿真巡检 (NEW v0.4) — 启动后自动 log_finding
│   ├── dashboard.html            ← 实时看板
│   └── ... (历史工具)
├── prompts/                      ← 通用角色 prompt (跨案件)
│   └── roles/                    ← computer/mobile/server/network/binary 等
├── docs/                         ← 设计文档
│   ├── design_huoyan_cli.md             ← 火眼 CLI 化方案
│   ├── design_human_in_the_loop_v2.md   ← HITL v2 (AI 主导版, NEW v0.3)
│   ├── design_simulation_mode.md        ← 仿真模式
│   └── firepower_cli_conditions.md      ← 火眼 CLI 使用条件 (NEW v0.3)
├── tests/                        ← 自测
│   ├── test_collab_hub.py        ← Hub 集成测试
│   ├── test_ssh_helper.py        ← SSH 助手测试 (NEW v0.4)
│   └── ... 
└── knowledge/                    ← 通用知识库 (跨案件)
    └── solved/                    ← 历史解题 (空, 待填充)

e:\ffffff-JIANCAI\2026FIC团体赛\case\
├── role_prompt_*_v5.md           ← 5 角色 v5 prompt (含 HITL v2)
└── shared\
    └── knowledge_base\           ← 案件 KB
        ├── problems\             ← 题目卡 (52 题, 含官方 vs 我们答案)
        ├── techniques\           ← 技巧卡 (11 张)
        └── retrospectives\       ← 复盘 (NEW v0.3)
            └── main_designer\
                └── 2026-05-09_remote_collab_failures.yaml
```

---

## v0.5.2 — 2026-05-09 (12:30) 苍穹 AI 引擎发现 + 用户手册 + 启动协议

### 里程碑

**完整理解了火眼 + 苍穹 整套技术栈, 写完了用户手册和启动协议**.

### 苍穹 AI 引擎发现

`C:\Program Files\Honglian\FirmamentAIEngine\` (14.2 GB) — **火眼自家本地 AI 平台**.

运行中: 8 进程 + 8 端口监听.

**21 个本地 AI 模型** (我们通过火眼 8477 间接调用):

| 类型 | 模型 |
|---|---|
| LLM | qwen3:14b, qwen2.5:32b-instruct-q4_0 |
| Embedding | bge-large-zh-v1.5 |
| OCR | ch-pt-ocr-v4 |
| 取证视觉 | evidence-detection, face-detection, nsfw-classification |
| 通用视觉 | ViT-L-14-336 (CLIP), yolo-v8-base-object |
| 视频 | yolo-v8-traffic-accident, slowfast-r50-detection, Reid-{Pedestrian,Vehicle} |
| 图像增强 | basic-m-x{2,4}-gan, naf-net-{reds,sidd}-width64 |
| 语音 | asr-wss |
| 知识图谱 | relation_cls |

**关键洞察**: 火眼的 `ges_knowledge_qa` 背后跑的是 **qwen3:14b + bge-large-zh** 全本地, 不联网, 取证特化. 比 GPT/Claude 在隐私和取证场景上更合适.

### 火眼 11 个产品全审查

| 产品 | MCP | 我方采用 |
|---|---|---|
| 证据分析 GoldenEyesV4 | ✅ 8477 真 server | ⭐ 主力 |
| 苍穹 AI 引擎 FirmamentAIEngine | 🟡 9120 catalog (内部专用) | ⭐ 已被 8477 间接调 |
| app 分析 APPAnalysis | 🟡 client only (连 IDA/JADX) | binary 人工辅助 |
| 取证桌面 / 数据库 / 火眼仿真 / 视频取证 / 网探勘测 / 网矩 / 网镜 / 雷电系列 | ❌ 无 MCP | 人工 GUI |

### 新增文档

- **`docs/huoyan_mcp_user_manual.md`** — 完整用户手册
  - 软件清单 + 授权状态自检
  - 自动化自检命令
  - 标准比赛开赛流程 (T-30 到 T+30)
  - 13 个 tool 速查表
  - 常见排错 6 项
  - 21 个本地模型附录

### v5 prompt 启动协议升级

每个角色开局必跑**第 0 步: 火眼 MCP 自检**:
```python
hy = HuoyanClient()
probe = hy.probe()
HUOYAN_MCP = probe["ok"]
HUOYAN_CID = ...  # 暴力试 1,2,3 找当前案件
if HUOYAN_MCP:
    # 13 个 tool 可用, 用 ges_knowledge_qa / vector_search / chat_record_clue
else:
    # 走批次任务 (第六节)
```

新增第八节指向用户手册.

### 文件改动

- `tools/generate_role_prompts_v5.py` (启动协议)
- `case/role_prompt_{computer,mobile,server,internet,binary}_v5.md` (重新生成)
- `docs/huoyan_mcp_user_manual.md` (新)

### 测试

- 9/9 测试套件全绿 (PASSED=9 FAILED=0 SKIPPED=0)
- huoyan_adapter 50/50

### 用户答疑 (本轮)

**Q: 各用户怎么知道自己电脑能不能用 MCP?**  
A: 见 `docs/huoyan_mcp_user_manual.md` 第二/三节, 一行命令自检.

**Q: 火眼其他产品有补充价值吗?**  
A: 90% 没有. 已在用的两个 (证据分析 + 苍穹) 已经覆盖核心. app 分析的 MCP 是 client 模式, 给 binary 角色**人工**用 IDA/JADX 时增强分析, 不是给 AI 调.

**Q: 默认分工是?**  
A: 您手动开案件 + 拖检材 + 勾分析 + 等解析; AI 从"解析有部分输出"开始接管 13 个 tool 调用.

---

## v0.5.1 — 2026-05-09 (12:00) 火眼 MCP 实地连通 + Adapter 重写

### 里程碑 🎯

**首次从 AI 端成功调用火眼真实 MCP 服务 + 拿到真实案件数据**.

```
$ python3 tools/huoyan_adapter.py probe
✓ 127.0.0.1:8477 MCP ok: GoldenEyes MCP Server, 13 tools
Session: bf82964b73bd427ab9669c26fff214c6

$ hy.vfs_outline(cid=1, max_depth=1)
/
├── 检材-U盘.E01/
├── 检材-手机.tar/
├── 检材-计算机.E01/
└── 检材-1.E01/
```

### 探测结果

- 真实端口: **8477** (goldeneyes.exe 主进程), 不是 v0.5 假设的 8001
- 协议: **MCP 2024-11-05 streamable-http** (JSON-RPC 2.0 + Mcp-Session-Id header)
- 握手: `initialize` → `notifications/initialized` → `tools/list`/`tools/call`
- 13 个 tool (比假设的 12 多一个 `node_to_path`)
- 所有 tool 需要 `cid` 或 `case_id` (打开的案件 ID)

### 当前用户机火眼产品状态

| 产品 | 运行 | MCP | 端口 |
|---|---|---|---|
| 证据分析 GoldenEyesV4 | ✅ 6 进程 | ✅ 就绪 | 8477 |
| app 分析 AAConsole | ✅ 5 进程 | ❌ 只 /ping | 9112 |
| 火眼仿真 (VMware) | ✅ | N/A | — |
| 其他 8 个 | 未启动 | — | — |

### 改动 (相对 v0.5)

- **重写 `tools/huoyan_adapter.py`**:
  - `HuoyanClient` 类 (取代 `HuoyanAdapter`, 旧名做别名保留)
  - 完整 MCP 握手 (`connect()`: initialize + notifications/initialized)
  - 严格 JSON-RPC 2.0 + 自动 session header 传递
  - `call(tool_name, **params)` 通用入口 + 13 个便利方法
  - `probe()` 扫描 [8477, 8478, 8001, 9112, 8002] 兜底
  - 自动 cid 注入 (cfg.default_cid 机制)
  - None 值自动过滤 (MCP schema 禁 null)

- **重写 `tests/test_huoyan_adapter.py`**: 50/50 项
  - Fake MCP server 完整模拟 initialize / initialized / tools/list/call
  - 验证 session header 传递, default_cid 注入, None 过滤
  - 验证没发 initialized 时 tools/list 会 -32602
  - 避开真火眼 8477 端口干扰

### 下一步

1. 用 adapter 在 v5 prompt 里用真实 tool (知识图谱问答最高价值)
2. 测 chat_record_clue 拿聊天线索 (本次比赛最吃亏的环节)
3. 等您重装火眼/换新版后 probe 机制自动适配

### 用户答疑

**Q: 重装火眼到原目录会不会作废我的工作?**
A: 99% 不会. Adapter 只通过 MCP 协议通信, 不碰火眼内部文件:
- 端口变了 → probe() 自动扫备用端口
- tool 名字变了 → tools/list 动态拿, 不硬编码
- 装在别的目录 → 完全不影响 (代码只用原目录做指引文本)

---

## v0.5 — 2026-05-09 (11:45) 火眼 V4 MCP-Server Adapter

### 重大发现: 不用做 CLI 注入

实地探测 `D:\ffffffff\fireeyes\证据分析\GoldenEyesV4` 发现火眼 V4 **自带标准 MCP-Server**:

```
pyplugin/mcp-server/app/ (FastAPI + MCP)
  router/__init__.py  →  12 个已暴露 tools
  默认端口: 127.0.0.1:8001
  env.example:  GES_URL / GES_TOKEN / LLM / Qdrant / Neo4j
```

火眼 V4 架构已经是 **AI-Ready**: qdrant (向量) + neo4j (图谱) + LLM + MCP.
我们只需要当它的 **HTTP 客户端**, 不需要逆向 CDP / 解包 asar.

### 已暴露的 12 个 MCP tools

- **核心**: `data_analysis`, `ges_data/search` (关键词), `vector/search` (向量),
  `judge/chat_record_clue` (聊天线索), `ges/knowledge_qa` (图谱问答)
- **VFS**: `ls / glob / read / grep / search / fetch_next / outline / node_to_path`
  (把证据文件抽象成虚拟文件系统 — 这是最强的接口!)

### 新增

- **`@e:\项目\自动化取证\tools\huoyan_adapter.py`** — 火眼 HTTP 客户端
  - `HuoyanConfig` 从 env 加载 (HUOYAN_HOST / HUOYAN_PORT / GES_URL / GES_TOKEN)
  - `HuoyanAdapter.probe()` 三步探测: TCP 扫端口 + HTTP /health + 返回就绪状态
  - 13 个方法封装火眼 tools (search / vector_search / knowledge_qa / vfs_* ...)
  - CLI: `probe / search / vector-search / vfs-ls / qa / config`
  - 清晰错误信息: `HuoyanNotRunning` (端口未监听) / `HuoyanHttpError` (5xx)

- **`@e:\项目\自动化取证\tests\test_huoyan_adapter.py`** — 41/41 项
  - 手写 fake mcp-server (无 FastAPI 依赖, 纯 http.server)
  - mock 所有 12 个端点, 验证请求格式 + 响应解析
  - probe 未启动 / 启动两种场景
  - 5xx / ConnectionRefused 错误处理

### 修复

- `_request()` HTTPError 必须先于 URLError catch (HTTPError 是子类)

### 用户机信息 (来自用户)

- **安装目录**: `D:\ffffffff\fireeyes\` (11 个子软件: 证据分析/火眼仿真/雷电云快取等)
- **主程序**: `D:\ffffffff\fireeyes\证据分析\GoldenEyesV4\GoldenEyesV4.exe` (118MB, 2025-07-29)
- **授权**: `myirce123456@126.com` / `wuyi@2026` (网络授权)
- **证据存放**: `E:\fffff-TEMP`
- **仿真 VM**: `D:\VM-TEMP` (VMware 已装)

### 下一步 (待用户启动)

1. 用户侧: 启动 GoldenEyesV4.exe → 登录 → 开案件 → 手动起 mcp-server
2. AI 侧: `python3 tools/huoyan_adapter.py probe` 自检
3. 连通后: 集成到 role prompt v5 的 tool chain 里

### 测试结果

```
9 个测试套件全绿: PASSED=9 FAILED=0 SKIPPED=0
  test_huoyan_adapter.py  41/41
```

---

## v0.4.1 — 2026-05-09 (11:25) Dashboard 心跳列 + KB 检索 smoke test

### 改动摘要

接续 v0.4, 把心跳数据从后端打通到前端 dashboard, 并补 v5 prompt 强依赖工具的 smoke test。

### 新增

- **`@e:\项目\自动化取证\tools\dashboard.html`** — 心跳列集成
  - `renderRoles()` 接受 `heartbeat` 参数, 角色卡左上角加 🟢/🟡/🔴 圆点
  - 阈值: <60s = 🟢 alive, <300s = 🟡 stale, ≥300s = 🔴 offline
  - Header 加 `heartbeat-badge` 全局徽标: "🟢 5/5 角色活跃" / "🔴 2 角色掉线"
  - `ROLE_NAMES` 补 `internet_analyst` / `main_designer`

- **`@e:\项目\自动化取证\tests\test_dashboard_heartbeat.py`** — 35/35 项
  - 静态分析: HTML 元素 + JS 逻辑
  - 端到端: 启 hub + POST 心跳 + 验证 GET 返回结构 + dashboard HTML

- **`@e:\项目\自动化取证\tests\test_fic_kb_search.py`** — 31/31 项
  - v5 prompt 强依赖, 测试 5 子命令 (keywords/question/category/result/tech)
  - 验证 `--category {role}` 5 个分类全过, `--result incorrect` 输出 12 个错答

### 修复

- `dashboard.html` `/heartbeat` fetch 用 `.catch(() => ({}))` 兜底, 老 hub 不会让前端报错

### 测试结果 (本轮)

```
test_collab_hub.py             ✓ Hub 老端点
test_hub_v04_endpoints.py      ✓ Hub v0.4 新端点
test_dashboard_heartbeat.py    35/35 ✓ Dashboard 心跳 (静态 + e2e)
test_ssh_helper.py             ✓ SSH 助手
test_sim_recon.py              ✓ 仿真巡检
test_fic_kb_search.py          31/31 ✓ 知识库检索
test_parse_yaml.py             ✓ YAML 格式回归
test_prompt_gen.py             ✓ Prompt 生成

汇总: PASSED=8  FAILED=0  SKIPPED=0
```

---

## v0.4 — 2026-05-09 (10:57+) ssh_helper + sim_recon + Hub 探活/锁 + 测试机制

### 改动摘要

承接 v0.3 (HITL v2 设计), 这一轮把**设计变成代码**, 同时建立测试机制和变更日志。

### 新增

- **`@e:\项目\自动化取证\tools\ssh_helper.py`** — SSH 助手
  - 双路实现: `paramiko` (优选, 支持密码) + 标准库 `subprocess+ssh.exe` (零依赖, 仅密钥)
  - 方法: `ForensicSSH.run() / lxc_attach() / mysql() / tidb()`
  - 配置: `~/.forensic_ssh.yaml` 多 host 切换
  - 用途: server_analyst / internet_analyst 直连仿真起的虚拟机/容器

- **`@e:\项目\自动化取证\tools\sim_recon.py`** — 仿真启动后自动巡检
  - 用 `ssh_helper` 一键查 OS / 容器列表 / 端口 / Web 站点 / DB
  - 结果自动 log_finding 到 hub, 让 5 角色都看见环境状态
  - 跨 server / TiDB / nginx / maccms 一站式

- **Hub `POST /heartbeat`** — 角色探活 (修复 REMOTE-FAIL-06 静默失败)
  - 角色每 30 分钟 POST `/heartbeat`, hub 记录最后心跳时间
  - `GET /heartbeat` 返回所有角色的最近心跳, main_designer 看 dashboard 即知谁掉线

- **Hub `POST /answers/{cat}/{qid}/lock`** — 答案锁 (修复 REMOTE-FAIL-09 并发覆盖)
  - 角色改答案前必须先 lock, 锁定时间 5 分钟
  - 已锁的答案别的角色 POST 会被拒绝 (409)
  - `unlock` 显式释放, 5 分钟自动过期

- **`@e:\项目\自动化取证\tests\test_ssh_helper.py`** — SSH 助手单测 (mock subprocess)
- **`@e:\项目\自动化取证\tests\test_hub_v04_endpoints.py`** — /needs + /heartbeat + /lock 集成测试

- **`@e:\项目\自动化取证\CHANGELOG.md`** — 本文件 (变更日志)

### 测试结果 (本轮)

**全部 6 个测试套件通过, 132+ 项断言, 0 失败**:

```
test_collab_hub.py        25/25  ✓ Hub 老端点 (findings/answers/questions/session/files)
test_hub_v04_endpoints.py 29/29  ✓ Hub v0.4 (needs/heartbeat/answer-lock/confidence-5级)
test_ssh_helper.py        37/37  ✓ SSH 助手 (init/run/lxc-attach/mysql/quote/timeout)
test_sim_recon.py         41/41  ✓ 仿真巡检 (server/maccms/tidb/error-handling)
test_parse_yaml.py            ✓ YAML 格式回归 (老测试)
test_prompt_gen.py            ✓ Prompt 生成 (老测试)

汇总: PASSED=6  FAILED=0  SKIPPED=0
```

一键再跑: `python3 tests/run_all.py`

### 已知限制

- ssh_helper 默认 auto: 有密码 + paramiko = paramiko, 否则 ssh.exe 子进程 (要求密钥)
- 当前用户机 `paramiko` 未装, 走 subprocess 路径 (用密钥即可)
- `/heartbeat` 只记录 + 暴露状态, 不主动报警 (报警逻辑在 dashboard 端实现, 待加)
- 答案锁基于 yaml 文件持久化, hub 重启锁会保留 (5 分钟自动过期)
- `sim_recon` 测试用 mock, 真实仿真环境的连通性测试需要现场验证

---

## v0.3 — 2026-05-09 (10:45) 远程协作复盘 + HITL v2 + 火眼 CLI 条件

### 触发

用户痛批: "你的人机协作是什么规则? 不会又像远程协作时一样弄巧成拙吧? 永远记住, 设计你的用户为傻瓜, 保证效率优先, AI 不能让位于人。"

自检发现: `case/shared/knowledge_base/retrospectives/` 是**空目录**, 我口头说"吸取教训"但**没沉淀**。

### 改动摘要

**承认错误 + 沉淀教训 + 反转 HITL 设计**。

### 新增

- **`@e:\ffffff-JIANCAI\2026FIC团体赛\case\shared\knowledge_base\retrospectives\main_designer\2026-05-09_remote_collab_failures.yaml`**
  - 10 个具体翻车事件 (REMOTE-FAIL-01 ~ 10)
  - 5 条根因 (被动设计 / 指令膨胀 / 沉默失败 / 创造性让位 / 格式自由)
  - HITL v2 5 条铁律 (从远程协作教训反推)
  - 给下场比赛的 commitment

- **`@e:\项目\自动化取证\docs\design_human_in_the_loop_v2.md`** (重写 v1)
  - 反转 v1 ping-pong 节奏
  - 5 铁律: 批次任务 / 指令式 / AI验证 / AI兜底 / 零术语合约
  - 3 不让位禁令: 不问选择 / 不要确认 / 不接模糊
  - 标准批次模板 + 5 角色具体批次任务

- **`@e:\项目\自动化取证\docs\firepower_cli_conditions.md`** — 火眼 CLI 使用条件
  - 法律授权 + 加密狗 + 首次登录 + --remote-debugging-port
  - 5 个火眼产品的可行性
  - 4 种备选方案 (Web Lab / pywinauto / dissect.target / docker)
  - 推荐策略: 60% dissect.target + 30% SSH + 10% 火眼

### 修改

- **`@e:\项目\自动化取证\tools\generate_role_prompts_v5.py`**
  - 第六节 v1 → v2 (AI 主导版)
  - 5 个角色 `human_collab_examples` 从单行任务改成批次模板
  - server 批次模板"一次 ssh heredoc 7 个查询", 一次性覆盖 S-Q5/Q8/Q15/Q10/Q12/Q16/Q17

### 重新生成

- 5 份 v5 角色 prompt (`role_prompt_{computer,mobile,server,internet,binary}_v5.md`)

---

## v0.2 — 2026-05-09 (10:25) 3 个修复 + 3 份设计文档

### 触发

用户问: "复打 2026FIC 能保证全解吗? 下场比赛能不再犯老错吗?"

我承认 5 个根因里只修了 1.5 个, 用户要求"先修"。

### 新增 (修复 #1: 跨检材求助队列)

- **Hub `GET/POST /needs`** — 跨检材求助 (替代部分 log_blocker)
- **Hub `POST /needs/{id}/{claim,fulfill,abandon}`** — 状态流转
- **Hub `POST /log` 加 `kind=need` 路由**
- **`role_log.py` 新 API**: `log_need / claim_need / fulfill_need / list_open_needs`

### 修改 (修复 #4: confidence 5 级枚举)

- 5 级: `platform_confirmed > self_verified_db > cross_source_high > single_source_high > gui_observed > placeholder`
- 老 `high/medium/low` 自动映射 (high→single_source_high, medium→gui_observed, low→placeholder)
- 未知值 → `placeholder` (避免误评高)
- 旧字段保留在 `confidence_raw` 用于审计

### 新增 (修复 #3: v5 角色 prompt)

- **`@e:\项目\自动化取证\tools\generate_role_prompts_v5.py`** — 5 角色统一生成器
- 5 份 v5 prompt (computer/mobile/server/internet/binary)
- 强制启动读 KB + 回答开题 4 问题 + log_need 跨检材协作 + 中文题精读字典 + 多选穷举模板 + 平台格式潜规则 + 火眼 CLI 模式 + (旧) HITL 模式

### 新增 (3 份设计文档)

- **`@e:\项目\自动化取证\docs\design_huoyan_cli.md`** — 火眼 CLI 化 (基于 OpenCLI)
- **`@e:\项目\自动化取证\docs\design_human_in_the_loop.md`** — HITL v1 (后被 v2 反转)
- **`@e:\项目\自动化取证\docs\design_simulation_mode.md`** — 仿真环境 4 模式

### ⚠ 缺陷

- HITL v1 设计是 "AI 让位" 的 ping-pong 模式, 用户 v0.3 痛批后反转
- 没建 CHANGELOG (v0.4 补)
- 没自测 (v0.4 补)

---

## v0.1 — 2026-05-08 比赛收尾

### 状态

- 完成 2026FIC 团体赛 56% 命中率
- binary 100% / mobile 94% / server 65% / internet 33% / computer 40%
- 建立 KB 雏形: 11 张技巧卡 + 52 题题目卡

### 经验 (后被 v0.3 沉淀到 retrospectives/)

- 远程 AI 协作 10 个具体翻车 (静默失败 / 并发覆盖 / 创造性让位 / ...)
- 跨检材联动机制完全缺失
- 行业知识缺口 (maccms / nginx / lxc)
- 答题策略偏弱
- 信心校准过度乐观
- main_designer 中后期才介入

---

## 维护规则

1. **每次改动**, 立即更新本文件
2. 改动**先有自测**再交付 (v0.3 之前没做, 是教训)
3. 写**版本号 + 时间戳 + 触发原因 + 新增 + 修改 + 测试结果 + 已知限制**
4. 用 `@e:\path\file.md:行号` 格式引用文件 (Cascade 友好)
5. 历史版本**只新增不删除**, 删除用 strikethrough
