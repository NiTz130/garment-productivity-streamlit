"""Streamlit coordinator for the garment productivity frontend."""
from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

import streamlit as st

import ui_adapter
from frontend_component import COMPONENT_KEY, render_frontend


st.set_page_config(
    page_title="Năng suất chuyền may",
    page_icon="◈",
    layout="wide",
    initial_sidebar_state="collapsed",
)

_ROOT = Path(__file__).resolve().parent
_STREAMLIT_CSS = (_ROOT / "frontend" / "streamlit.css").read_text(encoding="utf-8")
st.markdown(f"<style>{_STREAMLIT_CSS}</style>", unsafe_allow_html=True)

_STATE_KEY = "garment_productivity_ui"


def _new_state() -> dict:
    return {
        "page": "forecast",
        "form": {
            "target": "0",
            "full_shift_workers": "",
            "half_shift_workers": "",
            "overtime": "0",
            "bonus": "0",
            "idle": "0",
        },
        "selected_item_key": "",
        "revision": 0,
        "catalog_ack": False,
        "catalog": None,
        "catalog_error": None,
        "last_client_id": None,
        "last_client_seq": -1,
        "prediction": None,
        "prediction_status": "no_product",
        "prediction_message": None,
        "prediction_errors": {},
        "prediction_revision": 0,
        "prediction_delta": None,
        "last_valid": None,
        "recommendations": None,
        "recommendation_status": "idle",
        "recommendation_message": None,
        "recommendation_revision": None,
        "filter_product": None,
        "dashboard": None,
        "dashboard_error": None,
        "dashboard_page": 0,
    }


def _ensure_state() -> dict:
    if _STATE_KEY not in st.session_state:
        st.session_state[_STATE_KEY] = _new_state()
    state = st.session_state[_STATE_KEY]
    if state.get("catalog") is None and state.get("catalog_error") is None:
        loaded = ui_adapter.load_catalog()
        state["catalog"] = loaded["catalog"]
        state["catalog_error"] = loaded["message"]
    return state


def _find_item(state: dict, item_key: str | None) -> dict | None:
    catalog = state.get("catalog")
    if not isinstance(catalog, dict) or not item_key:
        return None
    return next((item for item in catalog.get("items", []) if item.get("key") == item_key), None)


def _apply_form_event(state: dict, event: dict) -> bool:
    try:
        revision = int(event.get("revision", state["revision"]))
    except (TypeError, ValueError):
        return False
    if revision < state["revision"]:
        return False

    incoming = event.get("form")
    if not isinstance(incoming, dict):
        return False
    form = dict(state["form"])
    for name in ui_adapter.FORM_FIELDS:
        value = incoming.get(name, "")
        form[name] = "" if value is None else str(value)

    item_key = event.get("item_key", state["selected_item_key"])
    item_key = item_key if isinstance(item_key, str) else ""
    changed = (
        revision != state["revision"]
        or form != state["form"]
        or item_key != state["selected_item_key"]
    )
    if not changed:
        return False

    if item_key != state["selected_item_key"]:
        state["last_valid"] = None
        state["prediction_delta"] = None
        selected = _find_item(state, item_key)
        form["smv"] = str(selected["smv"]) if selected else ""
    state["selected_item_key"] = item_key
    state["form"] = form
    state["revision"] = revision
    return True


def _run_prediction(state: dict) -> None:
    state["prediction"] = None
    state["prediction_errors"] = {}
    state["prediction_message"] = None
    state["prediction_delta"] = None
    state["prediction_revision"] = state["revision"]
    state["recommendations"] = None
    state["recommendation_message"] = None
    state["recommendation_revision"] = None
    state["recommendation_status"] = "idle"

    item = _find_item(state, state["selected_item_key"])
    if item is None:
        state["prediction_status"] = "no_product"
        if state.get("catalog_error"):
            state["prediction_message"] = state["catalog_error"]
        else:
            state["prediction_errors"] = ui_adapter.parse_form(
                state["form"], None, state.get("catalog") or {}
            )["errors"]
        return

    catalog = state.get("catalog") or {}
    parsed = ui_adapter.parse_form(state["form"], item, catalog)
    if not parsed["ok"]:
        state["prediction_errors"] = parsed["errors"]
        invalid_fields = set(parsed["errors"]) - set(parsed["missing"])
        state["prediction_status"] = "invalid" if invalid_fields else "incomplete"
        return

    state["prediction_status"] = "pending"
    outcome = ui_adapter.run_prediction(parsed["inputs"])
    if not outcome["ok"]:
        state["prediction_status"] = outcome["kind"]
        state["prediction_message"] = outcome["message"]
        return

    prediction = outcome["result"]
    identity = ui_adapter.model_identity()
    previous = state.get("last_valid")
    if previous and previous.get("model_identity") == identity and previous.get("item_key") == item["key"]:
        state["prediction_delta"] = float(prediction["value"] - previous["value"])
    state["last_valid"] = {
        "model_identity": identity,
        "item_key": item["key"],
        "value": float(prediction["value"]),
    }
    state["prediction"] = prediction
    state["prediction_status"] = "success"
    if prediction["achieved"]:
        state["recommendation_status"] = "achieved"
    else:
        state["recommendation_status"] = "waiting"


