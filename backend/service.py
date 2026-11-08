"""调用本地视觉模型并组合一次可取消、可超时的完整分析。"""

import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import time
from typing import Callable

from pydantic import ValidationError
import requests

from backend.schemas import InventoryResult


ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = ROOT / "data" / "output"
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434").rstrip("/")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen3-vl:4b")
ANALYSIS_TIMEOUT_SECONDS = int(os.getenv("ANALYSIS_TIMEOUT_SECONDS", "900"))


class AnalysisCancelled(RuntimeError):
    pass


class AnalysisTimedOut(RuntimeError):
    pass


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


def _stop_process(process: subprocess.Popen) -> None:
    if process.poll() is not None:
        return
    try:
        if os.name == "posix":
            os.killpg(process.pid, signal.SIGTERM)
        else:
            process.terminate()
        process.wait(timeout=5)
    except (ProcessLookupError, subprocess.TimeoutExpired):
        if process.poll() is None:
            if os.name == "posix":
                os.killpg(process.pid, signal.SIGKILL)
            else:
                process.kill()
            process.wait(timeout=5)


def run_script(
    script_name: str,
    input_path: Path,
    *arguments: str | Path,
    deadline: float,
    should_cancel: Callable[[], bool],
) -> None:
    environment = os.environ.copy()
    environment["PYTHONUTF8"] = "1"
    command = [
        sys.executable,
        str(ROOT / "src" / script_name),
        str(input_path),
        *(str(argument) for argument in arguments),
    ]
    process = subprocess.Popen(
        command,
        cwd=ROOT,
        env=environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        start_new_session=(os.name == "posix"),
    )
    try:
        while process.poll() is None:
            if should_cancel():
                raise AnalysisCancelled("分析已由用户取消")
            if time.monotonic() >= deadline:
                raise AnalysisTimedOut("分析任务超过总时限")
            time.sleep(0.5)
        stdout, stderr = process.communicate()
    except BaseException:
        _stop_process(process)
        process.communicate()
        raise
    if process.returncode != 0:
        details = stderr.strip() or stdout.strip()
        raise RuntimeError(f"{script_name} 运行失败：\n{details}")


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _validate_vlm_result(data: dict) -> dict:
    try:
        validated = InventoryResult.model_validate(
            {"scene": data.get("scene"), "items": data.get("items")}
        )
    except ValidationError as error:
        raise RuntimeError(f"视觉大模型结果校验失败：{error}") from error
    return {**data, **validated.model_dump()}


def run_analysis(
    run_id: str,
    input_path: Path,
    should_cancel: Callable[[], bool] | None = None,
    timeout_seconds: int = ANALYSIS_TIMEOUT_SECONDS,
) -> dict:
    should_cancel = should_cancel or (lambda: False)
    deadline = time.monotonic() + timeout_seconds
    result_dir = OUTPUT_DIR / run_id
    result_dir.mkdir(parents=True, exist_ok=True)
    paths = {
        "yolo_image": result_dir / "yolo_result.jpg",
        "sam_image": result_dir / "sam_result.jpg",
        "yolo_json": result_dir / "yolo_detections.json",
        "sam_json": result_dir / "sam_masks.json",
        "vlm_json": result_dir / "vlm_inventory.json",
    }

    if should_cancel():
        raise AnalysisCancelled("分析已由用户取消")
    check_ollama()
    run_script(
        "yolo_detect.py",
        input_path,
        "--output",
        paths["yolo_image"],
        "--json",
        paths["yolo_json"],
        deadline=deadline,
        should_cancel=should_cancel,
    )
    yolo = read_json(paths["yolo_json"])
    detections = yolo.get("detections")
    if not isinstance(detections, list):
        raise RuntimeError("YOLO 结果缺少 detections 列表")

    if detections:
        run_script(
            "sam_segment.py",
            input_path,
            "--detections",
            paths["yolo_json"],
            "--output",
            paths["sam_image"],
            "--json",
            paths["sam_json"],
            deadline=deadline,
            should_cancel=should_cancel,
        )
        sam = read_json(paths["sam_json"])
    else:
        sam = {
            "model": os.getenv("SAM_MODEL", "mobile_sam.pt"),
            "prompt_type": "YOLO bounding boxes",
            "mask_count": 0,
            "segments": [],
            "skipped": True,
            "skip_reason": "YOLO 未检测到目标",
        }
        paths["sam_json"].write_text(
            json.dumps(sam, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        shutil.copyfile(paths["yolo_image"], paths["sam_image"])

    run_script(
        "vlm_inventory.py",
        input_path,
        "--output",
        paths["vlm_json"],
        "--model",
        OLLAMA_MODEL,
        deadline=deadline,
        should_cancel=should_cancel,
    )
    vlm = _validate_vlm_result(read_json(paths["vlm_json"]))
    paths["vlm_json"].write_text(
        json.dumps(vlm, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    summary = {
        "yolo_detection_count": len(detections),
        "sam_mask_count": int(sam.get("mask_count", 0)),
        "vlm_item_count": sum(item["count"] for item in vlm["items"]),
    }
    return {
        "summary": summary,
        "yolo": yolo,
        "sam": sam,
        "vlm": vlm,
    }
