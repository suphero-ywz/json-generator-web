$host.UI.RawUI.WindowTitle = "动作数据集 JSON 生成器"
$dir = Resolve-Path "$PSScriptRoot\..\.."

$beProc = $null
$feProc = $null

function Cleanup {
    Write-Host "`n  停止服务..." -NoNewline
    if ($beProc -and !$beProc.HasExited) { $beProc.Kill(); $beProc.Dispose() }
    if ($feProc -and !$feProc.HasExited) { $feProc.Kill(); $feProc.Dispose() }
    Get-Process python -EA 0 | ? { $_.Id -ne $PID } | Stop-Process -Force -EA 0
    Get-Process node  -EA 0 | ? { $_.Id -ne $PID } | Stop-Process -Force -EA 0
    Write-Host " 完成"
    Start-Sleep 1
}

function Check($url) {
    try { Invoke-WebRequest $url -TimeoutSec 3 -UseBasicParsing | Out-Null; return $true } catch { return $false }
}

try {
    # ---- 首次运行 ----
    $needSetup = $false
    if (-not (Test-Path "$dir\frontend\node_modules")) { $needSetup = $true }
    if ($needSetup) {
        Write-Host "  首次运行 - 需要先安装依赖，请稍候..."
        cmd /c "call `"$PSScriptRoot\setup.bat`""
        # setup.bat exit code 0=OK, 2=winget安装成功需重新运行
        if ($LASTEXITCODE -eq 2) {
            Write-Host "  环境安装完成，请重新双击 start.bat" -ForegroundColor Yellow
            Read-Host "  按 Enter 退出"
            exit 0
        }
        if ($LASTEXITCODE -ne 0) { Read-Host "  安装失败，按 Enter 退出"; exit 1 }
    }

    # 检查 Python 依赖
    python -c "import fastapi" 2>$null
    if ($LASTEXITCODE -ne 0) {
        Write-Host "  Python 依赖未安装，正在安装..." -ForegroundColor Yellow
        python -m pip install -r "$dir\backend\requirements.txt" -q 2>&1
        if ($LASTEXITCODE -ne 0) {
            Write-Host "  Python 依赖安装失败，请手动运行 setup.bat" -ForegroundColor Red
            Read-Host "  按 Enter 退出"
            exit 1
        }
    }

    if (-not (Test-Path "$dir\backend\data")) {
        New-Item -ItemType Directory -Path "$dir\backend\data" -Force | Out-Null
    }

    # 清理旧进程
    Get-Process python -EA 0 | ? { $_.Id -ne $PID } | Stop-Process -Force -EA 0
    Get-Process node  -EA 0 | ? { $_.Id -ne $PID } | Stop-Process -Force -EA 0
    Start-Sleep 1

    # ---- 启动服务 ----
    Write-Host ""
    Write-Host "  正在启动服务..." -ForegroundColor DarkGray

    $beProc = Start-Process python -Arg "main.py" -WorkingDirectory "$dir\backend" -WindowStyle Hidden -PassThru
    $feProc = Start-Process cmd   -Arg "/c npx vite --host" -WorkingDirectory "$dir\frontend" -WindowStyle Hidden -PassThru

    # ---- 等待就绪 ----
    Write-Host "  等待服务就绪..." -ForegroundColor DarkGray
    $okBe = $false; $okFe = $false; $n = 0

    while (-not ($okBe -and $okFe)) {
        Start-Sleep 1; $n++

        if (-not $okBe) { $okBe = Check "http://localhost:8000/api/status" }
        if (-not $okFe) { $okFe = Check "http://localhost:5173" }

        $beStr = if ($okBe) { "OK" } else { "..." }
        $feStr = if ($okFe) { "OK" } else { "..." }
        Write-Host "`r  Backend $beStr  |  Frontend $feStr  |  $($n)s" -NoNewline

        if ($n -ge 30) {
            Write-Host "`n  启动超时，请确认已运行 setup.bat 安装依赖"
            $ans = Read-Host "  继续等待?(Y/N)"
            if ($ans -notmatch "^(y|Y)") { exit 1 }
            $n = 0
        }
    }

    # ---- 就绪面板 ----
    Write-Host ""
    Write-Host ""
    Write-Host "  Backend   http://localhost:8000/docs" -ForegroundColor Cyan
    Write-Host "  Frontend  http://localhost:5173" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "  ● 服务运行中  |  Ctrl+点击链接打开  |  Ctrl+C 停止" -ForegroundColor Green

    # ---- 持续监控 ----
    while ($true) {
        Start-Sleep 5
        $okBe = Check "http://localhost:8000/api/status"
        $okFe = Check "http://localhost:5173"
        $beStr = if ($okBe) { "OK" } else { "!!" }
        $feStr = if ($okFe) { "OK" } else { "!!" }
        $beCol = if ($okBe) { "DarkGray" } else { "Red" }
        $feCol = if ($okFe) { "DarkGray" } else { "Red" }
        Write-Host "`r  Backend " -NoNewline
        Write-Host $beStr -NoNewline -ForegroundColor $beCol
        Write-Host "  |  Frontend " -NoNewline
        Write-Host $feStr -NoNewline -ForegroundColor $feCol
    }
}
catch {
    Write-Host "`n  ERROR: $_" -ForegroundColor Red
    Read-Host "  按 Enter 退出"
}
finally {
    Cleanup
}
