"""Thin HTTP client for the RAVDA FastAPI backend."""

from __future__ import annotations

import os
from typing import Any

import httpx
from dotenv import load_dotenv

load_dotenv()

DEFAULT_BASE_URL = os.getenv(
    "API_BASE_URL",
    f"http://{os.getenv('HOST', '127.0.0.1')}:{os.getenv('PORT', '8000')}",
).rstrip("/")

TIMEOUT_SEC = float(os.getenv("API_TIMEOUT_SEC", "120"))


class ApiError(Exception):
  def __init__(self, message: str, status_code: int | None = None) -> None:
    super().__init__(message)
    self.status_code = status_code


class RavdaClient:
  def __init__(self, base_url: str = DEFAULT_BASE_URL) -> None:
    self.base_url = base_url.rstrip("/")

  def _http_client(self, timeout: float) -> httpx.Client:
    # trust_env=False: ignore system HTTP_PROXY so localhost is not sent through a proxy (502).
    return httpx.Client(timeout=timeout, trust_env=False)

  def _url(self, path: str) -> str:
    return f"{self.base_url}{path}"

  def _handle_response(self, response: httpx.Response) -> Any:
    try:
      payload = response.json()
    except ValueError:
      payload = None

    if response.is_success:
      return payload

    detail = payload.get("detail") if isinstance(payload, dict) else None
    if isinstance(detail, list):
      message = "; ".join(str(item) for item in detail)
    elif detail is not None:
      message = str(detail)
    else:
      message = response.text or f"HTTP {response.status_code}"

    raise ApiError(message, status_code=response.status_code)

  def health(self) -> dict[str, Any]:
    try:
      with self._http_client(10.0) as client:
        response = client.get(self._url("/health"))
      return self._handle_response(response)
    except httpx.RequestError as exc:
      raise ApiError(f"无法连接后端: {exc}") from exc

  def upload_dataset(self, file_bytes: bytes, filename: str) -> dict[str, Any]:
    try:
      with self._http_client(TIMEOUT_SEC) as client:
        response = client.post(
          self._url("/api/v1/datasets/upload"),
          files={"file": (filename, file_bytes)},
        )
      return self._handle_response(response)
    except httpx.RequestError as exc:
      raise ApiError(f"上传失败: {exc}") from exc

  def list_datasets(self, limit: int = 10) -> dict[str, Any]:
    try:
      with self._http_client(30.0) as client:
        response = client.get(
          self._url("/api/v1/datasets"),
          params={"limit": limit},
        )
      return self._handle_response(response)
    except httpx.RequestError as exc:
      raise ApiError(f"获取历史数据集失败: {exc}") from exc

  def get_dataset(self, dataset_id: str) -> dict[str, Any]:
    try:
      with self._http_client(30.0) as client:
        response = client.get(self._url(f"/api/v1/datasets/{dataset_id}"))
      return self._handle_response(response)
    except httpx.RequestError as exc:
      raise ApiError(f"获取数据集详情失败: {exc}") from exc

  def get_rag_status(self, dataset_id: str) -> dict[str, Any]:
    try:
      with self._http_client(30.0) as client:
        response = client.get(self._url(f"/api/v1/datasets/{dataset_id}/rag"))
      return self._handle_response(response)
    except httpx.RequestError as exc:
      raise ApiError(f"获取 RAG 状态失败: {exc}") from exc

  def reindex_rag(self, dataset_id: str) -> dict[str, Any]:
    try:
      with self._http_client(TIMEOUT_SEC) as client:
        response = client.post(
          self._url(f"/api/v1/datasets/{dataset_id}/rag/reindex"),
        )
      return self._handle_response(response)
    except httpx.RequestError as exc:
      raise ApiError(f"重新索引失败: {exc}") from exc

  def create_session(self, dataset_id: str) -> dict[str, Any]:
    try:
      with self._http_client(30.0) as client:
        response = client.post(
          self._url(f"/api/v1/datasets/{dataset_id}/sessions"),
        )
      return self._handle_response(response)
    except httpx.RequestError as exc:
      raise ApiError(f"创建会话失败: {exc}") from exc

  def query(
    self,
    dataset_id: str,
    question: str,
    session_id: str | None = None,
  ) -> dict[str, Any]:
    body: dict[str, Any] = {"question": question}
    if session_id:
      body["session_id"] = session_id

    try:
      with self._http_client(TIMEOUT_SEC) as client:
        response = client.post(
          self._url(f"/api/v1/datasets/{dataset_id}/query"),
          json=body,
        )
      return self._handle_response(response)
    except httpx.RequestError as exc:
      raise ApiError(f"查询失败: {exc}") from exc

  def get_session(self, session_id: str) -> dict[str, Any]:
    try:
      with self._http_client(30.0) as client:
        response = client.get(self._url(f"/api/v1/sessions/{session_id}"))
      return self._handle_response(response)
    except httpx.RequestError as exc:
      raise ApiError(f"获取会话失败: {exc}") from exc

  def delete_session(self, session_id: str) -> dict[str, Any]:
    try:
      with self._http_client(30.0) as client:
        response = client.delete(self._url(f"/api/v1/sessions/{session_id}"))
      return self._handle_response(response)
    except httpx.RequestError as exc:
      raise ApiError(f"删除会话失败: {exc}") from exc
