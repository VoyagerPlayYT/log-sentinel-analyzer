@echo off
chcp 65001 > nul
title Log Sentinel Analyzer [Port 8017]
echo ========================================================
echo   LOG SENTINEL ANALYZER [PORT 8017]
echo ========================================================

if exist "C:\Python313\python.exe" (
    set "PY=C:\Python313\python.exe"
) else (
    set "PY=python"
)

echo [INFO] Проверка и освобождение порта 8017...
for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":8017" ^| findstr "LISTENING"') do taskkill /f /pid %%a >nul 2>&1

echo [INFO] Запуск веб-сервера на http://localhost:8017 ...
start "" cmd /c "timeout /t 2 /nobreak >nul && start http://localhost:8017"

cd /d "%~dp0"
"%PY%" -m uvicorn main:app --host 127.0.0.1 --port 8017
pause
