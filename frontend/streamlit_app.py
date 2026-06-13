"""RAVDA Streamlit frontend — upload data and ask questions in natural language."""

from __future__ import annotations

import base64
import os
from typing import Any

import pandas as pd
import streamlit as st
from dotenv import load_dotenv

from api_client import ApiError, RavdaClient

load_dotenv()

RAG_STATUS_LABELS = {
  "pending": "待索引",
  "indexing": "索引中",
  "ready": "已就绪",
  "failed": "失败",
  "skipped": "已跳过",
}


def _init_state() -> None:
  defaults: dict[str, Any] = {
    "api_base_url": os.getenv(
      "API_BASE_URL",
      f"http://{os.getenv('HOST', '127.0.0.1')}:{os.getenv('PORT', '8000')}",
    ),
    "dataset_id": None,
    "profile": None,
    "rag_status": None,
    "session_id": None,
    "chat_turns": [],
    "pending_question": None,
  }
  for key, value in defaults.items():
    if key not in st.session_state:
      st.session_state[key] = value


def _client() -> RavdaClient:
  return RavdaClient(st.session_state.api_base_url)


def _rag_badge(status: str | None) -> str:
  label = RAG_STATUS_LABELS.get(status or "", status or "未知")
  return label


def _decode_chart(data_b64: str) -> bytes:
  return base64.b64decode(data_b64)


def _result_to_dataframe(result: Any) -> pd.DataFrame | None:
  if result is None:
    return None
  if isinstance(result, list):
    if not result:
      return pd.DataFrame()
    if all(isinstance(row, dict) for row in result):
      return pd.DataFrame(result)
    return pd.DataFrame({"value": result})
  if isinstance(result, dict):
    return pd.DataFrame([result])
  return pd.DataFrame({"结果": [result]})


def _render_profile(profile: dict[str, Any]) -> None:
  st.subheader("数据概览")
  cols = st.columns(4)
  cols[0].metric("行数", profile.get("row_count", 0))
  cols[1].metric("列数", profile.get("column_count", 0))
  cols[2].metric("文件名", profile.get("filename", ""))
  cols[3].metric("数据集 ID", profile.get("dataset_id", ""))

  column_rows = []
  for col in profile.get("columns", []):
    extra = ""
    if col.get("min_value") is not None and col.get("max_value") is not None:
      extra = f"{col['min_value']:.4g} ~ {col['max_value']:.4g}"
    elif col.get("date_min") and col.get("date_max"):
      extra = f"{col['date_min']} ~ {col['date_max']}"
    column_rows.append(
      {
        "列名": col.get("name"),
        "类型": col.get("dtype"),
        "空值率": f"{col.get('null_rate', 0):.1%}",
        "唯一值": col.get("unique_count"),
        "范围/摘要": extra,
      }
    )
  if column_rows:
    st.dataframe(pd.DataFrame(column_rows), use_container_width=True, hide_index=True)

  preview = profile.get("preview")
  if preview:
    st.caption("前 5 行预览")
    st.dataframe(pd.DataFrame(preview), use_container_width=True, hide_index=True)


def _render_turn(turn: dict[str, Any], index: int) -> None:
  role = "user" if turn.get("_role") == "user" else "assistant"
  with st.chat_message(role):
    if role == "user":
      st.markdown(turn.get("question", ""))
      return

    if turn.get("summary"):
      st.markdown(turn["summary"])

    if not turn.get("success", True):
      st.error(turn.get("error") or "执行失败")

    df = _result_to_dataframe(turn.get("result"))
    if df is not None and not df.empty:
      st.dataframe(df, use_container_width=True, hide_index=True)
    elif turn.get("result") is not None and turn.get("success"):
      st.json(turn["result"])

    for chart in turn.get("charts", []):
      try:
        img_bytes = _decode_chart(chart.get("data", ""))
        st.image(img_bytes, use_container_width=True)
      except (ValueError, TypeError):
        st.warning(f"图表 {index + 1} 解码失败")

    meta_parts = []
    if turn.get("codegen_source"):
      meta_parts.append(f"代码来源: {turn['codegen_source']}")
    if turn.get("summary_source"):
      meta_parts.append(f"结论来源: {turn['summary_source']}")
    if turn.get("rag_used"):
      meta_parts.append(f"RAG 片段: {turn.get('rag_chunk_count', 0)}")
    if turn.get("attempts", 0) > 0:
      meta_parts.append(f"重试: {turn['attempts']} 次")
    if meta_parts:
      st.caption(" · ".join(meta_parts))

    code = turn.get("generated_code")
    if code:
      with st.expander("生成的 Pandas 代码"):
        st.code(code, language="python")


