"""Translate the browser's editable strings into the backend's input contract."""
from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
import json
import math
from pathlib import Path
import re

import config
import services


FORM_FIELDS = ("target", "full_shift_workers", "half_shift_workers", "overtime", "bonus", "idle")
FIELD_LABELS = {
    "target": "Mục tiêu",
    "full_shift_workers": "Nhân công cả ca",
    "half_shift_workers": "Nhân công nửa ca",
    "overtime": "Tăng ca mỗi người",
    "bonus": "Tiền thưởng",
    "idle": "Máy dừng",
}


def catalog_item_key(item: dict) -> str:
    """Return an identity that remains unique when product names are repeated."""
    return json.dumps(
        [str(item["sku"]), str(item["product"]), float(item["smv"])],
        ensure_ascii=False,
        separators=(",", ":"),
    )


def catalog_for_frontend(catalog: dict) -> dict:
    """Copy catalog data and add a stable browser key without changing services."""
    result = dict(catalog)
    result["items"] = [
        {**item, "key": catalog_item_key(item)} for item in catalog.get("items", [])
    ]
    result["input_limits"] = {
        **catalog.get("input_limits", {}),
        "overtime_per_worker": {"min": 0.0, "max": config.OVERTIME_PER_WORKER_MAX, "unit": "phút/người"},
    }
    return result


def _decimal_from_locale(raw: object, *, integer_field: bool = False) -> Decimal:
    if raw is None:
        raise ValueError("Trường này đang để trống.")
    value = str(raw).strip().replace("\u00a0", "").replace(" ", "")
    if not value:
        raise ValueError("Trường này đang để trống.")
    if value in {"-", "+", ".", ",", "-.", ","}:
        raise ValueError("Hãy nhập một số hoàn chỉnh.")
    if not re.fullmatch(r"[+-]?(?:\d+(?:[.,]\d*)?|[.,]\d+)(?:[.,]\d+)*", value):
        raise ValueError("Hãy nhập số theo định dạng Việt Nam.")

    # A dot-separated 3-digit grouping is unambiguous for integer VND/minutes
    # (for example 500.000); commas remain decimal separators in vi-VN.
    if integer_field and "," not in value and re.fullmatch(r"\d{1,3}(?:\.\d{3})+", value):
        normalized = value.replace(".", "")
    elif "." in value and "," in value:
        decimal_separator = "." if value.rfind(".") > value.rfind(",") else ","
        grouping_separator = "," if decimal_separator == "." else "."
        integer, fractional = value.rsplit(decimal_separator, 1)
        if grouping_separator in fractional:
            raise ValueError("Hãy nhập số theo định dạng Việt Nam.")
        integer = integer.replace(grouping_separator, "")
        if not integer or not integer.lstrip("+-").isdigit() or (fractional and not fractional.isdigit()):
            raise ValueError("Hãy nhập số theo định dạng Việt Nam.")
        normalized = f"{integer}.{fractional}" if fractional else integer
    else:
        normalized = value.replace(",", ".")

    try:
        number = Decimal(normalized)
    except InvalidOperation as exc:
        raise ValueError("Hãy nhập số theo định dạng Việt Nam.") from exc
    if not number.is_finite():
        raise ValueError("Số phải hữu hạn.")
    return number


def _read_number(raw: object, field: str, errors: dict, missing: list,
                 *, integer: bool = False) -> Decimal | None:
    if raw is None or str(raw).strip() == "":
        missing.append(field)
        errors[field] = f"Nhập {FIELD_LABELS[field].lower()}."
        return None
    try:
        number = _decimal_from_locale(raw, integer_field=integer)
    except ValueError as exc:
        errors[field] = str(exc)
        return None
    if number < 0:
        errors[field] = "Giá trị không được âm."
        return None
    if integer and number != number.to_integral_value():
        errors[field] = "Nhập số nguyên, không tự làm tròn."
        return None
    return number


