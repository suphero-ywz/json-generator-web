@chcp 65001 >nul
setlocal enabledelayedexpansion
echo ================================
echo  动作数据集 JSON 生成器 - 安装
echo ================================
echo.

set ERROR_FLAG=0

:: 检查 winget 是否可用
set WINGET_OK=0
where winget >nul 2>&1 && set WINGET_OK=1

:: === Python 检查 ===
echo [1/3] 检查 Python...
where python >nul 2>&1
if !ERRORLEVEL! NEQ 0 (
    call :install_python
    if !ERRORLEVEL! EQU 2 exit /b 0
) else (
    for /f "tokens=2" %%v in ('python --version 2^>^&1') do echo   v Python %%v
)

:: === Node.js 检查 ===
echo.
echo [2/3] 检查 Node.js...
where node >nul 2>&1
if !ERRORLEVEL! NEQ 0 (
    call :install_node
    if !ERRORLEVEL! EQU 2 exit /b 0
) else (
    for /f "tokens=1" %%v in ('node --version 2^>^&1') do echo   v Node.js %%v
)

if !ERROR_FLAG! EQU 1 (
    echo.
    echo ================================
    echo   请先安装缺失的环境后重新运行
    echo ================================
    pause
    exit /b 1
)

:: === 安装依赖 ===
echo.
echo [3/3] 安装项目依赖...

echo   安装 Python 依赖...
cd /d "%~dp0..\..\backend"
python -m pip install -r requirements.txt -q
if !ERRORLEVEL! NEQ 0 (
    echo   x Python 依赖安装失败，正在重试...
    python -m pip install -r requirements.txt -q --default-timeout=60
    if !ERRORLEVEL! NEQ 0 (
        echo   x Python 依赖安装失败，请检查网络连接后重试
        pause
        exit /b 1
    )
)
echo   v Python 依赖安装完成

echo   安装 Node.js 依赖...
cd /d "%~dp0..\..\frontend"
call npm install --silent
if !ERRORLEVEL! NEQ 0 (
    echo   x npm 依赖安装失败，正在重试...
    call npm install
    if !ERRORLEVEL! NEQ 0 (
        echo   x npm 依赖安装失败，请检查网络连接后重试
        pause
        exit /b 1
    )
)
echo   v npm 依赖安装完成

:: === 完成 ===
echo.
echo ================================
echo   安装完成！请运行 start.bat 启动
echo ================================
echo.
echo   默认使用「要素池模式」，无需额外配置。
echo   如需启用 LLM 模式，请在 backend 目录下创建 .env 文件：
echo     DEEPSEEK_API_KEY=你的API密钥
echo   注册地址：https://platform.deepseek.com
echo.
pause
goto :eof

:: ==========================================
::  子程序：安装 Python
:: ==========================================
:install_python
echo   x Python 未安装
if !WINGET_OK! EQU 1 (
    echo   正在通过 winget 自动下载安装 Python...
    echo.
    winget install Python.Python.3.10 --accept-package-agreements --accept-source-agreements
    if !ERRORLEVEL! EQU 0 (
        echo.
        echo   v Python 安装完成！
        echo.
        echo   请关闭此窗口，重新双击 setup.bat 继续安装依赖。
        pause
        exit /b 2
    )
    echo   x winget 安装失败，尝试打开下载页面...
)
echo   正在打开 Python 下载页面...
start "" https://www.python.org/downloads/
echo   请下载安装后重新运行 setup.bat（安装时勾选 "Add Python to PATH"）
set ERROR_FLAG=1
goto :eof

:: ==========================================
::  子程序：安装 Node.js
:: ==========================================
:install_node
echo   x Node.js 未安装
if !WINGET_OK! EQU 1 (
    echo   正在通过 winget 自动下载安装 Node.js LTS...
    echo.
    winget install OpenJS.NodeJS.LTS --accept-package-agreements --accept-source-agreements
    if !ERRORLEVEL! EQU 0 (
        echo.
        echo   v Node.js 安装完成！
        echo.
        echo   请关闭此窗口，重新双击 setup.bat 继续安装依赖。
        pause
        exit /b 2
    )
    echo   x winget 安装失败，尝试打开下载页面...
)
echo   正在打开 Node.js 下载页面...
start "" https://nodejs.org/zh-cn/download/
echo   请下载 LTS 版本安装后重新运行 setup.bat
set ERROR_FLAG=1
goto :eof
