# 人机协作引导模式 (Human-in-the-Loop)

> **目标**: AI 不能直接动鼠标点 GUI 时, 通过 chat 让"远程手"(人类) 帮忙, 同时**保证人类零知识也能完成**。
> **关键约束**: 人类是新手取证 (可能), 不能假设他们懂 IDA/SQL/正则。
> **价值**: 火眼 CLI 化前的过渡方案 + 永远的备份方案。

---

## 一、核心矛盾

| 你 (AI) | 人类 |
|---|---|
| 能想清楚每一步要什么 | 不一定理解为什么 |
| 不能点鼠标/敲键盘 | 能点能敲 |
| 能秒查 KB / 跑脚本 / 解析 JSON | 看 JSON 头大 |
| 不会累 | 30 分钟后注意力下降 |

**解决思路**: AI 把任务**拆到一键级别**, 人类只负责"机械执行 + 报告结果"。

---

## 二、指令格式标准 (HITL Schema v1)

### 2.1 格式模板

每条给人类的指令必须包含:

```markdown
## 🎯 任务 #N: <一句话目标 (人类语言)>

**估时**: 3 分钟
**前置**:
- 你已经打开了: <软件 + 版本>
- 你已经挂载了: <检材路径>

**步骤** (逐步执行, 别合并别跳):
1. **点** 火眼左侧栏的 "文件浏览" 按钮 (放大镜图标右边)
2. **输入** 在地址栏粘贴: `C:\Users\李安弘\Desktop`
3. **回车** 等列表加载 (5-10 秒, 鼠标会变沙漏)
4. **截图** 整个文件列表 (Win+Shift+S 框选, 不要截到任务栏)
5. **发** 截图给我

**预期看到**: ~10 个文件, 包含 `.png` `.jpg` 推广设计相关图

**异常处理**:
- ❌ 提示 "权限错误" → 回复 "权限错误", 我换路径
- ❌ 列表空 → 检查地址栏是不是少了 `\`, 没问题就回复 "空"
- ❌ 卡死 5+ 分钟 → 强制结束火眼重新打开, 回复 "重启"

**完成后回复格式**: 
> 任务 #N 完成
> 结果: [文件列表 / 截图 / 我看到的现象]
```

### 2.2 反例 (不要这样写)

```markdown
❌ 帮我看下计算机里的桌面有什么文件
❌ 找一下推广图
❌ 解密一下这个 VC 容器
```

这种指令对**有经验的取证师**可以, 对新手会卡 30 分钟。

---

## 三、9 种典型任务模板

### 3.1 火眼: 全盘关键词搜

```markdown
## 🎯 任务: 全盘搜关键词 "{keyword}"

1. 在火眼证据分析里打开你的案件
2. **点** 顶部菜单 "搜索" → "全文搜索" (快捷键 Ctrl+F)
3. **输入** 关键词: `{keyword}`
4. **勾选** 选项: "搜索文件名" + "搜索文件内容" + "区分大小写=否"
5. **点** "开始搜索" 按钮
6. 等待结果 (大盘 5-15 分钟, 中途别动)
7. 搜索完成后, **导出** 结果: 右键结果列表 → "导出到 CSV"
8. 把导出的 CSV 文件路径发我, 或直接打开 CSV 复制前 50 行发我

预期: 一个 CSV, 含命中文件路径 + 偏移 + 周边 100 字符
```

### 3.2 火眼: 提取单个文件

```markdown
## 🎯 任务: 提取文件 `<source_path>` 到本地

1. 火眼里 **导航** 到 `<source_path>` 所在目录
2. **右键** 文件名 → "导出"
3. 弹窗里选 "导出到本地", 路径填: `D:\extract\`
4. 点 "确定", 等待提取完成
5. 完成后回复 "已提取", 并附带提取后的文件大小 (右键文件 → 属性)
```

### 3.3 IDA Pro: 反汇编看函数

```markdown
## 🎯 任务: 看二进制 main_main 函数的汇编

1. **打开** IDA Pro 9.x (检查版本: Help → About, 必须 9.0+)
2. **拖入** 文件 `D:\path\to\binary` 到 IDA 窗口
3. 弹窗 "Load a new file" → 全部默认 → OK
4. 等待自动分析 (1-3 分钟, 右下角进度条 100% 才算完)
5. **跳转** 按 G → 输入 `main_main` → 回车
6. **截图** 反汇编窗口 (左半边的 IDA View)
7. **截图** 同时函数右下角的 Strings 窗口 (如果有 hex 常量)
8. 把两张图发我

预期看到: 一堆 mov/call 指令 + 可能有 0xAFE886AFE5A3A7E8LL 这类 hex 常量
```

### 3.4 SQL: 数据库查询

