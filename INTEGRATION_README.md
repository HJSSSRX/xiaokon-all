# 🤖 ForHacker + Claude Code - 整合配置

## ✅ 已完成配置

| 项目 | 状态 |
|------|------|
| ForHacker 仓库 | ✅ `D:\ai` |
| Claude Code 安装 | ✅ 2.1.143 |
| DeepSeek API Key | ✅ 已配置 |
| 小空主提示词 | ✅ `CLAUDE.md` |
| 启动脚本 | ✅ `启动小空.bat` / `启动小空.ps1` |

## 🚀 启动方式

### 方式一：双击启动
直接双击运行 `启动小空.bat`

### 方式二：PowerShell
```powershell
cd D:\ai
.\启动小空.ps1
```

### 方式三：手动启动
```powershell
cd D:\ai
$env:Path = "D:\nodejs;C:\Users\Lenovo\AppData\Roaming\npm;" + $env:Path
$env:CLAUDE_CODE_GIT_BASH_PATH = "D:\git\Git\bin\bash.exe"
claude
```

## 🎯 快捷指令

| 指令 | 功能 |
|------|------|
| **"小空自己动"** | 激活主设计师模式 |
| **"小空自己托"** | 激活喂食者模式 |

## 📁 项目结构

```
D:\ai\
├── CLAUDE.md                    # Claude Code 项目配置
├── 启动小空.bat / 启动小空.ps1 # 启动脚本
├── prompts\
│   ├── main.md                  # 主设计师提示词
│   └── roles\                   # 专家角色提示词
├── tools\                       # CLI 工具链
├── knowledge\                   # 知识库
└── .claude\                     # Claude Code 配置
```

## 🔧 配置文件

| 配置项 | 位置 |
|--------|------|
| 全局 Claude 配置 | `C:\Users\Lenovo\.claude\settings.json` |
| 项目级配置（可选） | `D:\ai\.claude\settings.local.json` |

## 💡 首次使用

1. **启动 Claude Code**：运行 `启动小空.bat`
2. **激活小空**：说 "小空自己动"
3. **选择模式**：比赛/训练/灌知识/教育/顾问

## 📚 参考文档

- `README.md` - 项目总览
- `DEPLOY.md` - 部署指南
- `TRAINING.md` - 训练模式说明
- `TOOLCHAIN.md` - 工具链文档
