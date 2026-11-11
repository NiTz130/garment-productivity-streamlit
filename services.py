"""Thin Python facade for the Streamlit frontend; no network or UI dependency."""
from __future__ import annotations

from itertools import product
import math
from decimal import Decimal
from numbers import Real
from pathlib import Path

import numpy as np
import pandas as pd

import config
import model
from data import dataset_fingerprint, history_usable_mask, quality_report, read_workbook, validate


_ACTUAL_BIN_WIDTH = .05
_DATA_CACHE: dict[str, dict] = {}
_MODEL_CACHE: dict[str, dict] = {}

_FIELD_UNITS = {
    "target": "ratio",
    "smv": "minutes_per_piece",
    "workers": "workers_per_shift",
    "overtime": "minutes_per_team",
    "bonus": "VND",
    "idle": "minutes",
}


def clear_caches() -> None:
    """Clear process-local resources, primarily useful after explicit retraining."""
    _DATA_CACHE.clear()
    _MODEL_CACHE.clear()


def _file_signature(path: Path) -> tuple[str, int, int]:
    path = Path(path).resolve()
    stat = path.stat()
    return str(path), stat.st_mtime_ns, stat.st_size


def _get_dataset(path=config.SOURCE) -> dict:
    path = Path(path)
    signature = _file_signature(path)
    cache_key = str(path.resolve())
    cached = _DATA_CACHE.get(cache_key)
    if cached is None or cached["signature"] != signature:
        frame = read_workbook(path)
        report = quality_report(frame)
        mask = history_usable_mask(frame)
        valid = frame.loc[mask].copy()
        _DATA_CACHE[cache_key] = {
            "signature": signature,
            "frame": frame,
            "valid": valid,
            "quality": report,
            "fingerprint": dataset_fingerprint(frame),
        }
        _MODEL_CACHE.pop(cache_key, None)
    return _DATA_CACHE[cache_key]


def _get_model(data: dict, path=config.MODEL) -> dict:
    path = Path(path)
    signature = _file_signature(path)
    cache_key = str(path.resolve())
    cached = _MODEL_CACHE.get(cache_key)
    if (cached is not None and cached["signature"] == signature
            and cached["dataset_signature"] == data["signature"]
            and cached["dataset_fingerprint"] == data["fingerprint"]):
        return cached["bundle"]
    bundle = model.load(path)
    model.assert_compatible(bundle)
    metadata = bundle["metadata"]
    if metadata.get("dataset_fingerprint") != data["fingerprint"]:
        raise ValueError(
            "LỖI: Dataset vận hành đã đổi so với model; cần huấn luyện model mới bằng dataset VNĐ."
        )
    _MODEL_CACHE[cache_key] = {
        "signature": signature,
        "dataset_signature": data["signature"],
        "dataset_fingerprint": data["fingerprint"],
        "bundle": bundle,
    }
    return bundle


def _input_ranges(data: dict) -> dict:
    ranges = dict(config.INPUT_RANGES)
    if len(data["valid"]):
        observed_max = float(data["valid"]["bonus"].max())
        ranges["bonus"] = (ranges["bonus"][0], min(ranges["bonus"][1], math.ceil(observed_max)))
    return ranges


def _whole_count(value: object, name: str) -> Decimal:
    if isinstance(value, bool) or not isinstance(value, (Real, Decimal)):
        raise ValueError(f"LỖI: {name} phải là số nguyên.")
    number = Decimal(str(value))
    if not number.is_finite() or number != number.to_integral_value() or number < 0:
        raise ValueError(f"LỖI: {name} phải là số nguyên không âm.")
    return number


def normalize_shift_inputs(inputs: dict) -> dict:
    """Convert full-shift and half-shift headcounts to model workers (a half shift is 4 of 8 hours)."""
    if not isinstance(inputs, dict):
        raise ValueError("LỖI: Đầu vào ca phải là một ánh xạ tên trường/giá trị.")
    has_full_count = "full_shift_workers" in inputs
    has_half_count = "half_shift_workers" in inputs
    if not has_full_count and not has_half_count:
        return dict(inputs)
    if not has_full_count or not has_half_count:
        raise ValueError("LỖI: Cần gửi cả full_shift_workers và half_shift_workers.")
    if "workers" in inputs:
        raise ValueError("LỖI: Chỉ gửi workers hoặc cặp trường nhân lực theo ca, không gửi đồng thời.")

    full_count = _whole_count(inputs["full_shift_workers"], "full_shift_workers")
    half_count = _whole_count(inputs["half_shift_workers"], "half_shift_workers")

    normalized = {key: value for key, value in inputs.items()
                  if key not in ("full_shift_workers", "half_shift_workers")}
    normalized["workers"] = float(full_count + Decimal("0.5") * half_count)
    return normalized


