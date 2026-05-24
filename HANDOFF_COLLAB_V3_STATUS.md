# v3 协作系统实施状态 — HANDOFF

> **更新 2026-05-24**: 2026FIC 比赛已结束。E: 盘案件共享数据不可访问，cloudflared 未安装。V3 Hub 基础设施已加固（空目录自动创建），等待下一场比赛复用。
> 未完成项：cloudflared 隧道（需用户决定+操作）、B001 LVM 解密（检材不再可用）、答案表（已存档至 cases/2026FIC/answers_final_legacy.md）。

> 给下一个 AI：本会话完成了 v3 HTTP Hub 协作系统的**设计 + 实现 + 文档 + 部分实战验证**。
> 一句话现状：本机 2 角色已通过 Hub 工作，远程 2 角色未接入（cloudflared 隧道未启动）。

---

## 当前活动状态（截至 2026-05-07 15:30）

```
Hub URL:        http://127.0.0.1:8765 (port 8765, bind 0.0.0.0)
Hub PID 进程:   后台运行（用 Get-NetTCPConnection -LocalPort 8765 查 PID）
Case dir:       E:\ffffff-JIANCAI\2026FIC团体赛\case\
Findings:       10 条（F-B001~003, F-S001~007）
Blockers:       1 条 active（B001: server LVM 加密待解）
Progress:
  - computer_analyst: idle    （远程机1，已连 Hub 但未提交发现）
  - mobile_analyst:   idle    （远程机2，物理网络隔离，无法连接）
  - server_analyst:   in_progress （正做 ngrok/Q16/Telegram）
  - binary_analyst:   in_progress （正做 Q3+Q4 AES 解密）
```

## ✅ 已完成

| 项 | 文件 | 备注 |
|---|---|---|
| Hub 服务端 | `tools/collab_hub.py` | 400 行 stdlib，7 大 API |
| 回归测试 | `tests/test_collab_hub.py` | 25/25 通过 |
| 数据导入工具 | `tools/import_yaml_to_hub.py` | yaml → Hub 批量导入 |
| 主设计师 prompt | `prompts/main.md` | 加 Phase 0 会话恢复 + HTTP Hub 监控 |
| 4 个角色 prompt | `case/role_prompt_*.md` | 嵌入 v3 协作指令 |
| 远程机部署指南 | `case/REMOTE_DEPLOYMENT.md` | 含防火墙/故障排查/API 速查 |
| 已修复白名单 bug | `tools/collab_hub.py:68` | 现在允许全大写 .md + import_*.py |

## ⏸️ 待完成（按优先级）

### 1. 启动 cloudflared 公网隧道（卡在这里）
**为什么需要**：手机角色（远程机2）只有 VMware 虚拟网卡，与主机 LAN 隔离，必须走公网。

**已装好**：cloudflared 2025.8.1 在 `C:\Program Files (x86)\cloudflared\cloudflared.exe`

**用户上次取消了启动尝试**。你应该：
```powershell
# 启动 quick tunnel（前台运行，会输出 trycloudflare URL）
& "C:\Program Files (x86)\cloudflared\.\cloudflared.exe" tunnel --url http://localhost:8765
```
- 前 30 秒会输出 `https://xxx-xxx-xxx.trycloudflare.com`
- 把这个 URL 发给手机角色用户，让它的 AI 用作 `$Hub`
- **隧道进程不能关**，关了 URL 失效

**备选**（如果用户不想用 cloudflared）：
- **GitHub 桥接**：手机角色 git push autoforensicai_data → 主机临时解除 hosts 屏蔽 git pull → 用 `import_yaml_to_hub.py` 导入
- **手动应急**：手机角色导出 JSON 通过聊天工具发给用户，用户贴给你批量 POST

### 2. 实战监控（持续做）
每隔几分钟拉一次 Hub 看变化：
```powershell
$Hub = "http://127.0.0.1:8765"
Invoke-RestMethod "$Hub/progress"
Invoke-RestMethod "$Hub/findings" | Select-Object -Last 5
Invoke-RestMethod "$Hub/session" | Select-Object -ExpandProperty blockers
```

### 3. 答案表维护（你的核心职责）
角色只管交 findings，**主设计师从 findings 提取答案**写入 `shared/answers.yaml`：
```powershell
# 例：把 F-S006 ngrok 域名写成互联网Q3答案
$body = @{
    category = "internet_forensics"
    qid = "Q3"
    question = "ngrok提供的域名为？"
    answer = "blemish-junior-unengaged.ngrok-free.dev"
    confidence = "high"
    source_role = "server_analyst"
    evidence = "F-S006"
} | ConvertTo-Json
Invoke-RestMethod "$Hub/answers" -Method POST -Body $body -ContentType "application/json"
```

