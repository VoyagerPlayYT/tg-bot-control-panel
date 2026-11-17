@echo off
chcp 65001 > nul
title Telegram Bot Control Panel
echo ========================================================
echo   Telegram Bot Control Panel & Orchestration Hub
echo ========================================================
echo [INFO] Запуск панели управления ботом на http://localhost:8004 ...
start http://localhost:8004
python -m uvicorn main:app --host 0.0.0.0 --port 8004
pause
