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

# 复制文件（排除不必要的内容：依赖、构建产物、源码管理、个人配置、内部文档、运行数据）
Write-Host "  复制文件..."
robocopy $projectDir $tempDir /E /NFL /NDL /NJH /NJS /NC /NS `
  /XD node_modules __pycache__ .git .claude .vscode data dist 开发流程 `
  /XF *.pyc .env *.db *.log

# 确保 data 目录存在但为空（运行时生成）
New-Item -ItemType Directory -Path "$tempDir\backend\data" -Force | Out-Null

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
Write-Host "  已包含: README.md（使用说明）、LICENSE、backend\.env.example"
Write-Host "`n  接收方使用步骤："
Write-Host "  Windows:"
Write-Host "    1. 解压 ZIP 到任意目录"
Write-Host "    2. 运行 scripts\windows\setup.bat 安装依赖"
Write-Host "    3. 运行 scripts\windows\start.bat 启动项目"
Write-Host "  Linux:"
Write-Host "    1. 解压 ZIP 到任意目录"
Write-Host "    2. 运行 bash scripts/linux/setup.sh 安装依赖"
Write-Host "    3. 运行 bash scripts/linux/start.sh 启动项目"
