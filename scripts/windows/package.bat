@chcp 65001 >nul
setlocal enabledelayedexpansion

echo ================================
echo  动作数据集 JSON 生成器 - 打包
echo ================================
echo.

set "PROJECT_DIR=%~dp0..\.."
set "PROJECT_DIR=!PROJECT_DIR:~0,-1!"
for %%i in ("!PROJECT_DIR!") do set "PARENT=%%~dpi"
set "PARENT=!PARENT:~0,-1!"
set "PROJECT_NAME=json-generator-web"
set "OUTPUT_ZIP=!PARENT!\!PROJECT_NAME!.zip"

echo   项目目录: !PROJECT_DIR!
echo   输出位置: !OUTPUT_ZIP!
echo.

:: 临时目录
set "TEMP_DIR=!PARENT!\!PROJECT_NAME!_package"
if exist "!TEMP_DIR!" rmdir /s /q "!TEMP_DIR!"
mkdir "!TEMP_DIR!"

echo   复制文件...

:: 复制整个项目（排除不必要的文件）
robocopy "!PROJECT_DIR!" "!TEMP_DIR!" /E /NFL /NDL /NJH /NJS /NC /NS ^
  /XD node_modules __pycache__ .git data ^
  /XF *.pyc .env *.db >nul

:: 确保 data 目录存在但为空
mkdir "!TEMP_DIR!\backend\data" 2>nul

echo   创建 ZIP 压缩包...

:: 使用 PowerShell 压缩
powershell -Command ^
  "Set-Location '!PARENT!';" ^
  "if (Test-Path '!OUTPUT_ZIP!') { Remove-Item '!OUTPUT_ZIP!' -Force };" ^
  "Compress-Archive -Path '!PROJECT_NAME!_package\*' -DestinationPath '!OUTPUT_ZIP!' -Force;" ^
  "Write-Host '   ZIP 创建完成'"

echo.
echo   清理临时文件...
rmdir /s /q "!TEMP_DIR!"

:: 显示文件大小
for %%i in ("!OUTPUT_ZIP!") do set "ZIP_SIZE=%%~zi"
set /a "ZIP_KB=!ZIP_SIZE! / 1024"

echo.
echo ================================
echo   打包完成！
echo ================================
echo.
echo   文件: !OUTPUT_ZIP!
echo   大小: !ZIP_KB! KB
echo.
echo   接收方使用步骤：
echo   Windows:
echo     1. 解压 ZIP 到任意目录
echo     2. 运行 scripts\windows\setup.bat 安装依赖
echo     3. 运行 scripts\windows\start.bat 启动项目
echo   Linux:
echo     1. 解压 ZIP 到任意目录
echo     2. 运行 bash scripts/linux/setup.sh 安装依赖
echo     3. 运行 bash scripts/linux/start.sh 启动项目
echo.
pause
