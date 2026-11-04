"""Load local assets and mount the official Streamlit v2 bidirectional component."""
from pathlib import Path
from collections.abc import Callable

import streamlit.components.v2 as components_v2


_ASSETS = Path(__file__).resolve().parent / "frontend"
COMPONENT_KEY = "garment_frontend"

_component = components_v2.component(
    "garment_productivity_frontend",
    html=(_ASSETS / "index.html").read_text(encoding="utf-8"),
    css=(_ASSETS / "styles.css").read_text(encoding="utf-8"),
    js=(_ASSETS / "app.js").read_text(encoding="utf-8"),
    isolate_styles=True,
)


def render_frontend(payload: dict, *, on_event_change: Callable[[], None]):
    return _component(
        data=payload,
        key=COMPONENT_KEY,
        on_event_change=on_event_change,
    )
