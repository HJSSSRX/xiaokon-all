# 火眼 CLI 化设计 — 基于 OpenCLI

> **目标**: 让 AI agent 能直接 CLI 调用火眼 (FireEye Forensics) 全系列, 不再依赖人类点击 GUI。
> **可行性**: ⭐⭐⭐⭐ (基于 OpenCLI 的 Electron+CDP 路径, 比纯 GUI 自动化稳定)
> **预期收益**: 解题速度提升 3-5 倍, 错误率降低, 可在远程机/无人值守环境跑

---

## 一、火眼是什么类型的应用?

| 火眼产品 | 技术栈 | CLI 化路径 |
|---|---|---|
| **火眼仿真** (Volatility 仿真) | C++ Native + Qt? | 较难, 需要逆向接口 |
| **火眼证据分析** (取证分析师) | **Electron + Chromium** | ✅ OpenCLI 适配器 (主推) |
| **火眼移动取证** | Electron + Native 解析器 | ✅ OpenCLI 适配器 |
| **火眼服务器仿真** (lxc 包装) | 后端 Linux + Web UI | ✅ 直接走 SSH/HTTP API |
| **火眼破解大师** (密码暴破) | C++ Native + GPU | 较难, 需要 IPC hook |

**结论**: **火眼证据分析 / 移动取证 / 服务器仿真** 这 3 个最常用的, 都能 CLI 化。

---

## 二、技术路径: OpenCLI Electron Adapter

### 2.1 OpenCLI 给出的能力

```bash
# 安装 OpenCLI
npm install -g opencli

# 给火眼写 adapter
opencli browser init huoyan/forensics       # 初始化 adapter 模板
opencli browser analyze "火眼证据分析的 file://...index.html"  # 探测 UI 结构
# 编辑 ~/.opencli/sites/huoyan/forensics/adapter.ts 实现具体命令
opencli browser verify huoyan/forensics      # 验证 adapter

# 之后就能这样调用:
opencli huoyan list-cases
opencli huoyan open-case "D:\\2026FIC.fyt"
opencli huoyan list-files --case <id> --partition C --path "/Users/李安弘"
opencli huoyan extract --case <id> --src "C:/secret.txt" --dst "D:/out/"
```

### 2.2 火眼 Electron 内部 (推测)

```
火眼证据分析.exe (Electron 主进程)
├── resources/app/                  # 实际逻辑代码 (asar 打包)
│   ├── main.js                      # Electron main
│   ├── preload.js                   # IPC 桥
│   └── renderer/                    # Vue/React UI
└── 解析后端 (C++ DLL)
    ├── ewf_parser.dll               # E01 解析
    ├── reg_parser.dll               # 注册表解析
    └── ...
```

**两个切入点**:
- **A 路径 (CDP)**: Chromium DevTools Protocol, OpenCLI 默认走这条
  - 启动火眼时加 `--remote-debugging-port=9222`
  - OpenCLI 通过 9222 端口控制渲染进程
  - 能模拟点击/读取 DOM/截图
- **B 路径 (直接调 backend)**: 找到火眼调用 C++ DLL 的接口, 直接调
  - 需要 IDA 逆向, 但稳定性高

**推荐**: **先 A 后 B**, A 路径 80% 场景够用。

---

## 三、最小可用 (MVP) 适配器命令

### 3.1 MUST HAVE (10 个核心命令, 覆盖 90% 用例)

```bash
# 案件管理
opencli huoyan list-cases                       # 列所有案件
opencli huoyan open-case <path>                 # 打开 .fyt 文件
opencli huoyan close-case <id>                  # 关闭

# 检材管理
opencli huoyan add-evidence --case <id> --path <e01>     # 添加 E01
opencli huoyan list-evidence --case <id>                  # 列检材

# 文件浏览
opencli huoyan ls --case <id> --partition C --path "/Users"   # 列目录
opencli huoyan extract --case <id> --src "/path/file" --dst <local>   # 提取文件
opencli huoyan info --case <id> --src "/path/file"            # 文件元数据

# 全文搜索 (火眼最强项)
opencli huoyan grep --case <id> --keyword "推广设计图"          # 全盘关键词搜索
opencli huoyan grep --case <id> --keyword "VeraCrypt" --path "/Users/李安弘"

# 注册表/事件日志专项
opencli huoyan reg-query --case <id> --hive SOFTWARE --key "Microsoft\\Windows NT\\CurrentVersion"
opencli huoyan evtx --case <id> --filter "EventID=4624"
```

### 3.2 SHOULD HAVE (高级)

```bash
# 自动解密 (火眼内建的 VeraCrypt/BitLocker 解密)
opencli huoyan decrypt --case <id> --vol <vol_id> --type veracrypt --password <pwd>

# 时间线
opencli huoyan timeline --case <id> --start 2026-04-01 --end 2026-04-30 --output csv

# 应用解析 (移动取证)
opencli huoyan parse-app --case <id> --app wechat       # 解析 IM 应用
opencli huoyan parse-app --case <id> --app dji-fly      # 解析 DJI

# 仿真启动 (服务器取证)
opencli huoyan simulate --case <id> --evidence <id>     # 仿真启动 server
                                                          # 返回 SSH 端口
```

