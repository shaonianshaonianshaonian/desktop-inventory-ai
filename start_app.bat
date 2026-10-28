@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo 未找到项目虚拟环境，请先创建 .venv 并安装 requirements.txt。
    pause
    exit /b 1
)

curl --silent --fail http://127.0.0.1:11434/api/tags >nul
if errorlevel 1 (
    echo 无法连接本机 Ollama，请先启动 Ollama。
    pause
    exit /b 1
)

echo 正在启动桌面物品双方案对比界面...
echo 关闭服务请在此窗口按 Ctrl+C。
".venv\Scripts\python.exe" -m streamlit run app.py

endlocal
