"""Nhánh biên của ui_adapter: số theo định dạng Việt Nam, lỗi backend, nhận dạng model."""
from __future__ import annotations

from decimal import Decimal

import pytest

import config
import ui_adapter

LIMITS = {
    "target": {"min": 0.0, "max": 1.0},
    "smv": {"min": 0.01, "max": 1000.0},
    "overtime": {"min": 5.0, "max": 25920.0, "unit": "phút"},
    "bonus": {"min": 0.0, "max": 746709.0, "unit": "VND"},
    "idle": {"min": 0.0, "max": 300.0, "unit": "phút"},
}
LABOR = {"full_shift_workers_min": 2, "half_shift_workers_min": 0, "converted_workers_max": 89}
ITEM = {"sku": "S", "product": "Áo", "smv": 18.5, "key": "k"}
FORM = {"target": "80", "full_shift_workers": "30", "half_shift_workers": "0",
        "overtime": "10", "bonus": "0", "idle": "0"}


def catalog(**limit_overrides):
    return {"input_limits": {**LIMITS, **limit_overrides}, "labor_entry": LABOR}


@pytest.mark.parametrize("raw, integer, expected", [
    ("1.234,56", False, Decimal("1234.56")),
    ("1,234.56", False, Decimal("1234.56")),
    ("500.000", True, Decimal("500000")),
    ("12,5", False, Decimal("12.5")),
    ("\u00a07 ", False, Decimal("7")),
    ("+3", False, Decimal("3")),
])
def test_locale_numbers_accept_vietnamese_and_mixed_separators(raw, integer, expected):
    assert ui_adapter._decimal_from_locale(raw, integer_field=integer) == expected


@pytest.mark.parametrize("raw", [None, "", "   ", "-", ",", "abc", "1.234,5.6", "1,234.5,6", "1e3"])
def test_locale_numbers_reject_blank_or_malformed(raw):
    with pytest.raises(ValueError):
        ui_adapter._decimal_from_locale(raw)


def test_negative_target_is_rejected():
    result = ui_adapter.parse_form({**FORM, "target": "-5"}, ITEM, catalog())
    assert result["errors"]["target"] == "Giá trị không được âm."


def test_target_below_catalog_minimum_is_rejected():
    result = ui_adapter.parse_form({**FORM, "target": "5"}, ITEM, catalog(target={"min": 0.1, "max": 1.0}))
    assert result["errors"]["target"] == "Mục tiêu thấp hơn giới hạn cho phép."


def test_target_above_one_hundred_percent_is_rejected():
    result = ui_adapter.parse_form({**FORM, "target": "100,1"}, ITEM, catalog())
    assert result["errors"]["target"] == "Mục tiêu vượt giới hạn cho phép."


def test_workers_below_minimum_is_rejected():
    result = ui_adapter.parse_form({**FORM, "full_shift_workers": "1"}, ITEM, catalog())
    assert "Tối thiểu 2" in result["errors"]["full_shift_workers"]


def test_integer_field_below_catalog_minimum_and_above_maximum():
    low = ui_adapter.parse_form({**FORM, "full_shift_workers": "2", "overtime": "1"}, ITEM, catalog())  # tổng cả tổ 2 < 5
    assert low["errors"]["overtime"].startswith("Giá trị tối thiểu là 5")
    high = ui_adapter.parse_form({**FORM, "idle": "301"}, ITEM, catalog())
    assert high["errors"]["idle"].startswith("Vượt giới hạn 300")


def test_product_missing_or_with_smv_out_of_range():
    missing = ui_adapter.parse_form(FORM, None, catalog())
    assert missing["missing"] == ["product"] and "product" in missing["errors"]
    far = ui_adapter.parse_form(FORM, {**ITEM, "smv": 5000.0}, catalog())
    assert far["errors"]["product"] == "Định mức của mẫu hàng nằm ngoài giới hạn dự báo."


def test_valid_form_without_limits_falls_back_to_defaults():
    result = ui_adapter.parse_form(FORM, ITEM, {})
    assert result["ok"] is False  # thiếu giới hạn nhân lực thì không chấp nhận 30 người


def test_prediction_and_recommendation_success(monkeypatch):
    monkeypatch.setattr(ui_adapter.services, "predict_shift", lambda inputs: {"value": 0.5})
    monkeypatch.setattr(ui_adapter.services, "recommend_options", lambda inputs: {"options": []})
    assert ui_adapter.run_prediction({}) == {"ok": True, "result": {"value": 0.5}, "message": None}
    assert ui_adapter.run_recommendations({})["result"] == {"options": []}


@pytest.mark.parametrize("error, kind", [(KeyError("x"), "backend_error"), (OSError("x"), "model_unavailable")])
def test_prediction_maps_unexpected_and_expected_errors(monkeypatch, error, kind):
    def boom(_inputs):
        raise error
    monkeypatch.setattr(ui_adapter.services, "predict_shift", boom)
    result = ui_adapter.run_prediction({})
    assert not result["ok"] and result["kind"] == kind
    assert result["message"]


@pytest.mark.parametrize("error", [ValueError("đường dẫn riêng D:/x"), KeyError("k")])
def test_recommendation_errors_are_sanitized(monkeypatch, error):
    def boom(_inputs):
        raise error
    monkeypatch.setattr(ui_adapter.services, "recommend_options", boom)
    result = ui_adapter.run_recommendations({})
    assert not result["ok"] and result["kind"] == "backend_error"
    assert "D:/x" not in result["message"]


def test_model_identity_handles_missing_files(monkeypatch, tmp_path):
    present = tmp_path / "source.xlsx"
    present.write_bytes(b"abc")
    monkeypatch.setattr(config, "MODEL", tmp_path / "chua-co.joblib")
    monkeypatch.setattr(config, "SOURCE", present)
    model_sig, source_sig = ui_adapter.model_identity()
    assert model_sig[1:] == (None, None)
    assert source_sig[2] == 3
    present.write_bytes(b"abcd")
    assert ui_adapter.model_identity()[1][2] == 4


def test_catalog_and_dashboard_loaders(monkeypatch):
    services = ui_adapter.services
    monkeypatch.setattr(services, "get_catalog", lambda: {"items": [ITEM]})
    loaded = ui_adapter.load_catalog()
    assert loaded["ok"] and loaded["catalog"]["items"][0]["key"] == ui_adapter.catalog_item_key(ITEM)
    monkeypatch.setattr(services, "get_management_dashboard", lambda product: {"p": product})
    assert ui_adapter.load_dashboard("Áo")["dashboard"] == {"p": "Áo"}

    def boom(*_args):
        raise RuntimeError("D:/bí-mật")
    monkeypatch.setattr(services, "get_catalog", boom)
    monkeypatch.setattr(services, "get_management_dashboard", boom)
    for failed in (ui_adapter.load_catalog(), ui_adapter.load_dashboard(None)):
        assert failed["ok"] is False and "D:/bí-mật" not in failed["message"]
