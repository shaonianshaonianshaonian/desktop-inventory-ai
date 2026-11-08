import json
import time

import pytest

from backend import service


def option_path(arguments, option):
    index = arguments.index(option)
    return arguments[index + 1]


def test_zero_yolo_skips_sam_and_continues_vlm(tmp_path, monkeypatch):
    monkeypatch.setattr(service, "OUTPUT_DIR", tmp_path / "output")
    monkeypatch.setattr(service, "check_ollama", lambda: {"model": "test"})
    called = []

    def fake_run_script(script_name, input_path, *arguments, **kwargs):
        called.append(script_name)
        if script_name == "yolo_detect.py":
            output = option_path(arguments, "--output")
            json_path = option_path(arguments, "--json")
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_bytes(b"fake-image")
            json_path.write_text(
                json.dumps({"counts": {}, "detections": []}), encoding="utf-8"
            )
        elif script_name == "vlm_inventory.py":
            json_path = option_path(arguments, "--output")
            json_path.write_text(
                json.dumps(
                    {
                        "model": "test",
                        "scene": "空桌面",
                        "items": [
                            {
                                "name": "杯子",
                                "count": 1,
                                "confidence": "high",
                                "reason": "清晰可见",
                            }
                        ],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
        else:
            raise AssertionError("YOLO 为 0 时不应调用 SAM")

    monkeypatch.setattr(service, "run_script", fake_run_script)
    input_path = tmp_path / "input.jpg"
    input_path.write_bytes(b"input")

    result = service.run_analysis("run-zero", input_path)

    assert called == ["yolo_detect.py", "vlm_inventory.py"]
    assert result["summary"] == {
        "yolo_detection_count": 0,
        "sam_mask_count": 0,
        "vlm_item_count": 1,
    }
    assert result["sam"]["skipped"] is True


def make_slow_script(tmp_path, monkeypatch):
    root = tmp_path / "project"
    source = root / "src"
    source.mkdir(parents=True)
    (source / "slow.py").write_text(
        "import time\ntime.sleep(30)\n", encoding="utf-8"
    )
    input_path = root / "input.jpg"
    input_path.write_bytes(b"input")
    monkeypatch.setattr(service, "ROOT", root)
    return input_path


def test_model_subprocess_timeout_is_enforced(tmp_path, monkeypatch):
    input_path = make_slow_script(tmp_path, monkeypatch)
    with pytest.raises(service.AnalysisTimedOut):
        service.run_script(
            "slow.py",
            input_path,
            deadline=time.monotonic() + 0.1,
            should_cancel=lambda: False,
        )


def test_model_subprocess_can_be_cancelled(tmp_path, monkeypatch):
    input_path = make_slow_script(tmp_path, monkeypatch)
    with pytest.raises(service.AnalysisCancelled):
        service.run_script(
            "slow.py",
            input_path,
            deadline=time.monotonic() + 30,
            should_cancel=lambda: True,
        )
