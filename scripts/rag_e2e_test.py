"""
RAVDA RAG end-to-end integration test (real environment).

Flow: health -> upload -> poll RAG index -> query -> verify rag_used.

Usage (from project root, server must be running):
    python scripts/rag_e2e_test.py
    python scripts/rag_e2e_test.py --base-url http://127.0.0.1:8000
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
SAMPLE_CSV = ROOT / "tests" / "data" / "sample_sales.csv"
DEFAULT_QUESTION = "按地区统计销售额并画柱状图"


def poll_rag_status(base_url: str, dataset_id: str, *, max_wait_sec: int = 300) -> dict:
    deadline = time.monotonic() + max_wait_sec
    last: dict = {}
    attempt = 0
    while time.monotonic() < deadline:
        attempt += 1
        resp = requests.get(
            f"{base_url}/api/v1/datasets/{dataset_id}/rag",
            timeout=30,
        )
        resp.raise_for_status()
        last = resp.json()
        status = last.get("rag_index_status")
        print(
            f"  rag poll {attempt}: status={status}, "
            f"kb={last.get('ragflow_kb_id')}, err={last.get('rag_index_error')}"
        )
        if status in ("ready", "failed", "skipped"):
            return last
        time.sleep(5)
    raise TimeoutError(f"RAG index did not finish within {max_wait_sec}s; last={last}")


def main() -> int:
    parser = argparse.ArgumentParser(description="RAVDA RAG end-to-end test")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--question", default=DEFAULT_QUESTION)
    parser.add_argument("--max-wait-sec", type=int, default=300)
    args = parser.parse_args()
    base_url = args.base_url.rstrip("/")

    print("RAVDA RAG end-to-end test\n")
    print(f"Base URL: {base_url}")

    if not SAMPLE_CSV.is_file():
        print(f"FAIL: sample file not found: {SAMPLE_CSV}")
        return 1

    try:
        health = requests.get(f"{base_url}/health", timeout=10)
        health.raise_for_status()
    except requests.RequestException as exc:
        print(f"FAIL: health check: {exc}")
        return 1

    health_data = health.json()
    print(f"health: {health_data}")
    if not health_data.get("rag_configured"):
        print("WARN: rag_configured=false (server may be old build or RAG disabled)")

    print("\n== upload ==")
    with SAMPLE_CSV.open("rb") as handle:
        upload_resp = requests.post(
            f"{base_url}/api/v1/datasets/upload",
            files={"file": ("sample_sales.csv", handle, "text/csv")},
            timeout=120,
        )
    if upload_resp.status_code != 200:
        print(f"FAIL: upload {upload_resp.status_code}: {upload_resp.text[:500]}")
        return 1

    upload = upload_resp.json()
    dataset_id = upload["profile"]["dataset_id"]
    print(f"dataset_id: {dataset_id}")
    print(f"initial rag_index_status: {upload.get('rag_index_status')}")

    print("\n== wait for RAG index ==")
    try:
        rag = poll_rag_status(base_url, dataset_id, max_wait_sec=args.max_wait_sec)
    except (requests.RequestException, TimeoutError) as exc:
        print(f"FAIL: {exc}")
        return 1

    if rag.get("rag_index_status") == "failed":
        err = str(rag.get("rag_index_error") or "")
        print(f"FAIL: RAG indexing failed: {err}")
        if "Fail to bind embedding model" in err or "has no attribute 'encode'" in err:
            print(
                "\nHint: configure an embedding model in RAGFlow "
                "(Settings -> Model Providers), then set RAGFLOW_EMBEDDING_MODEL in .env "
                "and POST /api/v1/datasets/{id}/rag/reindex"
            )
        return 1

    print("\n== query ==")
    try:
        query_resp = requests.post(
            f"{base_url}/api/v1/datasets/{dataset_id}/query",
            json={"question": args.question},
            timeout=180,
        )
        query_resp.raise_for_status()
    except requests.RequestException as exc:
        print(f"FAIL: query: {exc}")
        return 1

    result = query_resp.json()
    print(f"success: {result.get('success')}")
    print(f"rag_used: {result.get('rag_used')}")
    print(f"rag_chunk_count: {result.get('rag_chunk_count')}")
    print(f"rag_skip_reason: {result.get('rag_skip_reason')}")
    print(f"codegen_source: {result.get('codegen_source')}")
    print(f"summary_source: {result.get('summary_source')}")
    if result.get("error"):
        print(f"error: {result.get('error')}")

    issues: list[str] = []
    if not result.get("success"):
        issues.append("query execution failed")
    if rag.get("rag_index_status") == "ready" and not result.get("rag_used"):
        issues.append("index ready but rag_used=false")
    if rag.get("rag_index_status") not in ("ready", "skipped"):
        issues.append(f"unexpected rag_index_status={rag.get('rag_index_status')}")

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
