from __future__ import annotations

from hashlib import sha256
from io import BytesIO
import math
from numbers import Real
from decimal import Decimal, InvalidOperation

import pandas as pd

import config


def _normalized(df: pd.DataFrame) -> pd.DataFrame:
    """Rename known Excel headers without hiding missing or extra columns."""
    result = df.rename(columns=config.SOURCE_TO_INTERNAL).copy()
    if result.index.name != "excel_row":
        result.index = pd.RangeIndex(2, len(result) + 2, name="excel_row")
    return result


def read_workbook(source=config.SOURCE) -> pd.DataFrame:
    """Read the first Excel sheet; byte sources are kept in memory."""
    if isinstance(source, (bytes, bytearray, memoryview)):
        source = BytesIO(bytes(source))
    raw = pd.read_excel(source, sheet_name=0, engine="openpyxl")
    raw.attrs["source_column_count"] = len(raw.columns)
    return _normalized(raw)


def _excel_rows(df: pd.DataFrame, mask: pd.Series | list[bool]) -> list[int]:
    return [int(value) for value in df.index[mask].tolist()]


def _numeric(value) -> bool:
    return isinstance(value, (Real, Decimal)) and not isinstance(value, (bool,))


def _history_in_range(column: str, value: float) -> bool:
    low, high = config.HISTORY_RANGES[column]
    return value >= low and (high is None or value <= high)


def history_usable_mask(df: pd.DataFrame) -> pd.Series:
    """Mark complete, valid historical rows without imposing intake increments."""
    frame = _normalized(df)
    usable = []
    for _, row in frame.iterrows():
        good = True
        for column in config.DATA_COLUMNS:
            if column not in frame.columns:
                good = False
                break
            value = row[column]
            if column in ("sku", "product"):
                if not isinstance(value, str) or not value.strip():
                    good = False
                    break
                continue
            if (not _numeric(value) or not math.isfinite(float(value))
                    or not _history_in_range(column, float(value))):
                good = False
                break
        usable.append(good)
    return pd.Series(usable, index=frame.index, dtype=bool)


def quality_report(df: pd.DataFrame) -> dict:
    """Report quality problems without requiring the dataset to be trainable."""
    frame = _normalized(df)
    missing_columns = [column for column in config.DATA_COLUMNS if column not in frame.columns]
    required = [column for column in config.DATA_COLUMNS if column in frame.columns]

    missing_cells: list[dict] = []
    type_errors: list[dict] = []
    non_finite: list[dict] = []
    out_of_range: list[dict] = []
    iqr_outliers: list[dict] = []
    invalid_rows: set[int] = set()

    for row_number, row in frame.iterrows():
        for column in required:
            value = row[column]
            if pd.isna(value) or (isinstance(value, str) and not value.strip()):
                missing_cells.append({"row": int(row_number), "column": column})
                invalid_rows.add(int(row_number))
                if column in config.NUMERIC_COLUMNS and _numeric(value) and not math.isfinite(float(value)):
                    non_finite.append({"row": int(row_number), "column": column, "value": str(value)})
                continue
            if column in config.NUMERIC_COLUMNS:
                if not _numeric(value):
                    type_errors.append({"row": int(row_number), "column": column,
                                        "value": str(value), "type": type(value).__name__})
                    invalid_rows.add(int(row_number))
                    continue
                if not math.isfinite(float(value)):
                    non_finite.append({"row": int(row_number), "column": column,
                                       "value": str(value)})
                    invalid_rows.add(int(row_number))
                    continue
                low, high = config.HISTORY_RANGES[column]
                if not _history_in_range(column, float(value)):
                    out_of_range.append({"row": int(row_number), "column": column,
                                         "value": float(value), "min": low, "max": high})
                    invalid_rows.add(int(row_number))

    text_type_errors: list[dict] = []
    for row_number, row in frame.iterrows():
        for column in ("sku", "product"):
            if column not in frame.columns:
                continue
            value = row[column]
            if not pd.isna(value) and not isinstance(value, str):
                text_type_errors.append({"row": int(row_number), "column": column,
                                         "value": str(value), "type": type(value).__name__})
                invalid_rows.add(int(row_number))

    worker_step_errors = []
    if "workers" in frame.columns:
        for row_number, value in frame["workers"].items():
            if _numeric(value) and math.isfinite(float(value)):
                try:
                    steps = Decimal(str(value)) / Decimal("0.5")
                    if steps != steps.to_integral_value():
                        worker_step_errors.append({"row": int(row_number), "value": float(value)})
                except (InvalidOperation, ValueError):
                    worker_step_errors.append({"row": int(row_number), "value": str(value)})
                    invalid_rows.add(int(row_number))

    exact_duplicates: list[int] = []
    numeric_duplicates: list[int] = []
    if set(config.DATA_COLUMNS).issubset(frame.columns) and not frame.empty:
        exact_duplicates = _excel_rows(frame, frame[config.DATA_COLUMNS].duplicated(keep=False))
        numeric_duplicates = _excel_rows(frame, frame[config.NUMERIC_COLUMNS].duplicated(keep=False))

    for column in config.NUMERIC_COLUMNS:
        if column not in frame.columns:
            continue
        values = [float(value) for value in frame[column].tolist()
                  if _numeric(value) and math.isfinite(float(value))]
        if len(values) < 4:
            continue
        q1, q3 = pd.Series(values, dtype="float64").quantile([0.25, 0.75]).tolist()
        spread = q3 - q1
        low, high = q1 - 1.5 * spread, q3 + 1.5 * spread
        for row_number, value in frame[column].items():
            if _numeric(value) and math.isfinite(float(value)) and not low <= float(value) <= high:
                iqr_outliers.append({"row": int(row_number), "column": column,
                                     "value": float(value), "lower": float(low), "upper": float(high)})

    outlier_rows = sorted({item["row"] for item in iqr_outliers})
    numeric_duplicate_key = list(config.NUMERIC_COLUMNS) if set(config.NUMERIC_COLUMNS).issubset(frame.columns) else []
    type_errors.extend(text_type_errors)
    trainable = bool(len(frame) > 0 and not missing_columns and not missing_cells
                     and not type_errors and not non_finite and not out_of_range
                     and set(config.NUMERIC_COLUMNS).issubset(frame.columns))
    return {
        "rows": int(len(frame)),
        "columns": int(df.attrs.get("source_column_count", len(df.columns))),
        "missing_columns": missing_columns,
        "missing_cells": missing_cells,
        "missing_cell_count": len(missing_cells),
        "rows_with_missing": sorted({item["row"] for item in missing_cells}),
        "exact_duplicate_count": int(frame[config.DATA_COLUMNS].duplicated().sum())
        if set(config.DATA_COLUMNS).issubset(frame.columns) else 0,
        "exact_duplicate_rows": exact_duplicates,
        "numeric_duplicate_count": int(frame[numeric_duplicate_key].duplicated().sum()) if numeric_duplicate_key else 0,
        "numeric_duplicate_rows": numeric_duplicates,
        "type_errors": type_errors,
        "historical_workers_off_half_step": worker_step_errors,
        "non_finite": non_finite,
        "out_of_range": out_of_range,
        "iqr_outlier_count": len(iqr_outliers),
        "iqr_outlier_rows": outlier_rows,
        "iqr_outliers": iqr_outliers,
        "invalid_rows": sorted(invalid_rows),
        "trainable": trainable,
    }


