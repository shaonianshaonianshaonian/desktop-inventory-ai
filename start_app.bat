@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo Project virtual environment was not found.
    echo Create .venv and install requirements.txt first.
    pause
    exit /b 1
)
echo Starting FastAPI, Celery worker and Streamlit...
echo Redis must already be running. Press Ctrl+C to stop local services.
".venv\Scripts\python.exe" src\run_web.py
endlocal
