"""RAG service: index datasets into RAGFlow and retrieve semantic context for queries."""

from __future__ import annotations

import logging
import threading
import time
from pathlib import Path

from app.config import (
    RAGFLOW_EMBEDDING_MODEL,
    RAG_INDEX_MAX_WAIT_SEC,
    RAG_INDEX_POLL_INTERVAL_SEC,
    RAG_SIMILARITY_THRESHOLD,
    RAG_TOP_K,
)
from app.db.repositories.dataset_repo import get_rag_meta, update_rag_meta
from app.models.schemas import DatasetProfile, RagChunk, RagContext
from app.services.ragflow_client import get_ragflow_client, is_rag_configured

logger = logging.getLogger(__name__)

_inflight_lock = threading.Lock()
_inflight_indexing: set[str] = set()

KB_NAME_PREFIX = "ravda-"
PROFILE_DOC_NAME = "dataset_profile.md"
TABLE_CHUNK_METHOD = "table"
PROFILE_CHUNK_METHOD = "naive"


def kb_name_for_dataset(dataset_id: str) -> str:
    return f"{KB_NAME_PREFIX}{dataset_id}"


COLUMN_ZH_HINTS: dict[str, str] = {
    "region": "地区/区域",
    "city": "城市",
    "sales_amount": "销售额/销售金额",
    "cost_amount": "成本/成本金额",
    "product_name": "产品名称/商品名",
    "product_category": "产品品类/商品类别",
    "order_date": "订单日期/下单日期",
    "order_id": "订单编号/订单号",
    "quantity": "数量/购买数量",
    "unit_price": "单价/商品单价",
    "discount_rate": "折扣率/优惠比例",
    "payment_method": "支付方式/付款方式",
    "customer_segment": "客户分层/客群/会员等级",
    "sales_channel": "销售渠道/渠道",
    "is_returned": "是否退货/退货标记",
    "satisfaction_score": "满意度评分/客户满意度",
    "shipping_days": "配送天数/物流时效",
    "salesperson_id": "导购员/销售人员工号",
    "is_promotion": "是否大促/促销标记",
    "sku_code": "SKU编码/货号",
}


def profile_to_markdown(profile: DatasetProfile) -> str:
    lines = [
        f"# Dataset Profile: {profile.filename}",
        "",
        "数据集字段说明（供中英文语义检索）",
        "",
        f"- Dataset ID: {profile.dataset_id}",
        f"- Rows: {profile.row_count}",
        f"- Columns: {profile.column_count}",
        "",
        "## Columns",
    ]

    for col in profile.columns:
        lines.append(f"### {col.name}")
        zh_hint = COLUMN_ZH_HINTS.get(col.name.lower())
        if zh_hint:
            lines.append(f"- 中文语义: {zh_hint}")
        lines.append(f"- dtype: {col.dtype}")
        lines.append(f"- null_rate: {col.null_rate:.4f}")
        lines.append(f"- unique_count: {col.unique_count}")
        if col.min_value is not None:
            lines.append(
                f"- numeric range: min={col.min_value}, max={col.max_value}, mean={col.mean_value}"
            )
        if col.date_min:
            lines.append(f"- date range: {col.date_min} to {col.date_max}")
        if col.top_values:
            tops = ", ".join(f"{item['value']}({item['count']})" for item in col.top_values[:5])
            lines.append(f"- top values: {tops}")

    if profile.preview:
        lines.extend(["", "## Preview (first rows)"])
        for row in profile.preview[:5]:
            lines.append(f"- {row}")

    return "\n".join(lines)


def format_rag_context_for_prompt(context: RagContext | None) -> str:
    if context is None or context.skipped or not context.chunks:
        return ""

    chunk_lines: list[str] = []
    for idx, chunk in enumerate(context.chunks, start=1):
        source = chunk.document_name or "unknown"
        chunk_lines.append(f"[{idx}] ({source}, score={chunk.similarity:.3f})\n{chunk.content}")

    return (
        "Relevant knowledge from indexed dataset documents (semantic hints; "
        "use DatasetProfile for numeric stats):\n"
        + "\n\n".join(chunk_lines)
        + "\n\n"
    )


def _set_index_status(
    dataset_id: str,
    status: str,
    *,
    kb_id: str | None = None,
    error: str | None = None,
) -> None:
    try:
        update_rag_meta(
            dataset_id,
            ragflow_kb_id=kb_id,
            rag_index_status=status,
            rag_index_error=error,
        )
    except ValueError as exc:
        logger.warning("Failed to update RAG index status for %s: %s", dataset_id, exc)


