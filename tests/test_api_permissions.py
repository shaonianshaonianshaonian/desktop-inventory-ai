from types import SimpleNamespace

import cv2
from fastapi.testclient import TestClient
import numpy as np

from backend.main import app
from backend.database import AnalysisRecord, SessionLocal


def token_headers(client, username):
    password = "test-password-123"
    response = client.post(
        "/api/auth/register", json={"username": username, "password": password}
    )
    assert response.status_code == 201
    response = client.post(
        "/api/auth/token", data={"username": username, "password": password}
    )
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def test_history_images_and_cancel_are_owner_scoped(monkeypatch, tmp_path):
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    input_dir.mkdir()
    output_dir.mkdir()
    monkeypatch.setattr("backend.main.INPUT_DIR", input_dir)
    monkeypatch.setattr("backend.main.OUTPUT_DIR", output_dir)
    monkeypatch.setattr(
        "backend.main.run_analysis_task.delay",
        lambda record_id: SimpleNamespace(id=f"task-{record_id}"),
    )
    with TestClient(app) as client:
        owner = token_headers(client, "owner_user")
        other = token_headers(client, "other_user")
        success, encoded = cv2.imencode(
            ".jpg", np.zeros((20, 20, 3), dtype=np.uint8)
        )
        assert success
        response = client.post(
            "/api/analyses",
            headers=owner,
            files={"file": ("desk.jpg", encoded.tobytes(), "image/jpeg")},
        )
        assert response.status_code == 202
        analysis_id = response.json()["id"]
        run_id = response.json()["run_id"]

        assert client.get(f"/api/analyses/{analysis_id}", headers=other).status_code == 404
        assert client.get("/api/analyses", headers=other).json() == []
        assert (
            client.get(
                f"/api/analyses/{analysis_id}/artifacts/original", headers=other
            ).status_code
            == 404
        )

        response = client.post(
            f"/api/analyses/{analysis_id}/cancel", headers=owner
        )
        assert response.status_code == 200
        assert response.json()["status"] == "cancelled"

        with SessionLocal() as session:
            record = session.get(AnalysisRecord, analysis_id)
            record.status = "succeeded"
            record.result_json = "{}"
            session.commit()
        (input_dir / f"{run_id}.jpg").write_bytes(b"private-image")
        result_dir = output_dir / run_id
        result_dir.mkdir()
        (result_dir / "yolo_result.jpg").write_bytes(b"yolo")
        (result_dir / "sam_result.jpg").write_bytes(b"sam")

        assert (
            client.get(
                f"/api/analyses/{analysis_id}/artifacts/original", headers=owner
            ).content
            == b"private-image"
        )
        assert (
            client.get(f"/api/analyses/{analysis_id}/artifacts/original").status_code
            == 401
        )

