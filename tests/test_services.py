from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pandas as pd
import pytest

import config
import model
import services
from data import history_usable_mask, quality_report
from data import read_workbook


@pytest.fixture(scope="module")
def frame():
    return read_workbook()


def _record(frame):
    quality = quality_report(frame)
    return {
        "frame": frame,
        "valid": frame.loc[history_usable_mask(frame)].copy(),
        "quality": quality,
        "fingerprint": "test-fingerprint",
        "signature": None,
    }


def _small_history():
    return pd.DataFrame([
        {"sku": "S1", "product": "Áo", "target": .8, "smv": 10.0, "workers": 2.0,
         "overtime": 0, "bonus": 0.0, "idle": 0, "actual": .4},
        {"sku": "S1", "product": "Áo", "target": .8, "smv": 10.0, "workers": 10.0,
         "overtime": 600, "bonus": 1000.0, "idle": 5, "actual": .7},
    ], columns=config.DATA_COLUMNS, index=pd.Index([2, 3], name="excel_row"))


class _DirectionalEstimator:
    def __init__(self, slope=1.0):
        self.slope = slope

    def predict(self, features):
        return [0.2 + self.slope * (
            (row.workers - 2) * .03 + row.overtime * .0001 + row.bonus * .0001
        ) for row in features.itertuples()]


def _compatible_bundle(estimator=None, fingerprint="test-fingerprint"):
    return {
        "model": estimator or _DirectionalEstimator(),
        "metadata": {
            "schema_version": config.SCHEMA_VERSION,
            "bonus_unit": config.BONUS_UNIT,
            "features": config.FEATURES.copy(),
            "dataset_fingerprint": fingerprint,
        },
    }


def test_catalog_has_sku_product_median_smv_and_vnd_limits(monkeypatch):
    frame = _small_history()
    frame.loc[3, "smv"] = 20.0
    record = _record(frame)
    monkeypatch.setattr(services, "_get_dataset", lambda path=config.SOURCE: record)
    result = services.get_catalog()
    assert result["items"] == [{
        "sku": "S1", "product": "Áo", "smv": 15.0,
        "smv_values": [10.0, 20.0], "has_multiple_smv": True, "observations": 2,
    }]
    assert result["input_limits"]["bonus"]["unit"] == "VND"
    assert result["input_limits"]["bonus"]["max"] == 1000
    assert result["input_limits"]["workers"]["step"] == .5
    assert result["labor_entry"]["full_shift_workers_max_with_half"] == 88
    assert result["recommendation_limits"]["bonus"]["max"] <= 1000


def test_predict_shift_returns_ratio_status_and_batch_matches_single(frame, monkeypatch):
    record = _record(frame)
    bundle = _compatible_bundle(_DirectionalEstimator(), record["fingerprint"])
    monkeypatch.setattr(services, "_get_dataset", lambda path=config.SOURCE: record)
    monkeypatch.setattr(services, "_get_model", lambda data, path=config.MODEL: bundle)
    inputs = {"target": .8, "smv": 10.0, "workers": 30.5,
              "overtime": 0, "bonus": 0, "idle": 0}
    result = services.predict_shift(inputs)
    batch = model.predict_batch(bundle, [inputs, inputs])
    assert result["inputs"]["workers"] == 30.5
    assert result["value"] == batch[0]["value"]
    assert batch[0] == batch[1]
    assert result["status"] == ("achieved" if result["value"] >= inputs["target"] else "below_target")
    assert "raw" in result and "clipped" in result
    half_shift = {key: value for key, value in inputs.items() if key != "workers"}
    half_shift.update(full_shift_workers=30, has_half_shift_worker=True)
    assert services.predict_shift(half_shift)["inputs"]["workers"] == 30.5


@pytest.mark.parametrize("entry", [
    {"full_shift_workers": 30},
    {"has_half_shift_worker": True},
    {"full_shift_workers": True, "has_half_shift_worker": False},
    {"full_shift_workers": 30.1, "has_half_shift_worker": False},
    {"full_shift_workers": 30, "has_half_shift_worker": 1},
    {"full_shift_workers": 30, "has_half_shift_worker": False, "workers": 30},
])
def test_shift_labor_entry_rejects_partial_or_ambiguous_counts(entry):
    with pytest.raises(ValueError):
        services.normalize_shift_inputs(entry)


def test_predict_validates_before_model_access_and_applies_dataset_bonus_limit(monkeypatch):
    record = _record(_small_history())
    monkeypatch.setattr(services, "_get_dataset", lambda path=config.SOURCE: record)
    monkeypatch.setattr(services, "_get_model", lambda *args: pytest.fail("invalid input loaded model"))
    incomplete = {"target": .8, "smv": 10.0, "workers": 2.0,
                  "overtime": 0, "idle": 0}
    with pytest.raises(ValueError, match="Tiền thưởng"):
        services.predict_shift(incomplete)
    excessive = {**incomplete, "bonus": 1001}
    with pytest.raises(ValueError, match="Tiền thưởng"):
        services.predict_shift(excessive)


