# 火眼 CLI 使用条件详说

> **回答用户问题**: "使用火眼 CLI 有什么条件吗? 只要下载就可以用, 还是仍然需要登录软件?"
> **简短答案**: **不能"下载即用"**, 需要授权 + 加密狗 + 首次登录, 但**首次登录后整场比赛 CLI 接管**, 不再需要人工点击。

---

## 一、火眼是什么

火眼 (FireEye Forensics) 由**奇安信**旗下"网神信安"开发, 是国内最广泛使用的电子取证一站式平台:

| 子产品 | 功能 |
|---|---|
| **火眼证据分析** | 计算机取证 (E01/DD/VMDK 解析, 注册表, 浏览器, 文件雕刻) |
| **火眼移动取证** | 手机/平板取证 (Android/iOS 物理逻辑提取, 应用解析) |
| **火眼仿真** | 把取证镜像启动成虚拟机 |
| **火眼服务器仿真** | 服务器镜像启动 + 网络仿真 |
| **火眼破解大师** | 密码暴力破解 (GPU 加速) |
| **火眼 Lab** | 多检材协作分析平台 (web 版) |

---

## 二、授权机制 (核心障碍)

### 2.1 三种授权方式

| 方式 | 描述 | CLI 能绕过? |
|---|---|---|
| **加密狗 (USB Key)** | 插 USB dongle 才能启动 | ❌ 不能 |
| **云端激活** | 联网验证账号 license | ❌ 不能 |
| **离线 license 文件** | 单位购买后给的 .lic | ❌ 不能 |

**结论**: 任何方式都需要**人类先完成激活**, CLI 只是 wrapper, 不绕过授权检查。

### 2.2 比赛环境的特殊性

- **官方比赛 (FIC/全国大学生取证大赛)**: 通常预装授权版, 不需选手自己解决授权
- **学校实验室**: 有单位 license, 一次激活长期有效
- **个人/培训**: 几乎都需要购买 (年费数千-数万)

**警告**: 如果是非授权使用, 法律风险自己承担。CLI 化只是技术手段, 不解决合规问题。

---

## 三、CLI 化技术路径 (再说一遍)

### 3.1 OpenCLI + CDP 路径 (主推)

**前提条件**:
1. 火眼**已安装** + **已授权** + **已用人工启动一次**
2. 火眼启动时加 `--remote-debugging-port=9222` (改快捷方式启动参数)
3. 火眼基于 Electron (大概率, 需验证版本)

**实际工作流**:

```
比赛 T+0 时刻:
├─ 人类: 插加密狗
├─ 人类: 双击火眼证据分析快捷方式 (改了启动参数, 加 --remote-debugging-port=9222)
├─ 人类: 输入 license / 等待联网激活 (1-3 分钟)
├─ 人类: 看到主界面, 报告"已登录"
└─ AI 接管:
   ├─ AI: opencli huoyan list-cases  (验证 CDP 连接)
   ├─ AI: opencli huoyan open-case "D:\2026FIC.fyt"
   ├─ AI: opencli huoyan grep --case 1 --keyword "推广设计图"
   └─ ... 全程 CLI, 不再需要人类
```

### 3.2 哪些火眼版本能 CLI 化?

| 版本 | Electron? | CDP 端口? | CLI 化可行? |
|---|---|---|---|
| 火眼证据分析 (新版 ≥ 6.0) | ✅ 是 | 需测试 | ⭐⭐⭐⭐ 大概率可 |
| 火眼证据分析 (老版 ≤ 5.x) | ❌ 是 Qt/MFC | ❌ | ⭐⭐ 走 Win32 控件 |
| 火眼移动取证 (新版) | ✅ 是 | 需测试 | ⭐⭐⭐⭐ |
| 火眼 Lab (Web 版) | N/A (浏览器) | ✅ 直接 HTTP API | ⭐⭐⭐⭐⭐ 最容易 |
| 火眼仿真 | ❌ Native | ❌ | ⭐⭐ 走 Win32 |

**结论**: **新版本 (≥ 2024 年发布的) 大概率支持**, 老版本困难。比赛前必须先验证。

### 3.3 验证步骤 (5 分钟)

```cmd
# 1. 火眼快捷方式右键 → 属性 → "目标"末尾加: --remote-debugging-port=9222
# 2. 重启火眼, 完成登录
# 3. 浏览器开 http://127.0.0.1:9222/
#    - 如果显示 JSON 列表 (含 webSocketDebuggerUrl) = 支持, 可 CLI 化
#    - 如果 404 或拒绝连接 = 不支持, 走备选方案
```

---

## 四、备选方案 (火眼 CLI 不可用时)

### 4.1 火眼 Web Lab 走 HTTP API (推荐)

如果买的是 Web 版 (火眼 Lab):

```python
import requests

# 通常有 REST API
r = requests.post("http://lab-server:8080/api/v1/auth/login", 
                  json={"username": "x", "password": "y"})
token = r.json()["token"]

r = requests.post(f"http://lab-server:8080/api/v1/cases/{case_id}/files/grep",
                  headers={"Authorization": f"Bearer {token}"},
                  json={"keyword": "推广设计图"})
hits = r.json()
```

