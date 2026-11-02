from __future__ import annotations
import math
import config
from data import validate
from model import predict


def light(value: float, target: float) -> str:
    if not math.isfinite(value) or not math.isfinite(target) or value < 0 or not 0 <= target <= 1:
        raise ValueError("LỖI: Năng suất hoặc mục tiêu không hợp lệ.")
    return "Đạt" if value >= target else "Không đạt"


def compare(bundle, base: dict, changes: dict, limits: dict) -> tuple[list, str | None]:
    validate(base)
    for key, (low, high) in limits.items():
        for row in (base, changes):
            value = row.get(key)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not low <= value <= high:
                raise ValueError(f"LỖI: {config.LABELS[key]} vượt giới hạn thanh trượt.")
    current = predict(bundle, base)["value"]
    rows = []
    for name, keys in [("Giữ nguyên", []), ("Tăng ca", ["overtime"]),
                       ("Thêm công nhân", ["workers"]), ("Tăng thưởng", ["bonus"]),
                       ("Kết hợp", list(limits))]:
        inputs = {**base, **{k: changes[k] for k in keys}}
        result = predict(bundle, inputs)
        effort = sum(abs(inputs[k] - base[k]) / (high - low) for k, (low, high) in limits.items())
        rows.append({"name": name, "inputs": inputs, "value": result["value"],
                     "clipped": result["clipped"], "status": light(result["value"], base["target"]),
                     "delta": result["value"] - current, "effort": effort})
    eligible = [r for r in rows if r["status"] == "Đạt"]
    best = min(eligible, key=lambda r: r["effort"])["name"] if eligible else None
    return rows, best
