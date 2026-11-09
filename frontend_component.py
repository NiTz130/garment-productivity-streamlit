"""Load local assets and mount the official Streamlit v2 bidirectional component."""
import json
from pathlib import Path
from collections.abc import Callable

import streamlit.components.v2 as components_v2


_ASSETS = Path(__file__).resolve().parent / "frontend"
_STATIC_FONTS = Path(__file__).resolve().parent / "static" / "fonts"
COMPONENT_KEY = "garment_frontend"


def build_script() -> str:
    """app.js kèm danh sách font. Tệp font nằm ở static/fonts (Streamlit phục vụ tĩnh), không nhúng vào chuỗi JS."""
    faces = json.loads((_STATIC_FONTS / "fonts.json").read_text(encoding="utf-8"))
    prelude = "const FONT_FACES = " + json.dumps(faces, ensure_ascii=False, separators=(",", ":")) + ";\n"
    return prelude + (_ASSETS / "app.js").read_text(encoding="utf-8")


_component = components_v2.component(
    "garment_productivity_frontend",
    html=(_ASSETS / "index.html").read_text(encoding="utf-8"),
    css=(_ASSETS / "styles.css").read_text(encoding="utf-8"),
    js=build_script(),
    isolate_styles=True,
)


def render_frontend(payload: dict, *, on_event_change: Callable[[], None]):
    return _component(
        data=payload,
        key=COMPONENT_KEY,
        on_event_change=on_event_change,
    )