def _recommendation_limits(data: dict) -> dict:
    valid = data["valid"]
    limits = {}
    definitions = {
        "workers": (config.WORKER_STEP, config.INPUT_RANGES["workers"][1]),
        "overtime": (1, config.INPUT_RANGES["overtime"][1]),
        "bonus": (1, config.INPUT_RANGES["bonus"][1]),
    }
    for field, (step, configured_max) in definitions.items():
        if valid.empty:
            maximum = config.INPUT_RANGES[field][0]
        else:
            empirical = float(valid[field].quantile(config.RECOMMENDATION_QUANTILE))
            if field == "workers":
                empirical = math.floor(empirical / step) * step
            else:
                empirical = math.ceil(empirical)
            maximum = min(configured_max, empirical)
        limits[field] = {
            "min": config.INPUT_RANGES[field][0],
            "max": maximum,
            "step": step,
            "unit": _FIELD_UNITS[field],
            "basis": f"phân vị {config.RECOMMENDATION_QUANTILE:.0%} của dữ liệu hợp lệ, có chặn cấu hình",
        }
    # Máy dừng chỉ giảm được, tối đa về 0; min/max chỉ dùng làm thang chấm mức can thiệp.
    limits["idle"] = {
        "min": config.INPUT_RANGES["idle"][0],
        "max": config.INPUT_RANGES["idle"][1],
        "step": 1,
        "unit": _FIELD_UNITS["idle"],
        "basis": "giảm dần về 0 phút",
    }
    return limits


def get_catalog() -> dict:
    """Return SKU/product/SMV choices and current intake/search limits."""
    data = _get_dataset()
    valid = data["valid"]
    items = []
    if not valid.empty:
        for (product_name, sku), group in valid.groupby(["product", "sku"], sort=True):
            smvs = sorted(float(value) for value in group["smv"].dropna().unique())
            items.append({
                "sku": str(sku),
                "product": str(product_name),
                "smv": float(group["smv"].median()),
                "smv_values": smvs,
                "has_multiple_smv": len(smvs) > 1,
                "observations": int(len(group)),
            })

    input_ranges = _input_ranges(data)
    fields = {}
    for field in config.FEATURES:
        low, high = input_ranges[field]
        fields[field] = {
            "min": low,
            "max": high,
            "unit": _FIELD_UNITS[field],
            "type": "integer" if field in config.INTEGER_INPUTS else "number",
        }
        if field == "workers":
            fields[field]["step"] = config.WORKER_STEP
        elif field in config.INTEGER_INPUTS:
            fields[field]["step"] = 1

    # Giới hạn bonus bị kéo dài bởi vài ca ngoại lai; nửa giữa các ca có thưởng cho khoảng thực tế.
    paid = valid["bonus"][valid["bonus"] > 0]
    if len(paid):
        fields["bonus"]["typical"] = {
            "min": math.floor(paid.quantile(.25)),
            "max": math.ceil(paid.quantile(.75)),
            "paid_share": len(paid) / len(valid),
        }

    return {
        "items": items,
        "input_limits": fields,
        "labor_entry": {
            "full_shift_workers_min": math.ceil(input_ranges["workers"][0]),
            "half_shift_workers_min": 0,
            "converted_workers_max": math.floor(input_ranges["workers"][1]),
            "derived_workers_step": config.WORKER_STEP,
        },
        "recommendation_limits": _recommendation_limits(data),
        "quality": {
            "source_rows": data["quality"]["rows"],
            "valid_rows": int(len(valid)),
            "excluded_rows": int(len(data["quality"]["invalid_rows"])),
            "historical_workers_off_half_step": data["quality"]["historical_workers_off_half_step"],
        },
    }


