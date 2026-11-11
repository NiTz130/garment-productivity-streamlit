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
            "half_shift_workers_min": 0,
            "converted_workers_max": 89,
        },
    }


@pytest.fixture
def item():
    return {"sku": "S-01", "product": "Áo", "smv": 18.5, "key": '["S-01","Áo",18.5]'}


def test_form_converts_percent_and_half_shift_without_duplicate_workers(catalog, item):
    result = ui_adapter.parse_form({
        "target": "80,5",
        "full_shift_workers": "30",
        "half_shift_workers": "1",
        "overtime": "0",
        "bonus": "500.000",
        "idle": "0",
    }, item, catalog)

    assert result["ok"]
    assert result["inputs"] == {
        "target": 0.805,
        "smv": 18.5,
        "full_shift_workers": 30,
        "half_shift_workers": 1,
        "overtime": 0,
        "bonus": 500000,
        "idle": 0,
    }
    assert "workers" not in result["inputs"]


def test_empty_is_missing_and_never_becomes_zero(catalog, item):
    result = ui_adapter.parse_form({
        "target": "80", "full_shift_workers": "30",
        "half_shift_workers": "0", "overtime": "0",
        "bonus": "", "idle": "0",
    }, item, catalog)

    assert not result["ok"]
    assert "bonus" in result["missing"]
    assert result["inputs"] is None


@pytest.mark.parametrize("value", ["30.1", "30,3", "-1", "1.2.3"])
def test_integer_fields_reject_fractional_or_invalid_input(catalog, item, value):
    result = ui_adapter.parse_form({
        "target": "80", "full_shift_workers": value,
        "half_shift_workers": "0", "overtime": "0",
        "bonus": "0", "idle": "0",
    }, item, catalog)

    assert not result["ok"]
    assert "full_shift_workers" in result["errors"]


def test_form_uses_dynamic_catalog_limits(catalog, item):
    result = ui_adapter.parse_form({
        "target": "80", "full_shift_workers": "30",
        "half_shift_workers": "0", "overtime": "0",
        "bonus": "746.710", "idle": "0",
    }, item, catalog)

    assert not result["ok"]
    assert "bonus" in result["errors"]


def test_converted_labor_above_the_ceiling_is_an_error_on_the_half_shift_field(catalog, item):
    result = ui_adapter.parse_form(_form(full_shift_workers="89", half_shift_workers="1"), item, catalog)
    assert not result["ok"]
    assert "half_shift_workers" in result["errors"] and "full_shift_workers" not in result["errors"]


def test_converted_labor_exactly_at_the_ceiling_is_accepted(catalog, item):
    result = ui_adapter.parse_form(_form(full_shift_workers="80", half_shift_workers="18"), item, catalog)
    assert result["ok"] and result["inputs"]["half_shift_workers"] == 18


def test_full_shift_workers_alone_above_the_ceiling_is_an_error_on_the_full_field(catalog, item):
    result = ui_adapter.parse_form(_form(full_shift_workers="90", half_shift_workers="5"), item, catalog)
    assert "full_shift_workers" in result["errors"] and "half_shift_workers" not in result["errors"]


@pytest.mark.parametrize("blank", ["", "  ", None])
def test_blank_half_shift_count_means_zero_and_is_not_missing(catalog, item, blank):
    result = ui_adapter.parse_form(_form(half_shift_workers=blank), item, catalog)
    assert result["ok"] and result["inputs"]["half_shift_workers"] == 0


def test_missing_half_shift_key_means_zero(catalog, item):
    form = _form()
    del form["half_shift_workers"]
    assert ui_adapter.parse_form(form, item, catalog)["inputs"]["half_shift_workers"] == 0


@pytest.mark.parametrize("value", ["1,5", "2.5", "-1", "abc", "1.2.3"])
def test_half_shift_count_rejects_fractions_negatives_and_text(catalog, item, value):
    result = ui_adapter.parse_form(_form(half_shift_workers=value), item, catalog)
    assert not result["ok"] and "half_shift_workers" in result["errors"]
    assert "half_shift_workers" not in result["missing"]


