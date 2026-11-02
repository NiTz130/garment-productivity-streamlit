from __future__ import annotations
import math
import pandas as pd
import config
from data import validate


def report(logs: pd.DataFrame, stats: dict, threshold=config.DRIFT_THRESHOLD) -> pd.DataFrame:
    if not math.isfinite(threshold) or threshold <= 0:
        raise ValueError("LỖI: Ngưỡng drift phải lớn hơn 0.")
    if logs.empty:
        return pd.DataFrame(columns=["Biến", "Mức lệch", "Nhãn"])
    for row in logs.to_dict("records"):
        validate(row)
    rows = []
    for key in config.FEATURES:
        original = stats[key]
        gap = abs(float(logs[key].mean()) - original["mean"])
        score = gap / original["std"] if original["std"] > 0 else (0. if gap == 0 else float("inf"))
        rows.append({"Biến": config.LABELS[key], "Mức lệch": score,
                     "Nhãn": "cảnh báo" if score > threshold else "Bình thường"})
    return pd.DataFrame(rows)
