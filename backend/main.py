"""FastAPI 文件上传、模型分析与历史记录接口。"""

from contextlib import asynccontextmanager
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
from uuid import uuid4

import cv2
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.staticfiles import StaticFiles
import numpy as np
from sqlalchemy import select

from backend.database import AnalysisRecord, SessionLocal, initialize_database
from backend.service import OLLAMA_BASE_URL, OLLAMA_MODEL, check_ollama, run_analysis


ROOT = Path(__file__).resolve().parents[1]
INPUT_DIR = ROOT / "data" / "input"
OUTPUT_DIR = ROOT / "data" / "output"
MAX_UPLOAD_BYTES = 20 * 1024 * 1024
ALLOWED_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp"}


@asynccontextmanager
async def lifespan(_: FastAPI):
    INPUT_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    initialize_database()
    yield


app = FastAPI(
    title="桌面物品清点 API",
    version="3.0.0",
    lifespan=lifespan,
)
app.mount("/artifacts/input", StaticFiles(directory=INPUT_DIR), name="input")
app.mount("/artifacts/output", StaticFiles(directory=OUTPUT_DIR), name="output")


def serialize_record(record: AnalysisRecord, include_result: bool = False) -> dict:
    data = {
        "id": record.id,
        "run_id": record.run_id,
        "filename": record.filename,
        "digest": record.digest,
        "status": record.status,
        "error_message": record.error_message,
        "summary": {
            "yolo_detection_count": record.yolo_detection_count,
            "sam_mask_count": record.sam_mask_count,
            "vlm_item_count": record.vlm_item_count,
        },
        "created_at": record.created_at.isoformat(),
        "completed_at": (
            record.completed_at.isoformat() if record.completed_at else None
        ),
    }
    if include_result and record.result_json:
        data.update(json.loads(record.result_json))
    return data


@app.get("/api/health")
def health() -> dict:
    try:
        ollama = check_ollama()
        return {"api": "ok", "ollama": "ok", **ollama}
    except RuntimeError as error:
        return {
            "api": "ok",
            "ollama": "unavailable",
            "base_url": OLLAMA_BASE_URL,
            "model": OLLAMA_MODEL,
            "detail": str(error),
        }


@app.post("/api/analyses")
async def create_analysis(file: UploadFile = File(...)) -> dict:
    suffix = Path(file.filename or "upload.jpg").suffix.lower()
    if suffix not in ALLOWED_SUFFIXES:
        raise HTTPException(status_code=400, detail="只支持 JPG、PNG 或 WebP 图片")

    content = await file.read(MAX_UPLOAD_BYTES + 1)
    if not content:
        raise HTTPException(status_code=400, detail="上传文件为空")
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="图片不能超过 20 MB")
    image = cv2.imdecode(np.frombuffer(content, dtype=np.uint8), cv2.IMREAD_COLOR)
    if image is None:
        raise HTTPException(status_code=400, detail="上传内容不是有效图片")

    run_id = str(uuid4())
    digest = sha256(content).hexdigest()
    input_path = INPUT_DIR / f"{run_id}{suffix}"
    input_path.write_bytes(content)

    with SessionLocal() as session:
        record = AnalysisRecord(
            run_id=run_id,
            filename=file.filename or input_path.name,
            digest=digest,
            status="running",
        )
        session.add(record)
        session.commit()

        try:
            result = run_analysis(run_id, input_path)
            summary = result["summary"]
            record.status = "succeeded"
            record.result_json = json.dumps(result, ensure_ascii=False)
            record.yolo_detection_count = summary["yolo_detection_count"]
            record.sam_mask_count = summary["sam_mask_count"]
            record.vlm_item_count = summary["vlm_item_count"]
            record.completed_at = datetime.now(timezone.utc)
            session.commit()
            return serialize_record(record, include_result=True)
        except Exception as error:
            record.status = "failed"
            record.error_message = str(error)
            record.completed_at = datetime.now(timezone.utc)
            session.commit()
            raise HTTPException(
                status_code=500,
                detail={"analysis_id": record.id, "message": str(error)},
            ) from error


@app.get("/api/analyses")
def list_analyses(limit: int = 20) -> list[dict]:
    safe_limit = max(1, min(limit, 100))
    with SessionLocal() as session:
        records = session.scalars(
            select(AnalysisRecord)
            .order_by(AnalysisRecord.id.desc())
            .limit(safe_limit)
        ).all()
        return [serialize_record(record) for record in records]


@app.get("/api/analyses/{analysis_id}")
def get_analysis(analysis_id: int) -> dict:
    with SessionLocal() as session:
        record = session.get(AnalysisRecord, analysis_id)
        if record is None:
            raise HTTPException(status_code=404, detail="分析记录不存在")
        return serialize_record(record, include_result=True)
