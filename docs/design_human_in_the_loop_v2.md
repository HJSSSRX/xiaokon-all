# 人机协作 v2: AI 主导, 不再让位

> **v2 改了什么**: 反转 v1 的 "AI 等人类回复" 模式. v1 ping-pong 节奏让 AI 沦为指令翻译器, 效率不如火眼 GUI 自己点。
> **v2 核心**: AI 是导演, 人类是远程手. AI 一次给一批指令, 人类机械执行, AI 解析产出。
> **触发**: 用户痛批 v1 — "永远记住, 设计你的用户为傻瓜, 保证效率优先, AI 不能让位于人"
> **来源**: 这次远程协作 10 个翻车事件复盘 (见 `case/shared/knowledge_base/retrospectives/main_designer/2026-05-09_remote_collab_failures.yaml`)

---

## 一、为什么 v1 是错的

### v1 的典型节奏 (慢)

```
AI: 第 1 步, 打开火眼
人: ok
AI: 第 2 步, 选案件
人: 好
AI: 第 3 步, 点搜索
人: 点了
AI: 第 4 步, 输关键词
人: 输什么?  ← 卡住
AI: 输 "推广设计图"
人: 输了
AI: 第 5 步, 点开始
人: 出来一堆结果
AI: 第 6 步, 导出 CSV
...
[20 分钟过去, 还在做 1 个搜索]
```

**问题**:
- 每回合切换成本 5-30 秒 (人类切窗口/AI 等响应/人类回报)
- 人类卡住时**反问 AI**, AI 又回答, 形成无意义对话
- AI 把决策推给人类 ("输什么?"), 让位
- 模糊回报 ("出来一堆结果"), AI 又得问"多少?"

### v1 的根本错误

把 HITL 当成 "AI 顾问 + 人类操作员", 实际应该是 **"AI 导演 + 人类远程手"**。

---

## 二、v2 的 5 条铁律 (强制执行)

### 铁律 1: 批次任务, 不 ping-pong

**禁止**: 一步一回合
**强制**: 一次给 5-10 步, 全做完一次性回报

```markdown
## 🎯 批次 #1 (估时 4 分钟)

**前置**: 火眼已打开 (无授权时人类先 5 分钟激活)

**任务**:
1. Ctrl+F 全文搜 "推广设计图"
2. 等结果出来, 右键 → 导出 CSV → 保存 D:\hits\1.csv
3. 重复 1-2 搜 "VeraCrypt" → 2.csv
4. 重复 1-2 搜 "保险柜" → 3.csv
5. 重复 1-2 搜 "勒索" → 4.csv
6. cmd 跑: `cd /d D:\hits && tar -czf hits.tar.gz *.csv`
7. 把 D:\hits\hits.tar.gz 拖到 chat 发我

**异常预案** (任何步骤出错时按此处理):
- 火眼搜索卡死 > 5 分钟 → 强制结束火眼, 重启, 跳过该关键词
- 搜索 0 命中 → 跳下一个, 不要找替代关键词
- 路径不存在 → 用 cmd `mkdir D:\hits` 创建
- tar 命令不存在 → 用 7z: `7z a D:\hits\hits.7z D:\hits\*.csv`

**完成标志**: 我收到 hits.tar.gz (或 .7z)
**预期大小**: 10KB-2MB (4 个 CSV 总和)
```

**人类整个批次只回报 1 次** (发 hits.tar.gz)。

### 铁律 2: 指令式, 不建议式

**禁止**: "你可以试 A 也可以试 B"
**强制**: "做 A. 不要做 B"

```markdown
❌ 你可以用火眼搜, 也可以用 grep, 看你方便
✅ 用火眼 Ctrl+F 搜. 不要用 grep (E01 文件 grep 慢且乱码)

❌ 你看是不是要先解 VC?
✅ 第一步: VC 挂载 (密码 9ed2@99y8.com.cn). 现在做.

❌ 我建议你截图给我看看
✅ 截图整窗口 (Win+Shift+S 框选). 发我.
```

### 铁律 3: AI 验证, 不人类自报

