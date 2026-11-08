"""独立 Worker 执行耗时视觉推理。"""

from datetime import datetime, timezone
import json
from pathlib import Path
import shutil

from billiard.exceptions import SoftTimeLimitExceeded

from backend.celery_app import celery_app
from backend.database import AnalysisRecord, SessionLocal, initialize_database
from backend.service import AnalysisCancelled, AnalysisTimedOut, run_analysis


TERMINAL_STATUSES = {"succeeded", "failed", "timed_out", "cancelled"}


def _set_terminal(record_id: int, status: str, error: str | None = None) -> None:
    with SessionLocal() as session:
        record = session.get(AnalysisRecord, record_id)
        if record is None:
            return
        record.status = status
        record.error_message = error
        record.completed_at = datetime.now(timezone.utc)
        session.commit()


def _remove_partial_output(run_id: str) -> None:
    path = Path(__file__).resolve().parents[1] / "data" / "output" / run_id
    if path.is_dir():
        shutil.rmtree(path)


@celery_app.task(bind=True, name="analysis.run")
def run_analysis_task(self, record_id: int) -> dict:
    initialize_database()
    with SessionLocal() as session:
        record = session.get(AnalysisRecord, record_id)
        if record is None:
            return {"status": "missing"}
        if record.status in {"cancelled", "cancelling"}:
            record.status = "cancelled"
            record.completed_at = datetime.now(timezone.utc)
            session.commit()
            return {"status": "cancelled"}
        record.status = "running"
        record.started_at = datetime.now(timezone.utc)
        if not record.task_id:
            record.task_id = self.request.id
        run_id = record.run_id
        suffix = Path(record.filename).suffix.lower() or ".jpg"
        input_path = Path(__file__).resolve().parents[1] / "data" / "input" / f"{run_id}{suffix}"
        session.commit()

    def should_cancel() -> bool:
        with SessionLocal() as check_session:
            current = check_session.get(AnalysisRecord, record_id)
            return current is None or current.status in {"cancelling", "cancelled"}

    try:
        result = run_analysis(run_id, input_path, should_cancel=should_cancel)
        with SessionLocal() as session:
            record = session.get(AnalysisRecord, record_id)
            if record is None or record.status in {"cancelling", "cancelled"}:
                _remove_partial_output(run_id)
                if record is not None:
                    record.status = "cancelled"
                    record.completed_at = datetime.now(timezone.utc)
                    session.commit()
                return {"status": "cancelled"}
            summary = result["summary"]
            record.status = "succeeded"
            record.result_json = json.dumps(result, ensure_ascii=False)
            record.yolo_detection_count = summary["yolo_detection_count"]
            record.sam_mask_count = summary["sam_mask_count"]
            record.vlm_item_count = summary["vlm_item_count"]
            record.completed_at = datetime.now(timezone.utc)
            session.commit()
            return {"status": "succeeded", "analysis_id": record_id}
    except AnalysisCancelled as error:
        _remove_partial_output(run_id)
        _set_terminal(record_id, "cancelled", str(error))
        return {"status": "cancelled"}
    except (AnalysisTimedOut, SoftTimeLimitExceeded) as error:
        _remove_partial_output(run_id)
        _set_terminal(record_id, "timed_out", str(error) or "分析任务超时")
        return {"status": "timed_out"}
    except Exception as error:
        _remove_partial_output(run_id)
        _set_terminal(record_id, "failed", str(error))
        raise