def dataset_fingerprint(df: pd.DataFrame) -> str:
    """Stable identity for the normalized, currently selected working dataset."""
    frame = _normalized(df)
    columns = [column for column in config.DATA_COLUMNS if column in frame.columns]
    digest = sha256()
    digest.update("\x1f".join(columns).encode("utf-8"))
    digest.update(pd.util.hash_pandas_object(frame[columns], index=False).values.tobytes())
    return digest.hexdigest()


def validate(row: dict, actual: bool = False, limits: dict | None = None) -> dict:
    """Validate new shift input; this intentionally differs from history checks."""
    if not isinstance(row, dict):
        raise ValueError("LỖI: Đầu vào ca phải là một ánh xạ tên trường/giá trị.")
    allowed_ranges = limits or config.INPUT_RANGES
    result = {}
    for key in config.FEATURES + (["actual"] if actual else []):
        if key not in row or row[key] is None:
            raise ValueError(f"LỖI: Thiếu giá trị {config.LABELS[key]}.")
        value = row[key]
        if isinstance(value, bool) or not isinstance(value, (Real, Decimal)):
            raise ValueError(f"LỖI: {config.LABELS[key]} phải là số, không nhận chuỗi hoặc boolean.")
        try:
            number = float(value)
        except (TypeError, ValueError, OverflowError):
            raise ValueError(f"LỖI: {config.LABELS[key]} phải là số hữu hạn.") from None
        if not math.isfinite(number):
            raise ValueError(f"LỖI: {config.LABELS[key]} phải là số hữu hạn.")
        low, high = (config.HISTORY_RANGES[key] if key == "actual" else allowed_ranges[key])
        if number < low or (high is not None and number > high):
            raise ValueError(f"LỖI: {config.LABELS[key]} phải từ {low} đến {high}.")
        decimal_value = Decimal(str(value))
        if key in config.INTEGER_INPUTS and decimal_value != decimal_value.to_integral_value():
            raise ValueError(f"LỖI: {config.LABELS[key]} phải là số nguyên.")
        if key == "workers":
            steps = decimal_value / Decimal(str(config.WORKER_STEP))
            if steps != steps.to_integral_value():
                raise ValueError(f"LỖI: {config.LABELS[key]} chỉ nhận bước {config.WORKER_STEP}.")
        result[key] = int(decimal_value) if key in config.INTEGER_INPUTS else number
    return result


def load_data(path=config.SOURCE) -> pd.DataFrame:
    """Strict dataset reader retained for backend callers that require trainable rows."""
    frame = read_workbook(path)
    report = quality_report(frame)
    if not report["trainable"]:
        raise ValueError(
            "LỖI: Dữ liệu chưa đủ điều kiện huấn luyện; "
            f"thiếu cột {len(report['missing_columns'])}, ô thiếu {report['missing_cell_count']}, "
            f"sai kiểu {len(report['type_errors'])}, không hữu hạn {len(report['non_finite'])}, "
            f"ngoài miền {len(report['out_of_range'])}."
        )
    return frame[config.DATA_COLUMNS].copy()
