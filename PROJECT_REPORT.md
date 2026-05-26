# 小空项目整体报告

**生成日期**: 2026-05-26 | **版本**: v3.5+ | **仓库**: [xiaokon-plus](https://github.com/wwyhji/xiaokon-plus)

---

## 项目概览

小空是网络攻防多 AI 角色协作平台，覆盖取证+攻防双端视角，按能力域组织知识体系。

| 指标 | 数值 |
|------|------|
| 源码文件 | 603 tracked |
| Python 代码 | ~49,000 行 |
| 子包数 | 18 |
| 测试用例 | 370 |
| 测试通过率 | 100% |
| 项目体积 | 215 MB |

## 知识域覆盖（11 域）

| 领域 | 文件数 | 地位 |
|------|--------|------|
| mobile | 39 | ★★★★★ 极强 |
| computer | 15 | ★★★★ 强 |
| cloud | 7 | ★★★ 中等 |
| crypto | 7 | ★★★ 中等 |
| iot | 7 | ★★★ 中等 |
| server | 7 | ★★★ 中等 |
| stego_crypto | 7 | ★★★ 中等 |
| misc | 6 | ★★★ 中等 |
| binary | 5 | ★★ 下限 |
| network | 5 | ★★ 下限 |
| web | 5 | ★★ 下限 |

**已解题库**: 23 个 solved cases（含长安杯/FIC/平航杯等赛事复盘）

## 工具链架构（18 子包）

```
tools/
├── analytics/     — Apriori, FCA, NCD, 因果推断, 不变量, 群论, 宏观报告
├── decomposer/    — 自动分解, 执行引擎, 分配器, Boost超频, 证据分类器
├── kb/            — 知识库搜索, 构建, 同步, Feeder爬取
├── forensics/     — E01/VMDK/ZFS 读取, 内存取证, 磁盘工具
├── collab/        — HTTP Hub (8765), 同步, 冲突解决
├── vision/        — OCR (Tesseract), 思维导图解析
├── competition/   — 题目解析, 答案对比, 格式检查
├── feeder/        — 知识摄入引擎
├── browser/       — JS渲染 (Chrome CDP), API提取
├── pcap/          — 流量分析
├── hub/           — 导入, 检查, 线索, 角色日志
├── integration/   — 火眼MCP适配器, 远程存活探测
├── core/          — HTTP基础, YAML, 缓存, ID生成
├── dev/           — 布局检测, 监控
├── shared/        — 共享数据
├── bin/           — nuclei等外部工具
├── _archived/     — 历史一次性脚本 (37个)
```

## 角色体系（11角色）

| 角色 | 领域 | Prompt |
|------|------|--------|
| computer_analyst | 计算机取证 | ✓ |
| mobile_analyst | 移动端 | ✓ |
| server_analyst | 服务端/Web | ✓ |
| network_analyst | 网络/流量 | ✓ |
| binary_analyst | 二进制/逆向 | ✓ |
| stego_crypto_analyst | 隐写+密码 | ✓ |
| web_pentester | Web渗透 | ✓ |
| misc_analyst | 杂项/通用 | ✓ |
| crypto_analyst | 密码学专精 | ✓ |
| pwn_exploiter | 漏洞利用 | ✓ |
| reverse_engineer | 逆向工程 | ✓ |

## 核心分析套件

| 模块 | 行数 | 功能 |
|------|------|------|
| causality.py | ~920 | 因果图, 逆向推理, 反事实, 根因分析 |
| macro_report.py | ~1175 | 6维整合报告 (Apriori+FCA+NCD+Propagation+Causal) |
| invariant.py | ~600 | 数学不变量检测, 轨道分解, 跨域同构 |
| apriori.py | ~300 | 频繁项集+关联规则挖掘 |
| grouptheory.py | ~400 | 群论结构分析 |
| ncd.py | ~200 | 归一化压缩距离聚类 |
| boost.py | ~572 | 弱模型6步超频流水线 |
| allocator.py | ~350 | 9维加权评分, 动态优先级 |
| decomposer_engine.py | ~530 | 18域关键词矩阵, Kahn拓扑排序 |
| evidence_classifier.py | ~250 | 40+扩展名+27魔术字节签名 |

## 协作系统

- **Hub**: HTTP 协议 (端口 8765), 多角色协作, v3 协议
- **答案同步**: 冲突解决, YAML持久化
- **火眼MCP**: 端口 8862, 工具代理
- **远程**: SSH辅助, 存活探测, 远程推送

## 测试基线

| 测试文件 | 数量 |
|----------|------|
| test_analytics_integration | 40 |
| test_invariant | 140 |
| test_grouptheory | 42 |
| test_llm_loop | 63 |
| test_huoyan_adapter | 16 |
| test_sim_recon | 11 |
| test_ssh_helper | 12 |
| test_comp_search | 9 |
| test_multi_machine | 12 |
| test_vision_smoke | 6 |
| 其他 | 19 |
| **总计** | **370** |

## 三阶段优化记录

| 日期 | 内容 |
|------|------|
| 05-21 | manifest YAML修复, KB补齐 crypto/cloud/iot, 7子包模块化 |
| 05-22 | Decomposer自动分解, 聚焦执行引擎, Boost超频, 9维分配 |
| 05-23 | Domain逻辑评估, Logit捕获, 火眼端口修复, Python 3.14 兼容 |
| 05-24 | 工具链15/15, 测试10/10, 计算机KB 5→10, V3 Hub加固, 11角色, 视觉OCR |
| 05-25 R1 | 四维并行优化: 结构/模块化/检材/工具 |
| 05-25 R2 | Apriori测试修复, 20脚本归档, misc+web补齐, Vision测试, CLAUDE.md同步 |
| 05-26 | 5薄弱域各+2(全11域≥5), _archived审计, misc关键词40+, 邮件类型映射, 新仓建立 |

## 已知差距

- **binary/network/web**: 各仅 5 文件（下限），可各补 2-3 个
- **Vision**: 无 Tesseract 集成测试（需 OCR 环境）
- **_archived/**: 37 个历史脚本，部分可删除
- **mobile 倾斜**: 39 文件占总数 35%，计算机取证仅 15
- **领域标签覆盖率**: ~30%（macro_report 识别的瓶颈）