```markdown
## 🎯 任务: 在 mac_user 表查 IP

**前置**: 你已经能 ssh 到服务器 (火眼仿真启动了)

1. **打开** PowerShell / cmd (Win+R 输入 cmd)
2. **粘贴** 这行命令:
   ```bash
   ssh root@192.168.x.x mysql -u maccms -p<pwd> maccms_db -e "SELECT user_name, inet_ntoa(user_last_login_ip) as ip FROM mac_user WHERE user_name LIKE '%Ma%';"
   ```
3. 回车, 等 5 秒
4. **复制完整输出** 发我 (含表头)

预期看到: 1-3 行结果, ip 列是 192.168.x.x 或公网 IP
```

### 3.5 VeraCrypt 挂载

```markdown
## 🎯 任务: 解密 VC 容器到 V: 盘

1. **打开** VeraCrypt (开始菜单 / 桌面图标)
2. **点** "Select File...", 浏览到 `D:\path\to\vc_file`
3. **点** "Mount", 弹出密码框
4. **粘贴** 密码: `9ed2@99y8.com.cn`
5. **不要勾** "Save password", **不要改** PIM (留空)
6. 点 OK, 等 10-30 秒
7. 出现 V: 盘符 = 成功
8. **打开** "我的电脑", 看到 V: → 截图整个窗口发我

异常:
- ❌ "Incorrect password" → 密码错, 报告我换
- ❌ "Failed to read header" → 文件路径错或文件损坏
```

### 3.6 抓包 / 网络分析

```markdown
## 🎯 任务: Wireshark 抓 X 应用流量

1. **打开** Wireshark
2. **选** 网卡: 以太网 / WiFi (随便选活跃的, 包数 > 0 那个)
3. **过滤器** 输入: `host backup.sp-live88.xyz`
4. **点** 蓝色鲨鱼图标开始抓
5. 在另一台电脑/手机打开 X 应用, 进行相关操作
6. 等 30 秒, 点红色方块停止
7. **File → Export Packet Dissections → Plain Text**, 保存到 `D:\packet.txt`
8. 把 D:\packet.txt 前 100 行发我
```

### 3.7 Linux 终端命令

```markdown
## 🎯 任务: 列服务器的所有数据库服务

**前置**: 已 ssh 上服务器

1. **粘贴** 这一长串到 ssh 终端, 一次执行 (复制 → 右键粘贴 → 回车):
   ```bash
   echo "=== 已装包 ==="; dpkg -l | grep -iE 'mysql|tidb|postgres|mariadb|redis|mongo' | awk '{print $2}'
   echo "=== 服务状态 ==="; for svc in mysql mariadb postgresql tidb redis mongodb; do
     printf "%-12s " $svc; systemctl is-active $svc 2>/dev/null || echo "(未装)"
   done
   echo "=== 监听端口 ==="; ss -tlnp 2>/dev/null | grep -E ':(3306|3307|4000|5432|6379|27017)'
   ```
2. **复制完整输出** 发我

预期看到: 三段输出, 一共 10-20 行
```

### 3.8 截图 + OCR (备份方案)

```markdown
## 🎯 任务: 看 GUI 里某个数字 (无法复制时)

1. **截图** 火眼里那块数字所在区域 (Win+Shift+S)
2. **保存** 截图到 D:\snap.png
3. (可选) 打开 https://ocr.online/ 上传 → 复制识别结果发我
4. 或直接把截图发我, 我自己看
```

### 3.9 多步连环 (复杂任务)

```markdown
## 🎯 任务: VC 解密 → 提取 mp4 → 用 Python 解密

我会分 3 步给你, 每步完成后等我下一步指令, **不要自己往下做**。

**第 1 步**: VC 挂载 (见任务模板 3.5, 密码: `9ed2@99y8.com.cn`)
[等你回复 "已挂载到 V:" 后我给第 2 步]

**第 2 步**: 提取 V:/encrypted.mp4 到 D:/decrypt_work/
[等你回复后我给第 3 步]

**第 3 步**: 跑 Python 脚本 (我给完整命令)
```

---

## 四、给人类的"心理建设"

### 4.1 第一次对话的开场

```markdown
你好! 这场比赛我们是搭档:
- 我 (AI): 负责想"做什么 + 怎么做", 给你详细指令
- 你 (人类): 负责操作, 把结果(截图/文本)发我

**我会这样标记任务**: "## 🎯 任务 #N: ..."
**你只需要**: 跟着步骤做, 完成后回复 "任务 #N 完成 + 结果"

**遇到问题随时问**:
- 看不懂步骤? → 直接说 "第 X 步看不懂"
- 软件没装? → 说 "没装 X", 我换方案
- 不知道怎么截图? → 说 "怎么截图", 我教

**禁忌**:
- ❌ 不要自己跳步 (跳了我不知道你做到哪)
- ❌ 不要把多步合并成一步 (中间出错难定位)
- ❌ 不要安装/删除文件除非我明确说

ok?
```

