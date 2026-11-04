from __future__ import annotations

from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime, timezone
from hashlib import sha256
import json
import math
import os
from pathlib import Path
import shutil
import tempfile

import joblib
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.linear_model import LinearRegression
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.model_selection import GroupKFold, GroupShuffleSplit
from sklearn.tree import DecisionTreeRegressor

import config
from data import dataset_fingerprint, quality_report, validate


_ESTIMATORS = {
    "Linear Regression": lambda: LinearRegression(),
    "Decision Tree": lambda: DecisionTreeRegressor(**config.TRAINING_CONFIG["estimators"]["Decision Tree"]["params"]),
    "Random Forest": lambda: RandomForestRegressor(
        **config.TRAINING_CONFIG["estimators"]["Random Forest"]["params"]
    ),
}


def _group_ids(df: pd.DataFrame) -> list[str]:
    values = df[config.FEATURES].astype("float64").to_numpy()
    group_ids = []
    for row in values:
        normalized = [0. if value == 0 else float(value) for value in row]
        group_ids.append(sha256(json.dumps(normalized, separators=(",", ":"), allow_nan=False)
                                .encode("ascii")).hexdigest())
    return group_ids


def _validated_frame(df: pd.DataFrame) -> pd.DataFrame:
    if not set(config.FEATURES + ["actual"]).issubset(df.columns):
        raise ValueError("LỖI: Thiếu cột huấn luyện.")
    report = quality_report(df)
    if not report["trainable"]:
        raise ValueError(
            "LỖI: Dataset không đủ điều kiện huấn luyện; "
            f"ô thiếu {report['missing_cell_count']}, sai kiểu {len(report['type_errors'])}, "
            f"không hữu hạn {len(report['non_finite'])}, ngoài miền {len(report['out_of_range'])}."
        )
    result = df.copy()
    result["_source_index"] = df.index.tolist()
    return result.reset_index(drop=True)


def _metrics(actual, prediction) -> dict:
    return {
        "mae": float(mean_absolute_error(actual, prediction)),
        "rmse": float(math.sqrt(mean_squared_error(actual, prediction))),
        "r2": float(r2_score(actual, prediction)),
    }