---

## 四、实现方式对比

| 方案 | 实现量 | 稳定性 | 维护成本 | 推荐度 |
|---|---|---|---|---|
| **A. OpenCLI + CDP** | 中 (~500 行 TS) | 中 (UI 改了要更新 selector) | 中 | ⭐⭐⭐⭐ 主推 |
| **B. 直接调 DLL** | 大 (~2000 行 + 逆向) | 高 (接口稳定) | 低 | ⭐⭐⭐ 备用 |
| **C. PyAutoGUI 截图识别** | 小 (~200 行) | 低 (分辨率敏感) | 高 | ⭐ 不推荐 |
| **D. Win32 API 控件操作** | 中 (~300 行) | 中 | 中 | ⭐⭐ 备用 |

**最终选择: A (OpenCLI + CDP) + 部分 B (关键命令直接调)**

---

## 五、与 collab_hub 的集成

火眼 CLI 调用结果通过 hub `/findings` 自动入库, 让其他角色看见:

```python
# 角色 prompt 里写
import subprocess, json

def huoyan_grep(keyword: str, case_id: str = "default"):
    """火眼全盘搜 + 自动 log_finding"""
    result = subprocess.run(
        ["opencli", "huoyan", "grep", "--case", case_id, "--keyword", keyword, "--json"],
        capture_output=True, text=True, encoding="utf-8",
    )
    hits = json.loads(result.stdout)
    
    # 自动 log_finding 高价值命中
    if hits:
        log_finding(
            f"火眼搜 '{keyword}' 命中 {len(hits)} 条",
            detail="\n".join(f"{h['path']}: {h['preview']}" for h in hits[:10]),
            kind="lead",
        )
    return hits

# 用法
hits = huoyan_grep("推广设计图")
# 自动 hub 上多了一条 finding, 其他角色能看到
```

---

## 六、分阶段实施

### 阶段 1 (1-2 周): MVP 适配器

- [ ] 安装 OpenCLI + adapter author skill
- [ ] 启动火眼 with `--remote-debugging-port=9222`
- [ ] 写 list-cases / open-case / ls / extract / grep 5 个命令
- [ ] 在 case/shared/knowledge_base/techniques/ 建 `huoyan_cli_basic.yaml`

### 阶段 2 (1 周): 集成到 v5 角色 prompt

- [ ] 修改 v5 prompt 第五节, 把假代码改成真命令
- [ ] 写 `huoyan_helper.py` 库 (像 role_log 一样, AI 直接调函数)
- [ ] 测试: server_analyst 用 huoyan grep 找配置文件

### 阶段 3 (2-4 周): 高级功能

- [ ] 注册表查询 / 事件日志过滤
- [ ] 应用解析 (parse-app)
- [ ] 移动取证适配器
- [ ] 仿真启动适配器

### 阶段 4 (持续): 知识库联动

- [ ] 每个 huoyan 命令的常见用例写到 KB
- [ ] 失败模式 (找不到/慢/卡死) 写到 KB
- [ ] 把火眼 GUI 操作 → CLI 命令的映射做成 cheatsheet

---

## 七、备选: 如果 OpenCLI 在火眼上 CDP 不工作

火眼可能没启用 remote debugging, 或 asar 加密了。备选:

### B 路径: PyMemo + Win32

```python
# 用 pywinauto (Win32 控件树) 操作
from pywinauto import Application

app = Application(backend="uia").connect(title_re=".*火眼.*")
window = app.window(title_re=".*火眼.*")

# 点开案件
window.child_window(title="文件浏览", control_type="Button").click()
# 输入路径
window.child_window(auto_id="addressBar").set_text(r"C:\Users\李安弘")
```

不如 OpenCLI 优雅, 但能用。

### C 路径: 走火眼 Web UI

火眼证据分析的服务器版本 (火眼网络仿真 / 火眼 Lab) 有 Web UI, **直接 HTTP API**:

```python
import requests
r = requests.post("http://localhost:8080/api/cases/123/files/grep",
                  json={"keyword": "推广设计图"})
hits = r.json()
```

如果用户用的是 Web 版, 跳过 Electron 直接走 HTTP。

---

## 八、风险

1. **火眼版本兼容**: 不同版本 UI 不一样, adapter 要按版本维护
2. **asar 解包**: 火眼可能加密 asar, OpenCLI CDP 还能用但 selector 难定位
3. **法律边界**: 适配器只是自动化点击, 不是破解, 但火眼 EULA 可能禁止逆向
4. **维护**: 火眼升级后可能要重写 adapter

---

## 九、TLDR

**结论**: 火眼 CLI 化**完全可行**, 推荐路径:

1. **本场比赛 (短期)**: 不做, 用 v5 的人机协作模式, 让人类操作火眼 GUI, AI 给精确指令
2. **2-4 周后**: 投入 1-2 周做 MVP 适配器, 覆盖 list/open/ls/grep/extract 5 个命令
3. **长期 (3 个月+)**: 完整覆盖火眼 + 知识库联动, AI 全自主操作火眼

**短期 (现在)**: 用人机协作模式, 给人类的指令一定要**精确到点击哪个按钮**。这是 v5 prompt 第六节的全部价值。
