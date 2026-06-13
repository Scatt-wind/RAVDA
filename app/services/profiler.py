import math
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from app.models.schemas import ColumnProfile, DatasetProfile


def _sanitize_value(value: Any) -> Any:
    if value is None or (isinstance(value, float) and (math.isnan(value) or math.isinf(value))):
        return None
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        return None if math.isnan(float(value)) or math.isinf(float(value)) else float(value)
    if isinstance(value, (pd.Timestamp,)):
        return value.isoformat()
    if pd.isna(value):
        return None
    return value


def _preview_records(df: pd.DataFrame, limit: int = 5) -> list[dict[str, Any]]:
    preview_df = df.head(limit).copy()
    records: list[dict[str, Any]] = []
    for row in preview_df.to_dict(orient="records"):
        records.append({key: _sanitize_value(val) for key, val in row.items()})
    return records


def _build_column_profile(series: pd.Series) -> ColumnProfile:
    null_rate = float(series.isna().mean()) if len(series) else 0.0
    unique_count = int(series.nunique(dropna=True))

    profile = ColumnProfile(
        name=str(series.name),
        dtype=str(series.dtype),
        null_rate=null_rate,
        unique_count=unique_count,
    )

    if pd.api.types.is_numeric_dtype(series):
        numeric = pd.to_numeric(series, errors="coerce")
        profile.min_value = _sanitize_value(numeric.min())
        profile.max_value = _sanitize_value(numeric.max())
        profile.mean_value = _sanitize_value(numeric.mean())
    elif pd.api.types.is_datetime64_any_dtype(series):
        non_null = series.dropna()
        if not non_null.empty:
            profile.date_min = non_null.min().isoformat()
            profile.date_max = non_null.max().isoformat()
    else:
        top = series.value_counts(dropna=True).head(5)
        profile.top_values = [
            {"value": _sanitize_value(idx), "count": int(count)}
            for idx, count in top.items()
        ]

    return profile


def read_dataframe(file_path: Path) -> pd.DataFrame:
    suffix = file_path.suffix.lower()
    try:
        if suffix == ".csv":
            df = pd.read_csv(file_path)
        elif suffix in {".xlsx", ".xls"}:
            df = pd.read_excel(file_path)
        else:
            raise ValueError(f"Unsupported file type: {suffix}")
    except Exception as exc:
        raise ValueError(f"Failed to read file: {exc}") from exc

    if df.empty:
        raise ValueError("File contains no data rows")

    return df


def profile_dataframe(
    df: pd.DataFrame,
    dataset_id: str,
    filename: str,
) -> DatasetProfile:
    columns = [_build_column_profile(df[col]) for col in df.columns]

    return DatasetProfile(
        dataset_id=dataset_id,
        filename=filename,
        row_count=len(df),
        column_count=len(df.columns),
        columns=columns,
        preview=_preview_records(df),
    )


def profile_file(file_path: Path, dataset_id: str, filename: str) -> DatasetProfile:
    df = read_dataframe(file_path)
    return profile_dataframe(df, dataset_id, filename)