def test_recommendations_use_three_distinct_directions_and_integer_steps(monkeypatch):
    record = _record(_small_history())
    bundle = _compatible_bundle(_DirectionalEstimator(), record["fingerprint"])
    monkeypatch.setattr(services, "_get_dataset", lambda path=config.SOURCE: record)
    monkeypatch.setattr(services, "_get_model", lambda data, path=config.MODEL: bundle)
    inputs = {"target": .5, "smv": 10.0, "workers": 2.0,
              "overtime": 0, "bonus": 0, "idle": 0}
    result = services.recommend_options(inputs)
    options = {option["id"]: option for option in result["options"]}
    assert set(options) == {"workers", "overtime", "combined"}
    assert all(option["available"] for option in options.values())
    staff = options["workers"]
    overtime = options["overtime"]
    combined = options["combined"]
    assert staff["inputs"]["workers"] > inputs["workers"]
    assert all(staff["deltas"][key] == 0 for key in ("overtime", "bonus", "idle", "smv", "target"))
    assert overtime["inputs"]["overtime"] > inputs["overtime"]
    assert all(overtime["deltas"][key] == 0 for key in ("workers", "bonus", "idle", "smv", "target"))
    assert sum(combined["deltas"][key] > 0 for key in ("workers", "overtime", "bonus")) >= 2
    for option in options.values():
        assert option["inputs"]["workers"] * 2 % 1 == 0
        assert isinstance(option["inputs"]["overtime"], int)
        assert isinstance(option["inputs"]["bonus"], int)
        assert option["inputs"]["target"] == inputs["target"]
        assert option["inputs"]["smv"] == inputs["smv"]
        assert option["inputs"]["idle"] == inputs["idle"]
        assert option["scope"] == "best_within_search"


def test_combined_option_can_hold_bonus_at_its_ceiling(monkeypatch):
    record = _record(_small_history())
    bundle = _compatible_bundle(_DirectionalEstimator(), record["fingerprint"])
    monkeypatch.setattr(services, "_get_dataset", lambda: record)
    monkeypatch.setattr(services, "_get_model", lambda data: bundle)
    inputs = {"target": .5, "smv": 10., "workers": 2.,
              "overtime": 0, "bonus": 950, "idle": 0}
    options = services.recommend_options(inputs)["options"]
    combined = next(option for option in options if option["id"] == "combined")
    assert combined["available"] and combined["achieved"]
    assert combined["inputs"]["bonus"] == 950
    assert combined["deltas"]["workers"] > 0
    assert combined["deltas"]["overtime"] > 0


def test_dashboard_reports_out_of_range_rows_as_excluded(monkeypatch):
    frame = _small_history()
    frame.loc[3, "target"] = 2.
    record = _record(frame)
    monkeypatch.setattr(services, "_get_dataset", lambda: record)
    assert record["quality"]["invalid_rows"] == [3]
    dashboard = services.get_management_dashboard()
    assert dashboard["quality"]["excluded_rows"] == 1
    assert dashboard["quality"]["excluded_source_rows"] == [3]
    assert dashboard["kpis"]["shift_count"] == 1


def test_recommendations_report_shortfall_or_unavailable_honestly(monkeypatch):
    record = _record(_small_history())
    bundle = _compatible_bundle(_DirectionalEstimator(slope=.05), record["fingerprint"])
    monkeypatch.setattr(services, "_get_dataset", lambda path=config.SOURCE: record)
    monkeypatch.setattr(services, "_get_model", lambda data, path=config.MODEL: bundle)
    inputs = {"target": 1.0, "smv": 10.0, "workers": 2.0,
              "overtime": 0, "bonus": 0, "idle": 0}
    result = services.recommend_options(inputs)
    assert any(option["available"] and option["status"] == "below_target"
               and option["shortfall"] > 0 for option in result["options"])

    constant = _compatible_bundle(type("Constant", (), {"predict": lambda self, x: [.2] * len(x)})(),
                                  record["fingerprint"])
    monkeypatch.setattr(services, "_get_model", lambda data, path=config.MODEL: constant)
    no_gain = services.recommend_options(inputs)
    assert all(not option["available"] and option["reason"] for option in no_gain["options"])


def test_recommendation_when_baseline_already_meets_goal_returns_no_adjustment(monkeypatch):
    record = _record(_small_history())
    bundle = _compatible_bundle(_DirectionalEstimator(), record["fingerprint"])
    monkeypatch.setattr(services, "_get_dataset", lambda path=config.SOURCE: record)
    monkeypatch.setattr(services, "_get_model", lambda data, path=config.MODEL: bundle)
    result = services.recommend_options({
        "target": .1, "smv": 10.0, "workers": 2.0,
        "overtime": 0, "bonus": 0, "idle": 0,
    })
    assert result["baseline"]["achieved"]
    assert all(not option["available"] and "đạt mục tiêu" in option["reason"]
               for option in result["options"])


