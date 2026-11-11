from __future__ import annotations

import hashlib
import math
from pathlib import Path

import joblib
import pandas as pd
import pytest
from sklearn.dummy import DummyRegressor
from sklearn.linear_model import LinearRegression
from sklearn.model_selection import GroupKFold

import config
import model
from data import (
    dataset_fingerprint,
    load_data,
    quality_report,
    read_workbook,
    validate,
)
from model import activate, atomic_save, load, predict, train


@pytest.fixture(scope="module")
def frame():
    return read_workbook()


@pytest.fixture(scope="module")
def bundle(frame):
    return train(frame)


@pytest.fixture
def row(frame):
    result = frame.iloc[0].to_dict()
    result.update(workers=30.5, overtime=0, bonus=0, idle=0, team="Tổ 1", shift_date="2026-11-02")
    return result


def _excel_frame(frame):
    return frame.rename(columns={v: k for k, v in config.SOURCE_TO_INTERNAL.items()})[config.SOURCE_COLUMNS]


def test_default_source_and_exact_headers(frame):
    assert frame.shape == (1197, 9)
    assert frame.index[0] == 2 and frame.index[-1] == 1198
    assert list(config.SOURCE_TO_INTERNAL)[5] == "Tiền thưởng năng suất (VNĐ)"
    assert list(config.SOURCE_TO_INTERNAL)[-1] == "Năng xuất thực tế (%)"
    assert list(frame.columns) == config.DATA_COLUMNS
    assert frame["actual"].max() > 1
    assert frame["actual"].max() <= config.HISTORY_RANGES["actual"][1]
    assert frame["bonus"].max() > 3600
    assert frame["bonus"].max() <= 1_000_000
    assert quality_report(frame)["trainable"]
    assert quality_report(frame)["exact_duplicate_count"] == 0
    assert quality_report(frame)["numeric_duplicate_count"] == 192
    loaded = load_data()
    assert loaded.shape == frame.shape
    assert loaded.index.equals(frame.index)


def test_workbook_bytes_empty_missing_columns_and_missing_values(frame, tmp_path):
    valid_path = tmp_path / "valid.xlsx"
    _excel_frame(frame.iloc[:8]).to_excel(valid_path, index=False)
    before = hashlib.sha256(valid_path.read_bytes()).hexdigest()
    in_memory = read_workbook(valid_path.read_bytes())
    assert in_memory.shape == (8, 9)
    assert hashlib.sha256(valid_path.read_bytes()).hexdigest() == before

    empty_path = tmp_path / "empty.xlsx"
    _excel_frame(frame.iloc[:0]).to_excel(empty_path, index=False)
    empty = read_workbook(empty_path)
    assert quality_report(empty)["rows"] == 0
    assert not quality_report(empty)["trainable"]
    with pytest.raises(ValueError, match="chưa đủ điều kiện"):
        load_data(empty_path)

    missing_path = tmp_path / "missing-column.xlsx"
    _excel_frame(frame.iloc[:3]).drop(columns=config.SOURCE_COLUMNS[0]).to_excel(missing_path, index=False)
    missing = read_workbook(missing_path)
    assert config.DATA_COLUMNS[0] in quality_report(missing)["missing_columns"]
    assert not quality_report(missing)["trainable"]

    blanks = _excel_frame(frame.iloc[:4]).copy()
    blanks.iloc[1, 2] = None
    missing_path = tmp_path / "missing-cell.xlsx"
    blanks.to_excel(missing_path, index=False)
    report = quality_report(read_workbook(missing_path))
    assert report["missing_cell_count"] == 1
    assert report["rows_with_missing"] == [3]
    with pytest.raises(ValueError, match="ô thiếu 1"):
        load_data(missing_path)


def test_type_boolean_nonfinite_and_range_are_blocking(frame):
    cases = []
    invalid = frame.iloc[:6].copy()
    invalid["target"] = invalid["target"].astype(object)
    invalid.iloc[0, invalid.columns.get_loc("target")] = "0.8"
    cases.append((invalid, "type_errors"))
    invalid = frame.iloc[:6].copy()
    invalid["target"] = invalid["target"].astype(object)
    invalid.iloc[0, invalid.columns.get_loc("target")] = True
    cases.append((invalid, "type_errors"))
    invalid = frame.iloc[:6].copy()
    invalid.iloc[0, invalid.columns.get_loc("target")] = float("inf")
    cases.append((invalid, "non_finite"))
    invalid = frame.iloc[:6].copy()
    invalid.iloc[0, invalid.columns.get_loc("target")] = float("nan")
    cases.append((invalid, "non_finite"))
    invalid = frame.iloc[:6].copy()
    invalid["actual"] = invalid["actual"].astype(object)
    invalid.iloc[0, invalid.columns.get_loc("actual")] = 2.01
    cases.append((invalid, "out_of_range"))
    for invalid, issue in cases:
        report = quality_report(invalid)
        assert report[issue]
        assert not report["trainable"]
        with pytest.raises(ValueError, match="không đủ điều kiện"):
            train(invalid)


