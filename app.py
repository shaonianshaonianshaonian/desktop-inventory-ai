"""桌面物品清点：登录后提交异步任务并查看本人结果。"""

from hashlib import sha256
import os
import time
from urllib.parse import urljoin

import requests
import streamlit as st


API_BASE_URL = os.getenv("API_BASE_URL", "http://127.0.0.1:8000").rstrip("/")
ANALYSIS_URL = f"{API_BASE_URL}/api/analyses"
TERMINAL_STATUSES = {"succeeded", "failed", "timed_out", "cancelled"}
STATUS_LABELS = {
    "queued": "排队中",
    "running": "正在推理",
    "cancelling": "正在中断",
    "succeeded": "成功",
    "failed": "失败",
    "timed_out": "超时",
    "cancelled": "已取消",
}


def get_upload_digest(uploaded_file) -> str:
    return sha256(uploaded_file.getvalue()).hexdigest()


def clear_displayed_result() -> None:
    st.session_state.pop("result", None)


def auth_headers() -> dict[str, str]:
    token = st.session_state.get("access_token")
    return {"Authorization": f"Bearer {token}"} if token else {}


def extract_error(response: requests.Response) -> str:
    try:
        detail = response.json().get("detail", response.text)
    except ValueError:
        return response.text or f"HTTP {response.status_code}"
    if isinstance(detail, dict):
        return detail.get("message", str(detail))
    return str(detail)


def login(username: str, password: str) -> None:
    response = requests.post(
        f"{API_BASE_URL}/api/auth/token",
        data={"username": username, "password": password},
        timeout=10,
    )
    if not response.ok:
        raise RuntimeError(extract_error(response))
    st.session_state["access_token"] = response.json()["access_token"]


def register(username: str, password: str) -> None:
    response = requests.post(
        f"{API_BASE_URL}/api/auth/register",
        json={"username": username, "password": password},
        timeout=10,
    )
    if not response.ok:
        raise RuntimeError(extract_error(response))


def load_current_user() -> dict | None:
    if not st.session_state.get("access_token"):
        return None
    try:
        response = requests.get(
            f"{API_BASE_URL}/api/auth/me", headers=auth_headers(), timeout=5
        )
        if response.status_code == 401:
            st.session_state.pop("access_token", None)
            return None
        response.raise_for_status()
        return response.json()
    except requests.RequestException:
        return None


def enqueue_analysis(uploaded_file) -> dict:
    files = {
        "file": (
            uploaded_file.name,
            uploaded_file.getvalue(),
            uploaded_file.type or "application/octet-stream",
        )
    }
    response = requests.post(
        ANALYSIS_URL, files=files, headers=auth_headers(), timeout=30
    )
    if not response.ok:
        raise RuntimeError(extract_error(response))
    return response.json()


def get_analysis(analysis_id: int) -> dict:
    response = requests.get(
        f"{ANALYSIS_URL}/{analysis_id}", headers=auth_headers(), timeout=10
    )
    if not response.ok:
        raise RuntimeError(extract_error(response))
    return response.json()


def cancel_analysis(analysis_id: int) -> None:
    response = requests.post(
        f"{ANALYSIS_URL}/{analysis_id}/cancel",
        headers=auth_headers(),
        timeout=10,
    )
    if not response.ok:
        raise RuntimeError(extract_error(response))


def fetch_artifact(relative_path: str) -> bytes:
    url = urljoin(f"{API_BASE_URL}/", relative_path.lstrip("/"))
    response = requests.get(url, headers=auth_headers(), timeout=30)
    response.raise_for_status()
    return response.content


def load_history() -> list[dict]:
    try:
        response = requests.get(
            ANALYSIS_URL,
            params={"limit": 10},
            headers=auth_headers(),
            timeout=5,
        )
        response.raise_for_status()
        return response.json()
    except requests.RequestException:
        return []


st.set_page_config(page_title="桌面物品双方案对比", page_icon="🔎", layout="wide")
st.title("桌面物品双方案对比")
st.caption("Streamlit + FastAPI + Celery Worker + SQLAlchemy")

