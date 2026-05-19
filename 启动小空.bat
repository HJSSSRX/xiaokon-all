@echo off
echo ============================================
echo   ForHacker + Claude Code - 启动小空
echo ============================================
echo.

REM 切换到项目目录
cd /d "%~dp0"

REM Auto-detect Node.js and Git Bash from PATH
for %%i in (node.exe) do set "NODE_DIR=%%~dp$PATH:i"
if defined NODE_DIR set "PATH=%NODE_DIR%;%PATH%"

for %%i in (bash.exe) do set "BASH_PATH=%%~$PATH:i"
if defined BASH_PATH set "CLAUDE_CODE_GIT_BASH_PATH=%BASH_PATH%"

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
