"""调用本地视觉模型并组合一次完整分析。"""

import json
import os
from pathlib import Path
import subprocess
import sys

import requests


ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = ROOT / "data" / "output"
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434").rstrip("/")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen3-vl:4b")


def check_ollama() -> dict:
    try:
        response = requests.get(f"{OLLAMA_BASE_URL}/api/tags", timeout=5)
        response.raise_for_status()
    except requests.RequestException as error:
        raise RuntimeError(
            f"无法连接 Ollama（{OLLAMA_BASE_URL}），请确认模型服务已经启动"
        ) from error

    models = {item.get("name") for item in response.json().get("models", [])}
    if OLLAMA_MODEL not in models:
        raise RuntimeError(f"Ollama 中没有 {OLLAMA_MODEL}，请先下载该模型")
    return {"base_url": OLLAMA_BASE_URL, "model": OLLAMA_MODEL}


def run_script(script_name: str, input_path: Path, *arguments: str | Path) -> None:
    environment = os.environ.copy()
    environment["PYTHONUTF8"] = "1"
    command = [
        sys.executable,
        str(ROOT / "src" / script_name),
        str(input_path),
        *(str(argument) for argument in arguments),
    ]
    result = subprocess.run(
        command,
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if result.returncode != 0:
        details = result.stderr.strip() or result.stdout.strip()
        raise RuntimeError(f"{script_name} 运行失败：\n{details}")


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def run_analysis(run_id: str, input_path: Path) -> dict:
    result_dir = OUTPUT_DIR / run_id
    result_dir.mkdir(parents=True, exist_ok=True)
    paths = {
        "yolo_image": result_dir / "yolo_result.jpg",
        "sam_image": result_dir / "sam_result.jpg",
        "yolo_json": result_dir / "yolo_detections.json",
        "sam_json": result_dir / "sam_masks.json",
        "vlm_json": result_dir / "vlm_inventory.json",
    }

    check_ollama()
    run_script(
        "yolo_detect.py",
        input_path,
        "--output",
        paths["yolo_image"],
        "--json",
        paths["yolo_json"],
    )
    run_script(
        "sam_segment.py",
        input_path,
        "--detections",
        paths["yolo_json"],
        "--output",
        paths["sam_image"],
        "--json",
        paths["sam_json"],
    )
    run_script(
        "vlm_inventory.py",
        input_path,
        "--output",
        paths["vlm_json"],
        "--model",
        OLLAMA_MODEL,
    )

    yolo = read_json(paths["yolo_json"])
    sam = read_json(paths["sam_json"])
    vlm = read_json(paths["vlm_json"])
    summary = {
        "yolo_detection_count": len(yolo.get("detections", [])),
        "sam_mask_count": int(sam.get("mask_count", 0)),
        "vlm_item_count": sum(
            int(item.get("count", 0)) for item in vlm.get("items", [])
        ),
    }
    artifacts = {
        "original": f"/artifacts/input/{input_path.name}",
        "yolo_image": f"/artifacts/output/{run_id}/yolo_result.jpg",
        "sam_image": f"/artifacts/output/{run_id}/sam_result.jpg",
    }
    return {
        "summary": summary,
        "yolo": yolo,
        "sam": sam,
        "vlm": vlm,
        "artifacts": artifacts,
    }
