from __future__ import annotations
import math
from numbers import Real
import pandas as pd
import config


def rename_columns(df: pd.DataFrame) -> pd.DataFrame:
    mapping = dict(zip([
        "Mã SKU (Sản phẩm)", "Tên sản phẩm (Đề xuất)", "Năng suất mục tiêu(%)",
        "Thời gian tạo sản phẩm (Phút)", "Thời gian tăng ca (Phút)",
        "Tiền thưởng năng suất(NDT)", "Thời gian máy nghỉ(Phút)",
        "Số công nhân(Người)", "Năng xuất thực tế (%)"],
        ["sku", "product", "target", "smv", "overtime", "bonus", "idle", "workers", "actual"]))
    if not set(mapping).issubset(df.columns):
        raise ValueError("LỖI: Tệp dữ liệu thiếu cột bắt buộc.")
    return df.rename(columns=mapping)[list(mapping.values())].copy()


def validate(row: dict, actual: bool = False) -> dict:
    result = {}
    for key in config.FEATURES + (["actual"] if actual else []):
        value = row.get(key)
        low, high = config.RANGES[key]
        if isinstance(value, bool) or not isinstance(value, Real) or not math.isfinite(value):
            raise ValueError(f"LỖI: {config.LABELS[key]} bị thiếu hoặc không phải số hữu hạn.")
        if not low <= value <= high:
            raise ValueError(f"LỖI: {config.LABELS[key]} phải từ {low} đến {high}.")
        result[key] = float(value)
    return result


def load_data(path=config.SOURCE) -> pd.DataFrame:
    df = rename_columns(pd.read_excel(path, sheet_name=0, engine="openpyxl"))
    if df.empty or df.isna().any().any():
        raise ValueError("LỖI: Dữ liệu rỗng hoặc có ô trống.")
    for row in df.to_dict("records"):
        validate(row, actual=True)
    return df


def product_table(df: pd.DataFrame) -> pd.DataFrame:
    return df.groupby("product")["smv"].agg(smv="median", variants="nunique").reset_index()


def product_smv(table: pd.DataFrame, name: str) -> float:
    match = table.loc[table["product"] == name, "smv"]
    if match.empty:
        raise ValueError("LỖI: Tên sản phẩm không có trong dữ liệu.")
    return float(match.iloc[0])
