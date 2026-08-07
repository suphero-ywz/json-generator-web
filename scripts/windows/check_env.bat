@chcp 65001 >nul
echo ================================
echo  开发环境检查
echo ================================
echo.

set ERROR_FLAG=0

echo [1/4] 检查 Python...
where python >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo   x Python 未安装，请从 https://www.python.org/downloads/ 下载安装
    set ERROR_FLAG=1
) else (
    for /f "tokens=2" %%v in ('python --version 2^>^&1') do echo   v Python %%v
)

echo.
echo [2/4] 检查 Node.js...
where node >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo   x Node.js 未安装，请从 https://nodejs.org/zh-cn/download/ 下载安装
    set ERROR_FLAG=1
) else (
    for /f "tokens=1" %%v in ('node --version 2^>^&1') do echo   v Node.js %%v
)

echo.
echo [3/4] 检查 npm...
where npm >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo   x npm 未安装
    set ERROR_FLAG=1
) else (
    for /f "tokens=1" %%v in ('npm --version 2^>^&1') do echo   v npm %%v
)

echo.
echo [4/4] 检查 Ollama（可选）...
where ollama >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo   - Ollama 未安装（将使用要素池模式）
    echo     如需 LLM 模式，请从 https://ollama.com/download/windows 下载安装
) else (
    for /f "tokens=1" %%v in ('ollama --version 2^>^&1') do echo   v Ollama %%v
    echo   检查 qwen3:4b 模型...
    ollama list 2>nul | findstr "qwen3:4b" >nul
    if %ERRORLEVEL% NEQ 0 (
        echo   - qwen3:4b 模型未下载，运行: ollama pull qwen3:4b
    ) else (
        echo   v qwen3:4b 模型已就绪
    )
)

echo.
echo ================================
if %ERROR_FLAG% EQU 1 (
    echo   检查完毕：存在缺失项，请安装后再继续
) else (
    echo   检查完毕：所有必需环境已就绪
)
echo ================================
pause
