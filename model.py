from __future__ import annotations
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
import os
import tempfile
import joblib
import pandas as pd
from sklearn.linear_model import LinearRegression
from sklearn.model_selection import train_test_split
from sklearn.metrics import r2_score, mean_absolute_error
import config
from data import validate


def train(df: pd.DataFrame, logs: pd.DataFrame | None = None) -> dict:
    if not set(config.FEATURES + ["actual"]).issubset(df.columns):
        raise ValueError("LỖI: Thiếu cột huấn luyện.")
    for row in df.to_dict("records"):
        validate(row, actual=True)
    fit, test = train_test_split(df, test_size=.2, random_state=config.SEED)
    if logs is not None and not logs.empty:
        for row in logs.to_dict("records"):
            validate(row, actual=True)
        fit = pd.concat([fit, logs], ignore_index=True)
    estimator = LinearRegression().fit(fit[config.FEATURES], fit["actual"])
    predictions = estimator.predict(test[config.FEATURES])
    return {"model": estimator, "metadata": {
        "trained_at": datetime.now(timezone.utc).isoformat(),
        "r2": float(r2_score(test["actual"], predictions)),
        "mae": float(mean_absolute_error(test["actual"], predictions)),
        "rows": len(df) + (len(logs) if logs is not None else 0),
        "train_rows": len(fit), "test_rows": len(test),
        "stats": {k: {"mean": float(fit[k].mean()), "std": float(fit[k].std(ddof=0)),
                       "min": float(fit[k].min()), "max": float(fit[k].max())} for k in config.FEATURES},
        "log_id": int(logs["id"].max()) if logs is not None and not logs.empty else 0}}


def predict(bundle: dict, row: dict) -> dict:
    values = validate(row)
    raw = float(bundle["model"].predict(pd.DataFrame([values])[config.FEATURES])[0])
    if not pd.notna(raw) or abs(raw) == float("inf"):
        raise ValueError("LỖI: Mô hình trả kết quả không hữu hạn.")
    return {"raw": raw, "value": max(0., raw), "clipped": raw < 0}


@contextmanager
def model_lock(path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.with_suffix(".lock").open("a+b") as handle:
        handle.seek(0, 2)
        if handle.tell() == 0:
            handle.write(b"0")
            handle.flush()
        handle.seek(0)
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            raise ValueError("LỖI: Mô hình đang được cập nhật. Hãy thử lại.") from exc
        try:
            yield
        finally:
            handle.seek(0)
            if os.name == "nt":
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(handle, fcntl.LOCK_UN)


def atomic_save(bundle: dict, path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    os.close(fd)
    try:
        joblib.dump(bundle, name)
        os.replace(name, path)
    finally:
        Path(name).unlink(missing_ok=True)


def load(path=config.MODEL) -> dict:
    return joblib.load(path)


def initialize(df, path=config.MODEL) -> dict:
    with model_lock(path):
        if not Path(path).exists():
            atomic_save(train(df), path)
        return load(path)


def retrain(df, logs, path=config.MODEL, minimum=config.MIN_NEW_LOGS) -> dict:
    with model_lock(path):
        current = load(path)
        new_count = int((logs["id"] > current["metadata"]["log_id"]).sum()) if not logs.empty else 0
        if new_count < minimum:
            raise ValueError(f"LỖI: Cần ít nhất {minimum} dòng nhật ký mới; hiện có {new_count}.")
        updated = train(df, logs)
        backup = Path(path).with_suffix(".previous.joblib")
        atomic_save(current, backup)
        atomic_save(updated, path)
        return updated


def rollback(path=config.MODEL) -> dict:
    with model_lock(path):
        backup = Path(path).with_suffix(".previous.joblib")
        if not backup.exists():
            raise ValueError("LỖI: Chưa có bản mô hình cũ.")
        previous = load(backup)
        atomic_save(previous, path)
        return previous