def _find_dataset_by_name(client, name: str):
    """Find a knowledge base by name without server-side name filter.

    RAGFlow 0.19.x returns a permission error when ``list_datasets(name=...)``
    targets a non-existent dataset; listing all and filtering locally avoids that.
    """
    try:
        datasets = client.list_datasets(page_size=100)
    except Exception as exc:
        raise RuntimeError(f"Failed to list RAGFlow knowledge bases: {exc}") from exc

    for dataset in datasets:
        if getattr(dataset, "name", "") == name:
            return dataset
    return None


def _ensure_knowledge_base(client, dataset_id: str, filename: str):
    name = kb_name_for_dataset(dataset_id)
    try:
        existing = _find_dataset_by_name(client, name)
        if existing is not None:
            return existing
        return client.create_dataset(
            name=name,
            description=f"RAVDA dataset {dataset_id} ({filename})",
            chunk_method=PROFILE_CHUNK_METHOD,
            embedding_model=RAGFLOW_EMBEDDING_MODEL,
        )
    except Exception as exc:
        raise RuntimeError(f"Failed to ensure RAGFlow knowledge base: {exc}") from exc


def _wait_for_documents(dataset, document_ids: list[str]) -> None:
    deadline = time.monotonic() + RAG_INDEX_MAX_WAIT_SEC
    pending = set(document_ids)
    terminal_states = {"DONE", "FAIL", "CANCEL"}

    while pending and time.monotonic() < deadline:
        for doc_id in list(pending):
            try:
                docs = dataset.list_documents(id=doc_id)
            except Exception:
                continue
            if not docs:
                continue

            doc = docs[0]
            run_state = str(getattr(doc, "run", "") or "").upper()
            progress = float(getattr(doc, "progress", 0.0) or 0.0)

            if run_state in terminal_states or progress >= 1.0:
                if run_state == "FAIL":
                    raise RuntimeError(
                        f"Document {doc_id} parsing failed: {getattr(doc, 'progress_msg', '')}"
                    )
                pending.discard(doc_id)

        if pending:
            time.sleep(RAG_INDEX_POLL_INTERVAL_SEC)

    if pending:
        raise TimeoutError(
            f"RAG indexing timed out after {RAG_INDEX_MAX_WAIT_SEC}s for documents: {sorted(pending)}"
        )


def index_dataset(
    dataset_id: str,
    stored_path: Path,
    profile: DatasetProfile,
) -> None:
    if not is_rag_configured():
        _set_index_status(dataset_id, "skipped", error="RAGFlow is not configured")
        return

    client = get_ragflow_client()
    if client is None:
        _set_index_status(dataset_id, "skipped", error="RAGFlow client unavailable")
        return

    _set_index_status(dataset_id, "indexing", error=None)

    try:
        kb = _ensure_knowledge_base(client, dataset_id, profile.filename)
        kb_id = kb.id
        _set_index_status(dataset_id, "indexing", kb_id=kb_id, error=None)

        current_model = str(getattr(kb, "embedding_model", "") or "")
        if current_model != RAGFLOW_EMBEDDING_MODEL:
            try:
                kb.update({"embedding_model": RAGFLOW_EMBEDDING_MODEL})
            except Exception as exc:
                logger.warning(
                    "Failed to update embedding model for dataset %s (%s -> %s): %s",
                    dataset_id,
                    current_model,
                    RAGFLOW_EMBEDDING_MODEL,
                    exc,
                )

        doc_count = int(getattr(kb, "document_count", 0) or 0)
        if doc_count > 0:
            try:
                existing_docs = kb.list_documents(page_size=1000)
                doc_ids = [doc.id for doc in existing_docs if doc.id]
                if doc_ids:
                    kb.delete_documents(doc_ids)
                else:
                    kb.delete_documents()
            except Exception as exc:
                logger.warning(
                    "Failed to clear existing documents for dataset %s: %s",
                    dataset_id,
                    exc,
                )

        profile_blob = profile_to_markdown(profile).encode("utf-8")
        try:
            file_blob = stored_path.read_bytes()
        except OSError as exc:
            raise RuntimeError(f"Failed to read dataset file for indexing: {exc}") from exc

        if not file_blob:
            raise ValueError("Dataset file is empty; cannot index")

        docs = kb.upload_documents(
            [
                {"display_name": PROFILE_DOC_NAME, "blob": profile_blob},
                {"display_name": profile.filename, "blob": file_blob},
            ]
        )
        if len(docs) < 2:
            raise RuntimeError("RAGFlow upload returned fewer documents than expected")

        table_doc = docs[1]
        try:
            table_doc.update({"chunk_method": TABLE_CHUNK_METHOD})
        except Exception as exc:
            logger.warning(
                "Failed to set table chunk_method for %s, continuing with dataset default: %s",
                dataset_id,
                exc,
            )

        doc_ids = [doc.id for doc in docs if doc.id]
        kb.async_parse_documents(doc_ids)
        _wait_for_documents(kb, doc_ids)

        _set_index_status(dataset_id, "ready", kb_id=kb_id, error=None)
        logger.info("RAG indexing completed for dataset %s (kb=%s)", dataset_id, kb_id)
    except Exception as exc:
        logger.exception("RAG indexing failed for dataset %s", dataset_id)
        _set_index_status(dataset_id, "failed", error=str(exc))


