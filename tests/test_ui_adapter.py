from __future__ import annotations

import pytest

import ui_adapter


@pytest.fixture
def catalog():
    return {
        "items": [],
        "input_limits": {
            "target": {"min": 0.0, "max": 1.0},
            "smv": {"min": 0.01, "max": 1000.0},
            "overtime": {"min": 0.0, "max": 25920.0},
            "bonus": {"min": 0.0, "max": 746709.0},
            "idle": {"min": 0.0, "max": 300.0},
        },
        "labor_entry": {
            "full_shift_workers_min": 2,
            "full_shift_workers_max_without_half": 89,
            "full_shift_workers_max_with_half": 88,
        },
    }


@pytest.fixture
def item():
    return {"sku": "S-01", "product": "Áo", "smv": 18.5, "key": '["S-01","Áo",18.5]'}


def test_form_converts_percent_and_half_shift_without_duplicate_workers(catalog, item):
    result = ui_adapter.parse_form({
        "target": "80,5",
        "full_shift_workers": "30",
        "has_half_shift_worker": True,
        "overtime": "0",
        "bonus": "500.000",
        "idle": "0",
    }, item, catalog)

    assert result["ok"]
    assert result["inputs"] == {
        "target": 0.805,
        "smv": 18.5,
        "full_shift_workers": 30,
        "has_half_shift_worker": True,
        "overtime": 0,
        "bonus": 500000,
        "idle": 0,
    }
    assert "workers" not in result["inputs"]


def test_empty_is_missing_and_never_becomes_zero(catalog, item):
    result = ui_adapter.parse_form({
        "target": "80", "full_shift_workers": "30",
        "has_half_shift_worker": False, "overtime": "0",
        "bonus": "", "idle": "0",
    }, item, catalog)

    assert not result["ok"]
    assert "bonus" in result["missing"]
    assert result["inputs"] is None


@pytest.mark.parametrize("value", ["30.1", "30,3", "-1", "1.2.3"])
def test_integer_fields_reject_fractional_or_invalid_input(catalog, item, value):
    result = ui_adapter.parse_form({
        "target": "80", "full_shift_workers": value,
        "has_half_shift_worker": False, "overtime": "0",
        "bonus": "0", "idle": "0",
    }, item, catalog)

    assert not result["ok"]
    assert "full_shift_workers" in result["errors"]


def test_form_uses_dynamic_catalog_limits(catalog, item):
    result = ui_adapter.parse_form({
        "target": "80", "full_shift_workers": "30",
        "has_half_shift_worker": False, "overtime": "0",
        "bonus": "746.710", "idle": "0",
    }, item, catalog)

    assert not result["ok"]
    assert "bonus" in result["errors"]


def test_selected_half_shift_uses_catalog_specific_integer_ceiling(catalog, item):
    result = ui_adapter.parse_form({
        "target": "80", "full_shift_workers": "89",
        "has_half_shift_worker": True, "overtime": "0",
        "bonus": "0", "idle": "0",
    }, item, catalog)

    assert not result["ok"]
    assert "full_shift_workers" in result["errors"]


def test_duplicate_product_names_keep_distinct_stable_catalog_keys():
    first = {"sku": "A", "product": "Áo", "smv": 12.0}
    second = {"sku": "B", "product": "Áo", "smv": 12.0}
    assert ui_adapter.catalog_item_key(first) != ui_adapter.catalog_item_key(second)


def test_model_errors_are_sanitized(monkeypatch):
    def unavailable(_inputs):
        raise ValueError("internal path D:/private/model.joblib is not compatible")

    monkeypatch.setattr(ui_adapter.services, "predict_shift", unavailable)
    result = ui_adapter.run_prediction({"target": 0.8})
    assert not result["ok"]
    assert result["kind"] == "model_unavailable"
    assert "D:/private" not in result["message"]
    assert "VNĐ" in result["message"]
