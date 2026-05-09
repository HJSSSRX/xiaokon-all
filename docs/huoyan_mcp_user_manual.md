# 火眼 MCP 用户手册 — 比赛开始前必读

> **版本**: v0.5.1 (2026-05-09 实地验证)  
> **适用**: 比赛/演练前 30 分钟, 在比赛机/参赛队员机上配置  
> **目标**: AI 角色启动时自动连上火眼, 调用 13 个 tool 高效挖证据

---

## 一、为什么需要这一步

我们的 AI 取证流水线 (5 个角色) **可以分两种工作模式**:

| 模式 | 描述 | 比赛速度 |
|---|---|---|
| **🟢 MCP 模式** (有火眼) | AI 直接通过 MCP 调火眼 13 个 tool, 秒级出结果 | **快 5-10 倍** |
| 🟡 人工模式 (无火眼) | AI 给"批次任务", 人类手动操作火眼 GUI 把产物发给 AI | 慢, 但能跑 |

**有火眼时, 务必让 AI 用 MCP 模式**. 比赛 4 小时, 这步差距决定胜负。

---

## 二、火眼软件状态自检 (开始比赛前 5 分钟)

### 2.1 必装清单 (主力)

| 软件 | 默认路径 | 当前已知端口 | 必须? |
|---|---|---|---|
| **证据分析 GoldenEyesV4** | `D:\ffffffff\fireeyes\证据分析\GoldenEyesV4\` | 8477 | ⭐ **必装必登** |
| **苍穹 AI 引擎 FirmamentAIEngine** | `C:\Program Files\Honglian\FirmamentAIEngine\` | 9120 (catalog), 内部 | ⭐ **必装必跑** (火眼后台调它做问答/向量/OCR/图像) |

### 2.2 选装清单 (按板块)

| 软件 | 用途 | 哪个角色用 |
|---|---|---|
| **app 分析 APPAnalysis** | APK 反编译, 配 IDA/JADX MCP | binary, mobile (人工) |
| **火眼仿真** (VMware) | Linux 服务器仿真起 lxc-attach | server (人工) |
| **取证桌面** | 检材中心管理 | 任何角色 (GUI) |
| **数据库** | SQLite 损坏修复 | server (备用) |
| **视频取证** | 视频证据分析 (内部用苍穹的 yolo/face-detect) | 跨板块 |
| **网探勘测 / 网矩 / 网镜** | 网络流量, 备用 | internet (备用) |
| **雷电系列 (云快取/手机快取)** | 手机数据获取 | mobile (人工) |

> **📌 当前我方实际只硬依赖**: 证据分析 + 苍穹. 其他都是辅助.

### 2.3 授权状态自检

火眼系列**都需要绑定账号授权**才能运行 (本机已有授权账号):
- 账号: `myirce123456@126.com`
- 密码: `wuyi@2026`

**如果换机**, 先确认证据分析 GUI 能打开案件. 否则后面 MCP 也连不上。

---

## 三、自动化自检命令

### 3.1 一行命令检测整套是否就绪

```powershell
python3 e:\项目\自动化取证\tools\huoyan_adapter.py probe
```

**预期输出 (就绪)**:
```
Huoyan adapter v0.5 (MCP streamable-http)
候选端口: [8477, 8478, 8001, 9112, 8002]

  [✓] 127.0.0.1:8477 /ping ok
  [✓] 127.0.0.1:8477 MCP ok: GoldenEyes MCP Server, 13 tools

✓ 火眼 MCP 已就绪
  服务器: GoldenEyes MCP Server
  端口:   127.0.0.1:8477
  Session: <随机>

  13 个 tool 可用:
    · data_analysis        required=['file_path', 'data_cmd']
    · ges_data_search      required=['case_id']
    · vector_search        required=['query', 'cid']
    · chat_record_clue     required=['case_id', 'analysis_focus']
    · ges_knowledge_qa     required=['case_id', 'question']
    · ls / glob / read / grep / search / outline / fetch_next / node_to_path
```

**未就绪输出**:
```
✗ 火眼未就绪

火眼 MCP 未就绪. 检查:
  1. 启动 GoldenEyesV4.exe 并登录
  2. 打开 (或创建) 一个案件 (位于 E:\fffff-TEMP 下)
  3. 火眼主界面等案件解析完
  4. 确认 goldeneyes.exe 进程在 127.0.0.1:8477 监听
```

### 3.2 苍穹 AI 引擎自检

```powershell
python3 -c "import urllib.request, json; r=urllib.request.urlopen('http://127.0.0.1:9120/v1/models', timeout=3); print(f'苍穹模型数: {len(json.loads(r.read())[\"data\"])}')"
```

**预期**: `苍穹模型数: 21` (含 qwen3:14b / qwen2.5:32b 等)

如果连不上 9120, 启动 `C:\Program Files\Honglian\FirmamentAIEngine\FirmamentAIEngine.exe`.

---

## 四、标准比赛开赛流程 (人工)

```
T-30 分钟: 装好火眼证据分析 + 苍穹 AI 引擎, 登录账号
T-20 分钟: 启动 FirmamentAIEngine.exe, 等到任务栏托盘出现苍穹图标
T-15 分钟: 启动 GoldenEyesV4.exe, 登录账号
T-10 分钟: 创建案件 (或打开已有), 命名规范如 "2026FIC_团体赛"
T-08 分钟: 拖检材文件 (.E01 / .tar / .img) 进案件
          → 注意: 如果检材在 E:\fffff-TEMP, 直接选