def test_half_shift_count_does_not_hide_other_field_errors(catalog, item):
    result = ui_adapter.parse_form(_form(half_shift_workers="x", bonus=""), item, catalog)
    assert {"half_shift_workers", "bonus"} <= set(result["errors"])


def test_half_shift_count_converts_to_service_workers_end_to_end(catalog, item):
    inputs = ui_adapter.parse_form(_form(full_shift_workers="10", half_shift_workers="5"), item, catalog)["inputs"]
    assert ui_adapter.services.normalize_shift_inputs(inputs)["workers"] == 12.5


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


def _form(**changes):
    return {"target": "80", "full_shift_workers": "30", "half_shift_workers": "0",
            "overtime": "60", "bonus": "0", "idle": "0", **changes}


def test_overtime_is_per_person_and_sent_as_team_total(catalog, item):
    result = ui_adapter.parse_form(_form(), item, catalog)
    assert result["ok"]
    assert result["inputs"]["overtime"] == 30 * 60


def test_half_shift_worker_does_not_count_toward_overtime_total(catalog, item):
    result = ui_adapter.parse_form(_form(half_shift_workers="4"), item, catalog)
    assert result["inputs"]["overtime"] == 1800


def test_overtime_total_is_rounded_to_whole_minutes(catalog, item):
    result = ui_adapter.parse_form(_form(full_shift_workers="35", overtime="51,43"), item, catalog)
    assert result["inputs"]["overtime"] == 1800
    assert isinstance(result["inputs"]["overtime"], int)


@pytest.mark.parametrize("workers", range(2, 90))
@pytest.mark.parametrize("total", [1, 600, 1799, 4321, 12345, 25920])
def test_per_person_text_for_a_team_total_round_trips(catalog, item, workers, total):
    # applyOption in app.js writes round(total / workers, 2); the adapter must recover total.
    text = f"{total / workers:.2f}".replace(".", ",")
    result = ui_adapter.parse_form(_form(full_shift_workers=str(workers), overtime=text), item, catalog)
    result_total = result["inputs"]["overtime"] if result["ok"] else None
    if total / workers <= 720:
        assert result_total == total


def test_per_person_limit_is_720_when_catalog_provides_it(catalog, item):
    catalog["input_limits"]["overtime_per_worker"] = {"min": 0.0, "max": 720.0}
    assert ui_adapter.parse_form(_form(full_shift_workers="20", overtime="720"), item, catalog)["ok"]
    result = ui_adapter.parse_form(_form(full_shift_workers="20", overtime="721"), item, catalog)
    assert not result["ok"] and "overtime" in result["errors"]


def test_team_total_still_obeys_the_team_limit(catalog, item):
    catalog["input_limits"]["overtime_per_worker"] = {"min": 0.0, "max": 720.0}
    result = ui_adapter.parse_form(_form(full_shift_workers="89", overtime="720"), item, catalog)
    assert not result["ok"] and "overtime" in result["errors"]


def test_negative_and_invalid_per_person_overtime_are_rejected(catalog, item):
    assert "overtime" in ui_adapter.parse_form(_form(overtime="-1"), item, catalog)["errors"]
    assert "overtime" in ui_adapter.parse_form(_form(overtime="abc"), item, catalog)["errors"]


def test_missing_workers_reports_only_workers_and_does_not_crash(catalog, item):
    result = ui_adapter.parse_form(_form(full_shift_workers=""), item, catalog)
    assert not result["ok"]
    assert "full_shift_workers" in result["errors"] and "overtime" not in result["errors"]


def test_zero_overtime_is_valid(catalog, item):
    assert ui_adapter.parse_form(_form(overtime="0"), item, catalog)["inputs"]["overtime"] == 0


def test_frontend_catalog_exposes_per_person_overtime_limit():
    result = ui_adapter.catalog_for_frontend({"items": [], "input_limits": {"overtime": {"max": 25920.0}}})
    assert result["input_limits"]["overtime_per_worker"]["max"] == 720.0
    assert result["input_limits"]["overtime"]["max"] == 25920.0