**优点**: 完全无 GUI, 离 AI 控制最近
**缺点**: 不是所有比赛都用 Web 版

### 4.2 PyAutoGUI / pywinauto (老版火眼)

```python
from pywinauto import Application
app = Application(backend="uia").connect(title_re=".*火眼.*")
window = app.window(title_re=".*火眼.*")
window.child_window(title="搜索", control_type="Button").click()
window.child_window(auto_id="searchBox").set_text("推广设计图")
```

**优点**: 不需要 CDP 支持
**缺点**: UI 改了就坏, 维护成本高

### 4.3 直接对底层文件操作 (绕过火眼)

火眼底层用的是开源工具:
- E01 解析 = libewf
- 文件系统 = pytsk3 / dissect
- 注册表 = python-registry / regipy

**完全可以不用火眼**, 用 `dissect.target` (Python) 直接解析:

```python
from dissect.target import Target
t = Target.open(r"D:\2026FIC\检材1-计算机.E01")
print(list(t.fs.path("/Users").iterdir()))
# 直接拿到注册表
hive = t.registry.key("HKEY_LOCAL_MACHINE\\SOFTWARE")
print(hive.value("ProductName"))
```

**优点**: 完全 AI 自主, 无授权依赖
**缺点**: 部分高级功能 (应用解析/解密) 火眼有但 dissect 没

**最佳实践**: **混合策略** — 简单解析用 dissect 直接做, 复杂解析用火眼 CLI

---

## 五、对本场比赛的具体建议

### 5.1 时间线

```
T-7 天 (赛前):
  1. 测试本机火眼是否支持 --remote-debugging-port=9222
  2. 如果支持 → 写 OpenCLI adapter (1-2 周)
  3. 如果不支持 → 完全靠 dissect.target + ssh_helper

T-1 天 (赛前最后):
  1. 准备 USB 加密狗 / 验证 license
  2. 测试启动流程, 卡秒表

T+0 (比赛开始):
  1. 人类: 插狗启动火眼 (5 分钟)
  2. AI: opencli huoyan ping 验证 CDP
  3. AI: 接管所有取证操作
  4. 人类: 只在 plan B 触发时介入

T+0 ~ T+50h (比赛):
  - 90% 时间 AI 自主跑
  - 10% 时间人类协助 (HITL v2 批次任务)
```

### 5.2 优先级

| 优先级 | 工具 | 理由 |
|---|---|---|
| ⭐⭐⭐⭐⭐ | dissect.target (Python) | 不需要火眼, 100% AI 自主 |
| ⭐⭐⭐⭐⭐ | ssh_helper.py + sim_recon.py | server/internet 角色直接 SQL |
| ⭐⭐⭐⭐ | 火眼 Web Lab API (如果有) | 直接 HTTP, 无 GUI |
| ⭐⭐⭐⭐ | OpenCLI 火眼 adapter | 复杂解析必须 |
| ⭐⭐⭐ | HITL v2 批次任务 | 兜底, 总要有 |

### 5.3 不要做的事

- ❌ 比赛前 1 周才开始测火眼 CDP (来不及写 adapter)
- ❌ 假设火眼一定能 CLI 化 (要先验证)
- ❌ 把所有取证压在火眼上 (dissect 能做的不要走火眼)
- ❌ 比赛中临时改火眼启动参数 (会失去登录态)

---

## 六、合规与法律

火眼是商业软件, EULA (用户协议) 通常明确:
- 禁止逆向工程
- 禁止规避授权机制
- 禁止用于非授权检材

**OpenCLI 路径属于自动化操作, 不是规避授权**, 但火眼厂商可能视为违反 EULA。

**建议**:
- 比赛/合法授权环境使用
- 不公开发布 adapter (防止被火眼厂商封禁/起诉)
- 不绕过加密狗 (即使技术上可行)

---

## 七、TLDR

### 用户的问题: "使用火眼 CLI 有什么条件? 只要下载就可以用, 还是仍然需要登录软件?"

**答**: **3 个条件**:

1. **法律 + 授权**: 加密狗 / license 必须先有 (CLI 不能绕过)
2. **首次人工登录**: 必须先**人工启动 + 输 license / 插狗 / 等激活** (5 分钟)
3. **改启动参数**: 加 `--remote-debugging-port=9222` 让 CLI 能接入

**首次登录后整场比赛 CLI 全程接管**, 人类不再点击。

### 但更现实的策略

**别把鸡蛋放在火眼一个篮子里**:
- 60% 操作用 `dissect.target` (Python, 完全 AI 自主, 无授权依赖)
- 30% 操作用 ssh_helper + 仿真 (服务器/网络)
- 10% 操作用火眼 CLI 或 HITL v2 (复杂应用解析 / 逆向)

火眼 CLI 化是**锦上添花**, 不是**唯一出路**。本场比赛没火眼也能打 70%+ 的题。
