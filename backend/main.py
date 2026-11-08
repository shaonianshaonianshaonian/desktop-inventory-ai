"""FastAPI 登录、异步分析、任务状态与受保护资源接口。"""

from contextlib import asynccontextmanager
from datetime import datetime, timezone
from hashlib import sha256
import json
import mimetypes
from pathlib import Path
from uuid import uuid4

import cv2
from fastapi import Depends, FastAPI, File, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from fastapi.security import OAuth2PasswordRequestForm
import numpy as np
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from backend.auth import (
    JWT_EXPIRE_MINUTES,
    authenticate_user,
    create_access_token,
    get_current_user,
    hash_password,
)
from backend.celery_app import celery_app
from backend.database import AnalysisRecord, SessionLocal, User, initialize_database
from backend.schemas import RegisterRequest
from backend.service import OLLAMA_BASE_URL, OLLAMA_MODEL, check_ollama
from backend.tasks import run_analysis_task


ROOT = Path(__file__).resolve().parents[1]
INPUT_DIR = ROOT / "data" / "input"
OUTPUT_DIR = ROOT / "data" / "output"
MAX_UPLOAD_BYTES = 20 * 1024 * 1024
ALLOWED_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp"}
TERMINAL_STATUSES = {"succeeded", "failed", "timed_out", "cancelled"}


@asynccontextmanager
async def lifespan(_: FastAPI):
    INPUT_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    initialize_database()
    yield


app = FastAPI(title="桌面物品清点 API", version="4.0.0", lifespan=lifespan)


def serialize_record(record: AnalysisRecord, include_result: bool = False) -> dict:
    data = {
        "id": record.id,
        "task_id": record.task_id,
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
        "started_at": record.started_at.isoformat() if record.started_at else None,
        "completed_at": record.completed_at.isoformat() if record.completed_at else None,
    }
    if include_result and record.result_json:
        data.update(json.loads(record.result_json))
    if record.status == "succeeded":
        data["artifacts"] = {
            "original": f"/api/analyses/{record.id}/artifacts/original",
            "yolo_image": f"/api/analyses/{record.id}/artifacts/yolo",
            "sam_image": f"/api/analyses/{record.id}/artifacts/sam",
        }
    return data


def get_owned_record(session, analysis_id: int, user: User) -> AnalysisRecord:
    record = session.scalar(
        select(AnalysisRecord).where(
            AnalysisRecord.id == analysis_id,
            AnalysisRecord.owner_id == user.id,
        )
    )
    if record is None:
        raise HTTPException(status_code=404, detail="分析记录不存在")
    return record


@app.get("/api/health")
def health() -> dict:
    result = {
        "api": "ok",
        "queue": "unknown",
        "ollama": "unavailable",
        "base_url": OLLAMA_BASE_URL,
        "model": OLLAMA_MODEL,
    }
    try:
        with celery_app.connection_for_read() as connection:
            connection.ensure_connection(max_retries=0)
        result["queue"] = "ok"
    except Exception as error:
        result["queue"] = "unavailable"
        result["queue_detail"] = str(error)
    try:
        result.update({"ollama": "ok", **check_ollama()})
    except RuntimeError as error:
        result["ollama_detail"] = str(error)
    return result


@app.post("/api/auth/register", status_code=status.HTTP_201_CREATED)
def register(payload: RegisterRequest) -> dict:
    try:
        password_hash = hash_password(payload.password)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    with SessionLocal() as session:
        user = User(username=payload.username, password_hash=password_hash)
        session.add(user)
        try:
            session.commit()
        except IntegrityError as error:
            session.rollback()
            raise HTTPException(status_code=409, detail="用户名已存在") from error
        session.refresh(user)
        return {"id": user.id, "username": user.username}


@app.post("/api/auth/token")
def login(form: OAuth2PasswordRequestForm = Depends()) -> dict:
    user = authenticate_user(form.username, form.password)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户名或密码错误",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return {
        "access_token": create_access_token(user),
        "token_type": "bearer",
        "expires_in": JWT_EXPIRE_MINUTES * 60,
    }


@app.get("/api/auth/me")
def current_user(user: User = Depends(get_current_user)) -> dict:
    return {"id": user.id, "username": user.username}


@app.post("/api/analyses", status_code=status.HTTP_202_ACCEPTED)
async def create_analysis(
    file: UploadFile = File(...), user: User = Depends(get_current_user)
) -> dict:
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
    original_name = Path(file.filename or input_path.name).name
    display_name = f"{Path(original_name).stem[:240]}{suffix}"
    with SessionLocal() as session:
        record = AnalysisRecord(
            owner_id=user.id,
            run_id=run_id,
            filename=display_name,
            digest=digest,
            status="queued",
        )
        session.add(record)
        session.commit()
        session.refresh(record)
        try:
            task = run_analysis_task.delay(record.id)
        except Exception as error:
            record.status = "failed"
            record.error_message = f"任务入队失败：{error}"
            record.completed_at = datetime.now(timezone.utc)
            session.commit()
            input_path.unlink(missing_ok=True)
            raise HTTPException(status_code=503, detail="消息队列暂不可用") from error
        record.task_id = task.id
        session.commit()
        return serialize_record(record)


@app.get("/api/analyses")
def list_analyses(
    limit: int = 20, user: User = Depends(get_current_user)
) -> list[dict]:
    safe_limit = max(1, min(limit, 100))
    with SessionLocal() as session:
        records = session.scalars(
            select(AnalysisRecord)
            .where(AnalysisRecord.owner_id == user.id)
            .order_by(AnalysisRecord.id.desc())
            .limit(safe_limit)
        ).all()
        return [serialize_record(record) for record in records]


@app.get("/api/analyses/{analysis_id}")
def get_analysis(analysis_id: int, user: User = Depends(get_current_user)) -> dict:
    with SessionLocal() as session:
        record = get_owned_record(session, analysis_id, user)
        return serialize_record(record, include_result=True)


@app.post("/api/analyses/{analysis_id}/cancel")
def cancel_analysis(analysis_id: int, user: User = Depends(get_current_user)) -> dict:
    with SessionLocal() as session:
        record = get_owned_record(session, analysis_id, user)
        if record.status in TERMINAL_STATUSES:
            return serialize_record(record, include_result=True)
        if record.status == "queued":
            record.status = "cancelled"
            record.completed_at = datetime.now(timezone.utc)
            if record.task_id:
                try:
                    celery_app.control.revoke(record.task_id, terminate=False)
                except Exception:
                    # 数据库中的取消状态优先；队列恢复后 Worker 也会再次检查状态。
                    pass
        else:
            record.status = "cancelling"
        session.commit()
        return serialize_record(record)


@app.get("/api/analyses/{analysis_id}/artifacts/{kind}")
def get_artifact(
    analysis_id: int,
    kind: str,
    user: User = Depends(get_current_user),
) -> FileResponse:
    with SessionLocal() as session:
        record = get_owned_record(session, analysis_id, user)
        if record.status != "succeeded":
            raise HTTPException(status_code=409, detail="分析尚未成功完成")
        suffix = Path(record.filename).suffix.lower() or ".jpg"
        paths = {
            "original": INPUT_DIR / f"{record.run_id}{suffix}",
            "yolo": OUTPUT_DIR / record.run_id / "yolo_result.jpg",
            "sam": OUTPUT_DIR / record.run_id / "sam_result.jpg",
        }
        path = paths.get(kind)
        if path is None:
            raise HTTPException(status_code=404, detail="资源类型不存在")
        if not path.is_file():
            raise HTTPException(status_code=404, detail="资源文件不存在")
        media_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        return FileResponse(path, media_type=media_type)
