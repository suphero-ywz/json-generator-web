$ErrorActionPreference = "Stop"
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$projectDir = Resolve-Path "$scriptDir\..\.."
$projectName = Split-Path -Leaf $projectDir
$parentDir = Split-Path -Parent $projectDir
$outputZip = "$parentDir\$projectName.zip"
$tempDir = "$parentDir\$projectName-package"

Write-Host "================================`n 动作数据集 JSON 生成器 — 打包`n================================"
Write-Host "  项目目录: $projectDir"
Write-Host "  输出位置: $outputZip`n"

# 清理
if (Test-Path $tempDir) { Remove-Item $tempDir -Recurse -Force }
if (Test-Path $outputZip) { Remove-Item $outputZip -Force }

# 创建临时目录
New-Item -ItemType Directory -Path $tempDir -Force | Out-Null

# 复制文件（排除不必要的内容）
Write-Host "  复制文件..."
robocopy $projectDir $tempDir /E /NFL /NDL /NJH /NJS /NC /NS `
  /XD node_modules __pycache__ .git .claude data `
  /XF *.pyc .env *.db

# 确保 data 目录存在但为空
New-Item -ItemType Directory -Path "$tempDir\backend\data" -Force | Out-Null

# 创建 .env.example
@"
# ===== 云端模式（默认）=====
# DeepSeek API Key，注册地址：https://platform.deepseek.com
DEEPSEEK_API_KEY=

# ===== 本地模式（可选，配合 Ollama，不消耗 API token）=====
# 使用步骤：
#   1. 安装 Ollama 并拉取小模型：ollama pull qwen3:8b
#   2. 取消下面两行注释，保存为 .env，重新启动项目
# DEEPSEEK_API_BASE=http://127.0.0.1:11434/v1
# DEEPSEEK_MODEL=qwen3:8b
"@ | Out-File -FilePath "$tempDir\backend\.env.example" -Encoding UTF8

# 压缩
Write-Host "  压缩中..."
Compress-Archive -Path "$tempDir\*" -DestinationPath $outputZip -Force

# 清理
Remove-Item $tempDir -Recurse -Force

# 显示结果
$zip = Get-Item $outputZip
Write-Host "`n================================`n  打包完成！`n================================"
Write-Host "  文件: $($zip.Name)"
Write-Host "  大小: $([math]::Round($zip.Length/1KB, 1)) KB"
Write-Host "`n  接收方使用步骤："
Write-Host "  Windows:"
Write-Host "    1. 解压 ZIP 到任意目录"
Write-Host "    2. 运行 scripts\windows\setup.bat 安装依赖"
Write-Host "    3. 运行 scripts\windows\start.bat 启动项目"
Write-Host "  Linux:"
Write-Host "    1. 解压 ZIP 到任意目录"
Write-Host "    2. 运行 bash scripts/linux/setup.sh 安装依赖"
Write-Host "    3. 运行 bash scripts/linux/start.sh 启动项目"
