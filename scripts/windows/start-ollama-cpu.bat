@echo off
chcp 65001 >nul
title Ollama 启动器（GPU 模式）
echo ================================
echo   Ollama 启动（GPU 模式）
echo ================================
echo.
echo   说明：CUDA 崩溃问题（0xc0000409）已在驱动 595.97 下修复，
echo   本脚本以 GPU 模式启动 Ollama（RTX 4060 全 GPU 推理）。
echo.

set OLLAMA_DIR=%LOCALAPPDATA%\Programs\Ollama

if not exist "%OLLAMA_DIR%\ollama.exe" (
    echo   [错误] 未找到 Ollama，请从 https://ollama.com/download/windows 安装
    echo   并运行: ollama pull Qwen3-8B
    pause
    exit /b 1
)

echo [1/3] 停止现有 Ollama（如有）...
taskkill /F /IM "ollama.exe" >nul 2>&1
taskkill /F /IM "ollama app.exe" >nul 2>&1
timeout /t 2 /nobreak >nul

echo [2/3] 以 GPU 模式启动 Ollama...
start "" "%OLLAMA_DIR%\ollama.exe" serve

echo [3/3] 等待服务就绪...
set /a TRIES=0
:waitloop
timeout /t 2 /nobreak >nul
curl -s -m 2 http://127.0.0.1:11434/api/tags >nul 2>&1
if %ERRORLEVEL% EQU 0 goto ready
set /a TRIES+=1
if %TRIES% LSS 15 goto waitloop
echo   [警告] 等待超时，Ollama 可能启动失败，请检查日志
pause
exit /b 1

:ready
echo.
echo   ✓ Ollama 已就绪（GPU 模式）
echo.
echo   现在可双击 start.bat 启动生成器，
echo   生成模式选「LLM 模式」、大模型选「Ollama · Qwen3-8B」。
echo.
echo   提示：此窗口可以关闭，Ollama 会继续在后台运行。
echo.
pause