def _prediction_payload(inputs: dict, prediction: dict) -> dict:
    difference = float(prediction["value"] - inputs["target"])
    return {
        "inputs": dict(inputs),
        **prediction,
        "achieved": difference >= 0,
        "status": "achieved" if difference >= 0 else "below_target",
        "difference_to_target": difference,
        "shortfall": max(0.0, -difference),
        "surplus": max(0.0, difference),
    }


def predict_shift(inputs: dict) -> dict:
    """Validate one new shift and predict using the already-loaded VND model."""
    data = _get_dataset()
    validated = validate(normalize_shift_inputs(inputs), limits=_input_ranges(data))
    bundle = _get_model(data)
    return _prediction_payload(validated, model.predict(bundle, validated))


def _axis_values(current: float, maximum: float, cap: int, multiplier: int = 1) -> list[int | float]:
    current_units = int(round(current * multiplier))
    max_units = int(math.floor(maximum * multiplier + 1e-10))
    distance = max_units - current_units
    if distance <= 0 or cap <= 0:
        return []
    count = min(cap, distance)
    offsets = sorted({math.ceil(i * distance / count) for i in range(1, count + 1)})
    values = [units / multiplier for units in (current_units + offset for offset in offsets)]
    if multiplier == 1:
        return [int(value) for value in values]
    return values


def _idle_values(current: int | float, cap: int) -> list[int]:
    """Giá trị máy dừng thấp hơn hiện tại, từ gần đến 0."""
    return [int(current) - step for step in _axis_values(0, int(current), cap)]


def _unavailable(option_id: str, name: str, reason: str, count: int = 0) -> dict:
    return {
        "id": option_id,
        "name": name,
        "available": False,
        "status": "unavailable",
        "reason": reason,
        "candidate_count": count,
    }


def _intervention_score(base: dict, candidate: dict, limits: dict, fields: tuple[str, ...]) -> float:
    squared = 0.0
    for field in fields:
        span = max(1.0, float(limits[field]["max"] - limits[field]["min"]))
        squared += ((candidate[field] - base[field]) / span) ** 2
    return math.sqrt(squared)


def _evaluate_option(option_id: str, name: str, base: dict, baseline_value: float,
                     target: float, candidates: list[dict], bundle: dict,
                     limits: dict, changed_fields: tuple[str, ...]) -> dict:
    if not candidates:
        return _unavailable(option_id, name, "Không còn khoảng điều chỉnh trong giới hạn vận hành.")
    predictions = model.predict_batch(bundle, candidates)
    scored = []
    for candidate, prediction in zip(candidates, predictions):
        if prediction["value"] <= baseline_value + 1e-12:
            continue
        cost = _intervention_score(base, candidate, limits, changed_fields)
        scored.append((candidate, prediction, cost))
    if not scored:
        return _unavailable(
            option_id, name,
            "Mô hình không dự báo cải thiện trong tập ứng viên đã tìm.",
            count=len(candidates),
        )

    achieved = [row for row in scored if row[1]["value"] >= target]
    if achieved:
        candidate, prediction, _ = min(achieved, key=lambda row: (row[2], row[1]["value"]))
        status = "achieved"
        reason = None
    else:
        candidate, prediction, _ = min(scored, key=lambda row: (-row[1]["value"], row[2]))
        status = "below_target"
        reason = f"Phương án cải thiện tốt nhất trong phạm vi tìm kiếm vẫn thiếu {target - prediction['value']:.6g} năng suất."

    deltas = {field: candidate[field] - base[field] for field in config.FEATURES}
    return {
        "id": option_id,
        "name": name,
        "available": True,
        "status": status,
        "reason": reason,
        "scope": "best_within_search",
        "candidate_count": len(candidates),
        "inputs": dict(candidate),
        "prediction": prediction,
        "achieved": prediction["value"] >= target,
        "difference_to_target": float(prediction["value"] - target),
        "shortfall": max(0.0, float(target - prediction["value"])),
        "surplus": max(0.0, float(prediction["value"] - target)),
        "deltas": deltas,
        "productivity_delta": float(prediction["value"] - baseline_value),
    }