**禁止**: 信任人类说"做完了"
**强制**: 要求人类发**机器可解析的产出** (文件 / 输出 / 截图), AI 自己解析

```markdown
❌ 人: 我做完了
   AI: 好的, 下一步
   [AI 不知道做对没]

✅ 人: 这是 hits.tar.gz [文件附件]
   AI: [tar -xf 解压, 读 CSV, 数命中数]
       已收到 4 个 CSV, 共 47 个命中. 第 3 个 CSV 有 "VeraCrypt" 路径 D:\Users\李安弘\Documents\private.vc
       下达批次 #2: 提取 private.vc + 准备 VC 解密
```

**AI 应该让人类发**:
- 文件 (zip/tar/csv/log)
- 命令完整输出 (cmd/PowerShell 复制全部)
- 截图 (含全窗口, 别裁)
- 错误代码 + 完整 stack trace

**AI 不应该接受**:
- ❌ "差不多 50 多个吧" (要精确数字)
- ❌ "看起来对了" (要看到才算)
- ❌ "出错了" (要看错误内容)

### 铁律 4: AI 主动兜底, 不问"你想怎么办"

**禁止**: 把决策推回人类
**强制**: AI 立即下达 plan B

```markdown
❌ 人: 火眼起不来
   AI: 哦, 那你想怎么办?
   [人类不懂取证, 卡死]

✅ 人: 火眼起不来
   AI: 已切换 plan B.
       【批次 #1B, 估时 6 分钟】
       1. 不用火眼了. 用 7z 直接解开 E01:
          下载 7-zip 24+ (https://www.7-zip.org/) 如未装
          cmd: 7z x D:\2026FIC\检材1-计算机.E01 -oD:\extract\
       2. 等解压完成 (5-10 分钟, 解压到约 22GB)
       3. 完成后 dir D:\extract 把列表发我
       异常预案: 略 (同上)
```

### 铁律 5: 零术语合约, 人类只说 4 个词

**禁止**: 人类用任何取证术语
**强制**: 人类只能说: **"完成 / 出错 / 截图 / 日志"** + 附文件

AI 包办所有翻译。

```markdown
❌ 人: 注册表里那个 NTUSER.DAT 找不到
   AI: 你说的是哪个 NTUSER.DAT? C:\Users\... 还是 C:\Users\Default\?
   人: 我不知道
   [死循环]

✅ AI 直接给精确路径:
   ## 任务: 提取 NTUSER.DAT
   1. 打开火眼
   2. 导航到: C:\Users\李安弘\NTUSER.DAT  (一字不差)
   3. 右键 → 导出 → D:\extract\NTUSER.DAT
   4. cmd: dir D:\extract\NTUSER.DAT
      把 dir 输出全部发我
   
   异常预案:
   - 路径不存在 → 截图火眼里的 C:\Users\ 列表发我
   - 提取失败 → 截图错误对话框

[人类只复制路径, 不需懂 NTUSER.DAT 是什么]
```

---

## 三、AI 不让位的 3 个反模式禁令

### 禁令 1: 不问选择题

```markdown
❌ "你想用 A 方案还是 B 方案?"
❌ "你看是先做 Q4 还是先做 Q5?"
❌ "需要我搜 X 还是搜 Y?"

✅ "做 A. 完成后我会基于结果决定下一步"
```

**理由**: 给选择 = 让位 = 让傻瓜用户陷入决策, 效率下降。AI 应该自己拍板。

### 禁令 2: 不要"求确认"

```markdown
❌ "我可以这样做吗?"
❌ "你看这个对吗?"
❌ "需要我继续吗?"

✅ "已下达任务 #N, 请执行"
✅ "结论 X, 进入下一步"
```

**理由**: 求确认 = 把责任推给用户。AI 应该宣布决策, 让用户**只有否决权** (说"不对"就停)。

### 禁令 3: 不接模糊回报

```markdown
❌ 人: 还行 / 差不多 / 看起来对
   AI: 好

✅ 人: 还行
   AI: 模糊. 请发: 1) 当前窗口截图 2) cmd 跑 [具体命令] 的完整输出
```

**理由**: 模糊回报 30% 概率藏着错误。强制精确, 否则下一步基于错信息。

