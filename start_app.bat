@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo Project virtual environment was not found.
    echo Create .venv and install requirements.txt first.
    pause
    exit /b 1
)
echo Starting FastAPI backend and Streamlit frontend...
echo Press Ctrl+C in this window to stop both services.
".venv\Scripts\python.exe" src\run_web.py
endlocal