def recommend_options(inputs: dict) -> dict:
    """Search bounded staffing, overtime, and combined adjustment directions."""
    data = _get_dataset()
    base = validate(normalize_shift_inputs(inputs), limits=_input_ranges(data))
    bundle = _get_model(data)
    baseline_prediction = model.predict(bundle, base)
    baseline = _prediction_payload(base, baseline_prediction)
    names = {
        "workers": "Nhân lực",
        "overtime": "Tăng ca",
        "bonus": "Tiền thưởng",
        "idle": "Giảm máy dừng",
        "combined": "Kết hợp nhân lực, tăng ca, tiền thưởng và máy dừng",
    }
    if baseline["achieved"]:
        options = [
            _unavailable(key, name, "Ca đang đạt mục tiêu; không cần tăng thông số.")
            for key, name in names.items()
        ]
        return {"baseline": baseline, "options": options, "search_limit": config.MAX_COMBINED_CANDIDATES}

    limits = _recommendation_limits(data)
    worker_values = _axis_values(base["workers"], max(base["workers"], limits["workers"]["max"]),
                                 config.MAX_AXIS_CANDIDATES, multiplier=2)
    overtime_values = _axis_values(base["overtime"], max(base["overtime"], limits["overtime"]["max"]),
                                   config.MAX_AXIS_CANDIDATES)
    bonus_values = _axis_values(base["bonus"], max(base["bonus"], limits["bonus"]["max"]),
                                config.MAX_AXIS_CANDIDATES)
    idle_values = _idle_values(base["idle"], config.MAX_AXIS_CANDIDATES)
    worker_candidates = [{**base, "workers": value} for value in worker_values]
    overtime_candidates = [{**base, "overtime": value} for value in overtime_values]
    bonus_candidates = [{**base, "bonus": value} for value in bonus_values]
    idle_candidates = [{**base, "idle": value} for value in idle_values]

    combined_worker_values = _axis_values(base["workers"],
                                           max(base["workers"], limits["workers"]["max"]),
                                           config.RECOMMENDATION_AXIS_POINTS, multiplier=2)
    combined_overtime_values = _axis_values(base["overtime"],
                                             max(base["overtime"], limits["overtime"]["max"]),
                                             config.RECOMMENDATION_AXIS_POINTS)
    combined_bonus_values = _axis_values(base["bonus"],
                                         max(base["bonus"], limits["bonus"]["max"]),
                                         config.RECOMMENDATION_AXIS_POINTS)
    combined_idle_values = _idle_values(base["idle"], config.RECOMMENDATION_AXIS_POINTS)
    combined_candidates = [
        {**base, "workers": workers, "overtime": overtime, "bonus": bonus, "idle": idle}
        for workers, overtime, bonus, idle in product(
            [base["workers"], *combined_worker_values],
            [base["overtime"], *combined_overtime_values],
            [base["bonus"], *combined_bonus_values],
            [base["idle"], *combined_idle_values],
        )
        if sum((workers != base["workers"], overtime != base["overtime"],
                bonus != base["bonus"], idle != base["idle"])) >= 2
    ]
    if len(combined_candidates) > config.MAX_COMBINED_CANDIDATES:
        stride = len(combined_candidates) / config.MAX_COMBINED_CANDIDATES
        combined_candidates = [combined_candidates[int(i * stride)]
                               for i in range(config.MAX_COMBINED_CANDIDATES)]

    options = [
        _evaluate_option("workers", names["workers"], base, baseline["value"], base["target"],
                         worker_candidates, bundle, limits, ("workers",)),
        _evaluate_option("overtime", names["overtime"], base, baseline["value"], base["target"],
                         overtime_candidates, bundle, limits, ("overtime",)),
        _evaluate_option("bonus", names["bonus"], base, baseline["value"], base["target"],
                         bonus_candidates, bundle, limits, ("bonus",)),
        _evaluate_option("idle", names["idle"], base, baseline["value"], base["target"],
                         idle_candidates, bundle, limits, ("idle",)),
        _evaluate_option("combined", names["combined"], base, baseline["value"], base["target"],
                         combined_candidates, bundle, limits, ("workers", "overtime", "bonus", "idle")),
    ]
    return {
        "baseline": baseline,
        "options": options,
        "search_limit": {
            "axis_candidates": config.MAX_AXIS_CANDIDATES,
            "combined_candidates": config.MAX_COMBINED_CANDIDATES,
        },
        "recommendation_limits": limits,
    }


def _number(value):
    if value is None or pd.isna(value):
        return None
    number = float(value)
    return number if math.isfinite(number) else None