def _clear_chat() -> None:
  st.session_state.session_id = None
  st.session_state.chat_turns = []


def _apply_upload_response(data: dict[str, Any]) -> None:
  profile = data.get("profile", {})
  st.session_state.dataset_id = profile.get("dataset_id")
  st.session_state.profile = profile
  st.session_state.rag_status = data.get("rag_index_status")
  _clear_chat()


def _apply_dataset_detail(data: dict[str, Any]) -> None:
  profile = data.get("profile", {})
  st.session_state.dataset_id = profile.get("dataset_id")
  st.session_state.profile = profile
  st.session_state.rag_status = data.get("rag_index_status")
  _clear_chat()


def _format_file_size(size_bytes: int) -> str:
  if size_bytes < 1024:
    return f"{size_bytes} B"
  if size_bytes < 1024 * 1024:
    return f"{size_bytes / 1024:.1f} KB"
  return f"{size_bytes / (1024 * 1024):.1f} MB"


def _render_recent_datasets() -> None:
  st.markdown("**最近上传**")
  try:
    payload = _client().list_datasets(limit=10)
    datasets = payload.get("datasets", [])
  except ApiError as exc:
    st.caption(str(exc))
    return

  if not datasets:
    st.caption("暂无历史记录")
    return

  for item in datasets:
    filename = item.get("original_filename", "未知文件")
    created_at = item.get("created_at", "")
    if created_at:
      created_at = created_at.replace("T", " ")[:19]
    size_label = _format_file_size(int(item.get("file_size_bytes", 0)))
    rows = item.get("row_count", 0)
    cols = item.get("column_count", 0)
    dataset_id = item.get("dataset_id", "")
    is_active = dataset_id == st.session_state.dataset_id
    label = f"{filename} ({rows}×{cols}, {size_label})"
    if is_active:
      label = f"▶ {label}"
    button_key = f"recent_dataset_{dataset_id}"
    if st.button(label, key=button_key, use_container_width=True):
      try:
        detail = _client().get_dataset(dataset_id)
        _apply_dataset_detail(detail)
        st.rerun()
      except ApiError as exc:
        st.error(str(exc))
    if created_at:
      st.caption(created_at)


def _append_assistant_turn(response: dict[str, Any]) -> None:
  st.session_state.session_id = response.get("session_id")
  st.session_state.chat_turns.append(
    {
      "_role": "assistant",
      "question": response.get("question"),
      "summary": response.get("summary"),
      "generated_code": response.get("generated_code"),
      "codegen_source": response.get("codegen_source"),
      "summary_source": response.get("summary_source"),
      "result": response.get("result"),
      "charts": response.get("charts", []),
      "success": response.get("success"),
      "error": response.get("error"),
      "attempts": response.get("attempts"),
      "rag_used": response.get("rag_used"),
      "rag_chunk_count": response.get("rag_chunk_count"),
    }
  )


