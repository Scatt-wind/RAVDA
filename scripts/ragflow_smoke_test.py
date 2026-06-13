"""
RAGFlow connectivity smoke test for RAVDA.

Uses ragflow-sdk (requests path). Do NOT use httpx against RAGFLOW_BASE_URL.

Usage (from project root):
    python scripts/ragflow_smoke_test.py
    python scripts/ragflow_smoke_test.py --dataset-id <ravda_dataset_id>
    python scripts/ragflow_smoke_test.py --dataset-id <id> --question "按地区统计销售额"
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.config import (  # noqa: E402
    RAG_ENABLED,
    RAG_SIMILARITY_THRESHOLD,
    RAG_TOP_K,
    RAGFLOW_API_KEY,
    RAGFLOW_BASE_URL,
)
from app.services.rag_service import kb_name_for_dataset  # noqa: E402
from app.services.ragflow_client import get_ragflow_client, is_rag_configured  # noqa: E402


def _mask_secret(value: str) -> str:
    if not value:
        return "(empty)"
    if len(value) <= 8:
        return "***"
    return f"{value[:4]}...{value[-4:]}"


def _check_config() -> list[str]:
    issues: list[str] = []
    print("== RAGFlow config ==")
    print(f"RAG_ENABLED: {RAG_ENABLED}")
    print(f"RAGFLOW_BASE_URL: {RAGFLOW_BASE_URL or '(empty)'}")
    print(f"RAGFLOW_API_KEY: {_mask_secret(RAGFLOW_API_KEY)}")
    print(f"RAG_TOP_K: {RAG_TOP_K}")
    print(f"RAG_SIMILARITY_THRESHOLD: {RAG_SIMILARITY_THRESHOLD}")

    if not RAG_ENABLED:
        issues.append("RAG_ENABLED is false")
    if not RAGFLOW_BASE_URL:
        issues.append("RAGFLOW_BASE_URL is empty")
    if not RAGFLOW_API_KEY:
        issues.append("RAGFLOW_API_KEY is empty")
    return issues


def _check_list_datasets(client) -> tuple[list, list[str]]:
    issues: list[str] = []
    print("\n== list_datasets ==")
    try:
        datasets = client.list_datasets(page_size=30)
    except Exception as exc:
        issues.append(f"list_datasets failed: {exc}")
        print(f"FAIL: {exc}")
        return [], issues

    print(f"OK: returned {len(datasets)} dataset(s)")
    ravda_sets = [ds for ds in datasets if str(getattr(ds, "name", "")).startswith("ravda-")]
    if datasets:
        for ds in datasets[:10]:
            name = getattr(ds, "name", "")
            ds_id = getattr(ds, "id", "")
            doc_count = getattr(ds, "document_count", "?")
            chunk_count = getattr(ds, "chunk_count", "?")
            print(f"  - {name} (id={ds_id}, docs={doc_count}, chunks={chunk_count})")
        if len(datasets) > 10:
            print(f"  ... and {len(datasets) - 10} more")
    else:
        print("  (no knowledge bases yet - normal on a fresh RAGFlow instance)")

    if ravda_sets:
        print(f"RAVDA knowledge bases: {len(ravda_sets)}")
    return datasets, issues


def _pick_retrieve_target(client, datasets: list, dataset_id: str | None):
    if dataset_id:
        target_name = kb_name_for_dataset(dataset_id)
        for ds in datasets:
            if getattr(ds, "name", "") == target_name:
                return ds, target_name
        return None, target_name

    ready = [
        ds
        for ds in datasets
        if int(getattr(ds, "chunk_count", 0) or 0) > 0
    ]
    if ready:
        ds = ready[0]
        return ds, getattr(ds, "name", "")
    if datasets:
        ds = datasets[0]
        return ds, getattr(ds, "name", "")
    return None, None


def _check_retrieve(client, datasets: list, *, dataset_id: str | None, question: str) -> list[str]:
    issues: list[str] = []
    print("\n== retrieve ==")

    target, target_name = _pick_retrieve_target(client, datasets, dataset_id)
    if target is None:
        if dataset_id:
            msg = f"Knowledge base '{kb_name_for_dataset(dataset_id)}' not found; skip retrieve"
        else:
            msg = "No knowledge base available; skip retrieve"
        print(f"SKIP: {msg}")
        return issues

    kb_id = getattr(target, "id", "")
    chunk_count = int(getattr(target, "chunk_count", 0) or 0)
    print(f"Target: {target_name} (id={kb_id}, chunks={chunk_count})")
    print(f"Question: {question!r}")

    if chunk_count <= 0:
        print("SKIP: target knowledge base has no chunks yet (index may still be running)")
        return issues

    try:
        chunks = client.retrieve(
            dataset_ids=[kb_id],
            question=question,
            page_size=RAG_TOP_K,
            similarity_threshold=RAG_SIMILARITY_THRESHOLD,
            keyword=True,
        )
    except Exception as exc:
        issues.append(f"retrieve failed: {exc}")
        print(f"FAIL: {exc}")
        return issues

    print(f"OK: returned {len(chunks)} chunk(s)")
    for idx, chunk in enumerate(chunks[:3], start=1):
        content = str(getattr(chunk, "content", "") or "").strip().replace("\n", " ")
        if len(content) > 120:
            content = content[:117] + "..."
        doc_name = getattr(chunk, "document_name", "") or "unknown"
        score = float(getattr(chunk, "similarity", 0.0) or 0.0)
        print(f"  [{idx}] {doc_name} (score={score:.3f}) {content}")
    if len(chunks) > 3:
        print(f"  ... and {len(chunks) - 3} more")
    return issues


def main() -> int:
    parser = argparse.ArgumentParser(description="RAGFlow connectivity smoke test for RAVDA")
    parser.add_argument(
        "--dataset-id",
        help="RAVDA dataset_id; smoke test retrieve against ravda-{dataset_id} knowledge base",
    )
    parser.add_argument(
        "--question",
        default="数据集有哪些列？",
        help="Probe question for retrieve (default: 数据集有哪些列？)",
    )
    parser.add_argument(
        "--skip-retrieve",
        action="store_true",
        help="Only test config + list_datasets",
    )
    args = parser.parse_args()

    print("RAVDA RAGFlow smoke test\n")

    issues = _check_config()
    if issues:
        print("\nConfig issues:")
        for item in issues:
            print(f"  - {item}")
        print("\nResult: FAIL (fix .env and retry)")
        return 1

    if not is_rag_configured():
        print("\nResult: FAIL (RAG is not fully configured)")
        return 1

    get_ragflow_client.cache_clear()
    client = get_ragflow_client()
    if client is None:
        print("\nResult: FAIL (failed to initialize RAGFlow client)")
        return 1

    datasets, list_issues = _check_list_datasets(client)
    issues.extend(list_issues)

    if not args.skip_retrieve and not list_issues:
        issues.extend(
            _check_retrieve(
                client,
                datasets,
                dataset_id=args.dataset_id,
                question=args.question,
            )
        )

    print("\n== summary ==")
    if issues:
        for item in issues:
            print(f"FAIL: {item}")
        print("\nResult: FAIL")
        return 1

    print("Result: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
