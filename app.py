"""桌面物品清点：调用 FastAPI 后端的 Streamlit 前端。"""

from hashlib import sha256
import os
from urllib.parse import urljoin

import requests
import streamlit as st


API_BASE_URL = os.getenv("API_BASE_URL", "http://127.0.0.1:8000").rstrip("/")
ANALYSIS_URL = f"{API_BASE_URL}/api/analyses"


def get_upload_digest(uploaded_file) -> str:
    return sha256(uploaded_file.getvalue()).hexdigest()


def clear_displayed_result() -> None:
    st.session_state.pop("result", None)


def extract_error(response: requests.Response) -> str:
    try:
        detail = response.json().get("detail", response.text)
    except ValueError:
        return response.text or f"HTTP {response.status_code}"
    if isinstance(detail, dict):
        return detail.get("message", str(detail))
    return str(detail)


def request_analysis(uploaded_file) -> dict:
    files = {
        "file": (
            uploaded_file.name,
            uploaded_file.getvalue(),
            uploaded_file.type or "application/octet-stream",
        )
    }
    try:
        response = requests.post(ANALYSIS_URL, files=files, timeout=900)
    except requests.ConnectionError as error:
        raise RuntimeError(
            f"无法连接后端 API（{API_BASE_URL}），请先启动完整 Web 项目"
        ) from error
    except requests.Timeout as error:
        raise RuntimeError("后端分析超时，请检查模型服务状态") from error
    if not response.ok:
        raise RuntimeError(extract_error(response))
    return response.json()


def fetch_artifact(relative_path: str) -> bytes:
    url = urljoin(f"{API_BASE_URL}/", relative_path.lstrip("/"))
    response = requests.get(url, timeout=30)
    response.raise_for_status()
    return response.content


def load_history() -> list[dict]:
    try:
        response = requests.get(ANALYSIS_URL, params={"limit": 10}, timeout=5)
        response.raise_for_status()
        return response.json()
    except requests.RequestException:
        return []


st.set_page_config(
    page_title="桌面物品双方案对比",
    page_icon="🔎",
    layout="wide",
)

st.title("桌面物品双方案对比")
st.caption("Streamlit 前端 + FastAPI 后端 + SQLAlchemy 记录")

st.info(
    "上传同一张桌面图片，由 YOLO + MobileSAM 与本地 Qwen3-VL 分别处理，"
    "比较目标定位、图像分割和开放语义理解能力。"
)

with st.expander("系统架构与隐私", expanded=False):
    st.markdown(
        f"""
        - 当前前端通过 `{API_BASE_URL}` 调用 FastAPI。
        - FastAPI 统一调用 YOLO、MobileSAM 和 Qwen3-VL，并使用 SQLAlchemy 保存记录。
        - Qwen3-VL 由本机 Ollama 运行，图片不会发送到云端模型。
        - 输入图片、模型输出和 SQLite 数据库均被 Git 忽略。
        """
    )

uploaded = st.file_uploader(
    "选择一张桌面图片",
    type=["jpg", "jpeg", "png", "webp"],
    accept_multiple_files=False,
)

current_digest = get_upload_digest(uploaded) if uploaded is not None else None
if st.session_state.get("selected_digest") != current_digest:
    st.session_state["selected_digest"] = current_digest
    clear_displayed_result()

if uploaded is not None and current_digest is not None:
    st.image(uploaded, caption="待分析图片", width="stretch")

    if st.button("调用后端运行两种方案", type="primary", width="stretch"):
        clear_displayed_result()
        try:
            with st.status("后端正在运行本地模型…", expanded=True) as status:
                st.write("FastAPI 已接收图片，正在执行 YOLO、MobileSAM 和 Qwen3-VL")
                result = request_analysis(uploaded)
                status.update(label="分析完成", state="complete", expanded=False)
            if result.get("digest") != current_digest:
                raise RuntimeError("后端返回结果与当前图片不一致")
            st.session_state["result"] = result
        except Exception as error:
            clear_displayed_result()
            st.error(str(error))

result = st.session_state.get("result")
if result and result.get("digest") == current_digest:
    yolo_result = result.get("yolo", {})
    vlm_result = result.get("vlm", {})
    artifacts = result.get("artifacts", {})

    try:
        yolo_image = fetch_artifact(artifacts["yolo_image"])
        sam_image = fetch_artifact(artifacts["sam_image"])
    except (KeyError, requests.RequestException) as error:
        clear_displayed_result()
        st.error(f"无法读取本次分析图片：{error}")
    else:
        st.divider()
        st.subheader("同一输入的处理结果")
        original_column, yolo_column, sam_column = st.columns(3)
        with original_column:
            st.markdown("#### 原始图片")
            st.image(uploaded, width="stretch")
        with yolo_column:
            st.markdown("#### YOLO 目标检测")
            st.image(yolo_image, width="stretch")
        with sam_column:
            st.markdown("#### MobileSAM 分割")
            st.image(sam_image, width="stretch")

        traditional_column, vlm_column = st.columns(2, gap="large")
        with traditional_column:
            st.markdown("### 传统视觉方案")
            yolo_rows = [
                {"类别": name, "数量": count}
                for name, count in yolo_result.get("counts", {}).items()
            ]
            st.dataframe(yolo_rows, width="stretch", hide_index=True)
            st.caption("优势：提供边界框、置信度和像素掩膜。")

        with vlm_column:
            st.markdown("### 本地视觉大模型方案")
            vlm_rows = [
                {
                    "物品": item.get("name"),
                    "数量": item.get("count"),
                    "置信度": item.get("confidence"),
                    "判断依据": item.get("reason"),
                }
                for item in vlm_result.get("items", [])
            ]
            st.dataframe(vlm_rows, width="stretch", hide_index=True)
            st.caption("优势：理解开放类别，并生成自然语言物品清单。")

        st.subheader("当前运行结果统计")
        st.caption("数字来自当前分析记录，不代表人工标注准确率。")
        summary = result.get("summary", {})
        metric_yolo, metric_vlm, metric_masks = st.columns(3)
        metric_yolo.metric(
            "YOLO 检测目标", summary.get("yolo_detection_count", 0)
        )
        metric_vlm.metric("Qwen3-VL 清单物品", summary.get("vlm_item_count", 0))
        metric_masks.metric("MobileSAM 生成掩膜", summary.get("sam_mask_count", 0))

        st.success(
            f"分析记录 #{result.get('id')} 已保存到 SQLAlchemy 数据库。"
            "三种输出均属于当前上传图片。"
        )

with st.expander("最近分析记录", expanded=False):
    history = load_history()
    if history:
        st.dataframe(
            [
                {
                    "编号": item.get("id"),
                    "文件名": item.get("filename"),
                    "状态": item.get("status"),
                    "YOLO目标": item.get("summary", {}).get(
                        "yolo_detection_count"
                    ),
                    "SAM掩膜": item.get("summary", {}).get("sam_mask_count"),
                    "VLM物品": item.get("summary", {}).get("vlm_item_count"),
                    "创建时间": item.get("created_at"),
                }
                for item in history
            ],
            width="stretch",
            hide_index=True,
        )
    else:
        st.caption("暂无记录，或后端 API 当前不可访问。")
