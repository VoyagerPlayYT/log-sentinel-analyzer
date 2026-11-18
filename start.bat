@echo off
chcp 65001 > nul
title Log Sentinel Analyzer [Port 8017]
echo ========================================================
echo   LOG SENTINEL // WEBSOCKET STREAMING & SPIKE ANALYZER
echo ========================================================
echo [INFO] Проверка и установка зависимостей...
python -m pip install -r requirements.txt --quiet
echo [INFO] Запуск FastAPI веб-сервера на http://localhost:8017 ...
start http://localhost:8017
python -m uvicorn main:app --host 0.0.0.0 --port 8017
pause