current_user = load_current_user()
if current_user is None:
    st.info("请先登录。分析记录与结果图片仅本人可访问。")
    login_tab, register_tab = st.tabs(["登录", "注册"])
    with login_tab:
        with st.form("login_form"):
            login_username = st.text_input("用户名", key="login_username")
            login_password = st.text_input("密码", type="password", key="login_password")
            login_submit = st.form_submit_button("登录", type="primary")
        if login_submit:
            try:
                login(login_username, login_password)
                st.rerun()
            except Exception as error:
                st.error(str(error))
    with register_tab:
        with st.form("register_form"):
            register_username = st.text_input("用户名", key="register_username")
            register_password = st.text_input(
                "密码（至少 8 位）", type="password", key="register_password"
            )
            register_submit = st.form_submit_button("注册并登录")
        if register_submit:
            try:
                register(register_username, register_password)
                login(register_username, register_password)
                st.rerun()
            except Exception as error:
                st.error(str(error))
    st.stop()

with st.sidebar:
    st.write(f"当前用户：`{current_user['username']}`")
    if st.button("退出登录"):
        for key in ["access_token", "result", "active_analysis_id"]:
            st.session_state.pop(key, None)
        st.rerun()

st.info(
    "图片进入独立消息队列，由 Worker 运行 YOLO、MobileSAM 和本地 Qwen3-VL。"
    "页面通过任务状态接口查询进度；图片与历史记录按登录用户隔离。"
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

if uploaded is not None:
    st.image(uploaded, caption="待分析图片", width="stretch")
    if st.button(
        "提交异步分析任务",
        type="primary",
        width="stretch",
        disabled=bool(st.session_state.get("active_analysis_id")),
    ):
        clear_displayed_result()
        try:
            queued = enqueue_analysis(uploaded)
            st.session_state["active_analysis_id"] = queued["id"]
            st.session_state["active_digest"] = current_digest
            st.rerun()
        except Exception as error:
            st.error(str(error))

active_id = st.session_state.get("active_analysis_id")
if active_id:
    try:
        active = get_analysis(active_id)
        active_status = active.get("status")
        st.info(
            f"任务 #{active_id}：{STATUS_LABELS.get(active_status, active_status)}"
        )
        if active_status not in TERMINAL_STATUSES:
            if st.button("取消当前任务", type="secondary"):
                cancel_analysis(active_id)
                st.rerun()
            time.sleep(2)
            st.rerun()
        else:
            st.session_state.pop("active_analysis_id", None)
            if active_status == "succeeded":
                if active.get("digest") == current_digest:
                    st.session_state["result"] = active
                    st.success("分析完成")
                else:
                    st.info("任务已完成，可在最近分析记录中查看。")
            else:
                clear_displayed_result()
                st.error(
                    active.get("error_message")
                    or f"任务{STATUS_LABELS.get(active_status, active_status)}"
                )
    except Exception as error:
        st.error(str(error))

result = st.session_state.get("result")
if result and result.get("digest") == current_digest:
    yolo_result = result.get("yolo", {})
    sam_result = result.get("sam", {})
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
            if sam_result.get("skipped"):
                st.caption("YOLO 未检测到目标，本次已跳过 SAM。")

        traditional_column, vlm_column = st.columns(2, gap="large")
        with traditional_column:
            st.markdown("### 传统视觉方案")
            st.dataframe(
                [
                    {"类别": name, "数量": count}
                    for name, count in yolo_result.get("counts", {}).items()
                ],
                width="stretch",
                hide_index=True,
            )
        with vlm_column:
            st.markdown("### 本地视觉大模型方案")
            st.dataframe(
                [
                    {
                        "物品": item["name"],
                        "数量": item["count"],
                        "置信度": item["confidence"],
                        "判断依据": item["reason"],
                    }
                    for item in vlm_result.get("items", [])
                ],
                width="stretch",
                hide_index=True,
            )

        summary = result.get("summary", {})
        metric_yolo, metric_vlm, metric_masks = st.columns(3)
        metric_yolo.metric("YOLO 检测目标", summary.get("yolo_detection_count", 0))
        metric_vlm.metric("Qwen3-VL 清单物品", summary.get("vlm_item_count", 0))
        metric_masks.metric("MobileSAM 生成掩膜", summary.get("sam_mask_count", 0))
        st.success(f"分析记录 #{result.get('id')} 已保存，且仅当前用户可访问。")

with st.expander("最近分析记录", expanded=False):
    history = load_history()
    if history:
        st.dataframe(
            [
                {
                    "编号": item.get("id"),
                    "文件名": item.get("filename"),
                    "状态": STATUS_LABELS.get(item.get("status"), item.get("status")),
                    "YOLO目标": item.get("summary", {}).get("yolo_detection_count"),
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
        st.caption("暂无属于当前用户的分析记录。")