def _fit_candidates(train_df: pd.DataFrame, test_df: pd.DataFrame,
                    dataset_hash: str, split: dict) -> dict:
    x_train = train_df[config.FEATURES]
    y_train = train_df["actual"]
    x_test = test_df[config.FEATURES]
    y_test = test_df["actual"]
    groups = _group_ids(train_df)
    group_count = len(set(groups))
    if group_count < config.TRAINING_CONFIG["cv_splits"]:
        raise ValueError(
            f"LỖI: Tập học chỉ có {group_count} nhóm đầu vào; cần ít nhất "
            f"{config.TRAINING_CONFIG['cv_splits']} nhóm cho GroupKFold."
        )
    if len(test_df) < 2:
        raise ValueError("LỖI: Tập kiểm tra có dưới 2 dòng, không đủ đánh giá R².")

    cv = GroupKFold(n_splits=config.TRAINING_CONFIG["cv_splits"])
    folds = list(cv.split(x_train, y_train, groups))
    for _, validation_indices in folds:
        if len(validation_indices) < 2:
            raise ValueError("LỖI: Một phần kiểm định chéo có dưới 2 dòng, không đủ đánh giá R².")

    evaluation = {}
    fitted = {}
    for name, factory in _ESTIMATORS.items():
        fold_scores = []
        for train_indices, validation_indices in folds:
            estimator = factory()
            estimator.fit(x_train.iloc[train_indices], y_train.iloc[train_indices])
            raw_prediction = estimator.predict(x_train.iloc[validation_indices])
            fold_scores.append(_metrics(y_train.iloc[validation_indices], raw_prediction))

        cv_rmse = [row["rmse"] for row in fold_scores]
        cv_mae = [row["mae"] for row in fold_scores]
        cv_r2 = [row["r2"] for row in fold_scores]
        estimator = factory().fit(x_train, y_train)
        test_metrics = _metrics(y_test, estimator.predict(x_test))
        evaluation[name] = {
            "cv_rmse_mean": float(pd.Series(cv_rmse).mean()),
            "cv_rmse_std": float(pd.Series(cv_rmse).std(ddof=0)),
            "cv_mae_mean": float(pd.Series(cv_mae).mean()),
            "cv_r2_mean": float(pd.Series(cv_r2).mean()),
            "test_mae": test_metrics["mae"],
            "test_rmse": test_metrics["rmse"],
            "test_r2": test_metrics["r2"],
        }
        fitted[name] = estimator

    selected_name = min(config.MODELS, key=lambda name: evaluation[name]["cv_rmse_mean"])
    training_config = deepcopy(config.TRAINING_CONFIG)
    metadata = {
        "format_version": config.MODEL_FORMAT_VERSION,
        "schema_version": config.SCHEMA_VERSION,
        "bonus_unit": config.BONUS_UNIT,
        "trained_at": datetime.now(timezone.utc).isoformat(),
        "selected_model": selected_name,
        "algorithm": selected_name,
        "evaluations": evaluation,
        "rows": len(train_df) + len(test_df),
        "train_rows": len(train_df),
        "test_rows": len(test_df),
        "dataset_hash": dataset_hash,
        "dataset_fingerprint": dataset_hash,
        "features": config.FEATURES.copy(),
        "split": split,
        "training_config": training_config,
        # Legacy keys remain real test-set metrics, never synthesized.
        "r2": evaluation[selected_name]["test_r2"],
        "mae": evaluation[selected_name]["test_mae"],
        "rmse": evaluation[selected_name]["test_rmse"],
    }
    return {
        "format_version": config.MODEL_FORMAT_VERSION,
        "selected_model": selected_name,
        "algorithm": selected_name,
        "model": fitted[selected_name],
        "candidates": fitted,
        "evaluations": evaluation,
        "training_config": training_config,
        "features": config.FEATURES.copy(),
        "dataset_hash": dataset_hash,
        "dataset_fingerprint": dataset_hash,
        "split": split,
        "metadata": metadata,
    }


def train(df: pd.DataFrame, dataset_hash: str | None = None) -> dict:
    """Train and compare all candidates using grouped holdout and grouped CV."""
    source = _validated_frame(df)
    groups = _group_ids(source)
    unique_groups = len(set(groups))
    if unique_groups < config.TRAINING_CONFIG["cv_splits"] + 1:
        raise ValueError(
            f"LỖI: Dataset chỉ có {unique_groups} nhóm đầu vào; cần đủ nhóm cho tập kiểm tra "
            "và 5 phần kiểm định chéo trên tập học."
        )
    splitter = GroupShuffleSplit(
        n_splits=1,
        test_size=config.TRAINING_CONFIG["test_size"],
        random_state=config.TRAINING_CONFIG["random_state"],
    )
    train_positions, test_positions = next(splitter.split(source, source["actual"], groups))
    train_df = source.iloc[train_positions].copy()
    test_df = source.iloc[test_positions].copy()
    if len(set(_group_ids(train_df))) < 5 or len(test_df) < 2:
        raise ValueError("LỖI: Chia nhóm hiện tại không tạo được tập đánh giá đủ lớn cho 5 phần CV và R².")
    test_groups = set(groups[position] for position in test_positions)
    train_groups = set(groups[position] for position in train_positions)
    if train_groups.intersection(test_groups):
        raise ValueError("LỖI: Nhóm đầu vào bị rò rỉ giữa tập học và tập kiểm tra.")
    identity = dataset_hash or dataset_fingerprint(df)
    split = {
        "method": "GroupShuffleSplit",
        "test_size": config.TRAINING_CONFIG["test_size"],
        "random_state": config.TRAINING_CONFIG["random_state"],
        "train_indices": [source.iloc[position]["_source_index"] for position in train_positions],
        "test_indices": [source.iloc[position]["_source_index"] for position in test_positions],
        "train_group_ids": sorted(train_groups),
        "test_group_ids": sorted(test_groups),
        "train_group_count": len(train_groups),
        "test_group_count": len(test_groups),
    }
    return _fit_candidates(train_df, test_df, identity, split)


