"""Test máy trạng thái của app.py mà không cần phiên Streamlit thật."""
from __future__ import annotations

import importlib
from types import SimpleNamespace

import pytest

import ui_adapter

CATALOG = {
    "items": [{"key": "k1", "sku": "S-01", "product": "Áo", "smv": 18.5}],
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
FORM = {"target": "80", "full_shift_workers": "30", "half_shift_workers": "0",
        "overtime": "0", "bonus": "0", "idle": "0"}


@pytest.fixture(scope="module")
def app():
    mp = pytest.MonkeyPatch()
    mp.setattr(ui_adapter, "load_catalog",
               lambda: {"ok": True, "catalog": CATALOG, "message": None})
    try:
        yield importlib.import_module("app")
    finally:
        mp.undo()


@pytest.fixture
def state(app):
    result = app._new_state()
    result["catalog"] = CATALOG
    return result


def prediction(value=0.7, achieved=False):
    return {"ok": True, "message": None,
            "result": {"value": value, "achieved": achieved, "inputs": {"target": 0.8}}}


def test_ensure_state_creates_state_and_loads_catalog(app, monkeypatch):
    store = {}
    monkeypatch.setattr(app.st, "session_state", store)
    monkeypatch.setattr(ui_adapter, "load_catalog",
                        lambda: {"ok": False, "catalog": None, "message": "hỏng"})
    result = app._ensure_state()
    assert store[app._STATE_KEY] is result
    assert result["catalog_error"] == "hỏng" and result["catalog"] is None


def test_apply_form_event_rejects_stale_or_malformed(app, state):
    state["revision"] = 2
    assert app._apply_form_event(state, {"revision": "x", "form": {}}) is False
    assert app._apply_form_event(state, {"revision": 1, "form": {}}) is False
    assert app._apply_form_event(state, {"revision": 2, "form": "không phải dict"}) is False
    assert state["revision"] == 2


def test_apply_form_event_ignores_unchanged_form(app, state):
    assert app._apply_form_event(state, {"revision": 0, "form": dict(state["form"])}) is False


def test_apply_form_event_sets_item_and_smv(app, state):
    event = {"revision": 1, "item_key": "k1", "form": {**FORM, "half_shift_workers": "3"}}
    assert app._apply_form_event(state, event) is True
    assert state["selected_item_key"] == "k1"
    assert state["form"]["smv"] == "18.5"
    assert state["form"]["half_shift_workers"] == "3"
    assert state["revision"] == 1


def test_apply_form_event_unknown_item_clears_smv_and_last_valid(app, state):
    state["last_valid"] = {"value": 1}
    event = {"revision": 1, "item_key": 123, "form": {"target": None}}
    state["selected_item_key"] = "k1"
    assert app._apply_form_event(state, event) is True
    assert state["selected_item_key"] == ""
    assert state["form"]["smv"] == "" and state["form"]["target"] == ""
    assert state["last_valid"] is None


def test_run_prediction_without_product(app, state):
    app._run_prediction(state)
    assert state["prediction_status"] == "no_product"
    assert "product" in state["prediction_errors"]
    state["catalog_error"] = "Danh mục lỗi"
    app._run_prediction(state)
    assert state["prediction_message"] == "Danh mục lỗi"


def test_run_prediction_incomplete_and_invalid(app, state):
    state["selected_item_key"] = "k1"
    app._run_prediction(state)
    assert state["prediction_status"] == "incomplete"
    state["form"] = {**FORM, "target": "150"}
    app._run_prediction(state)
    assert state["prediction_status"] == "invalid"
    assert "target" in state["prediction_errors"]


def test_run_prediction_success_tracks_delta_and_recommendation_status(app, state, monkeypatch):
    state["selected_item_key"] = "k1"
    state["form"] = dict(FORM)
    monkeypatch.setattr(ui_adapter, "model_identity", lambda: ("m",))
    monkeypatch.setattr(ui_adapter, "run_prediction", lambda inputs: prediction(0.7))
    app._run_prediction(state)
    assert state["prediction_status"] == "success"
    assert state["recommendation_status"] == "waiting"
    assert state["prediction_delta"] is None

    monkeypatch.setattr(ui_adapter, "run_prediction", lambda inputs: prediction(0.75, True))
    app._run_prediction(state)
    assert state["prediction_delta"] == pytest.approx(0.05)
    assert state["recommendation_status"] == "achieved"

    monkeypatch.setattr(ui_adapter, "model_identity", lambda: ("model mới",))
    app._run_prediction(state)
    assert state["prediction_delta"] is None


def test_run_prediction_backend_failure_is_reported(app, state, monkeypatch):
    state["selected_item_key"] = "k1"
    state["form"] = dict(FORM)
    monkeypatch.setattr(ui_adapter, "run_prediction", lambda inputs: {
        "ok": False, "result": None, "message": "chưa sẵn sàng", "kind": "model_unavailable"})
    app._run_prediction(state)
    assert state["prediction_status"] == "model_unavailable"
    assert state["prediction_message"] == "chưa sẵn sàng"
    assert state["prediction"] is None


def test_load_dashboard_resets_page(app, state, monkeypatch):
    state["dashboard_page"] = 3
    monkeypatch.setattr(ui_adapter, "load_dashboard",
                        lambda product: {"ok": True, "dashboard": {"p": product}, "message": None})
    state["filter_product"] = "Áo"
    app._load_dashboard(state)
    assert state["dashboard"] == {"p": "Áo"} and state["dashboard_page"] == 0


@pytest.mark.parametrize("event", [
    None, "x", {"seq": 1}, {"client_id": "", "seq": 1},
    {"client_id": "c", "seq": "x"}, {"client_id": "c"},
])
def test_process_event_ignores_malformed_events(app, state, event):
    app._process_event(state, event)
    assert state["last_client_id"] is None


def test_process_event_dedupes_by_client_sequence(app, state, monkeypatch):
    calls = []
    monkeypatch.setattr(ui_adapter, "load_dashboard",
                        lambda product: calls.append(product) or
                        {"ok": True, "dashboard": {}, "message": None})
    event = {"client_id": "a", "seq": 1, "kind": "filter", "product": "Áo"}
    app._process_event(state, event)
    app._process_event(state, event)
    assert calls == ["Áo"]
    app._process_event(state, {**event, "client_id": "b", "seq": 0})
    assert calls == ["Áo", "Áo"] and state["last_client_id"] == "b"


def test_process_event_catalog_ack_and_reload(app, state, monkeypatch):
    app._process_event(state, {"client_id": "a", "seq": 1, "catalog_ready": True})
    assert state["catalog_ack"] is True
    monkeypatch.setattr(ui_adapter, "load_catalog",
                        lambda: {"ok": True, "catalog": {"items": []}, "message": None})
    app._process_event(state, {"client_id": "a", "seq": 2, "kind": "catalog_needed"})
    assert state["catalog_ack"] is False and state["catalog"] == {"items": []}


def test_process_event_form_runs_prediction_only_on_change(app, state, monkeypatch):
    runs = []
    monkeypatch.setattr(app, "_run_prediction", lambda s: runs.append(1))
    change = {"client_id": "a", "seq": 1, "kind": "form", "revision": 1,
              "item_key": "k1", "form": dict(FORM)}
    app._process_event(state, change)
    app._process_event(state, {**change, "seq": 2})
    assert runs == [1]


def test_process_event_navigate(app, state, monkeypatch):
    runs, loads = [], []
    monkeypatch.setattr(app, "_run_prediction", lambda s: runs.append(1))
    monkeypatch.setattr(app, "_load_dashboard", lambda s: loads.append(1) or s.update(dashboard={}))
    app._process_event(state, {"client_id": "a", "seq": 1, "kind": "navigate", "page": "bogus"})
    assert state["page"] == "forecast" and not loads
    app._process_event(state, {"client_id": "a", "seq": 2, "kind": "navigate",
                               "page": "management", "revision": 1, "item_key": "k1",
                               "form": dict(FORM)})
    assert state["page"] == "management" and runs == [1] and loads == [1]
    app._process_event(state, {"client_id": "a", "seq": 3, "kind": "navigate", "page": "forecast"})
    assert state["page"] == "forecast" and loads == [1]


def test_process_event_filter_rejects_non_string(app, state, monkeypatch):
    loads = []
    monkeypatch.setattr(app, "_load_dashboard", lambda s: loads.append(1))
    app._process_event(state, {"client_id": "a", "seq": 1, "kind": "filter", "product": 5})
    assert not loads
    app._process_event(state, {"client_id": "a", "seq": 2, "kind": "filter", "product": None})
    assert loads == [1] and state["filter_product"] is None


def test_process_event_page_is_clamped_to_history(app, state):
    state["dashboard"] = {"history": [{}] * 45}
    app._process_event(state, {"client_id": "a", "seq": 1, "kind": "page", "page": 99})
    assert state["dashboard_page"] == 2
    app._process_event(state, {"client_id": "a", "seq": 2, "kind": "page", "page": -4})
    assert state["dashboard_page"] == 0
    app._process_event(state, {"client_id": "a", "seq": 3, "kind": "page", "page": "x"})
    assert state["dashboard_page"] == 0


def _ready_for_recommend(state, achieved=False):
    state.update(revision=3, prediction_status="success",
                 prediction={"achieved": achieved, "inputs": {"target": 0.8}})


@pytest.mark.parametrize("mutation", [
    {"revision": 9}, {"prediction_status": "invalid"}, {"prediction": None},
    {"prediction": {"achieved": True, "inputs": {}}}, {"recommendation_revision": 3},
])
def test_recommend_event_guards(app, state, monkeypatch, mutation):
    _ready_for_recommend(state)
    state.update(mutation)
    monkeypatch.setattr(ui_adapter, "run_recommendations",
                        lambda inputs: pytest.fail("không được gọi gợi ý"))
    app._process_event(state, {"client_id": "a", "seq": 1, "kind": "recommend", "revision": 3})
    assert state["recommendations"] is None


def test_recommend_event_success_and_error(app, state, monkeypatch):
    _ready_for_recommend(state)
    monkeypatch.setattr(ui_adapter, "run_recommendations",
                        lambda inputs: {"ok": True, "result": {"options": []}, "message": None})
    app._process_event(state, {"client_id": "a", "seq": 1, "kind": "recommend", "revision": 3})
    assert state["recommendation_status"] == "success"
    assert state["recommendations"] == {"options": []}

    _ready_for_recommend(state)
    state["recommendation_revision"] = None
    monkeypatch.setattr(ui_adapter, "run_recommendations",
                        lambda inputs: {"ok": False, "result": None, "message": "lỗi"})
    app._process_event(state, {"client_id": "a", "seq": 2, "kind": "recommend", "revision": 3})
    assert state["recommendation_status"] == "error"
    assert state["recommendation_message"] == "lỗi" and state["recommendations"] is None


def test_payload_hides_acknowledged_catalog_and_gates_dashboard(app, state):
    state["dashboard"] = {"kpis": {}}
    forecast = app._payload(state)
    assert forecast["catalog"] == CATALOG["items"] and forecast["dashboard"] is None
    assert forecast["items_count"] == 1
    state.update(catalog_ack=True, page="management", selected_item_key="k1")
    management = app._payload(state)
    assert management["catalog"] is None and management["dashboard"] == {"kpis": {}}
    assert management["selected_item"]["sku"] == "S-01"


def test_component_event_callback_reads_mapping_or_attribute(app, monkeypatch):
    seen = []
    monkeypatch.setattr(app, "_process_event", lambda s, e: seen.append(e))
    state = {"x": 1}
    session = {app._STATE_KEY: state, app.COMPONENT_KEY: {"event": "từ-dict"}}
    monkeypatch.setattr(app.st, "session_state", session)
    app._on_component_event()
    session[app.COMPONENT_KEY] = SimpleNamespace(event="từ-thuộc-tính")
    app._on_component_event()
    session[app._STATE_KEY] = "không phải dict"
    app._on_component_event()
    assert seen == ["từ-dict", "từ-thuộc-tính"]


def test_new_state_defaults_numeric_inputs_to_zero_but_not_workers(app):
    form = app._new_state()["form"]
    assert {form[k] for k in ("target", "overtime", "bonus", "idle")} == {"0"}
    assert form["full_shift_workers"] == "" and form["half_shift_workers"] == ""