### 4. 解决 server B001 卡点
B001: VG volum / LV root PE 数据全零，需要 WSL ewfmount + cryptsetup 解密。
**方案**：你（主设计师）在主机用 WSL 协助。或者把这个 blocker 路由给 binary_analyst（POST /questions）让它分析加密机制。

---

## 🛠️ 关键文件位置一览

```
项目代码：
  e:\项目\自动化取证\tools\collab_hub.py
  e:\项目\自动化取证\tools\import_yaml_to_hub.py
  e:\项目\自动化取证\tests\test_collab_hub.py
  e:\项目\自动化取证\prompts\main.md            # 主设计师 prompt（这是给你的）

Case 数据：
  E:\ffffff-JIANCAI\2026FIC团体赛\case\role_prompt_*.md   # 4 个角色 prompt
  E:\ffffff-JIANCAI\2026FIC团体赛\case\REMOTE_DEPLOYMENT.md
  E:\ffffff-JIANCAI\2026FIC团体赛\case\import_yaml_to_hub.py    # case 内副本，给远程机下载
  E:\ffffff-JIANCAI\2026FIC团体赛\case\shared\
    ├── findings.yaml    # 10 条
    ├── progress.yaml    # 4 角色状态
    ├── blockers.yaml    # 1 条 active
    ├── strategy.yaml    # 主设计师策略
    ├── answers.yaml     # 空（待你维护）
    ├── questions.yaml   # 空
    └── session_log.yaml # 空
```

## 🐛 已修复的 bug 历史（避免重复踩坑）

1. **白名单 403** — `FILE_WHITELIST` 原本不允许 `REMOTE_DEPLOYMENT.md`。已扩展到允许全大写 `.md` 和 `import_*.py`。位置：`tools/collab_hub.py:68`
2. **PowerShell JSON 转义地狱** — 不要用 `curl + -d '{...}'`。一律用 `Invoke-RestMethod + @{} + ConvertTo-Json`，role_prompt 里都已改好。

## ⚠️ 已知限制和注意

1. **手机角色物理隔离** — 它的机器只有 VMware host-only 虚拟网卡，无法直接连主机 LAN。必须用 cloudflared 公网隧道或 GitHub 桥接。
2. **主机 hosts 屏蔽 GitHub** — v2 遗留（防 v2 时代 AI 自动 push）。v3 不依赖 GitHub，用户可以选择永久解除。
3. **cloudflared quick tunnel URL 每次重启都变** — 长期使用考虑配置 named tunnel（需要免费 Cloudflare 账号）。
4. **server 写 yaml 而非调 Hub API** — F-S006/S007 是它直接编辑 yaml 添加的（旧习惯）。Hub 重启时会自动 load yaml，所以数据没丢，但**它没用 Hub API**。下一会话提醒它用 `Invoke-RestMethod $Hub/findings -Method POST`。

---

## 📋 立即可做的下一步（推荐顺序）

1. **看 Hub 是否还在跑**：`Invoke-RestMethod http://127.0.0.1:8765/ping`
2. **如果 Hub 停了**：`python e:\项目\自动化取证\tools\collab_hub.py serve "E:\ffffff-JIANCAI\2026FIC团体赛\case" --port 8765 --bind 0.0.0.0` （后台启动）
3. **拉一次态势快照**（按 Phase 0 流程）
4. **从已有 findings 提取答案**填入 `shared/answers.yaml`：
   - F-S002 → 服务器Q1: OS = Debian 13 trixie
   - F-S006 → 互联网Q3: ngrok 域名 = blemish-junior-unengaged.ngrok-free.dev
   - F-B001 → 二进制Q1: SampleVC.exe MD5 = 764789dd9c095d74b6b258cf0f7568b2
   - F-B002 → 二进制Q2: 编译日期 = 2026-04-17
5. **决策 cloudflared**：要不要启动？或者改 GitHub 桥接？取决于用户当前态度
6. **持续监控**：binary 的 AES 解密结果（应该会很快出来）→ Q3+Q4 答案

---

## 🎯 验收标准（v3 协作算成功）

- [ ] 4 个角色都通过 Hub 提交至少 1 条 finding（当前 2/4：server, binary）
- [ ] 主设计师 (`answers.yaml`) 收集到至少 5 个题的答案（当前 0/5）
- [ ] 至少 1 次跨角色提问（POST /questions）走通（当前 0）
- [ ] B001 卡点最终被解决（LVM 解密完成或转交其他角色）

---

**最后**：本会话设计哲学严守 Karpathy 准则——简单优先（stdlib only、单文件 Hub）、外科手术式修改（仅替换 4 个 prompt 的协作段，未动其他）、目标驱动执行（每 Phase 都有可验证目标）。下一会话延续这个原则。