def _idle_by_product(selected) -> list[dict]:
    """Idle minutes per product, largest first; share is of the filtered total."""
    total = float(selected["idle"].sum())
    rows = [{
        "product": str(name),
        "idle_minutes": _number(group["idle"].sum()),
        "share": _number(group["idle"].sum() / total) if total else 0.,
        "shifts": int(len(group)),
        "idle_per_shift": _number(group["idle"].mean()),
    } for name, group in selected.groupby("product", sort=True)]
    return sorted(rows, key=lambda row: -row["idle_minutes"])


def _actual_distribution(selected) -> dict:
    """Fixed 0.05-wide bins from 0; the last bin includes its upper edge."""
    if selected.empty:
        return {"bins": [], "stats": None}
    actual, width = selected["actual"].astype(float), _ACTUAL_BIN_WIDTH
    size = max(1, math.ceil(round(actual.max() / width, 9)))
    index = np.minimum(np.floor((actual / width).round(9)), size - 1).astype(int)
    counts = np.bincount(index, minlength=size)
    bins = [{"low": round(i * width, 10), "high": round((i + 1) * width, 10), "count": int(counts[i])}
            for i in range(size)]
    stats = {
        "count": int(len(actual)), "mean": _number(actual.mean()), "median": _number(actual.median()),
        "std": _number(actual.std(ddof=0)), "p10": _number(actual.quantile(.1)),
        "p90": _number(actual.quantile(.9)), "min": _number(actual.min()), "max": _number(actual.max()),
        "below_target_share": _number((actual < selected["target"]).mean()),
    }
    return {"bins": bins, "stats": stats}


def get_management_dashboard(product: str | None = None) -> dict:
    """Aggregate valid Excel history; all returned dashboard sections share a filter."""
    if product is not None and not isinstance(product, str):
        raise ValueError("LỖI: Bộ lọc sản phẩm phải là chuỗi hoặc None.")
    data = _get_dataset()
    valid = data["valid"]
    products = sorted(str(value) for value in valid["product"].dropna().unique()) if not valid.empty else []
    selected = valid if product is None else valid.loc[valid["product"] == product]
    count = int(len(selected))

    if count:
        actual_mean = _number(selected["actual"].mean())
        target_rate = _number((selected["actual"] >= selected["target"]).mean())
        idle_total = _number(selected["idle"].sum())
    else:
        actual_mean = target_rate = idle_total = None

    product_comparison = []
    if count:
        grouped = selected.groupby("product", sort=True)
        for product_name, group in grouped:
            product_comparison.append({
                "product": str(product_name),
                "target_mean": _number(group["target"].mean()),
                "actual_mean": _number(group["actual"].mean()),
                "observations": int(len(group)),
            })

    bonus_scatter = []
    overtime_scatter = []
    history = []
    for source_row, row in selected.iterrows():
        normalized = {column: row[column] for column in config.DATA_COLUMNS}
        bonus_scatter.append({
            "source_row": int(source_row),
            "bonus": _number(row["bonus"]),
            "actual": _number(row["actual"]),
            "target": _number(row["target"]),
            "product": str(row["product"]),
        })
        overtime_scatter.append({
            "source_row": int(source_row),
            "overtime": _number(row["overtime"]),
            "actual": _number(row["actual"]),
            "target": _number(row["target"]),
            "product": str(row["product"]),
        })
        history.append({
            "source_row": int(source_row),
            "sku": str(normalized["sku"]),
            "product": str(normalized["product"]),
            **{key: _number(normalized[key]) for key in config.FEATURES + ["actual"]},
        })

    return {
        "filter": {"product": product, "products": products},
        "quality": {
            "source_rows": int(data["quality"]["rows"]),
            "filtered_valid_rows": count,
            "excluded_rows": int(len(data["quality"]["invalid_rows"])),
            "excluded_source_rows": list(data["quality"]["invalid_rows"]),
            "historical_workers_off_half_step": data["quality"]["historical_workers_off_half_step"],
        },
        "kpis": {
            "shift_count": count,
            "actual_mean": actual_mean,
            "target_achievement_rate": target_rate,
            "idle_minutes_total": idle_total,
        },
        "charts": {
            "product_comparison": product_comparison,
            "bonus_vs_actual": bonus_scatter,
            "overtime_vs_actual": overtime_scatter,
            "idle_by_product": _idle_by_product(selected) if count else [],
            "actual_distribution": _actual_distribution(selected),
        },
        "history": history,
    }