def compatibility_errors(bundle: dict) -> list[str]:
    """Describe missing unit/schema evidence; never infer legacy model units."""
    if not isinstance(bundle, dict) or "model" not in bundle:
        return ["gói mô hình không hợp lệ"]
    metadata = bundle.get("metadata") or {}
    errors = []
    if metadata.get("schema_version") != config.SCHEMA_VERSION:
        errors.append("phiên bản schema đầu vào")
    if metadata.get("bonus_unit") != config.BONUS_UNIT:
        errors.append("đơn vị tiền thưởng VNĐ")
    if metadata.get("features", bundle.get("features")) != config.FEATURES:
        errors.append("thứ tự sáu đầu vào")
    if not metadata.get("dataset_fingerprint"):
        errors.append("fingerprint dataset huấn luyện")
    return errors


def assert_compatible(bundle: dict) -> None:
    errors = compatibility_errors(bundle)
    if errors:
        details = ", ".join(errors)
        raise ValueError(
            "LỖI: Mô hình cũ hoặc không tương thích (thiếu/xung đột "
            f"{details}); cần huấn luyện model mới bằng dataset VNĐ."
        )


def predict_batch(bundle: dict, rows) -> list[dict]:
    """Validate then predict a bounded batch in the configured feature order."""
    assert_compatible(bundle)
    validated = [validate(row) for row in rows]
    if not validated:
        return []
    matrix = pd.DataFrame(validated, columns=config.FEATURES)
    predictions = bundle["model"].predict(matrix)
    results = []
    for raw_value in predictions:
        raw = float(raw_value)
        if not math.isfinite(raw):
            raise ValueError("LỖI: Mô hình trả kết quả không hữu hạn.")
        results.append({"raw": raw, "value": max(0., raw), "clipped": raw < 0})
    return results


def predict(bundle: dict, row: dict) -> dict:
    return predict_batch(bundle, [row])[0]


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


def _stage_bundle(bundle: dict, path: Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    os.close(fd)
    try:
        joblib.dump(bundle, name)
    except Exception:
        Path(name).unlink(missing_ok=True)
        raise
    return Path(name)


def atomic_save(bundle: dict, path) -> None:
    path = Path(path)
    staged = _stage_bundle(bundle, path)
    try:
        os.replace(staged, path)
    finally:
        staged.unlink(missing_ok=True)


def _adapt_bundle(bundle: dict) -> dict:
    """Read legacy LinearRegression bundles without fabricating absent metrics."""
    if not isinstance(bundle, dict) or "model" not in bundle:
        raise ValueError("LỖI: Gói mô hình không hợp lệ.")
    metadata = dict(bundle.get("metadata") or {})
    selected = bundle.get("selected_model") or metadata.get("selected_model") or "Linear Regression"
    bundle["selected_model"] = selected
    bundle.setdefault("algorithm", metadata.get("algorithm", selected))
    bundle.setdefault("format_version", 1)
    bundle.setdefault("features", config.FEATURES.copy())
    bundle.setdefault("evaluations", metadata.get("evaluations", {}))
    bundle.setdefault("candidates", {selected: bundle["model"]})
    metadata.setdefault("selected_model", selected)
    metadata.setdefault("algorithm", selected)
    metadata.setdefault("format_version", bundle["format_version"])
    bundle["metadata"] = metadata
    return bundle


def load(path=config.MODEL) -> dict:
    return _adapt_bundle(joblib.load(path))


def activate(bundle: dict, path=config.MODEL) -> dict:
    """Atomically activate a complete bundle while preserving the former bundle."""
    path = Path(path)
    with model_lock(path):
        if path.exists():
            fd, name = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
            os.close(fd)
            staged_backup = Path(name)
            try:
                shutil.copyfile(path, staged_backup)
                os.replace(staged_backup, path.with_suffix(".previous.joblib"))
            finally:
                staged_backup.unlink(missing_ok=True)
        atomic_save(bundle, path)
        return _adapt_bundle(bundle)