def parse_form(form: dict, selected_item: dict | None, catalog: dict) -> dict:
    """Validate a browser draft and return the exact documented service input."""
    errors: dict[str, str] = {}
    missing: list[str] = []
    if selected_item is None:
        errors["product"] = "Chọn mẫu hàng để lấy định mức SMV."
        missing.append("product")

    target_percent = _read_number(form.get("target"), "target", errors, missing)
    full_workers = _read_number(
        form.get("full_shift_workers"), "full_shift_workers", errors, missing, integer=True
    )
    # A blank half-shift count means nobody works half a shift.
    half_blank = form.get("half_shift_workers") is None or str(form.get("half_shift_workers")).strip() == ""
    half_workers = Decimal(0) if half_blank else _read_number(
        form.get("half_shift_workers"), "half_shift_workers", errors, missing, integer=True
    )
    # Per-person minutes; decimals are allowed so an applied option's team total survives the round trip.
    overtime_per_person = _read_number(form.get("overtime"), "overtime", errors, missing)
    bonus = _read_number(form.get("bonus"), "bonus", errors, missing, integer=True)
    idle = _read_number(form.get("idle"), "idle", errors, missing, integer=True)

    limits = catalog.get("input_limits", {})
    if target_percent is not None:
        target_ratio = target_percent / Decimal(100)
        target_limit = limits.get("target", {})
        if target_ratio < Decimal(str(target_limit.get("min", 0))):
            errors["target"] = "Mục tiêu thấp hơn giới hạn cho phép."
        elif target_ratio > Decimal(str(target_limit.get("max", 1))):
            errors["target"] = "Mục tiêu vượt giới hạn cho phép."

    labor = catalog.get("labor_entry", {})
    maximum = Decimal(str(labor.get("converted_workers_max", 0)))
    if full_workers is not None:
        minimum = Decimal(str(labor.get("full_shift_workers_min", 0)))
        if full_workers < minimum:
            errors["full_shift_workers"] = f"Tối thiểu {minimum:g} người cả ca."
        elif full_workers > maximum:
            errors["full_shift_workers"] = f"Tối đa {maximum:g} người cả ca."
        elif half_workers is not None and full_workers + half_workers / 2 > maximum:
            errors["half_shift_workers"] = (
                f"Tổng quy đổi tối đa {maximum:g} lao động/ca; mỗi người nửa ca tính 0,5.")

    overtime = None
    per_person_limit = limits.get("overtime_per_worker")
    if overtime_per_person is not None and per_person_limit is not None:
        if overtime_per_person > Decimal(str(per_person_limit.get("max", math.inf))):
            errors["overtime"] = f"Vượt giới hạn {per_person_limit['max']:,.0f} phút mỗi người."
    # Only full-shift workers count toward overtime; the half-shift worker does not.
    if overtime_per_person is not None and full_workers is not None and "overtime" not in errors:
        overtime = (overtime_per_person * full_workers).to_integral_value(rounding=ROUND_HALF_UP)

    parsed_fields = {"overtime": overtime, "bonus": bonus, "idle": idle}
    for field, number in parsed_fields.items():
        if number is None:
            continue
        field_limit = limits.get(field, {})
        minimum = Decimal(str(field_limit.get("min", 0)))
        maximum = Decimal(str(field_limit.get("max", math.inf)))
        if number < minimum:
            errors[field] = f"Giá trị tối thiểu là {minimum:g}."
        elif number > maximum:
            errors[field] = (f"Tổng cả tổ vượt giới hạn {maximum:,.0f} phút." if field == "overtime"
                             else f"Vượt giới hạn {maximum:,.0f} {field_limit.get('unit', '')}.".strip())

    smv = None
    if selected_item is not None:
        smv = Decimal(str(selected_item.get("smv")))
        smv_limit = limits.get("smv", {})
        if smv < Decimal(str(smv_limit.get("min", 0))) or smv > Decimal(str(smv_limit.get("max", math.inf))):
            errors["product"] = "Định mức của mẫu hàng nằm ngoài giới hạn dự báo."

    if errors:
        return {
            "ok": False,
            "errors": errors,
            "missing": missing,
            "inputs": None,
        }

    assert target_percent is not None
    assert full_workers is not None and half_workers is not None and overtime is not None and bonus is not None and idle is not None
    assert smv is not None
    return {
        "ok": True,
        "errors": {},
        "missing": [],
        "inputs": {
            "target": float(target_percent / Decimal(100)),
            "smv": float(smv),
            "full_shift_workers": int(full_workers),
            "half_shift_workers": int(half_workers),
            "overtime": int(overtime),
            "bonus": int(bonus),
            "idle": int(idle),
        },
    }


def run_prediction(inputs: dict) -> dict:
    """Call the facade and convert expected readiness failures to safe UI text."""
    try:
        return {"ok": True, "result": services.predict_shift(inputs), "message": None}
    except (OSError, EOFError, ValueError, TypeError, RuntimeError):
        return {
            "ok": False,
            "result": None,
            "message": "Model hoặc dữ liệu chưa sẵn sàng dự báo. Cần model tương thích đơn vị VNĐ.",
            "kind": "model_unavailable",
        }
    except Exception:
        return {
            "ok": False,
            "result": None,
            "message": "Dự báo đang gặp lỗi. Vui lòng thử lại sau.",
            "kind": "backend_error",
        }


def run_recommendations(inputs: dict) -> dict:
    try:
        return {"ok": True, "result": services.recommend_options(inputs), "message": None}
    except (OSError, EOFError, ValueError, TypeError, RuntimeError):
        return {
            "ok": False,
            "result": None,
            "message": "Chưa thể tạo phương án cho bộ thông số này.",
            "kind": "backend_error",
        }
    except Exception:
        return {
            "ok": False,
            "result": None,
            "message": "Chưa thể tạo phương án lúc này. Vui lòng thử lại.",
            "kind": "backend_error",
        }


def model_identity() -> tuple:
    """Fingerprint active model and source files without loading or training them."""
    signatures = []
    for path in (config.MODEL, config.SOURCE):
        try:
            stat = Path(path).stat()
            signatures.append((str(Path(path).resolve()), stat.st_mtime_ns, stat.st_size))
        except OSError:
            signatures.append((str(Path(path).resolve()), None, None))
    return tuple(signatures)


def load_catalog() -> dict:
    try:
        return {"ok": True, "catalog": catalog_for_frontend(services.get_catalog()), "message": None}
    except Exception:
        return {
            "ok": False,
            "catalog": None,
            "message": "Chưa đọc được danh mục dữ liệu. Vui lòng kiểm tra workbook nguồn.",
        }


def load_dashboard(product: str | None) -> dict:
    try:
        return {"ok": True, "dashboard": services.get_management_dashboard(product), "message": None}
    except Exception:
        return {
            "ok": False,
            "dashboard": None,
            "message": "Chưa tải được thống kê. Vui lòng thử lại sau.",
        }