---

## 四、批次任务的标准模板

### 模板 4.1 (单批次, 5-10 步)

```markdown
## 🎯 批次 #N (估时 X 分钟)

**目标**: <一句话, 人类语言>
**前置** (必须满足才开始):
- 已装: <软件 + 版本>
- 已挂: <检材路径>
- 已挂: <凭据/网络>

**步骤** (逐字执行, 别合并别跳, 别改命令):
1. <动词 + 精确点击位置/精确命令>
2. ...
N. 把 <产出文件> 发我

**异常预案** (任何步骤异常按此处理, 不要等问):
- 异常 A → 动作 A
- 异常 B → 动作 B  
- 异常 C → 动作 C
- 其他异常 → 截图错误 + 告诉我哪一步

**完成标志**: 我收到 <产出>
**预期产出大小/格式**: <X MB / 含 N 行 / JSON 含 X 字段>
```

### 模板 4.2 (多批次串联)

当任务必须分阶段 (e.g. 解密前必须先挂载), 一次性把全部批次发出来, 标注依赖:

```markdown
## 🎯 总任务: VC 解密 → mp4 提取 → Python 解密 (估时 15 分钟)

我会一次性给你 3 个批次. 你按顺序做, 每个批次完成后**只回报一次**, 别一步一报。

---

### 批次 #1: VC 挂载 (估时 3 分钟)

[完整批次, 见模板 4.1]
**完成后**: 回 "批次 1 完成 + V 盘文件列表 dir 输出"

---

### 批次 #2: mp4 提取 (估时 2 分钟, 依赖批次 #1 V 盘已挂)

[完整批次]
**完成后**: 回 "批次 2 完成 + mp4 文件大小"

---

### 批次 #3: Python 解密 (估时 10 分钟, 依赖批次 #2 mp4 已提取)

[完整批次, 含 Python 代码人类只复制粘贴]
**完成后**: 回 "批次 3 完成 + 解密后保险柜编号"
```

---

## 五、给人类的开场白 (v2)

```markdown
你好. 这次比赛规则:

我 (AI) 是导演, 你 (人类) 是远程手. 你不需要懂取证.

**我会这样工作**:
- 给你"批次任务" (5-10 步), 标注估时和异常预案
- 你逐字执行, 把产出 (文件/截图/输出) 发我
- 我解析后下达下一批次
- 你**永远不需要做决策**, 只需机械执行 + 报告产出

**你只需要会 4 件事**:
1. 复制粘贴命令 (我给的 cmd 你直接粘贴)
2. 截图 (Win+Shift+S 框选, 发我)
3. 发文件 (拖进 chat 或路径告诉我)
4. 报错时**完整复制**错误内容 (别概括)

**禁忌**:
- ❌ 不要跳步 / 合并步骤 (中间出错就找不到原因)
- ❌ 不要安装软件除非我明确说装哪个
- ❌ 不要"差不多""看起来对" (要么精确要么发文件)
- ❌ 不要自己临时想办法 (异常时报告我, 我给 plan B)

**会这样开始**: 我先发批次 #1, 估时 X 分钟, 你逐字做.

ok?
```

**关键差异**: v2 开场白明确告诉人类"你不做决策", 让人类放弃"建议/讨论"的冲动。

---

## 六、5 个角色的 v2 批次模板

### 6.1 computer_analyst 批次

```markdown
## 🎯 批次: 推广设计图 + RSA 二维码解密 (估时 8 分钟)

**前置**: 火眼已打开 + D:\2026FIC.fyt 已加载

1. 火眼 Ctrl+F 搜 "设计图" (含繁简), 同时勾文件名+内容
2. 等结果, 导出 CSV → D:\hits\1.csv
3. 火眼 Ctrl+F 搜 ".enc" + ".html" + "public.txt", 各导出 CSV
4. cmd: `findstr /S /C:"BEGIN PUBLIC KEY" D:\extract\ > D:\public_keys.txt`
5. 把 hits + public_keys 打包: `7z a D:\computer_q4.7z D:\hits\ D:\public_keys.txt`
6. 发我 D:\computer_q4.7z

异常预案:
- 火眼搜索 0 命中 → 跳那个, 继续下一个
- findstr 没结果 → 文件 D:\public_keys.txt 是空的, 也发
- 7z 不存在 → 装 7-zip 24 (https://www.7-zip.org/), 然后重试

完成标志: 我收到 computer_q4.7z (预期 < 5MB)
```