T-07 分钟: 勾选要跑的分析模块
          建议: 默认全勾 (反正后台跑, 不影响 AI 调用读已解析的部分)
          关键模块: 文件解析 / 浏览器历史 / IM聊天 / 镜像挂载 / 注册表
T-05 分钟: 点"开始解析", 让火眼后台跑解析
          → 同时 AI 已经可以做"先验性"工作 (读 KB / 读题目)
T+00:    比赛开始
T+10:    火眼后台解析完一部分, AI 开始 probe + 调 tool
T+30:    火眼基本解析完, AI 全速挖题
```

**关键规则**:
1. **不要等火眼解析 100% 完才让 AI 开始** — AI 可以做大量先验工作 (读知识库 / 题目 / 跨检材关联思考)
2. **prober 失败不慌** — adapter 自动降级到"批次任务"模式, 人工配合
3. **解析中 ges_data_search 部分结果可能不全** — 30 分钟后再确认一次

---

## 五、AI 角色启动时的标准协议

### 5.1 启动第一步 (强制)

每个角色 (computer/mobile/server/internet/binary) 进入会话后**第一段**就跑:

```python
import sys
sys.path.insert(0, r"e:\项目\自动化取证\tools")
from huoyan_adapter import HuoyanClient

hy = HuoyanClient()
probe = hy.probe(verbose=True)

if probe["ok"]:
    HUOYAN_MCP = True
    print(f"✓ 火眼 MCP 就绪, {len(probe['tools'])} 个 tool 可用")
    # 后续直接调 hy.ges_data_search() / hy.vfs_outline() / 等
else:
    HUOYAN_MCP = False
    print(f"× 火眼未就绪: {probe.get('hint', '')}")
    # 走批次任务模式 (见 v5 prompt 第六节)
```

### 5.2 找到当前案件 ID (cid)

火眼 MCP 没暴露 list_cases tool, 用以下办法之一拿 `cid`:

```python
# 方案 A: 用户/主控直接告诉你
HUOYAN_CID = 1   # 主控指定

# 方案 B: 从环境变量读 (推荐, 主控启动时设)
import os
HUOYAN_CID = int(os.environ.get("HUOYAN_CID", "1"))

# 方案 C: 暴力试 (如果就一个案件, cid 大概率是 1)
for cid in [1, 2, 3]:
    try:
        r = hy.vfs_outline(cid=cid, max_depth=1)
        if not r.get("isError"):
            HUOYAN_CID = cid
            break
    except Exception:
        continue
```

### 5.3 第一次调用建议

进入工作前先 `vfs_outline` 看一眼检材结构, 知道**有哪些证据可挖**:

```python
r = hy.vfs_outline(cid=HUOYAN_CID, max_depth=2)
print(r["content"][0]["text"])
```

**实战例子** (本机当前案件):
```
/
├── 检材-U盘.E01/
├── 检材-手机.tar/
├── 检材-计算机.E01/
└── 检材-1.E01/
```

---

## 六、13 个 tool 速查表

### 6.1 智能问答类 (✨ 最高 ROI)

```python
hy.ges_knowledge_qa(case_id=1, question="李安弘有哪些手机号")
hy.ges_knowledge_qa(case_id=1, question="所有出现过的 Telegram 群")
# 背后由苍穹 qwen3:14b + 知识图谱驱动, 比 grep 强
```

### 6.2 关键词检索

```python
hy.ges_data_search(case_id=1, keyword="VeraCrypt")
hy.ges_data_search(case_id=1, keyword="9ed2", start_time="2026-04-01")
```

### 6.3 向量语义搜

```python
hy.vector_search(query="联系卖家的电话号码", cid=1)
hy.vector_search(query="无人机航拍记录", cid=1, max_results=20)
# 背后由 bge-large-zh-v1.5 + qdrant 驱动
```

### 6.4 聊天线索 (本届比赛痛点)

```python
hy.chat_record_clue(
    case_id=1,
    analysis_focus="涉案账户和金额",
    target_account_name="李安弘",
    start_time="2026-04-01",
)
```

### 6.5 VFS (虚拟文件系统)

```python
hy.vfs_outline(cid=1, max_depth=3)              # 看树
hy.vfs_ls(cid=1, path="/检材-计算机.E01")        # 列目录
hy.vfs_glob(cid=1, pattern="**/*.enc")          # 找加密文件
hy.vfs_read(cid=1, path="/检材-计算机.E01/Users/.../Chrome/History")
hy.vfs_grep(cid=1, pattern=r"\d{11}", path="/", recursive=True)
hy.vfs_search(cid=1, query="保险柜", search_mode="hybrid")
```

### 6.6 数据分析 (高级)

```python
hy.data_analysis(
    file_path="/检材-计算机.E01/.../db.sqlite",
    data_cmd="SELECT * FROM users LIMIT 10",
)
```

### 6.7 fetch_next (分页)

如果 search/grep 返回 `handle_id`, 用它翻页:

```python
r = hy.vfs_grep(cid=1, pattern="x", path="/", limit=50)
handle = r.get("handle_id")
if handle:
    page2 = hy.vfs_fetch_next(cid=1, handle_id=handle, page=2)
