@echo off
chcp 65001 >nul

echo [LocalChat] 启动 OmniVoice TTS 服务...
cd /d "D:\OmniVoice"
set HF_ENDPOINT=https://hf-mirror.com
set HF_HOME=%cd%\hf_download
set TORCH_HOME=%cd%\cache
start /min "OmniVoice" "D:\OmniVoice\py312\python.exe" -s app.py

echo [LocalChat] 等待 OmniVoice 加载模型（约 60 秒）...
:wait_omni
timeout /t 5 /nobreak >nul
curl -s -o nul http://localhost:7862/ 2>nul
if errorlevel 1 goto wait_omni

echo [LocalChat] OmniVoice 已就绪，启动 Web UI...
echo     打开 http://localhost:8000 使用
echo     按 Ctrl+C 停止
echo.
cd /d "%~dp0.."
"C:\Users\19613\AppData\Local\Programs\Python\Python311\python.exe" "%~dp0server.py"
