import ast
import base64
import io
import math
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from dataclasses import dataclass, field
from typing import Any

import matplotlib
import matplotlib.pyplot as plt
from matplotlib import font_manager
import numpy as np
import pandas as pd

from app.config import MAX_CHART_COUNT, SANDBOX_TIMEOUT_SEC
from app.models.schemas import ChartArtifact
from app.services.profiler import _sanitize_value

matplotlib.use("Agg")

_PREFERRED_CJK_FONTS = (
    "Microsoft YaHei",
    "SimHei",
    "Noto Sans SC",
    "PingFang SC",
    "Heiti SC",
    "WenQuanYi Micro Hei",
    "Source Han Sans SC",
    "Arial Unicode MS",
)


def _configure_matplotlib_chinese() -> None:
    """Pick an installed CJK font so chart labels render Chinese correctly."""
    try:
        available = {f.name for f in font_manager.fontManager.ttflist}
        chosen = next((name for name in _PREFERRED_CJK_FONTS if name in available), None)
        if chosen:
            matplotlib.rcParams["font.sans-serif"] = [chosen, "DejaVu Sans"]
        matplotlib.rcParams["axes.unicode_minus"] = False
    except Exception:
        matplotlib.rcParams["axes.unicode_minus"] = False


_configure_matplotlib_chinese()

DANGEROUS_CALLS = frozenset(
    {"open", "exec", "eval", "compile", "__import__", "breakpoint", "input", "getattr", "setattr"}
)
DANGEROUS_MODULES = frozenset(
    {
        "os",
        "sys",
        "subprocess",
        "shutil",
        "pathlib",
        "socket",
        "requests",
        "urllib",
        "http",
        "importlib",
        "builtins",
        "pickle",
        "sqlite3",
        "ctypes",
    }
)
DANGEROUS_ATTRS = frozenset(
    {"__import__", "__subclasses__", "__globals__", "__code__", "__builtins__"}
)


class CodeValidationError(ValueError):
    pass


def _validate_ast(code: str) -> None:
    try:
        tree = ast.parse(code)
    except SyntaxError as exc:
        raise CodeValidationError(f"Syntax error: {exc}") from exc

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            raise CodeValidationError("Import statements are not allowed")
        if isinstance(node, ast.ImportFrom):
            raise CodeValidationError("Import statements are not allowed")
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            if node.func.id in DANGEROUS_CALLS:
                raise CodeValidationError(f"Call to '{node.func.id}' is not allowed")
        if isinstance(node, ast.Attribute) and node.attr in DANGEROUS_ATTRS:
            raise CodeValidationError(f"Access to '{node.attr}' is not allowed")


def _serialize_result(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, (str, int, float, bool)):
        if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
            return None
        return value
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        f = float(value)
        return None if math.isnan(f) or math.isinf(f) else f
    if isinstance(value, pd.DataFrame):
        records: list[dict[str, Any]] = []
        for row in value.head(100).to_dict(orient="records"):
            records.append({k: _sanitize_value(v) for k, v in row.items()})
        return {"type": "dataframe", "rows": records, "total_rows": len(value)}
    if isinstance(value, pd.Series):
        items = {_sanitize_value(k): _sanitize_value(v) for k, v in value.head(100).items()}
        return {"type": "series", "data": items, "total_items": len(value)}
    if isinstance(value, (list, tuple)):
        return [_serialize_result(v) for v in value[:100]]
    if isinstance(value, dict):
        return {str(k): _serialize_result(v) for k, v in list(value.items())[:100]}
    return str(value)


def _capture_charts() -> list[ChartArtifact]:
    charts: list[ChartArtifact] = []
    for fig_num in plt.get_fignums()[:MAX_CHART_COUNT]:
        fig = plt.figure(fig_num)
        buf = io.BytesIO()
        try:
            fig.savefig(buf, format="png", bbox_inches="tight")
            buf.seek(0)
            width, height = fig.get_size_inches() * fig.dpi
            charts.append(
                ChartArtifact(
                    format="png",
                    data=base64.b64encode(buf.read()).decode("ascii"),
                    width=int(width),
                    height=int(height),
                )
            )
        except Exception:
            continue
        finally:
            buf.close()
            plt.close(fig)
    return charts


@dataclass
class SandboxResult:
    success: bool
    result: Any = None
    charts: list[ChartArtifact] = field(default_factory=list)
    stdout: str = ""
    error: str | None = None


def _run_code(code: str, df: pd.DataFrame) -> SandboxResult:
    stdout_capture: list[str] = []

    def safe_print(*args: Any, **kwargs: Any) -> None:
        stdout_capture.append(" ".join(str(a) for a in args))

    namespace: dict[str, Any] = {
        "df": df.copy(),
        "pd": pd,
        "np": np,
        "plt": plt,
        "print": safe_print,
        "result": None,
    }

    try:
        exec(code, {"__builtins__": {}}, namespace)
    except Exception as exc:
        plt.close("all")
        return SandboxResult(success=False, error=f"Execution error: {exc}")

    charts = _capture_charts()
    serialized = _serialize_result(namespace.get("result"))
    stdout = "\n".join(stdout_capture).strip()

    return SandboxResult(
        success=True,
        result=serialized,
        charts=charts,
        stdout=stdout,
    )


def execute_pandas_code(code: str, df: pd.DataFrame) -> SandboxResult:
    try:
        _validate_ast(code)
    except CodeValidationError as exc:
        return SandboxResult(success=False, error=str(exc))

    executor = ThreadPoolExecutor(max_workers=1)
    future = executor.submit(_run_code, code, df)
    try:
        result = future.result(timeout=SANDBOX_TIMEOUT_SEC)
    except FuturesTimeoutError:
        future.cancel()
        plt.close("all")
        result = SandboxResult(
            success=False,
            error=f"Execution timed out after {SANDBOX_TIMEOUT_SEC}s",
        )
    except Exception as exc:
        plt.close("all")
        result = SandboxResult(success=False, error=f"Sandbox error: {exc}")
    finally:
        executor.shutdown(wait=False, cancel_futures=True)

    return result