```

### 6.8 node_to_path (ID 反查)

KB 里有 nid 时, 用它拿完整路径:

```python
hy.vfs_node_to_path(cid=1, nid=12345)
```

---

## 七、常见问题排错

### Q1. probe 找不到 8477 端口

**检查清单**:
1. GoldenEyesV4 是否启动? `Get-Process goldeneyes`
2. 是否登录了? GUI 主界面右上角应显示账号
3. 是否打开了案件? 没打开案件 MCP 也不响应
4. 防火墙阻止? `netstat -ano | findstr 8477`

### Q2. tools/list 返回 -32602 Invalid request parameters

**原因**: 没发 `notifications/initialized`. adapter 已自动处理, 不会发生. 如果发生, 重新 `hy.connect()`.

### Q3. cid 不对 (拿到 isError: true)

**解决**: 用 6.1 节的方案 C 暴力试 cid=1,2,3 直到不报错.

### Q4. ges_knowledge_qa 卡住 30 秒+

**正常**. 苍穹 qwen3:14b 推理需要时间, 第一次调用尤其慢 (要加载模型).
- 第一次: 10-30 秒
- 之后: 3-8 秒

如果超过 60 秒, 检查苍穹是否在跑 (`Get-Process FirmamentAIEngine`).

### Q5. 苍穹 9120 连不上

**启动**: `C:\Program Files\Honglian\FirmamentAIEngine\FirmamentAIEngine.exe`

**验证**:
```powershell
python3 -c "import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:9120/ping', timeout=3).read())"
```

### Q6. 火眼版本升级后端口/tool 名变了

**好消息**: adapter 设计上防了:
- 端口扫描: `CANDIDATE_PORTS = [8477, 8478, 8001, 9112, 8002]`
- tool 名动态从 `tools/list` 拿
- 大部分情况自动适配

如果**真**变了, 改 `tools/huoyan_adapter.py` 顶部 `CANDIDATE_PORTS`. 一行的事.

---

## 八、附录: 苍穹 AI 引擎的 21 个本地模型

火眼内部自动调用, 我们不直接 call, 但**用 ges_knowledge_qa / vector_search / 视频取证产品时背后用的就是这些**:

| 模型 | 用途 | 调用方 |
|---|---|---|
| `qwen3:14b` | 中文 LLM 14B | `ges_knowledge_qa` |
| `qwen2.5:32b-instruct-q4_0` | 中文 LLM 32B (大模型) | 复杂问答 |
| `bge-large-zh-v1.5` | 中文 embedding | `vector_search` |
| `ch-pt-ocr-v4` | 中文 OCR | 截图/扫描件取证 |
| `evidence-detection` | **检材图片检测** | 火眼图片识别 |
| `face-detection` | 人脸检测 | 视频/图片取证 |
| `nsfw-classification` | 敏感图片识别 | 视频/图片取证 |
| `ViT-L-14-336` | CLIP 通用视觉 | 图像分类 |
| `Reid-Pedestrian` | 行人重识别 | 视频跟踪 |
| `Reid-Vehicle` | 车辆重识别 | 视频跟踪 |
| `yolo-v8-base-object` | 通用物体检测 | 视频取证 |
| `yolo-v8-traffic-accident` | 交通事故检测 | 视频取证 |
| `slowfast-r50-detection` | 行为检测 | 视频取证 |
| `relation_cls` | 实体关系分析 | 知识图谱 |
| `asr-wss` | 语音转文字 | 音频证据 |
| `base-classification[-v2]` | 基础图片分类 | 图像取证 |
| `basic-m-x{2,4}-gan` | 图像超分 | 模糊图增强 |
| `naf-net-reds-width64` | 去运动模糊 | 监控视频 |
| `naf-net-sidd-width64` | 去噪 | 模糊图增强 |

**关键洞察**: 全本地 + 全免费 + 不联网, 比走 GPT/Claude 更适合取证 (隐私 + 取证特化).

---

## 九、版本历史

- **v0.5.1** (2026-05-09): 实地验证 8477, 重写为 MCP streamable-http 客户端, 50/50 测试
- **v0.5** (2026-05-09): 假设 8001 端口的初版 (已废弃)

下一版预计:
- **v0.6**: 加 chat_record_clue / data_analysis 实战封装
- **v0.7**: 5 个角色 prompt 集成 probe 启动协议
