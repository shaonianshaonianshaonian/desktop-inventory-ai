"""同时启动 FastAPI 后端与 Streamlit 前端。"""

import os
from pathlib import Path
import subprocess
import sys
import time

import requests


ROOT = Path(__file__).resolve().parents[1]
API_URL = "http://127.0.0.1:8000/api/health"


def stop_process(process: subprocess.Popen | None) -> None:
    if process is not None and process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()


def wait_for_api(process: subprocess.Popen) -> None:
    for _ in range(60):
        if process.poll() is not None:
            raise RuntimeError("FastAPI 后端启动失败")
        try:
            response = requests.get(API_URL, timeout=1)
            if response.ok:
                return
        except requests.RequestException:
            pass
        time.sleep(0.5)
    raise RuntimeError("等待 FastAPI 后端启动超时")


def main() -> None:
    environment = os.environ.copy()
    environment["PYTHONUTF8"] = "1"
    environment.setdefault("API_BASE_URL", "http://127.0.0.1:8000")
    api_process = None
    web_process = None
    try:
        api_process = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "uvicorn",
                "backend.main:app",
                "--host",
                "127.0.0.1",
                "--port",
                "8000",
            ],
            cwd=ROOT,
            env=environment,
        )
        wait_for_api(api_process)
        print("FastAPI backend: http://127.0.0.1:8000/docs", flush=True)
        web_process = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "streamlit",
                "run",
                "app.py",
            ],
            cwd=ROOT,
            env=environment,
        )
        web_process.wait()
    except KeyboardInterrupt:
        print("\nStopping local web project...", flush=True)
    finally:
        stop_process(web_process)
        stop_process(api_process)


if __name__ == "__main__":
    main()