def _load_dashboard(state: dict) -> None:
    loaded = ui_adapter.load_dashboard(state["filter_product"])
    state["dashboard"] = loaded["dashboard"]
    state["dashboard_error"] = loaded["message"]
    state["dashboard_page"] = 0


def _process_event(state: dict, event: object) -> None:
    if not isinstance(event, Mapping):
        return
    client_id = event.get("client_id")
    try:
        client_seq = int(event.get("seq"))
    except (TypeError, ValueError):
        return
    if not isinstance(client_id, str) or not client_id:
        return
    if state.get("last_client_id") != client_id:
        state["last_client_id"] = client_id
        state["last_client_seq"] = -1
    if client_seq <= state["last_client_seq"]:
        return
    state["last_client_seq"] = client_seq

    if event.get("catalog_ready") is True:
        state["catalog_ack"] = True
    kind = event.get("kind")
    if kind == "catalog_needed":
        loaded = ui_adapter.load_catalog()
        state["catalog"] = loaded["catalog"]
        state["catalog_error"] = loaded["message"]
        state["catalog_ack"] = False
        return
    if kind == "form":
        if _apply_form_event(state, dict(event)):
            _run_prediction(state)
        return
    if kind == "navigate":
        changed = _apply_form_event(state, dict(event)) if isinstance(event.get("form"), dict) else False
        page = event.get("page")
        if page in {"forecast", "management"}:
            state["page"] = page
        if changed:
            _run_prediction(state)
        if state["page"] == "management" and state.get("dashboard") is None:
            _load_dashboard(state)
        return
    if kind == "filter":
        product = event.get("product")
        if product is not None and not isinstance(product, str):
            return
        state["filter_product"] = product
        _load_dashboard(state)
        return
    if kind == "page":
        try:
            requested = max(0, int(event.get("page", 0)))
        except (TypeError, ValueError):
            return
        dashboard = state.get("dashboard") or {}
        rows = dashboard.get("history", [])
        last_page = max(0, (len(rows) - 1) // 20)
        state["dashboard_page"] = min(requested, last_page)
        return
    if kind == "recommend":
        revision = event.get("revision")
        if (
            revision != state["revision"]
            or state.get("prediction_status") != "success"
            or not state.get("prediction")
            or state["prediction"].get("achieved")
            or state.get("recommendation_revision") == revision
        ):
            return
        state["recommendation_revision"] = revision
        state["recommendation_status"] = "loading"
        result = ui_adapter.run_recommendations(state["prediction"]["inputs"])
        if result["ok"]:
            state["recommendations"] = result["result"]
            state["recommendation_status"] = "success"
            state["recommendation_message"] = None
        else:
            state["recommendations"] = None
            state["recommendation_status"] = "error"
            state["recommendation_message"] = result["message"]


def _on_component_event() -> None:
    """Process a component state change before Streamlit redraws the page."""
    state = st.session_state.get(_STATE_KEY)
    component_state = st.session_state.get(COMPONENT_KEY)
    if not isinstance(state, dict):
        return
    if isinstance(component_state, Mapping):
        _process_event(state, component_state.get("event"))
    else:
        _process_event(state, getattr(component_state, "event", None))


def _payload(state: dict) -> dict:
    catalog = state.get("catalog") or {}
    page = state.get("page", "forecast")
    selected = _find_item(state, state.get("selected_item_key"))
    dashboard = state.get("dashboard") if page == "management" else None
    return {
        "page": page,
        "catalog": None if state.get("catalog_ack") else catalog.get("items"),
        "catalog_error": state.get("catalog_error"),
        "catalog_version": 1,
        "input_limits": catalog.get("input_limits", {}),
        "labor_entry": catalog.get("labor_entry", {}),
        "items_count": len(catalog.get("items", [])),
        "form": state["form"],
        "revision": state["revision"],
        "selected_item_key": state["selected_item_key"],
        "selected_item": selected,
        "prediction": state["prediction"],
        "prediction_status": state["prediction_status"],
        "prediction_message": state["prediction_message"],
        "prediction_errors": state["prediction_errors"],
        "prediction_revision": state["prediction_revision"],
        "prediction_delta": state["prediction_delta"],
        "recommendations": state["recommendations"],
        "recommendation_status": state["recommendation_status"],
        "recommendation_message": state["recommendation_message"],
        "recommendation_revision": state["recommendation_revision"],
        "dashboard": dashboard,
        "dashboard_error": state["dashboard_error"],
        "dashboard_page": state["dashboard_page"],
        "filter_product": state["filter_product"],
    }


state = _ensure_state()
if state["page"] == "management" and state.get("dashboard") is None and not state.get("dashboard_error"):
    _load_dashboard(state)

render_frontend(_payload(state), on_event_change=_on_component_event)