def schedule_dataset_indexing(
    dataset_id: str,
    stored_path: Path,
    profile: DatasetProfile,
    *,
    force: bool = False,
) -> bool:
    if not is_rag_configured():
        _set_index_status(dataset_id, "skipped", error="RAGFlow is not configured")
        return False

    with _inflight_lock:
        if dataset_id in _inflight_indexing and not force:
            return False
        _inflight_indexing.add(dataset_id)

    def _run() -> None:
        try:
            index_dataset(dataset_id, stored_path, profile)
        finally:
            with _inflight_lock:
                _inflight_indexing.discard(dataset_id)

    thread = threading.Thread(
        target=_run,
        name=f"rag-index-{dataset_id[:8]}",
        daemon=True,
    )
    thread.start()
    return True


def get_rag_status(dataset_id: str) -> dict[str, str | None]:
    meta = get_rag_meta(dataset_id)
    if meta is None:
        return {
            "rag_index_status": "unknown",
            "ragflow_kb_id": None,
            "rag_index_error": None,
        }
    return meta


def get_rag_index_status(dataset_id: str) -> str:
    meta = get_rag_meta(dataset_id)
    if meta is None:
        return "unknown"
    return str(meta.get("rag_index_status") or "pending")


def ensure_dataset_indexed(dataset_id: str) -> str:
    """Schedule background indexing when status is pending or failed."""
    if not is_rag_configured():
        return get_rag_index_status(dataset_id)

    status = get_rag_index_status(dataset_id)
    if status in ("ready", "indexing", "skipped"):
        return status

    # Lazy import avoids circular dependency with dataset_store.
    from app.services.dataset_store import find_dataset_path, get_dataset_profile

    path = find_dataset_path(dataset_id)
    profile = get_dataset_profile(dataset_id)
    if path is None or profile is None:
        return status

    if schedule_dataset_indexing(dataset_id, path, profile):
        return "indexing"
    return status


def reindex_dataset(dataset_id: str) -> str:
    if not is_rag_configured():
        _set_index_status(dataset_id, "skipped", error="RAGFlow is not configured")
        return "skipped"

    from app.services.dataset_store import find_dataset_path, get_dataset_profile

    path = find_dataset_path(dataset_id)
    profile = get_dataset_profile(dataset_id)
    if path is None or profile is None:
        raise ValueError(f"Dataset '{dataset_id}' not found")

    _set_index_status(dataset_id, "pending", error=None)
    with _inflight_lock:
        _inflight_indexing.discard(dataset_id)

    if schedule_dataset_indexing(dataset_id, path, profile, force=True):
        return "indexing"
    return get_rag_index_status(dataset_id)


def retrieve_context(dataset_id: str, question: str) -> RagContext:
    if not is_rag_configured():
        return RagContext(skipped=True, skip_reason="not_configured")

    meta = get_rag_meta(dataset_id)
    if meta is None:
        return RagContext(skipped=True, skip_reason="dataset_not_found")

    kb_id = meta.get("ragflow_kb_id")
    status = meta.get("rag_index_status") or "pending"
    if not kb_id:
        return RagContext(skipped=True, skip_reason="kb_not_created")
    if status != "ready":
        return RagContext(skipped=True, skip_reason=f"index_{status}")

    client = get_ragflow_client()
    if client is None:
        return RagContext(skipped=True, skip_reason="client_unavailable")

    try:
        raw_chunks = client.retrieve(
            dataset_ids=[kb_id],
            question=question,
            page_size=RAG_TOP_K,
            similarity_threshold=RAG_SIMILARITY_THRESHOLD,
            keyword=True,
        )
    except Exception as exc:
        logger.warning("RAG retrieval failed for dataset %s: %s", dataset_id, exc)
        return RagContext(skipped=True, skip_reason="retrieve_error")

    chunks = [
        RagChunk(
            content=str(getattr(chunk, "content", "") or "").strip(),
            document_name=str(getattr(chunk, "document_name", "") or ""),
            similarity=float(getattr(chunk, "similarity", 0.0) or 0.0),
        )
        for chunk in raw_chunks
        if str(getattr(chunk, "content", "") or "").strip()
    ]

    if not chunks:
        return RagContext(skipped=True, skip_reason="no_chunks")

    return RagContext(chunks=chunks)