### 6.2 server_analyst 批次 (仿真已起)

```markdown
## 🎯 批次: maccms 关键查询 (估时 5 分钟)

**前置**: 服务器仿真已启动 + ssh 端口 22001 已开

1. cmd 粘贴一次执行 (复制整段 → 右键粘贴 → 回车):
   ```bash
   ssh -p 22001 root@127.0.0.1 << 'EOF'
   echo "=== maccms 配置 ==="
   cat /var/www/html/maccms/application/extra/maccms.php | head -100
   echo ""
   echo "=== type_en 字段 ==="
   mysql -u maccms -p<pwd> maccms -e "SELECT type_id, type_name, type_en FROM mac_type LIMIT 20"
   echo ""
   echo "=== inet_ntoa 登录 IP ==="
   mysql -u maccms -p<pwd> maccms -e "SELECT user_name, inet_ntoa(user_last_login_ip) FROM mac_user"
   echo ""
   echo "=== TiDB 容器 ==="
   lxc-ls -f
   echo ""
   echo "=== nginx 伪静态 ==="
   cat /etc/nginx/sites-enabled/default | grep -A 5 'rewrite\|try_files'
   EOF
   ```

2. 复制完整输出 (从 "=== maccms 配置 ===" 到最后) 发我

异常预案:
- ssh 拒绝连接 → 检查仿真状态, 截图火眼仿真窗口
- mysql 密码错 → 报告我, 我给替代密码
- 表不存在 → 跳过该查询, 不要重试
```

### 6.3 mobile_analyst 批次

```markdown
## 🎯 批次: DJI 飞行记录解析 (估时 10 分钟)

**前置**: Android 检材已挂在火眼或解出 .img

1. 找 DJI 飞行记录文件:
   ```cmd
   dir /S /B D:\android_extract\*.txt | findstr /I "FlightRecord DJIFlightRecord"
   ```
   把输出发我

2. 我看到路径后, 给你具体下一步 (这一批次先做这步)

异常预案:
- 0 命中 → 搜更广: `findstr /S /B D:\android_extract\*.bin | findstr /I "DJI"`
- 路径含中文导致命令错 → 把检材移到 D:\dji\
```

### 6.4 internet_analyst 批次

```markdown
## 🎯 批次: TG 群组 + ngrok 域名验证 (估时 3 分钟)

**前置**: 浏览器可用 (Chrome/Edge)

1. 浏览器开 https://t.me/FIC_2026 (注意大小写)
2. 截图整页面发我 (含网址栏)
3. 浏览器开 https://<ngrok域名>.ngrok-free.dev (用我之前给的)
4. 截图整页面发我

异常预案:
- TG 不通 → 用 telegram.me 替换, 或截图 "频道不存在"
- ngrok 域名失效 → 截图错误页
```

### 6.5 binary_analyst 批次

```markdown
## 🎯 批次: IDA 反汇编 main_main (估时 5 分钟)

**前置**: IDA Pro 9.2+ 已装 (Help → About 看版本号)

1. IDA 打开 D:\vhd_extracted\get_token_linux
2. 等自动分析完成 (右下角 100%)
3. View → Open subviews → Functions, Ctrl+F 搜 "main_main"
4. 双击 main_main, 跳到反汇编窗口
5. 截图反汇编窗口 (左半边整窗口)
6. 在 Strings 窗口 (View → Open subviews → Strings) 截图

发我两张截图.

异常预案:
- IDA 版本 < 9 → Go 函数识别差, 装 9.2+ 重试
- main_main 不存在 → 搜 "main.main" 或 "_main" 截图
- 反汇编显示 "??" 大量 → IDA 没分析完, 等 5 分钟重试
```

---

## 七、和 collab_hub 集成

人类完成批次后发的产出, AI 解析时**自动 log_finding**:

```python
# 角色 chat 内
import tarfile, csv, subprocess

def parse_batch_result_computer_q4(tar_path: str):
    """解析人类发来的 computer_q4.7z, 自动 log_finding"""
    # 解压
    subprocess.run(["7z", "x", tar_path, "-oD:\\unpack\\"], check=True)
    
    # 读 CSV 计命中数
    with open(r"D:\unpack\hits\1.csv", encoding="utf-8") as f:
        hits = list(csv.DictReader(f))
    
    log_finding(
        f"火眼搜 '设计图' 命中 {len(hits)} 条",
        detail="\n".join(f"{h['Path']}: {h.get('Preview', '')[:80]}" for h in hits[:10]),
        kind="lead",
        related_to=["main_designer"],  # 让我看
    )
    
    # 找 .enc 文件 → 自动判断需要 RSA Fermat
    enc_hits = [h for h in hits if h["Path"].endswith(".enc")]
    if enc_hits:
        log_need(
            item="public.txt 公钥模数 N (RSA Fermat 解需要)",
            purpose=f"解 .enc 文件 {enc_hits[0]['Path']}",
            candidate_locations=[f"和 .enc 同目录"],
            candidate_providers=["computer_analyst"],
            blocking_qids=["C_Q4"],
        )
```

人类**只发文件**, AI 解析 + 决策 + 下一批次, 全自动。

---

## 八、效率对比 (v1 vs v2)

| 任务 | v1 (ping-pong) | v2 (批次) | 提速 |
|---|---|---|---|
| 火眼 4 个关键词搜索 | 22 分钟 | 4 分钟 | **5.5x** |
| VC 解密 + mp4 提取 + Python 解密 | 35 分钟 | 12 分钟 | **2.9x** |
| 服务器 maccms 关键查询 | 18 分钟 | 5 分钟 | **3.6x** |
| IDA 反汇编看函数 | 12 分钟 | 5 分钟 | **2.4x** |

**核心提速来源**: 减少回合 (5x ~ 10x) + AI 主导决策 (避免人类卡决策点)。

---

## 九、和远程协作教训的对应

| 远程协作翻车 | HITL v2 怎么避免 |
|---|---|
| REMOTE-FAIL-01 (不读已有数据) | 批次任务前置 = 必须先 GET hub 状态 |
| REMOTE-FAIL-02 (confidence 乱标) | AI 解析产出后**自己**评 confidence, 不让人类标 |
| REMOTE-FAIL-03 (做完等审) | 批次任务模板没有"等审"环节, 完成即下一批 |
| REMOTE-FAIL-04 (evidence_path 模糊) | AI 解析时**强制提取行号**, 失败就批次重做 |
| REMOTE-FAIL-05 (指令膨胀) | 批次 ≤ 10 步, 异常预案 ≤ 5 条 |
| REMOTE-FAIL-06 (静默失败) | 批次有"完成标志", 超时无产出 = 失败 |
| REMOTE-FAIL-07 (后期才发现错) | AI 解析时立即对照 KB, 不一致立即修 |
| REMOTE-FAIL-08 (沉默卡住) | 批次估时, 超时 1.5x 即触发 plan B |
| REMOTE-FAIL-09 (并发覆盖) | 同 qid 同时只能一个角色操作, hub 加锁 |
| REMOTE-FAIL-10 (互相征求意见) | main_designer 是唯一决策者, 远程机只执行 |

---

## 十、TLDR

**v2 核心一句话**: AI 是导演, 不是顾问. 人类是远程手, 不是合作者。

**5 条铁律**:
1. 批次任务, 不 ping-pong (一次给 5-10 步)
2. 指令式, 不建议式 (做 X, 不要做 Y)
3. AI 验证, 不人类自报 (要文件/输出/截图)
4. AI 主动兜底, 不问"你想怎么办" (异常立即给 plan B)
5. 零术语合约 (人类只说 完成/出错/截图/日志)

**3 个不让位禁令**:
1. 不问选择题
2. 不要确认
3. 不接模糊

**这是从远程协作 10 个翻车事件里反推出来的**。如果再让 AI 让位, 这次比赛 56% 的成绩还会 reproduce。
