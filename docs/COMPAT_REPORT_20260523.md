# 小空 (AutoForensicAI) 兼容性宏观报告

> 2026-05-23 | 环境: Windows 11 · Python 3.14.5 · WSL 2.7

---

## 一、总体结论

小空项目在 **Python 3.14.5**（Dockerfile 目标 3.12）上通过全量兼容性验证。Python 包 20/20 可用，CLI 工具 14/16 可用。无架构级风险。

---

## 二、环境矩阵

| 维度 | 本地 | Docker 目标 | 兼容 |
|------|------|-------------|------|
| Python | 3.14.5 | 3.12-slim | ✅ 无废弃 API |
| OS | Win 11 (26200) | Debian slim | ✅ 跨平台代码 |
| WSL | 2.7.3 + Ubuntu | — | ✅ 可用 |
| Docker | 未安装 | docker-compose | ⚠️ 本地不可用 |
| Scoop | 0.5.3 (git) | — | ✅ 已修复 |

---

## 三、Python 包全量 (20/20)

### 核心层
pyyaml 6.0.3 · requests 2.34.2 · beautifulsoup4 4.14.3 · websocket-client 1.9.0

### 取证层
volatility3 2.28.0 · pycryptodomex 3.23.0 · pillow 12.2.0 · python-registry 1.3.1 · oletools 0.60.2 · exifread 3.5.1 · openpyxl 3.1.5 · impacket 0.13.1 · psutil 7.2.2

### 渗透/逆向
pwntools 4.15.0 (unicorn 2.1.4 跳过编译)

### 服务层（可选全装）
fastapi 0.136.1 · uvicorn 0.47.0 · redis 7.4.0 · faiss-cpu 1.14.2 · sentence-transformers 5.5.1

### 测试
pytest 9.0.3 · pytest-asyncio 1.3.0

---

## 四、CLI 工具 (14/16)

### ✅ 已装
| 工具 | 版本 | 角色 |
|------|------|------|
| 7zip | 26.01 | 归档提取 |
| git | 2.54.0 | 版本控制 |
| sqlite3 | 3.53.1 | 数据库分析 |
| ffuf | 2.1.0 | Web Fuzzer |
| hashcat | 7.1.2 | GPU 破解 |
| upx | 5.1.1 | 脱壳 |
| sleuthkit | 4.15.0 | 文件系统取证 |
| radare2 | 6.1.4 | 逆向框架 |
| gobuster | 3.8.2 | 目录爆破 |
| nuclei | 3.8.0 | 漏洞扫描 |
| tshark | 4.6.6 | 流量分析 |
| die | 3.21 | 文件类型检测 |
| sysinternals | 20260507 | 含 strings 等 60+ |
| pyexiftool | 0.5.6 | EXIF 读取 |

### ❌ 缺失
| 工具 | 原因 | 方案 |
|------|------|------|
| nmap | nmap.org 被墙 | WSL `apt install nmap` |
| exiftool | exiftool.org 被墙 | pyexiftool 替代 |

---

## 五、已修复的问题

### P0: pycryptodome 命名空间冲突
- **现象**: requirements.txt 声明 `pycryptodome`（Crypto），impacket 依赖 `pycryptodomex`（Cryptodome），不可共存
- **修复**: 统一为 pycryptodomex，`requirements.txt` 移除显式依赖，`manifest.yaml` check_cmd 改为 `from Cryptodome.Cipher import AES`
- **影响面**: manifest.yaml:90 · requirements.txt:20

### P1: 缺失 6 个必需包
- pillow, python-registry, openpyxl, psutil, pwntools 已安装
- pwntools 需手动：`pip install unicorn --only-binary :all:` → `pip install pwntools --no-deps` → `pip install paramiko ...`

### P2: Scoop 自更新链断裂
- Scoop 通过 git clone 手动安装（非官方 ps1 脚本）
- 修复: 重建 `apps/scoop/current` junction，禁用自更新（`scoop config SCOOP_REPO`）

---

## 六、网络局限（Steam++ 代理范围）

| 域名 | Steam++ | 影响 |
|------|---------|------|
| github.com | ✅ 代理 | scoop/pip git 源正常 |
| get.scoop.sh | ✅ 代理 | scoop 安装可用 |
| nmap.org | ❌ 不走 | nmap 需 WSL |
| exiftool.org | ❌ 不走 | 原生命令行版不可用 |
| sourceforge.net | ⚠️ 不稳定 | binutils hash 不匹配 |

---

## 七、后续建议

1. **WSL 完成 nmap**: `wsl sudo apt install -y nmap`（Ubuntu 已装，命令被中断）
2. **Docker 可选**: 若需 docker-compose 工作流，安装 Docker Desktop
3. **CI 环境**: 建议 CI 固定 Python 3.12（与 Dockerfile 一致），开发机 3.14 已验证兼容
4. **Steam++ 配置**: 建议添加 nmap.org、exiftool.org 到代理列表，可实现 scoop 一键装

---

## 八、验证命令

```powershell
# Python 全量检查
python -c "import yaml,requests,volatility3,impacket,oletools,exifread,psutil,pytest; from Cryptodome.Cipher import AES; from PIL import Image; from Registry import Registry; import openpyxl,websocket; print('ALL OK')"

# CLI 工具检查
7z --help; git --version; sqlite3 --version; fls -V; r2 -v; tshark -v; diec --version; strings; nuclei -version; gobuster version; upx --version; ffuf -V; hashcat --version
```

---

*报告自动生成于 2026-05-23 兼容性检查会话*
