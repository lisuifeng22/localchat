@echo off
chcp 65001 >nul
cd /d "%~dp0.."

echo [LocalChat] 启动 Web UI...
echo.
echo 如果你使用火山引擎 TTS，不需要启动本地 OmniVoice。
echo 如果你使用本地 OmniVoice，请先手动启动 OmniVoice 的 7862 服务。
echo.
echo 打开 http://localhost:8000 使用
echo 按 Ctrl+C 停止

echo.
python "%~dp0server.py"
pause
