"""Kiểm tra tĩnh styles.css: cỡ chữ tối thiểu và độ tương phản chữ so với nền trắng."""
from __future__ import annotations

from pathlib import Path
import re

CSS = (Path(__file__).resolve().parents[1] / "frontend" / "styles.css").read_text(encoding="utf-8")
MIN_FONT_PX = 13
MIN_CONTRAST = 4.9  # ngưỡng WCAG AA là 4,5; chừa biên cho nền xám nhạt và xanh nhạt


def _luminance(hex_color: str) -> float:
    channels = [int(hex_color[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    linear = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def _contrast_on_white(hex_color: str) -> float:
    return 1.05 / (_luminance(hex_color) + 0.05)


def _rules():
    for match in re.finditer(r"([^{}]+)\{([^{}]*)\}", CSS):
        yield match.group(1).strip(), match.group(2)


def test_no_font_size_below_13px():
    small = [(selector, size) for selector, body in _rules()
             for size in re.findall(r"font-size:\s*([\d.]+)px", body) if float(size) < MIN_FONT_PX]
    assert small == []


BODY_TEXT_SELECTORS = [
    ".empty-result p", ".input-footnote", ".prediction-note", ".result-message",
    ".options-placeholder", ".options-message", ".options-summary", ".option-reason",
    ".quality-note", ".dashboard-error", ".chart-empty", ".table-empty",
    ".check-row", ".combobox-empty", ".combobox-option strong",
]


def test_body_text_is_at_least_16px():
    sizes = {}
    for selector, body in _rules():
        match = re.search(r"font-size:\s*([\d.]+)px", body)
        if match:
            for part in selector.split(","):
                sizes.setdefault(part.strip(), []).append(float(match.group(1)))
    short = {s: sizes.get(s) for s in BODY_TEXT_SELECTORS if min(sizes.get(s, [0])) < 16}
    assert short == {}


def test_text_colors_reach_aa_contrast_on_white():
    weak = []
    for selector, body in _rules():
        for prop, color in re.findall(r"(?<![-\w])(color|fill):\s*(#[0-9a-fA-F]{6})\b", body):
            if color.lower() in {"#ffffff", "#fff"} or ":disabled" in selector:
                continue  # chữ trắng nằm trên nền teal; nút vô hiệu được miễn
            if _contrast_on_white(color) < MIN_CONTRAST:
                weak.append((selector, color, round(_contrast_on_white(color), 2)))
    assert weak == []