@pytest.mark.parametrize("key", config.FEATURES + ["actual"])
@pytest.mark.parametrize("bad", [None, "1", True, float("nan"), float("inf"), -1])
def test_request_validation_rejects_bad_values(row, key, bad):
    row[key] = bad
    with pytest.raises(ValueError):
        validate(row, actual=True)


@pytest.mark.parametrize("key,bad", [
    ("target", 999999), ("smv", 999999), ("workers", 999999),
    ("overtime", 999999), ("bonus", 1_000_001), ("idle", 999999), ("actual", 999999),
])
def test_request_validation_rejects_over_limit(row, key, bad):
    row[key] = bad
    with pytest.raises(ValueError):
        validate(row, actual=True)


def test_request_validation_bounds(row):
    for key in config.FEATURES + ["actual"]:
        bounds = config.HISTORY_RANGES[key] if key == "actual" else config.INPUT_RANGES[key]
        for boundary in bounds:
            if boundary is None:
                continue
            assert validate({**row, key: boundary}, actual=True)[key] == boundary
        absent = dict(row)
        absent.pop(key)
        with pytest.raises(ValueError):
            validate(absent, actual=True)


def test_duplicates_and_outliers_are_reported(frame):
    duplicate = pd.concat([frame.iloc[:12], frame.iloc[[0]]], ignore_index=True)
    quality = quality_report(duplicate)
    assert quality["exact_duplicate_count"] == 1
    assert quality["numeric_duplicate_count"] >= 1
    assert quality["exact_duplicate_rows"] == [2, 14]
    assert quality["trainable"]

    outlier = frame.copy()
    outlier.loc[outlier.index[-1], "actual"] = 1.9
    report = quality_report(outlier)
    assert report["iqr_outlier_count"] > 0
    assert report["trainable"]


def test_prediction_order_units_and_clipping(frame, bundle, row, monkeypatch):
    expected = {key: row[key] for key in config.FEATURES}

    class OrderedEstimator:
        def predict(self, inputs):
            assert list(inputs.columns) == config.FEATURES
            assert inputs.iloc[0].to_dict() == expected
            return [-.2]

    monkeypatch.setitem(bundle, "model", OrderedEstimator())
    assert predict(bundle, row) == {"raw": -.2, "value": 0., "clipped": True}
    monkeypatch.setitem(bundle, "model", OrderedEstimator())
    bundle["model"].predict = lambda _: [1.4]
    assert predict(bundle, row) == {"raw": 1.4, "value": 1.4, "clipped": False}
    bundle["model"].predict = lambda _: [float("nan")]
    with pytest.raises(ValueError, match="không hữu hạn"):
        predict(bundle, row)


def test_grouped_training_has_one_candidate_metrics_and_no_leakage(frame, bundle):
    metadata = bundle["metadata"]
    assert config.MODELS == ("Linear Regression",)
    assert set(bundle["candidates"]) == set(config.MODELS)
    assert set(bundle["evaluations"]) == set(config.MODELS)
    assert metadata["train_rows"] + metadata["test_rows"] == len(frame)
    assert metadata["split"]["test_size"] == config.TRAINING_CONFIG["test_size"]
    assert metadata["split"]["random_state"] == config.TRAINING_CONFIG["random_state"]
    split = metadata["split"]
    assert set(split["train_group_ids"]).isdisjoint(split["test_group_ids"])
    train_frame = frame.loc[split["train_indices"]]
    groups = model._group_ids(train_frame)
    for train_index, valid_index in GroupKFold(n_splits=5).split(train_frame, train_frame.actual, groups):
        assert set(groups[i] for i in train_index).isdisjoint(groups[i] for i in valid_index)
    for score in bundle["evaluations"].values():
        assert all(math.isfinite(score[key]) for key in (
            "cv_rmse_mean", "cv_rmse_std", "test_mae", "test_rmse", "test_r2"
        ))
    assert metadata["features"] == config.FEATURES
    assert bundle["training_config"]["cv_splits"] == 5
    assert "r2" in metadata and "mae" in metadata
    same_inputs = frame.iloc[[0, 0]].copy()
    same_inputs.iloc[1, same_inputs.columns.get_loc("actual")] = .1
    assert model._group_ids(same_inputs)[0] == model._group_ids(same_inputs)[1]
    signed_zero = pd.DataFrame([
        {**{key: 0. for key in config.FEATURES}, "target": 0.},
        {**{key: 0. for key in config.FEATURES}, "target": -0.},
    ])
    assert model._group_ids(signed_zero)[0] == model._group_ids(signed_zero)[1]


def test_training_rejects_too_few_groups(frame):
    with pytest.raises(ValueError, match="nhóm đầu vào"):
        train(frame.iloc[:4])


