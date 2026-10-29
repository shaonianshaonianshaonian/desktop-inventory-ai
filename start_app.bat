@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo Project virtual environment was not found.
    echo Create .venv and install requirements.txt first.
    pause
    exit /b 1
)

curl.exe --silent --fail http://127.0.0.1:11434/api/tags >nul
if errorlevel 1 (
    echo Cannot connect to local Ollama. Start Ollama and try again.
    pause
    exit /b 1
)

echo Starting the local comparison dashboard...
echo Press Ctrl+C in this window to stop the server.
".venv\Scripts\python.exe" -m streamlit run app.py

endlocal
