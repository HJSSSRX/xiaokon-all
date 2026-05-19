@echo off
echo ============================================
echo   ForHacker + Claude Code - 启动小空
echo ============================================
echo.

REM 切换到项目目录
cd /d "%~dp0"

REM 设置环境变量
set PATH=D:\nodejs;C:\Users\Lenovo\AppData\Roaming\npm;%PATH%
set CLAUDE_CODE_GIT_BASH_PATH=D:\git\Git\bin\bash.exe

echo 工作目录: %CD%
echo.
echo 启动 Claude Code...
echo.
echo ============================================
echo.
echo 快捷指令：
echo   "小空自己动"  - 激活主设计师
echo   "小空自己托"  - 激活喂食者
echo.
echo ============================================
echo.

REM 启动 Claude Code
claude

pause
