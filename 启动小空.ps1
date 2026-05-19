Write-Host "============================================" -ForegroundColor Cyan
Write-Host "  ForHacker + Claude Code - 启动小空" -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan
Write-Host ""

# 设置环境变量
$env:Path = "D:\nodejs;C:\Users\Lenovo\AppData\Roaming\npm;" + $env:Path
$env:CLAUDE_CODE_GIT_BASH_PATH = "D:\git\Git\bin\bash.exe"

Write-Host "工作目录: $(Get-Location)" -ForegroundColor Gray
Write-Host ""
Write-Host "启动 Claude Code..." -ForegroundColor Yellow
Write-Host ""
Write-Host "============================================" -ForegroundColor Gray
Write-Host ""
Write-Host "快捷指令:" -ForegroundColor White
Write-Host "  `"小空自己动`"  - 激活主设计师" -ForegroundColor Gray
Write-Host "  `"小空自己托`"  - 激活喂食者" -ForegroundColor Gray
Write-Host ""
Write-Host "============================================" -ForegroundColor Gray
Write-Host ""

# 启动 Claude Code
claude
