"""Thành phần trình bày; không tính lại dự báo hoặc thay đổi dữ liệu nghiệp vụ."""
from __future__ import annotations
import json
from functools import lru_cache
from html import escape
from pathlib import Path
import math

ASSETS = Path(__file__).resolve().parent / "assets"


@lru_cache(maxsize=2)
def asset(name: str) -> str:
    return (ASSETS / name).read_text(encoding="utf-8")


def chart_html(kind: str, data: dict) -> str:
    if kind not in {"bullet", "scenarios", "drift"}:
        raise ValueError("LỖI: Loại biểu đồ không được hỗ trợ.")
    # Dữ liệu không được phép đóng thẻ script hoặc tạo HTML trong iframe.
    payload = json.dumps({"kind": kind, "data": data}, ensure_ascii=False, allow_nan=False)
    payload = payload.replace("&", "\\u0026").replace("<", "\\u003c").replace(">", "\\u003e")
    return """<!doctype html><html lang="vi"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
*{box-sizing:border-box}body{margin:0;background:#FFFFFF;color:#1E293B;font:16px Tahoma,'DejaVu Sans',sans-serif}
.plot{height:300px;position:relative;padding:8px}body[data-kind=bullet] .plot{height:175px}
.controls{display:flex;flex-wrap:wrap;gap:6px;padding:4px 8px}
button{font:14px Tahoma,'DejaVu Sans',sans-serif;min-height:40px;padding:6px 10px;border:1px solid #CBD5E1;border-radius:4px;background:white;color:#1E293B;cursor:pointer}
button:hover,button:focus-visible{background:#E8F2F0;outline:2px solid #00665C;outline-offset:1px}
#detail{padding:6px 8px;margin:0;font-size:14px;min-height:32px}canvas:focus-visible{outline:2px solid #00665C}
</style></head><body><div class="plot"><canvas id="chart" tabindex="0" role="img" aria-label="Biểu đồ tương tác; chọn tên bên dưới để xem số liệu"></canvas></div>
<div id="controls" class="controls" aria-label="Chọn điểm dữ liệu"></div>
<p id="detail" role="status" aria-live="polite"></p>
<script type="application/json" id="chart-data">""" + payload + '</script><script>' + asset("chart.umd.min.js") + '</script><script type="module">' + asset("charts.mjs") + '</script></body></html>'


def scenario_payload(rows: list, target: float, best: str | None) -> dict:
    return {"target": target, "best": best,
            "points": [{"name": r["name"], "effort": r["effort"], "value": r["value"],
                        "status": r["status"]} for r in rows]}


def drift_payload(frame, threshold: float) -> dict:
    return {"threshold": threshold, "points": [
        {"name": r["Biến"], "score": r["Mức lệch"] if math.isfinite(r["Mức lệch"]) else None,
         "unbounded": not math.isfinite(r["Mức lệch"]), "warning": r["Nhãn"] == "cảnh báo"}
        for r in frame.to_dict("records")]}


def selection_badge(best: str | None, effort: float | None) -> str:
    if best is None:
        return '<div class="selection empty">Chưa có phương án đạt chỉ tiêu trong các mức đang chọn.</div>'
    return ('<div class="selection"><span class="badge">Được chọn · Can thiệp thấp nhất</span>'
            f'<strong>{escape(best)}</strong><span>Điểm can thiệp: {effort:.3f}</span></div>')


def slider_marks(low: float, high: float, base: float) -> str:
    if not low <= base <= high or low >= high:
        raise ValueError("LỖI: Mốc thanh trượt không hợp lệ.")
    position = 100 * (base - low) / (high - low)
    return (f'<div class="slider-ruler" aria-hidden="true"><span style="left:{position:.6f}%"></span></div>'
            f'<div class="slider-labels"><span>Đầu ca: {base:g}</span><span>Tối đa: {high:g}</span></div>')
