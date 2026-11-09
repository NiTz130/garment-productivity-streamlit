"""Test giao diện bằng trình duyệt thật (Playwright + Microsoft Edge) trên máy chủ Streamlit thật.

Máy chủ chạy trên bản sao cô lập của dự án, có model riêng, nên không đụng tới `runtime/` thật.
Bỏ qua (NOT RUN) nếu thiếu gói playwright hoặc không mở được Edge.
"""
from __future__ import annotations

from pathlib import Path
import re
import shutil
import socket
import subprocess
import sys
import time
import urllib.request

import pytest

sync_api = pytest.importorskip("playwright.sync_api", reason="NOT RUN: chưa cài playwright (requirements.txt)")
expect = sync_api.expect

ROOT = Path(__file__).resolve().parents[1]
SKU = "QJ-ZJSSA"  # dòng đầu của dataset; SMV 26,16
COPY_IGNORE = shutil.ignore_patterns(
    ".git", "tests", "htmlcov", ".pytest*", "__pycache__", "runtime", ".coverage*", "docs", ".tmp")


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _start_server(project: Path, trained: bool):
    if trained:
        subprocess.run(
            [sys.executable, "-X", "utf8", "-c",
             "import model; from data import load_data; model.activate(model.train(load_data()))"],
            cwd=project, check=True)
    port = _free_port()
    process = subprocess.Popen(
        [sys.executable, "-m", "streamlit", "run", "app.py", "--server.headless", "true",
         "--server.port", str(port), "--server.address", "127.0.0.1",
         "--browser.gatherUsageStats", "false"],
        cwd=project, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(80):
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{port}/_stcore/health", timeout=1)
            return process, f"http://127.0.0.1:{port}"
        except OSError:
            time.sleep(0.5)
    process.terminate()
    raise RuntimeError("Máy chủ Streamlit không khởi động được trong 40 giây.")


@pytest.fixture(scope="module")
def project(tmp_path_factory):
    target = tmp_path_factory.mktemp("ui") / "project"
    shutil.copytree(ROOT, target, ignore=COPY_IGNORE)
    return target


@pytest.fixture(scope="module")
def server(project):
    process, url = _start_server(project, trained=True)
    yield url
    process.terminate()


@pytest.fixture(scope="module")
def server_without_model(tmp_path_factory):
    target = tmp_path_factory.mktemp("ui_nomodel") / "project"
    shutil.copytree(ROOT, target, ignore=COPY_IGNORE)
    process, url = _start_server(target, trained=False)
    yield url
    process.terminate()


@pytest.fixture(scope="module")
def browser():
    with sync_api.sync_playwright() as playwright:
        try:
            instance = playwright.chromium.launch(channel="msedge", headless=True)
        except Exception as exc:  # không có Edge: không thể kiểm tra giao diện
            pytest.skip(f"NOT RUN: không mở được Microsoft Edge ({type(exc).__name__}).")
        yield instance
        instance.close()


@pytest.fixture
def page(browser):
    context = browser.new_context(viewport={"width": 1280, "height": 900}, locale="vi-VN")
    page = context.new_page()
    page.errors = []
    page.on("console", lambda message: message.type == "error" and page.errors.append(message.text))
    page.on("pageerror", lambda error: page.errors.append(str(error)))
    yield page
    context.close()


def open_app(page, url):
    page.goto(url)
    page.wait_for_selector("#product-search", timeout=30000)


def pick_product(page, query=SKU):
    page.fill("#product-search", query)
    page.locator("#product-options [role=option]").first.click()
    expect(page.locator("#smv-display")).not_to_have_text("—")


def fill_shift(page, target="95", workers="20", overtime="0", bonus="0", idle="30"):
    page.fill("#target-input", target)
    page.fill("#workers-input", workers)
    page.fill("#overtime-input", overtime)
    page.fill("#bonus-input", bonus)
    page.fill("#idle-input", idle)


def test_initial_forecast_page_has_empty_state_and_navigation(page, server):
    open_app(page, server)
    expect(page.locator("#forecast-title")).to_have_text("Dự báo & ra quyết định")
    expect(page.locator("#result-empty")).to_contain_text("Chưa chọn sản phẩm")
    expect(page.locator("#prediction-block")).to_be_hidden()
    expect(page.locator("[data-page=forecast]")).to_have_attribute("aria-current", "page")
    expect(page.locator("#management-page")).to_be_hidden()


def test_product_search_selects_item_and_fills_smv(page, server):
    open_app(page, server)
    page.fill("#product-search", SKU)
    option = page.locator("#product-options [role=option]")
    expect(option).to_have_count(1)
    expect(option.first).to_contain_text(SKU)
    option.first.click()
    expect(page.locator("#smv-display")).to_have_text("26,16")


def test_product_search_without_match_says_so(page, server):
    open_app(page, server)
    page.fill("#product-search", "không-có-mẫu-này-zzz")
    expect(page.locator("#product-options")).to_contain_text("Không tìm thấy mẫu hàng phù hợp.")


def test_product_combobox_works_with_keyboard(page, server):
    open_app(page, server)
    page.fill("#product-search", SKU)
    expect(page.locator("#product-options [role=option]")).to_have_count(1)
    page.keyboard.press("ArrowDown")
    page.keyboard.press("Enter")
    expect(page.locator("#smv-display")).to_have_text("26,16")


def test_below_target_forecast_offers_three_adjustment_options(page, server):
    open_app(page, server)
    pick_product(page)
    fill_shift(page, target="95")
    expect(page.locator("#prediction-block")).to_be_visible()
    expect(page.locator("#prediction-status")).to_contain_text("Chưa đạt mục tiêu")
    expect(page.locator("#prediction-value")).to_contain_text("%")
    expect(page.locator("#target-gap")).to_contain_text("điểm %")
    expect(page.locator("#option-grid > *")).to_have_count(3, timeout=20000)
    expect(page.locator("#option-grid")).to_contain_text("Bổ sung nhân lực")
    expect(page.locator("#option-grid")).to_contain_text("Điều chỉnh tăng ca")


def test_target_met_hides_adjustment_options(page, server):
    open_app(page, server)
    pick_product(page)
    fill_shift(page, target="20")
    expect(page.locator("#prediction-status")).to_contain_text("Đạt mục tiêu")
    expect(page.locator("#option-grid")).to_be_hidden()
    expect(page.locator("#options-placeholder")).to_be_visible()


def test_changing_input_replaces_old_forecast(page, server):
    open_app(page, server)
    pick_product(page)
    fill_shift(page, target="95")
    expect(page.locator("#prediction-status")).to_contain_text("Chưa đạt mục tiêu")
    page.fill("#target-input", "20")
    expect(page.locator("#prediction-status")).to_contain_text("Đạt mục tiêu")


def test_half_shift_worker_adds_half_a_worker(page, server):
    open_app(page, server)
    page.fill("#workers-input", "20")
    expect(page.locator("#labor-converted")).to_contain_text("20 lao động/ca")
    page.check("#half-shift-input")
    expect(page.locator("#labor-converted")).to_contain_text("20,5 lao động/ca")
    expect(page.locator("#labor-summary")).to_contain_text("20 người cả ca + 1 người nửa ca")


@pytest.mark.parametrize("field, value, error_id, message", [
    ("#bonus-input", "10,5", "#error-bonus", "Nhập số nguyên"),
    ("#target-input", "150", "#error-target", "vượt giới hạn"),
    ("#idle-input", "301", "#error-idle", "Vượt giới hạn"),
    ("#workers-input", "1", "#error-full_shift_workers", "Tối thiểu"),
    ("#overtime-input", "-5", "#error-overtime", "không được âm"),
    ("#bonus-input", "abc", "#error-bonus", "định dạng"),
])
def test_invalid_input_shows_error_and_blocks_forecast(page, server, field, value, error_id, message):
    open_app(page, server)
    pick_product(page)
    fill_shift(page, target="95")
    expect(page.locator("#prediction-block")).to_be_visible()
    page.fill(field, value)
    expect(page.locator(error_id)).to_contain_text(message)
    expect(page.locator("#prediction-block")).to_be_hidden()


def test_blank_field_is_never_treated_as_zero(page, server):
    open_app(page, server)
    pick_product(page)
    fill_shift(page, bonus="")
    expect(page.locator("#error-bonus")).to_contain_text("Nhập tiền thưởng")
    expect(page.locator("#prediction-block")).to_be_hidden()
    page.fill("#bonus-input", "0")
    expect(page.locator("#prediction-block")).to_be_visible()


def test_forecast_keeps_inputs_after_switching_pages(page, server):
    open_app(page, server)
    pick_product(page)
    fill_shift(page, target="95")
    expect(page.locator("#prediction-block")).to_be_visible()
    page.click("[data-page=management]")
    expect(page.locator("#management-page")).to_be_visible()
    page.click("[data-page=forecast]")
    expect(page.locator("#target-input")).to_have_value("95")
    expect(page.locator("#prediction-block")).to_be_visible()


def test_management_page_shows_kpis_charts_and_first_history_page(page, server):
    open_app(page, server)
    page.click("[data-page=management]")
    expect(page.locator("[data-page=management]")).to_have_attribute("aria-current", "page")
    expect(page.locator("#kpi-shifts")).to_have_text("1.197", timeout=20000)
    expect(page.locator("#kpi-actual")).to_contain_text("%")
    expect(page.locator("#kpi-achievement")).to_contain_text("%")
    assert 1 <= page.locator("#comparison-chart .bar-row").count() <= 10
    expect(page.locator("#bonus-chart svg")).to_have_count(1)
    expect(page.locator("#history-body tr")).to_have_count(20)
    expect(page.locator("#page-summary")).to_contain_text("1–20 trong 1.197")


def test_history_pagination_moves_forward_and_back(page, server):
    open_app(page, server)
    page.click("[data-page=management]")
    expect(page.locator("#kpi-shifts")).to_have_text("1.197", timeout=20000)
    first_row = page.locator("#history-body tr").first.text_content()
    page.click("#page-next")
    expect(page.locator("#page-summary")).to_contain_text("21–40")
    assert page.locator("#history-body tr").first.text_content() != first_row
    page.click("#page-prev")
    expect(page.locator("#page-summary")).to_contain_text("1–20")
    expect(page.locator("#history-body tr").first).to_have_text(first_row)


def test_product_filter_narrows_every_dashboard_section(page, server):
    open_app(page, server)
    page.click("[data-page=management]")
    expect(page.locator("#kpi-shifts")).to_have_text("1.197", timeout=20000)
    assert page.locator("#product-filter option").count() > 2
    page.select_option("#product-filter", index=3)
    expect(page.locator("#kpi-shifts")).not_to_have_text("1.197")
    shown = int(page.inner_text("#kpi-shifts").replace(".", ""))
    expect(page.locator("#history-body tr")).to_have_count(min(shown, 20))
    expect(page.locator("#filter-summary")).to_contain_text(f"{shown} ca")
    page.select_option("#product-filter", index=0)
    expect(page.locator("#kpi-shifts")).to_have_text("1.197")


@pytest.mark.parametrize("target_page", ["forecast", "management"])
def test_pages_fit_phone_width_without_horizontal_scroll(page, server, target_page):
    page.set_viewport_size({"width": 390, "height": 800})
    open_app(page, server)
    page.click(f"[data-page={target_page}]")
    expect(page.locator(f"#{target_page}-page")).to_be_visible()
    if target_page == "management":
        expect(page.locator("#kpi-shifts")).to_have_text("1.197", timeout=20000)
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")


def test_every_form_input_has_a_label(page, server):
    open_app(page, server)
    inputs = page.locator("#forecast-page input")
    assert inputs.count() == 7  # giao diện nằm trong shadow DOM: document.querySelectorAll không thấy
    unlabeled = inputs.evaluate_all(
        "els => els.filter(el => !(el.labels && el.labels.length) && !el.getAttribute('aria-label')).map(el => el.id)")
    assert unlabeled == []


def test_full_session_produces_no_console_errors(page, server):
    open_app(page, server)
    pick_product(page)
    fill_shift(page, target="95")
    expect(page.locator("#option-grid > *")).to_have_count(3, timeout=20000)
    page.click("[data-page=management]")
    expect(page.locator("#kpi-shifts")).to_have_text("1.197", timeout=20000)
    page.select_option("#product-filter", index=2)
    assert page.errors == []


def test_missing_model_is_reported_in_vietnamese_without_internals(page, server_without_model):
    open_app(page, server_without_model)
    pick_product(page)
    fill_shift(page, target="95")
    expect(page.locator("#result-message")).to_contain_text("chưa sẵn sàng dự báo", timeout=20000)
    expect(page.locator("#result-message")).not_to_contain_text("Traceback")
    expect(page.locator("#prediction-block")).to_be_hidden()
    page.click("[data-page=management]")
    expect(page.locator("#kpi-shifts")).to_have_text("1.197", timeout=20000)


VIETNAMESE_SAMPLE = "ăâêôơưđ ệữẫổ"


def _computed_family(page, selector):
    return page.locator(selector).first.evaluate("el => getComputedStyle(el).fontFamily.split(',')[0].trim().replace(/[\"']/g, '')")


def test_three_distinct_font_families_are_loaded_and_assigned_to_roles(page, server):
    open_app(page, server)
    page.evaluate("document.fonts.ready")
    bundled = ["Be Vietnam Pro", "Source Serif 4", "JetBrains Mono"]  # bỏ qua font KaTeX của chính Streamlit
    faces = page.evaluate(
        "names => [...document.fonts].map(f => ({family: f.family.replace(/[\"']/g, ''), status: f.status}))"
        ".filter(f => names.includes(f.family))", bundled)
    assert {face["family"] for face in faces} == set(bundled)
    assert len(faces) == 12 and all(face["status"] == "loaded" for face in faces), faces
    roles = {
        "heading": _computed_family(page, "#forecast-title"),
        "body": _computed_family(page, "#product-search"),
        "numeric": _computed_family(page, "#smv-display"),
    }
    assert len(set(roles.values())) == 3, roles


@pytest.mark.parametrize("font", ["500 29px \"Source Serif 4\"", "700 29px \"Source Serif 4\"",
                                  "400 14px \"Be Vietnam Pro\"", "600 14px \"Be Vietnam Pro\"",
                                  "400 13px \"JetBrains Mono\"", "600 13px \"JetBrains Mono\""])
def test_each_font_renders_stacked_vietnamese_marks(page, server, font):
    open_app(page, server)
    page.evaluate("document.fonts.ready")
    assert page.evaluate("([font, text]) => document.fonts.check(font, text)", [font, VIETNAMESE_SAMPLE])


# ---- Sửa sau critique: chữ, màu trạng thái, phương án, ô tìm kiếm, biểu đồ, điện thoại ----

def _below_target_page(page, server, width=1280, height=900):
    page.set_viewport_size({"width": width, "height": height})
    open_app(page, server)
    pick_product(page)
    fill_shift(page, target="95")
    expect(page.locator("#option-grid > *")).to_have_count(3, timeout=20000)


def test_no_visible_text_is_smaller_than_13px(page, server):
    _below_target_page(page, server)
    scan = """root => [...root.querySelectorAll('*')].filter(el => {
        const own = [...el.childNodes].some(n => n.nodeType === 3 && n.textContent.trim());
        return own && !el.closest('[hidden]') && !el.closest('svg') && parseFloat(getComputedStyle(el).fontSize) < 13;
    }).map(el => el.className + ':' + getComputedStyle(el).fontSize)"""
    small = page.locator("#garment-app").evaluate(scan)
    page.click("[data-page=management]")
    expect(page.locator("#kpi-shifts")).to_have_text("1.197", timeout=20000)
    expect(page.locator("#comparison-chart .bar-row").first).to_be_attached()
    small += page.locator("#garment-app").evaluate(scan)
    assert small == []


def test_body_text_renders_at_16px(page, server):
    open_app(page, server)
    sizes = page.locator("#garment-app").evaluate("""root => ({
        empty: getComputedStyle(root.querySelector('.empty-result p')).fontSize,
        footnote: getComputedStyle(root.querySelector('.input-footnote')).fontSize,
        search: getComputedStyle(root.querySelector('#product-search')).fontSize,
    })""")
    assert sizes == {"empty": "16px", "footnote": "16px", "search": "16px"}
    _below_target_page(page, server)
    assert page.locator("#options-summary").evaluate("el => getComputedStyle(el).fontSize") == "16px"


def test_bonus_field_shows_typical_range_besides_the_allowed_limit(page, server):
    open_app(page, server)
    pick_product(page)
    expect(page.locator("#range-bonus")).to_contain_text("Cho phép")
    typical = page.locator("#typical-bonus")
    expect(typical).to_be_visible()
    text = typical.inner_text()
    assert text.startswith("Thường gặp ") and "VNĐ" in text and "ca có thưởng" in text, text
    low, high = [_vn_number(n) for n in re.findall(r"\d[\d.]*", text)[:2]]
    assert 0 < low < high < 746709, text  # khoảng thường gặp hẹp hơn nhiều so với giới hạn cho phép


def test_below_target_value_is_not_green_and_trend_is_neutral(page, server):
    _below_target_page(page, server)
    assert "is-below" in page.get_attribute("#prediction-value", "class")
    expect(page.locator("#prediction-trend")).to_have_class("numeric is-neutral")
    fill_shift(page, target="20")
    expect(page.locator("#prediction-status")).to_contain_text("Đạt mục tiêu")
    assert "is-below" not in page.get_attribute("#prediction-value", "class")
    expect(page.locator("#prediction-trend")).to_have_class("numeric is-neutral")


def test_summary_names_best_reachable_option_and_cards_have_no_boilerplate(page, server):
    _below_target_page(page, server)
    expect(page.locator("#options-summary")).to_contain_text("Chưa phương án nào đạt mục tiêu")
    expect(page.locator("#options-summary")).to_contain_text("điểm %")
    assert page.locator("#option-grid .option-reason").count() == 0
    assert "backend" not in page.locator("#garment-app").inner_text().lower()


def test_apply_option_copies_it_into_the_form_and_forecast_matches(page, server):
    _below_target_page(page, server)
    card = page.locator("#option-grid > *").first
    expected = card.locator(".option-prediction strong").inner_text()
    card.get_by_role("button", name="Áp dụng vào biểu mẫu").click()
    assert int(page.input_value("#workers-input")) > 20
    expect(page.locator("#prediction-value")).to_have_text(expected, timeout=20000)


def test_valid_ranges_are_shown_next_to_inputs(page, server):
    open_app(page, server)
    expect(page.locator("#range-target")).to_contain_text("0–100%")
    expect(page.locator("#range-workers")).to_contain_text("2–89")
    expect(page.locator("#range-idle")).to_contain_text("0–300")


def test_negative_workers_never_shows_a_valid_conversion(page, server):
    open_app(page, server)
    page.fill("#workers-input", "-1")
    expect(page.locator("#labor-summary")).to_contain_text("không được âm")
    expect(page.locator("#labor-converted")).not_to_contain_text("-1")


def test_enter_selects_the_only_matching_product_without_arrow_key(page, server):
    open_app(page, server)
    page.fill("#product-search", SKU)
    expect(page.locator("#product-options [role=option]")).to_have_count(1)
    page.keyboard.press("Enter")
    expect(page.locator("#smv-display")).to_have_text("26,16")


def test_leaving_the_search_box_restores_the_selected_product_name(page, server):
    open_app(page, server)
    pick_product(page)
    selected = page.input_value("#product-search")
    page.fill("#product-search", "zzzz")
    page.focus("#target-input")
    expect(page.locator("#product-search")).to_have_value(selected)
    expect(page.locator("#smv-display")).to_have_text("26,16")


def test_junk_search_text_is_cleared_when_nothing_is_selected(page, server):
    open_app(page, server)
    page.fill("#product-search", "zzzz")
    page.focus("#target-input")
    expect(page.locator("#product-search")).to_have_value("")


def test_scatter_points_are_not_tab_stops_and_missed_points_use_another_shape(page, server):
    open_app(page, server)
    page.click("[data-page=management]")
    expect(page.locator("#kpi-shifts")).to_have_text("1.197", timeout=20000)
    expect(page.locator("#bonus-chart .data-point").first).to_be_attached()
    assert page.locator("#bonus-chart [tabindex]").count() == 0
    assert page.locator("#bonus-chart circle.is-achieved").count() > 0
    assert page.locator("#bonus-chart path.is-missed").count() > 0
    rows = page.locator("#comparison-chart .bar-row")
    assert 1 <= rows.count() <= 10
    assert page.locator("#comparison-chart [tabindex]").count() == rows.count()


def test_tooltip_is_hidden_when_the_chart_is_redrawn(page, server):
    open_app(page, server)
    page.click("[data-page=management]")
    expect(page.locator("#kpi-shifts")).to_have_text("1.197", timeout=20000)
    page.locator("#comparison-chart .bar-row").first.hover()
    expect(page.locator("#chart-tooltip")).to_be_visible()
    page.select_option("#product-filter", index=2)
    expect(page.locator("#kpi-shifts")).not_to_have_text("1.197")
    expect(page.locator("#chart-tooltip")).to_be_hidden()


def test_chart_labels_are_full_names_and_text_stays_readable_on_phone(page, server):
    page.set_viewport_size({"width": 390, "height": 800})
    open_app(page, server)
    page.click("[data-page=management]")
    expect(page.locator("#kpi-shifts")).to_have_text("1.197", timeout=20000)
    labels = page.locator("#comparison-chart .row-label")
    expect(labels.first).to_be_attached()
    names = labels.all_inner_texts()
    assert names and not any(name.endswith("…") for name in names), names
    clipped = labels.evaluate_all("els => els.filter(el => el.scrollWidth > el.clientWidth).length")
    assert clipped == 0
    heights = page.locator("#bonus-chart svg text").evaluate_all(
        "els => els.map(el => el.getBoundingClientRect().height)")
    assert heights and min(heights) >= 11, heights  # chữ 13px ở tỉ lệ 1:1, không bị co theo viewBox


def test_phone_shows_a_sticky_result_bar_while_editing_the_form(page, server):
    page.set_viewport_size({"width": 390, "height": 844})
    open_app(page, server)
    pick_product(page)
    fill_shift(page, target="95")
    expect(page.locator("#prediction-block")).to_be_visible()
    page.focus("#idle-input")
    bar = page.locator("#result-bar")
    expect(bar).to_be_visible()
    box = bar.bounding_box()
    assert box and box["y"] + box["height"] <= 844 + 1, box
    expect(page.locator("#bar-value")).to_have_text(page.inner_text("#prediction-value"))


def test_result_bar_is_hidden_on_the_management_page(page, server):
    page.set_viewport_size({"width": 390, "height": 844})
    open_app(page, server)
    pick_product(page)
    fill_shift(page, target="95")
    expect(page.locator("#result-bar")).to_be_visible()
    page.click("[data-page=management]")
    expect(page.locator("#kpi-shifts")).to_have_text("1.197")
    expect(page.locator("#result-bar")).to_be_hidden()
    page.click("[data-page=forecast]")
    expect(page.locator("#result-bar")).to_be_visible()


@pytest.mark.parametrize("width", [390, 1440])
def test_field_labels_do_not_overlap_their_range_hints(page, server, width):
    page.set_viewport_size({"width": width, "height": 900})
    open_app(page, server)
    pick_product(page)
    fill_shift(page, target="95")
    expect(page.locator("#range-overtime")).to_contain_text("Cho phép")
    for field in ("overtime", "idle", "workers", "target", "bonus"):
        line = page.locator(f"#range-{field}").locator("xpath=..")
        label = line.locator("label").bounding_box()
        hint = page.locator(f"#range-{field}").bounding_box()
        overlap = (label["x"] < hint["x"] + hint["width"] and hint["x"] < label["x"] + label["width"]
                   and label["y"] < hint["y"] + hint["height"] and hint["y"] < label["y"] + label["height"])
        assert not overlap, (field, label, hint)
        assert label["height"] <= 24, (field, label)  # nhãn không bị ngắt thành nhiều dòng


def _vn_number(text):
    return float(text.replace(".", "").replace(",", "."))


def test_apply_option_copies_it_into_the_form_and_forecasts_again(page, server):
    page.set_viewport_size({"width": 1440, "height": 900})
    open_app(page, server)
    pick_product(page)
    fill_shift(page, target="95")
    card = page.locator(".option-card").first
    expect(card).to_be_visible()
    predicted = re.search(r"\d+,\d%", card.inner_text()).group(0)
    new_workers = _vn_number(re.search(r"→\s*([\d.,]+)", card.inner_text()).group(1))
    card.locator(".option-apply").click()
    assert _vn_number(page.input_value("#workers-input")) == int(new_workers)
    assert page.is_checked("#half-shift-input") == (new_workers % 1 >= 0.5)
    expect(page.locator("#prediction-value")).to_have_text(predicted, timeout=30000)


def test_apply_option_replaces_the_half_shift_flag_so_the_form_matches_the_option(page, server):
    page.set_viewport_size({"width": 1440, "height": 900})
    open_app(page, server)
    pick_product(page)
    fill_shift(page, target="95")
    page.check("#half-shift-input")
    card = page.locator(".option-card").first
    expect(card).to_be_visible()
    total = int(_vn_number(re.search(r"→\s*([\d.,]+)", card.inner_text()).group(1)))
    card.locator(".option-apply").click()
    assert not page.is_checked("#half-shift-input")
    assert int(_vn_number(page.input_value("#workers-input"))) == total
    expect(page.locator("#labor-converted")).to_contain_text(f"{total} lao động/ca")


def test_unavailable_options_have_no_apply_button(page, server):
    page.set_viewport_size({"width": 1440, "height": 900})
    open_app(page, server)
    pick_product(page)
    fill_shift(page, target="100", workers="89", overtime="25920", bonus="0", idle="300")
    expect(page.locator(".option-card").first).to_be_visible(timeout=30000)
    cards = page.locator(".option-card")
    unavailable = page.locator(".option-card:has(.is-unavailable)")
    assert unavailable.count() >= 1, cards.all_inner_texts()
    assert unavailable.locator(".option-apply").count() == 0
    assert cards.locator(".option-apply").count() == cards.count() - unavailable.count()


@pytest.mark.parametrize("width", [390, 1440])
def test_option_card_row_labels_stay_on_one_line(page, server, width):
    page.set_viewport_size({"width": width, "height": 900})
    open_app(page, server)
    pick_product(page)
    fill_shift(page, target="95")
    expect(page.locator(".option-card").first).to_be_visible()
    heights = page.locator(".option-change > span").evaluate_all(
        "els => els.map(el => [el.textContent, Math.round(el.getBoundingClientRect().height)])")
    assert heights and all(h <= 24 for _, h in heights), heights


def test_result_bar_is_hidden_on_desktop(page, server):
    page.set_viewport_size({"width": 1280, "height": 900})
    open_app(page, server)
    pick_product(page)
    fill_shift(page, target="95")
    expect(page.locator("#prediction-block")).to_be_visible()
    expect(page.locator("#result-bar")).to_be_hidden()


def test_touch_targets_on_phone_are_at_least_44px(page, server):
    page.set_viewport_size({"width": 390, "height": 844})
    open_app(page, server)
    small = page.locator("#forecast-page input:not([type=checkbox]), .nav-tab, .check-row").evaluate_all(
        "els => els.map(el => [el.id || el.className, Math.round(el.getBoundingClientRect().height)])"
        ".filter(([, h]) => h < 44)")
    assert small == [], small