def test_only_linear_regression_is_trained_and_selected(bundle):
    from sklearn.linear_model import LinearRegression

    assert isinstance(bundle["model"], LinearRegression)
    assert bundle["selected_model"] == bundle["algorithm"] == "Linear Regression"
    assert set(bundle["candidates"]) == {"Linear Regression"}
    assert set(bundle["training_config"]["estimators"]) == {"Linear Regression"}
    assert bundle["metadata"]["r2"] == bundle["evaluations"]["Linear Regression"]["test_r2"]


def test_bundle_of_another_algorithm_is_incompatible(bundle):
    other = {**bundle, "metadata": {**bundle["metadata"], "selected_model": "Random Forest"}}
    assert any("hồi quy tuyến tính" in error for error in model.compatibility_errors(other))
    with pytest.raises(ValueError, match="cần huấn luyện model mới"):
        predict(other, {key: 0 for key in config.FEATURES})


def test_legacy_load_is_read_only_and_does_not_invent_scores(bundle, tmp_path):
    old_path = tmp_path / "old.joblib"
    old = {"model": bundle["model"], "metadata": {"trained_at": "old", "mae": .12}}
    atomic_save(old, old_path)
    loaded = load(old_path)
    assert loaded["selected_model"] == "Linear Regression"
    assert loaded["metadata"]["mae"] == .12
    assert "r2" not in loaded["metadata"] and "rmse" not in loaded["metadata"]
    assert not loaded["evaluations"]
    assert model.compatibility_errors(loaded)
    with pytest.raises(ValueError, match="cần huấn luyện model mới"):
        predict(loaded, {key: 0 for key in config.FEATURES})


def test_activate_roundtrip_preserves_previous_file(bundle, tmp_path):
    path = tmp_path / "model.joblib"
    old = dict(bundle)
    old["metadata"] = {**bundle["metadata"], "marker": "old"}
    atomic_save(old, path)
    new = dict(bundle)
    new["metadata"] = {**bundle["metadata"], "marker": "new"}
    activate(new, path)
    assert load(path)["metadata"]["marker"] == "new"
    assert load(path.with_suffix(".previous.joblib"))["metadata"]["marker"] == "old"


def test_save_failure_keeps_active_model(bundle, tmp_path, monkeypatch):
    path = tmp_path / "model.joblib"
    atomic_save(bundle, path)
    before = path.read_bytes()
    new = dict(bundle)
    new["metadata"] = {**bundle["metadata"], "marker": "new"}
    original = model.atomic_save

    def fail_active(value, target):
        if Path(target) == path:
            raise OSError("disk full")
        return original(value, target)

    monkeypatch.setattr(model, "atomic_save", fail_active)
    with pytest.raises(OSError):
        activate(new, path)
    assert path.read_bytes() == before
    assert load(path)["metadata"].get("marker") is None


def test_atomic_failure_cleans_temp_and_lock_recovers(bundle, tmp_path, monkeypatch):
    path = tmp_path / "model.joblib"
    atomic_save(bundle, path)
    before = path.read_bytes()
    monkeypatch.setattr(model.joblib, "dump", lambda *args: (_ for _ in ()).throw(OSError("disk full")))
    with pytest.raises(OSError):
        atomic_save(bundle, path)
    assert path.read_bytes() == before
    assert not list(tmp_path.glob("*.tmp"))
    monkeypatch.undo()
    with model.model_lock(path):
        with pytest.raises(ValueError, match="đang được cập nhật"):
            with model.model_lock(path):
                pass


@pytest.mark.parametrize("workers", [30.0, 30.5])
def test_half_shift_workers_are_exactly_accepted(row, workers):
    row["workers"] = workers
    assert validate(row)["workers"] == workers


@pytest.mark.parametrize("workers", [30.1, 30.3, -0.5])
def test_off_step_or_negative_workers_are_rejected(row, workers):
    row["workers"] = workers
    with pytest.raises(ValueError):
        validate(row)


@pytest.mark.parametrize("key", ["bonus", "overtime", "idle"])
@pytest.mark.parametrize("value", [0, 5])
def test_zero_and_integer_minutes_or_vnd_are_valid(row, key, value):
    row[key] = value
    assert validate(row)[key] == value


@pytest.mark.parametrize("key", ["bonus", "overtime", "idle"])
def test_fractional_integer_input_is_rejected(row, key):
    row[key] = 0.5
    with pytest.raises(ValueError, match="số nguyên"):
        validate(row)


def test_historical_decimal_vnd_is_valid_but_not_an_input_value(frame):
    assert quality_report(frame)["trainable"]
    assert frame["bonus"].dtype.kind == "f"
    row = {"target": .8, "smv": 10.0, "workers": 30.0,
           "overtime": 0, "bonus": 10_370.95, "idle": 0}
    with pytest.raises(ValueError, match="số nguyên"):
        validate(row)


def test_history_reports_off_step_workers_without_repairing(frame):
    history = frame.copy()
    source_row = int(history.index[0])
    history.loc[source_row, "workers"] = 30.1
    report = quality_report(history)
    assert report["trainable"]
    assert report["historical_workers_off_half_step"] == [{"row": source_row, "value": 30.1}]
    assert history.loc[source_row, "workers"] == 30.1
