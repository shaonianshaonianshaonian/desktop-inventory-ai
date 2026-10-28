"""桌面物品清点：传统视觉方案与本地视觉大模型对比界面。"""

from hashlib import sha256
import json
import os
from pathlib import Path
import subprocess
import sys

import requests
import streamlit as st


ROOT = Path(__file__).resolve().parent
INPUT_DIR = ROOT / "data" / "input"
OUTPUT_DIR = ROOT / "data" / "output"
OLLAMA_TAGS_URL = "http://127.0.0.1:11434/api/tags"


def run_script(script_name: str, input_path: Path) -> None:
    environment = os.environ.copy()
    environment["PYTHONUTF8"] = "1"
    command = [
        sys.executable,
        str(ROOT / "src" / script_name),
        str(input_path),
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


def check_ollama() -> None:
    try:
        response = requests.get(OLLAMA_TAGS_URL, timeout=5)
        response.raise_for_status()
    except requests.RequestException as error:
        raise RuntimeError("无法连接本机 Ollama，请先启动 Ollama") from error

    models = {item["name"] for item in response.json().get("models", [])}
    if "qwen3-vl:4b" not in models:
        raise RuntimeError("本机没有 qwen3-vl:4b，请先运行 ollama pull qwen3-vl:4b")


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def save_upload(uploaded_file) -> Path:
    suffix = Path(uploaded_file.name).suffix.lower()
    if suffix not in {".jpg", ".jpeg", ".png", ".webp"}:
        suffix = ".jpg"
    image_bytes = uploaded_file.getvalue()
    digest = sha256(image_bytes).hexdigest()[:12]
    INPUT_DIR.mkdir(parents=True, exist_ok=True)
    input_path = INPUT_DIR / f"demo_{digest}{suffix}"
    input_path.write_bytes(image_bytes)
    return input_path


st.set_page_config(
    page_title="桌面物品双方案对比",
    page_icon="🔎",
    layout="wide",
)

st.title("桌面物品双方案对比")
st.caption("YOLO + MobileSAM 与本地 Qwen3-VL 处理同一张图片")

with st.expander("隐私与运行方式", expanded=False):
    st.markdown(
        """
        - 图片仅保存在本机 `data/input`，不会上传到云端。
        - YOLO、MobileSAM 和 Qwen3-VL 均在本机运行。
        - Qwen3-VL 只通过 `127.0.0.1:11434` 连接本机 Ollama。
        - 输入图片和模型输出均被 Git 忽略。
        """
    )

uploaded = st.file_uploader(
    "选择一张桌面图片",
    type=["jpg", "jpeg", "png", "webp"],
    accept_multiple_files=False,
)

if uploaded is not None:
    st.image(uploaded, caption="待分析图片", width="stretch")

    if st.button("运行两种方案", type="primary", width="stretch"):
        try:
            input_path = save_upload(uploaded)
            check_ollama()
            with st.status("正在运行本地模型…", expanded=True) as status:
                st.write("1/3：YOLO 正在检测物体")
                run_script("yolo_detect.py", input_path)
                st.write("2/3：MobileSAM 正在生成分割掩膜")
                run_script("sam_segment.py", input_path)
                st.write("3/3：Qwen3-VL 正在生成物品清单")
                run_script("vlm_inventory.py", input_path)
                status.update(label="分析完成", state="complete", expanded=False)
            st.session_state["result_input"] = str(input_path)
        except Exception as error:
            st.error(str(error))

result_input = st.session_state.get("result_input")
required_outputs = {
    "yolo_image": OUTPUT_DIR / "yolo_result.jpg",
    "sam_image": OUTPUT_DIR / "sam_result.jpg",
    "yolo_json": OUTPUT_DIR / "yolo_detections.json",
    "vlm_json": OUTPUT_DIR / "vlm_inventory.json",
}

if result_input and all(path.exists() for path in required_outputs.values()):
    yolo_result = read_json(required_outputs["yolo_json"])
    vlm_result = read_json(required_outputs["vlm_json"])

    st.divider()
    st.subheader("同一输入的处理结果")
    original_column, yolo_column, sam_column = st.columns(3)
    with original_column:
        st.markdown("#### 原始图片")
        st.image(result_input, width="stretch")
    with yolo_column:
        st.markdown("#### YOLO 目标检测")
        st.image(required_outputs["yolo_image"], width="stretch")
    with sam_column:
        st.markdown("#### MobileSAM 分割")
        st.image(required_outputs["sam_image"], width="stretch")

    traditional_column, vlm_column = st.columns(2, gap="large")
    with traditional_column:
        st.markdown("### 传统视觉方案")
        yolo_rows = [
            {"类别": name, "数量": count}
            for name, count in yolo_result.get("counts", {}).items()
        ]
        st.dataframe(yolo_rows, width="stretch", hide_index=True)
        st.caption("优势：能提供边界框、置信度和像素掩膜。")

    with vlm_column:
        st.markdown("### 本地视觉大模型方案")
        vlm_rows = [
            {
                "物品": item["name"],
                "数量": item["count"],
                "置信度": item["confidence"],
                "判断依据": item["reason"],
            }
            for item in vlm_result.get("items", [])
        ]
        st.dataframe(vlm_rows, width="stretch", hide_index=True)
        st.caption("优势：能理解开放类别，并生成自然语言物品清单。")

    st.info(
        "传统方案更适合定位和分割；视觉大模型更适合开放类别识别与语义理解。"
    )

