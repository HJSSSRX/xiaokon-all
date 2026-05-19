Write-Host "============================================" -ForegroundColor Cyan
Write-Host "  ForHacker + Claude Code - 启动小空" -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan
Write-Host ""

# Auto-detect Node.js and Git Bash from PATH
$nodePath = (Get-Command node -ErrorAction SilentlyContinue).Source
if ($nodePath) { $env:Path = (Split-Path $nodePath) + ";" + $env:Path }
$bashPath = (Get-Command bash -ErrorAction SilentlyContinue).Source
if ($bashPath) { $env:CLAUDE_CODE_GIT_BASH_PATH = $bashPath }

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
