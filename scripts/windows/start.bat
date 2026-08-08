@chcp 65001 >nul
@powershell -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0start.ps1"
@if %ERRORLEVEL% NEQ 0 pause