### 4.2 给指令时的语气

- **不用** 取证术语 ("MFT" "$Boot" "ENTRANCE 常量")
- **多用** 视觉描述 ("左侧栏放大镜下面那个" "蓝色鲨鱼图标")
- **必给** 异常处理 (报错时怎么办, 卡死了怎么办)
- **不假设** 软件版本 (问"你装的 IDA 是哪个版本?")

### 4.3 验证人类做对了

每条指令末尾加**自验证锚点**:

```markdown
**完成的标志** (你看到这些 = 做对了):
- ✅ 弹出 "Mount successful" 提示
- ✅ 我的电脑里出现 V: 盘符
- ✅ V: 里有至少 3 个文件夹

如果没看到任何一个 → 没做对, 报告我。
```

---

## 五、AI 端的辅助工具

### 5.1 任务追踪器

```python
# tools/hitl_tracker.py
import json
from datetime import datetime
from pathlib import Path

TRACKER = Path(r"E:\ffffff-JIANCAI\2026FIC团体赛\case\shared\hitl_tasks.json")

def assign_task(role: str, task_id: int, description: str, steps: list[str], expected: str):
    tasks = json.loads(TRACKER.read_text(encoding="utf-8")) if TRACKER.exists() else []
    tasks.append({
        "id": task_id,
        "role": role,
        "description": description,
        "steps": steps,
        "expected": expected,
        "status": "assigned",
        "assigned_at": datetime.now().isoformat(),
        "completed_at": None,
        "result": None,
    })
    TRACKER.write_text(json.dumps(tasks, ensure_ascii=False, indent=2), encoding="utf-8")

def complete_task(task_id: int, result: str):
    tasks = json.loads(TRACKER.read_text(encoding="utf-8"))
    for t in tasks:
        if t["id"] == task_id:
            t["status"] = "completed"
            t["completed_at"] = datetime.now().isoformat()
            t["result"] = result
    TRACKER.write_text(json.dumps(tasks, ensure_ascii=False, indent=2), encoding="utf-8")

def list_pending():
    if not TRACKER.exists():
        return []
    tasks = json.loads(TRACKER.read_text(encoding="utf-8"))
    return [t for t in tasks if t["status"] == "assigned"]
```

### 5.2 v5 prompt 内嵌的 hitl 模式

v5 prompt 第六节已经写了基础。可以加:

```python
# 角色 chat 里
from hitl_tracker import assign_task

assign_task(
    role="computer_analyst",
    task_id=1,
    description="火眼搜推广设计图",
    steps=["打开火眼", "Ctrl+F", "输入 推广设计图", "导出 CSV"],
    expected="CSV 含命中路径",
)

# 然后给人类 chat 输出标准化指令
```

---

## 六、风险与边界

### 6.1 不能让人类做的事

- ❌ 任何**安全敏感**操作 (改注册表 / 卸载杀毒 / 关防火墙)
- ❌ 任何**破坏性**操作 (删文件 / 格式化 / dd if=/dev/...)
- ❌ 任何**法律边界**操作 (绕过检材完整性 / 改 hash)
- ❌ 自己买/装新软件 (除非用户明确预算)

### 6.2 必须人类决策的

- 人类自己电脑的状态 (我们不知道装了啥)
- 是否分享真实凭据 (我们只能用题目给的)
- 是否打断比赛 (休息/吃饭)

### 6.3 何时切回 AI 直接做

- 火眼 CLI 化完成 → 不再需要人类点击
- 命令行任务 (人类只是复制粘贴) → 用 SSH agent 直接跑
- 简单查询 → AI 已经能跑 Python

---

## 七、和 collab_hub 的集成

人机任务可以通过 hub 跨角色传递:

```python
# computer_analyst 需要人类做某事, 但人类目前在 server_analyst 那边
log_question(
    to="server_analyst",
    question="人类完成你的任务后, 让他们做这个 [HITL 任务模板]: ...",
    context="阻塞 C-Q4 推广设计图分析"
)
```

---

## 八、TLDR

**人机协作的 5 条铁律**:

1. **任务原子化**: 每条指令 ≤ 5 分钟, ≤ 7 步
2. **零取证术语**: 用视觉描述 ("蓝色按钮"), 不用 ("MFT")
3. **强制异常处理**: 每步告诉人类报错时怎么办
4. **自验证锚点**: 每个任务末尾给"做对了的标志"
5. **追踪记录**: 每个任务进 hitl_tasks.json, 用完反思哪些步骤不清晰

**短期价值**: 这是火眼 CLI 化前的**唯一可行方案**, 必须做好。
**长期价值**: 即使有了 CLI, 仍是**应急方案** (CLI 出 bug / 新工具没适配)。