def test_dashboard_filter_aligns_kpis_charts_and_history(frame, monkeypatch):
    record = _record(frame)
    monkeypatch.setattr(services, "_get_dataset", lambda path=config.SOURCE: record)
    product_name = frame.iloc[0]["product"]
    result = services.get_management_dashboard(product_name)
    subset = record["valid"].loc[record["valid"]["product"] == product_name]
    assert result["kpis"]["shift_count"] == len(subset)
    assert sum(row["observations"] for row in result["charts"]["product_comparison"]) == len(subset)
    assert len(result["charts"]["bonus_vs_actual"]) == len(subset)
    assert len(result["history"]) == len(subset)
    assert all(row["product"] == product_name for row in result["history"])
    assert result["kpis"]["actual_mean"] == pytest.approx(subset["actual"].mean())
    assert result["kpis"]["target_achievement_rate"] == pytest.approx(
        (subset["actual"] >= subset["target"]).mean()
    )
    assert "shift_date" not in result["history"][0]
    json.dumps(result, allow_nan=False)


def test_dashboard_empty_filter_and_invalid_rows_use_null_not_nonfinite(monkeypatch):
    frame = _small_history()
    frame["actual"] = frame["actual"].astype(object)
    frame.loc[3, "actual"] = float("nan")
    record = _record(frame)
    monkeypatch.setattr(services, "_get_dataset", lambda path=config.SOURCE: record)
    result = services.get_management_dashboard("no such product")
    assert result["kpis"] == {
        "shift_count": 0, "actual_mean": None,
        "target_achievement_rate": None, "idle_minutes_total": None,
    }
    assert result["charts"]["product_comparison"] == []
    assert result["charts"]["bonus_vs_actual"] == []
    assert result["history"] == []
    assert result["quality"]["excluded_rows"] == 1
    result = services.get_management_dashboard()
    assert result["kpis"]["shift_count"] == 1
    assert result["quality"]["excluded_source_rows"] == [3]
    json.dumps(result, allow_nan=False)
    with pytest.raises(ValueError):
        services.get_management_dashboard(product=3)


def test_dataset_cache_refreshes_after_workbook_change(frame, tmp_path):
    path = tmp_path / "source.xlsx"
    first = frame.iloc[:4].rename(columns={v: k for k, v in config.SOURCE_TO_INTERNAL.items()})
    first.to_excel(path, index=False)
    services.clear_caches()
    cached = services._get_dataset(path)
    assert services._get_dataset(path) is cached
    second = first.copy()
    second.iloc[0, second.columns.get_loc(config.SOURCE_COLUMNS[2])] = .7
    second.to_excel(path, index=False)
    refreshed = services._get_dataset(path)
    assert refreshed is not cached
    assert refreshed["frame"].iloc[0]["target"] == .7


def test_model_cache_refreshes_on_file_version_and_checks_dataset(frame, tmp_path, monkeypatch):
    path = tmp_path / "model.joblib"
    path.write_bytes(b"version one")
    record = _record(frame)
    record["fingerprint"] = "model-dataset"
    bundle = _compatible_bundle(fingerprint="model-dataset")
    calls = []
    monkeypatch.setattr(services.model, "load", lambda target: calls.append(Path(target).read_bytes()) or bundle)
    assert services._get_model(record, path) is bundle
    assert services._get_model(record, path) is bundle
    assert len(calls) == 1
    record["signature"] = ("source.xlsx", 2, 100)
    assert services._get_model(record, path) is bundle
    assert len(calls) == 2
    path.write_bytes(b"version two is longer")
    assert services._get_model(record, path) is bundle
    assert len(calls) == 3
    wrong = _compatible_bundle(fingerprint="other-data")
    monkeypatch.setattr(services.model, "load", lambda target: wrong)
    path.write_bytes(b"version three is different")
    with pytest.raises(ValueError, match="Dataset vận hành đã đổi"):
        services._get_model(record, path)


def test_facade_reads_sources_without_changing_excel_or_sqlite():
    source = config.SOURCE
    sqlite = config.ROOT / "runtime" / "logs.sqlite"
    source_hash = hashlib.sha256(source.read_bytes()).hexdigest()
    sqlite_hash = hashlib.sha256(sqlite.read_bytes()).hexdigest() if sqlite.exists() else None
    services.clear_caches()
    services.get_catalog()
    services.get_management_dashboard()
    assert hashlib.sha256(source.read_bytes()).hexdigest() == source_hash
    assert (hashlib.sha256(sqlite.read_bytes()).hexdigest() if sqlite.exists() else None) == sqlite_hash
