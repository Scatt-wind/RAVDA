"""Verify RAVDA is reachable the same way Dify Docker containers call it."""

from __future__ import annotations

import json
import subprocess
import sys
from urllib.error import URLError
from urllib.request import urlopen

HOST_HEALTH_URL = "http://127.0.0.1:8000/health"
DIFY_HEALTH_URL = "http://host.docker.internal:8000/health"
DIFY_API_CONTAINER = "dify-api-1"


def _check_from_host() -> tuple[bool, str]:
    try:
        with urlopen(HOST_HEALTH_URL, timeout=5) as resp:
            body = json.loads(resp.read().decode())
    except URLError as exc:
        return False, f"host: cannot reach {HOST_HEALTH_URL} ({exc})"
    if body.get("service") != "ravda":
        return False, f"host: unexpected response {body!r}"
    return True, "host: OK (RAVDA listening on 0.0.0.0:8000)"


def _check_from_dify_container() -> tuple[bool, str]:
    script = (
        "import httpx; "
        f"r=httpx.get('{DIFY_HEALTH_URL}', "
        "timeout=5, proxy='http://ssrf_proxy:3128'); "
        "print(r.text)"
    )
    try:
        proc = subprocess.run(
            ["docker", "exec", DIFY_API_CONTAINER, "python", "-c", script],
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        return False, f"dify: docker check skipped ({exc})"

    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "").strip()
        return False, f"dify: container check failed ({detail})"

    try:
        body = json.loads(proc.stdout.strip())
    except json.JSONDecodeError:
        return False, f"dify: SSRF proxy returned non-RAVDA body: {proc.stdout.strip()!r}"

    if body.get("service") != "ravda":
        return False, f"dify: unexpected response {body!r}"
    return True, "dify: OK via SSRF proxy + host.docker.internal"


def main() -> int:
    checks = [_check_from_host(), _check_from_dify_container()]
    failed = False
    for ok, message in checks:
        prefix = "PASS" if ok else "FAIL"
        print(f"[{prefix}] {message}")
        failed = failed or not ok

    if failed:
        print(
            "\nFix checklist:\n"
            "  1. Start RAVDA: uvicorn app.main:app --host 0.0.0.0 --port 8000\n"
            "  2. In Dify Agent tools, base URL must be http://host.docker.internal:8000\n"
            "  3. Do NOT use http://127.0.0.1:8000 — SSRF proxy will not reach RAVDA\n"
            "  4. For /query tools, raise Dify SSRF_DEFAULT_*_TIME_OUT (default 5s is too short)"
        )
        return 1

    print("\nRAVDA is reachable from Dify. Use DIFY_TOOL_BASE_URL in Agent custom tools.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
