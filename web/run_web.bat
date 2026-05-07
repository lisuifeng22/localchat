@echo off
chcp 65001 >nul
echo 🌐 启动 Local AI Chat Web UI...
echo    打开 http://localhost:8000 使用
echo    按 Ctrl+C 停止
echo.
"C:\Users\19613\AppData\Local\Programs\Python\Python311\python.exe" "%~dp0server.py"