def main() -> None:
  st.set_page_config(
    page_title="RAVDA",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
  )

  st.markdown(
    """
    <style>
      .block-container { padding-top: 1.5rem; }
      [data-testid="stSidebar"] { background-color: #f8fafc; }
    </style>
    """,
    unsafe_allow_html=True,
  )

  _init_state()

  with st.sidebar:
    st.title("RAVDA")
    st.caption("智能数据分析与可视化助手")

    st.session_state.api_base_url = st.text_input(
      "后端 API 地址",
      value=st.session_state.api_base_url,
      help="FastAPI 服务地址，默认 http://127.0.0.1:8000",
    )

    if st.button("检查连接", use_container_width=True):
      try:
        health = _client().health()
        st.success(f"已连接 · {health.get('service', 'ravda')}")
        if health.get("rag_configured"):
          st.info("RAGFlow 已配置")
        else:
          st.caption("RAGFlow 未配置（检索将跳过）")
      except ApiError as exc:
        st.error(str(exc))

    st.divider()

    uploaded = st.file_uploader(
      "上传数据文件",
      type=["csv", "xlsx", "xls"],
      help="支持 CSV、Excel，最大 50 MB",
    )

    if uploaded is not None:
      if st.button("开始上传并分析", type="primary", use_container_width=True):
        try:
          file_bytes = uploaded.getvalue()
          if not file_bytes:
            st.error("文件为空")
          else:
            data = _client().upload_dataset(file_bytes, uploaded.name)
            _apply_upload_response(data)
            if data.get("deduplicated"):
              st.info("该文件已上传过，已加载历史数据集")
            else:
              st.success("上传成功，已生成数据画像")
            st.rerun()
        except ApiError as exc:
          st.error(str(exc))

    st.divider()
    _render_recent_datasets()

    if st.session_state.dataset_id:
      st.divider()
      st.markdown("**当前数据集**")
      st.code(st.session_state.dataset_id, language=None)

      rag_status = st.session_state.rag_status
      st.caption(f"RAG 索引: {_rag_badge(rag_status)}")

      if st.button("刷新 RAG 状态", use_container_width=True):
        try:
          rag = _client().get_rag_status(st.session_state.dataset_id)
          st.session_state.rag_status = rag.get("rag_index_status")
          if rag.get("rag_index_error"):
            st.warning(rag["rag_index_error"])
          st.rerun()
        except ApiError as exc:
          st.error(str(exc))

      if st.button("重新索引 RAG", use_container_width=True):
        try:
          rag = _client().reindex_rag(st.session_state.dataset_id)
          st.session_state.rag_status = rag.get("rag_index_status")
          st.success("已触发重新索引")
          st.rerun()
        except ApiError as exc:
          st.error(str(exc))

      if st.button("新建对话", use_container_width=True):
        _clear_chat()
        st.rerun()

      if st.session_state.session_id and st.button("删除当前会话", use_container_width=True):
        try:
          _client().delete_session(st.session_state.session_id)
          _clear_chat()
          st.success("会话已删除")
          st.rerun()
        except ApiError as exc:
          st.error(str(exc))

  st.title("📊 RAVDA 数据分析助手")
  st.markdown("上传 CSV / Excel，用自然语言提问，自动统计并生成图表。")

  if st.session_state.profile:
    _render_profile(st.session_state.profile)
    st.divider()

    st.subheader("对话分析")
    if st.session_state.session_id:
      st.caption(f"会话 ID: {st.session_state.session_id}")

    for idx, turn in enumerate(st.session_state.chat_turns):
      _render_turn(turn, idx)

    question = st.chat_input("输入你的问题，例如：按地区统计销售额并画柱状图")
    if question:
      if not st.session_state.dataset_id:
        st.error("请先上传数据集")
      else:
        st.session_state.chat_turns.append({"_role": "user", "question": question})
        try:
          with st.spinner("分析中，请稍候…"):
            response = _client().query(
              st.session_state.dataset_id,
              question,
              st.session_state.session_id,
            )
          _append_assistant_turn(response)
          st.rerun()
        except ApiError as exc:
          st.session_state.chat_turns.pop()
          st.error(str(exc))
  else:
    st.info("请在左侧上传 CSV 或 Excel 文件开始使用。")
    with st.expander("示例问题"):
      st.markdown(
        """
        - 数据有多少行、多少列？各列是什么类型？
        - 按地区统计销售额并画柱状图
        - 销售额最高的前 5 个产品是什么？
        - 换成折线图
        - 计算各地区的平均单价
        """
      )


if __name__ == "__main__":
  main()
