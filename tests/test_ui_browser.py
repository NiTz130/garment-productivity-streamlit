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


def test_below_target_forecast_offers_five_adjustment_options(page, server):
    open_app(page, server)
    pick_product(page)
    fill_shift(page, target="95")
    expect(page.locator("#prediction-block")).to_be_visible()
    expect(page.locator("#prediction-status")).to_contain_text("Chưa đạt mục tiêu")
    expect(page.locator("#prediction-value")).to_contain_text("%")
    expect(page.locator("#target-gap")).to_contain_text("điểm %")
    expect(page.locator("#option-grid > *")).to_have_count(5, timeout=20000)
    expect(page.locator("#option-grid")).to_contain_text("Bổ sung nhân lực")
    expect(page.locator("#option-grid")).to_contain_text("Điều chỉnh tăng ca")
    expect(page.locator("#option-grid")).to_contain_text("Tăng tiền thưởng")
    expect(page.locator("#option-grid")).to_contain_text("Giảm thời gian máy dừng")


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


def test_half_shift_workers_count_half_a_worker_each(page, server):
    open_app(page, server)
    page.fill("#workers-input", "20")
    expect(page.locator("#labor-converted")).to_contain_text("20 lao động/ca")
    page.fill("#half-shift-input", "1")
    expect(page.locator("#labor-converted")).to_contain_text("20,5 lao động/ca")
    expect(page.locator("#labor-summary")).to_contain_text("20 người cả ca + 1 người nửa ca")
    page.fill("#half-shift-input", "3")
    expect(page.locator("#labor-converted")).to_contain_text("21,5 lao động/ca")
    expect(page.locator("#labor-summary")).to_contain_text("20 người cả ca + 3 người nửa ca")
    page.fill("#half-shift-input", "")  # để trống = 0 người nửa ca
    expect(page.locator("#labor-converted")).to_contain_text("20 lao động/ca")
    page.fill("#half-shift-input", "2,5")
    expect(page.locator("#labor-summary")).to_contain_text("Nhập số nguyên người nửa ca")
    page.fill("#half-shift-input", "-1")
    expect(page.locator("#labor-summary")).to_contain_text("không được âm")


def test_labor_box_has_two_separate_numeric_inputs(page, server):
    open_app(page, server)
    expect(page.locator("label[for=workers-input]")).to_have_text("Số người làm cả ca")
    expect(page.locator("label[for=half-shift-input]")).to_have_text("Số người làm nửa ca")
    expect(page.locator("#half-shift-input")).to_have_attribute("type", "text")
    expect(page.locator("#half-shift-input")).to_have_attribute("placeholder", "0")


def test_half_shift_workers_do_not_block_forecast_when_blank(page, server):
    open_app(page, server)
    pick_product(page)
    fill_shift(page, target="95")
    expect(page.locator("#prediction-block")).to_be_visible()
    expect(page.locator("#error-half_shift_workers")).to_have_text("")
    page.fill("#half-shift-input", "4")
    expect(page.locator("#prediction-block")).to_be_visible()


@pytest.mark.parametrize("field, value, error_id, message", [
    ("#bonus-input", "10,5", "#error-bonus", "Nhập số nguyên"),
    ("#target-input", "150", "#error-target", "vượt giới hạn"),
    ("#idle-input", "301", "#error-idle", "Vượt giới hạn"),
    ("#workers-input", "1", "#error-full_shift_workers", "Tối thiểu"),
    ("#overtime-input", "-5", "#error-overtime", "không được âm"),
    ("#half-shift-input", "2,5", "#error-half_shift_workers", "Nhập số nguyên"),
    ("#half-shift-input", "200", "#error-half_shift_workers", "Tổng quy đổi"),
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
    assert 2 <= page.locator("#bonus-chart .dot-row").count() <= 5
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
    expect(page.locator("#option-grid > *")).to_have_count(5, timeout=20000)
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
    expect(page.locator("#option-grid > *")).to_have_count(5, timeout=20000)


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


def test_apply_idle_option_lowers_idle_in_the_form(page, server):
    _below_target_page(page, server)
    card = page.locator("#option-grid > *").filter(has_text="Giảm thời gian máy dừng")
    card.get_by_role("button", name="Áp dụng vào biểu mẫu").click()
    assert int(page.input_value("#idle-input")) < 30

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


def test_clear_button_is_hidden_until_the_search_box_has_text(page, server):
    open_app(page, server)
    expect(page.locator("#product-clear")).to_be_hidden()
    page.fill("#product-search", "zz")
    expect(page.locator("#product-clear")).to_be_visible()


def test_clear_button_removes_selected_product_and_resets_forecast(page, server):
    open_app(page, server)
    pick_product(page)
    fill_shift(page, target="95")
    expect(page.locator("#prediction-block")).to_be_visible()
    page.click("#product-clear")
    expect(page.locator("#product-search")).to_have_value("")
    expect(page.locator("#product-search")).to_be_focused()
    expect(page.locator("#smv-display")).to_have_text("—")
    expect(page.locator("#product-clear")).to_be_hidden()
    expect(page.locator("#prediction-block")).to_be_hidden()
    expect(page.locator("#product-options [role=option]").first).to_be_visible()
    pick_product(page)
    expect(page.locator("#smv-display")).to_have_text("26,16")
    page.click("#product-clear")
    page.focus("#target-input")
    expect(page.locator("#product-search")).to_have_value("")
    expect(page.locator("#smv-display")).to_have_text("—")


def test_clear_button_clears_junk_text_when_nothing_is_selected(page, server):
    open_app(page, server)
    page.fill("#product-search", "zzzz")
    page.click("#product-clear")
    expect(page.locator("#product-search")).to_have_value("")
    expect(page.locator("#smv-display")).to_have_text("—")


def test_bonus_chart_is_a_dot_plot_with_one_focusable_row_per_bonus_band(page, server):
    open_app(page, server)
    page.click("[data-page=management]")
    expect(page.locator("#kpi-shifts")).to_have_text("1.197", timeout=20000)
    rows = page.locator("#bonus-chart .dot-row")
    expect(rows.first).to_be_attached()
    assert 2 <= rows.count() <= 5
    assert page.locator("#bonus-chart svg, #bonus-chart .bar-fill").count() == 0
    assert page.locator("#bonus-chart [tabindex]").count() == rows.count()
    assert page.locator("#bonus-chart .dot").count() == rows.count()
    rows.first.hover()
    expect(page.locator("#chart-tooltip")).to_contain_text("Đạt mục tiêu")
    comparison = page.locator("#comparison-chart .bar-row")
    assert 1 <= comparison.count() <= 10
    assert page.locator("#comparison-chart [tabindex]").count() == comparison.count()


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
    sizes = page.locator("#bonus-chart .dot-value, #bonus-chart .row-label").evaluate_all(
        "els => els.map(el => parseFloat(getComputedStyle(el).fontSize))")
    assert sizes and min(sizes) >= 13, sizes
    overflow = page.evaluate("document.documentElement.scrollWidth - window.innerWidth")
    assert overflow <= 0, overflow


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
    assert page.input_value("#half-shift-input") == ("1" if new_workers % 1 >= 0.5 else "0")
    expect(page.locator("#prediction-value")).to_have_text(predicted, timeout=30000)


def test_apply_option_resets_an_odd_half_shift_count_so_the_form_matches_the_option(page, server):
    page.set_viewport_size({"width": 1440, "height": 900})
    open_app(page, server)
    pick_product(page)
    fill_shift(page, target="95")
    page.fill("#half-shift-input", "1")  # 1 người nửa ca không ghép được với phương án nguyên
    card = page.locator(".option-card").first
    expect(card).to_be_visible()
    total = int(_vn_number(re.search(r"→\s*([\d.,]+)", card.inner_text()).group(1)))
    card.locator(".option-apply").click()
    assert page.input_value("#half-shift-input") == "0"
    assert int(_vn_number(page.input_value("#workers-input"))) == total
    expect(page.locator("#labor-converted")).to_contain_text(f"{total} lao động/ca")


def test_apply_option_keeps_an_even_half_shift_count_and_lowers_full_shift_workers(page, server):
    page.set_viewport_size({"width": 1440, "height": 900})
    open_app(page, server)
    pick_product(page)
    fill_shift(page, target="95")
    page.fill("#half-shift-input", "2")  # 2 người nửa ca = 1 lao động quy đổi
    card = page.locator(".option-card").first
    expect(card).to_be_visible()
    total = int(_vn_number(re.search(r"→\s*([\d.,]+)", card.inner_text()).group(1)))
    card.locator(".option-apply").click()
    assert page.input_value("#half-shift-input") == "2"
    assert int(_vn_number(page.input_value("#workers-input"))) == total - 1
    expect(page.locator("#labor-converted")).to_contain_text(f"{total} lao động/ca")


def test_unavailable_options_have_no_apply_button(page, server):
    page.set_viewport_size({"width": 1440, "height": 900})
    open_app(page, server)
    pick_product(page)
    fill_shift(page, target="100", workers="89", overtime="291", bonus="0", idle="300")  # 89 × 291 ≈ trần cả tổ
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


def test_overtime_field_is_per_person_with_its_own_range(page, server):
    open_app(page, server)
    expect(page.locator("label[for=overtime-input]")).to_have_text("Tăng ca mỗi người")
    expect(page.locator("#range-overtime")).to_contain_text("0–720")


def test_overtime_total_line_multiplies_full_shift_workers_only(page, server):
    open_app(page, server)
    expect(page.locator("#overtime-total")).to_have_text("Tổng cả tổ: — phút")
    page.fill("#workers-input", "30")
    page.fill("#overtime-input", "60")
    expect(page.locator("#overtime-total")).to_have_text("Tổng cả tổ: 30 × 60 = 1.800 phút")
    page.fill("#half-shift-input", "4")  # người nửa ca không tính tăng ca
    expect(page.locator("#overtime-total")).to_have_text("Tổng cả tổ: 30 × 60 = 1.800 phút")
    page.fill("#overtime-input", "")
    expect(page.locator("#overtime-total")).to_have_text("Tổng cả tổ: — phút")
    page.fill("#overtime-input", "abc")
    expect(page.locator("#overtime-total")).to_have_text("Tổng cả tổ: — phút")


def test_overtime_above_720_per_person_shows_an_error(page, server):
    open_app(page, server)
    pick_product(page)
    fill_shift(page, target="95", workers="20", overtime="721")
    expect(page.locator("#error-overtime")).to_contain_text("720", timeout=20000)


def test_apply_overtime_option_keeps_the_team_total_and_forecast(page, server):
    page.set_viewport_size({"width": 1440, "height": 900})
    open_app(page, server)
    pick_product(page)
    fill_shift(page, target="95")
    card = page.locator(".option-card:has-text('PHƯƠNG ÁN 2')")
    expect(card).to_be_visible(timeout=30000)
    predicted = re.search(r"\d+,\d%", card.inner_text()).group(0)
    total = _vn_number(re.search(r"→\s*([\d.,]+)", card.locator(".option-change", has_text="Tăng ca cả tổ").inner_text()).group(1))
    card.locator(".option-apply").click()
    workers = int(page.input_value("#workers-input"))
    assert round(workers * _vn_number(page.input_value("#overtime-input"))) == total
    expect(page.locator("#overtime-total")).to_contain_text(f"= {total:,.0f}".replace(",", "."))
    expect(page.locator("#prediction-value")).to_have_text(predicted, timeout=30000)


ZERO_FIELDS = [("#target-input", "75", "75"), ("#overtime-input", "60", "60"),
               ("#idle-input", "5", "5"), ("#bonus-input", "5000", "5.000")]


def test_numeric_inputs_start_at_zero_and_workers_stays_empty(page, server):
    open_app(page, server)
    for selector, _, _ in ZERO_FIELDS:
        expect(page.locator(selector)).to_have_value("0")
    expect(page.locator("#workers-input")).to_have_value("")


@pytest.mark.parametrize("selector, typed, shown", ZERO_FIELDS)
def test_typing_replaces_the_default_zero(page, server, selector, typed, shown):
    open_app(page, server)
    page.click(selector)  # nhấp chuột thật, không dùng fill
    page.keyboard.type(typed)
    page.locator("#product-search").focus()  # rời ô để bonus được định dạng lại
    expect(page.locator(selector)).to_have_value(shown)


def test_forecast_runs_with_only_product_and_workers_filled(page, server):
    open_app(page, server)
    pick_product(page)
    page.fill("#workers-input", "20")
    expect(page.locator("#prediction-block")).to_be_visible(timeout=20000)


def test_editing_a_non_default_value_keeps_the_caret_instead_of_selecting_all(page, server):
    open_app(page, server)
    page.fill("#overtime-input", "60")
    page.click("#overtime-input")
    page.keyboard.press("End")
    page.keyboard.type("5")
    expect(page.locator("#overtime-input")).to_have_value("605")


# ---- Trang quản trị: biểu đồ tăng ca, máy dừng, phân bố năng suất; tiền thưởng làm tròn ----

MANAGEMENT_ONLY = "[data-page=management]"


def _open_management(page, server):
    open_app(page, server)
    page.click(MANAGEMENT_ONLY)
    expect(page.locator("#kpi-shifts")).to_have_text("1.197", timeout=20000)


def _rows_share_a_line(page, first, second):
    a = page.locator(first).bounding_box()
    b = page.locator(second).bounding_box()
    return abs(a["y"] - b["y"]) <= 4 and b["x"] > a["x"] + a["width"] - 1


def test_management_page_shows_overtime_idle_and_distribution_charts(page, server):
    from data import load_data
    frame = load_data()
    _open_management(page, server)
    expect(page.locator("#overtime-chart .scatter-dot").first).to_be_attached(timeout=20000)
    assert page.locator("#overtime-chart .scatter-dot").count() == len(frame)
    rows = page.locator("#idle-chart .donut-row")
    assert 1 <= rows.count() <= 6
    minutes = [float(t.replace(".", "").replace(",", ".")) for t in
               page.locator("#idle-chart .donut-min").evaluate_all("els => els.map(e => e.textContent.replace(/[^0-9.,]/g, ''))")]
    named = minutes[:-1] if page.locator("#idle-chart .donut-name").last.inner_text() == "Khác" else minutes
    assert named == sorted(named, reverse=True)  # "Khác" luôn nằm cuối
    assert page.locator("#idle-chart svg circle").count() == rows.count()
    expect(page.locator("#idle-chart .donut-row").first).to_contain_text("Áo sơ mi - Mẫu 21")
    expect(page.locator("#idle-chart .donut-row").first).to_contain_text("%")
    assert page.locator("#distribution-chart .hist-bar").count() >= 3
    assert page.locator("#distribution-chart .hist-line.is-mean").count() == 1
    assert page.locator("#distribution-chart .hist-line.is-median").count() == 1
    assert page.locator("#distribution-chart .hist-band").count() == 1
    expect(page.locator("#distribution-summary")).to_have_text(
        "Trên 1.197 ca: trung bình 73,5%, trung vị 77,3%; 80% số ca nằm trong khoảng 47,1%–93,9%; "
        "26,9% số ca dưới mục tiêu; độ lệch chuẩn 17,4 điểm %.")
    # tiền thưởng và tăng ca nằm cạnh nhau trên cùng một hàng
    assert _rows_share_a_line(page, "#bonus-chart >> xpath=ancestor::article", "#overtime-chart >> xpath=ancestor::article")
    assert page.errors == []


def test_overtime_scatter_tooltip_and_filter_change_the_points(page, server):
    _open_management(page, server)
    dots = page.locator("#overtime-chart .scatter-dot")
    expect(dots.first).to_be_attached(timeout=20000)
    page.locator("#overtime-chart .xy-plot").scroll_into_view_if_needed()
    dots.nth(5).hover(force=True)
    expect(page.locator("#chart-tooltip")).to_contain_text("Tăng ca")
    page.select_option("#product-filter", index=3)
    expect(page.locator("#kpi-shifts")).not_to_have_text("1.197")
    shown = int(page.inner_text("#kpi-shifts").replace(".", ""))
    expect(page.locator("#overtime-chart .scatter-dot")).to_have_count(shown)
    expect(page.locator("#chart-tooltip")).to_be_hidden()


def test_product_without_idle_minutes_shows_the_empty_donut_state(page, server):
    from data import load_data
    frame = load_data()
    totals = frame.groupby("product")["idle"].sum()
    zero_idle = str(totals[totals == 0].index[0])
    _open_management(page, server)
    expect(page.locator("#idle-chart .donut-row").first).to_be_attached(timeout=20000)
    page.select_option("#product-filter", label=zero_idle)
    expect(page.locator("#idle-empty")).to_be_visible(timeout=20000)
    assert page.locator("#idle-chart svg").count() == 0
    expect(page.locator("#distribution-chart .hist-bar").first).to_be_attached()  # biểu đồ khác vẫn có dữ liệu
    page.select_option("#product-filter", index=0)
    expect(page.locator("#idle-empty")).to_be_hidden(timeout=20000)


def test_history_bonus_column_is_whole_vnd_with_vietnamese_grouping(page, server):
    _open_management(page, server)
    cells = page.locator("#history-body tr td:nth-child(6)").all_inner_texts()
    assert len(cells) == 20
    assert all(c == "—" or re.fullmatch(r"\d{1,3}(\.\d{3})*", c) for c in cells), cells
    page.click("#page-next")
    expect(page.locator("#page-summary")).to_contain_text("21–40")
    cells = page.locator("#history-body tr td:nth-child(6)").all_inner_texts()
    assert all(c == "—" or re.fullmatch(r"\d{1,3}(\.\d{3})*", c) for c in cells), cells


def test_new_charts_fit_phone_width_and_keep_text_readable(page, server):
    page.set_viewport_size({"width": 390, "height": 800})
    _open_management(page, server)
    expect(page.locator("#distribution-chart .hist-bar").first).to_be_attached(timeout=20000)
    assert page.evaluate("document.documentElement.scrollWidth - window.innerWidth") <= 0
    sizes = page.locator("#idle-chart, #overtime-chart, #distribution-chart, .chart-summary").evaluate_all(
        "els => els.flatMap(root => [...root.querySelectorAll('*')].filter(el => [...el.childNodes].some(n => n.nodeType === 3 && n.textContent.trim()))"
        ".map(el => parseFloat(getComputedStyle(el).fontSize)))")
    assert sizes and min(sizes) >= 13, min(sizes)
    clipped = page.locator("#idle-chart .donut-name").evaluate_all("els => els.filter(el => el.scrollWidth > el.clientWidth).length")
    assert clipped == 0
    # trên điện thoại mỗi thẻ biểu đồ nằm trên một hàng riêng
    cards = page.locator(".charts-grid > article").evaluate_all("els => els.map(e => Math.round(e.getBoundingClientRect().left))")
    assert len(set(cards)) == 1


# ---- Cùng các biểu đồ trên, nhưng nạp app.js với dữ liệu giả (không cần máy chủ, không phụ thuộc backend) ----

FRONTEND = ROOT / "frontend"
LONG = "Quần Jeans/Kaki dài - Mẫu 12 phiên bản đặc biệt"
HARNESS_LOADER = """async ({html, css, js}) => {
    document.body.innerHTML = '<div id="host"></div>';
    const shadow = document.getElementById('host').attachShadow({mode: 'open'});
    shadow.innerHTML = `<style>${css}</style>${html}`;
    const url = URL.createObjectURL(new Blob([js], {type: 'text/javascript'}));
    const mod = await import(url);
    window.__render = (data) => mod.default({parentElement: shadow, data, setStateValue() {}});
}"""


@pytest.fixture
def harness(page):
    page.goto("about:blank")
    page.evaluate(HARNESS_LOADER, {
        "html": (FRONTEND / "index.html").read_text(encoding="utf-8"),
        "css": (FRONTEND / "styles.css").read_text(encoding="utf-8"),
        "js": (FRONTEND / "app.js").read_text(encoding="utf-8"),
    })
    return page


def _dashboard(**charts):
    base = {"product_comparison": [{"product": "A", "target_mean": .8, "actual_mean": .7, "observations": 3}],
            "bonus_vs_actual": [{"bonus": 0, "actual": .7, "target": .8}, {"bonus": 9000, "actual": .9, "target": .8}]}
    base.update(charts)
    row = {"sku": "S", "product": "A", "target": .8, "smv": 10, "overtime": 0, "idle": 0, "workers": 10, "actual": .9}
    history = [{**row, "source_row": i + 1, "bonus": bonus}
               for i, bonus in enumerate([12345.678, 0, 1234567.4, None])]
    return {"page": "management", "dashboard": {
        "kpis": {"shift_count": 4, "actual_mean": .8, "target_achievement_rate": .5, "idle_minutes_total": 30},
        "filter": {"products": ["A"]}, "quality": {"excluded_rows": 0}, "charts": base, "history": history}}


def _points(n=40, product="A", slope=.01):
    return [{"source_row": i, "overtime": 60 * i, "actual": .5 + slope * i, "target": .8, "product": product}
            for i in range(n)]


def _idle(*pairs):
    total = sum(m for _, m in pairs) or 1
    return [{"product": p, "idle_minutes": m, "share": m / total, "shifts": 3, "idle_per_shift": m / 3} for p, m in pairs]


def _distribution(count=30):
    counts = [1, 3, 7, 12, 4, 2, 1, 0, 0]
    bins = [{"low": .2 + .1 * i, "high": .3 + .1 * i, "count": c} for i, c in enumerate(counts)]
    stats = {"count": count, "mean": .735, "median": .75, "std": .174, "p10": .55, "p90": .92,
             "min": .23, "max": 1.12, "below_target_share": .312}
    return {"bins": bins, "stats": stats}


def _render(page, payload):
    page.evaluate("data => window.__render(data)", payload)


def _full_payload():
    return _dashboard(overtime_vs_actual=_points(), idle_by_product=_idle(("A", 570), ("B", 268), ("C", 9.5)),
                      actual_distribution=_distribution())


def test_harness_renders_three_new_charts_from_the_contract(harness):
    _render(harness, _full_payload())
    page = harness
    assert page.locator("#overtime-chart .scatter-dot").count() == 40
    assert page.locator("#idle-chart .donut-row").count() == 3
    assert page.locator("#idle-chart .donut-name").all_inner_texts() == ["A", "B", "C"]
    expect(page.locator("#idle-chart .donut-pct").first).to_have_text("67,3%")
    expect(page.locator("#idle-chart .donut-min").first).to_contain_text("570")
    assert page.locator("#idle-chart .donut-min").nth(2).inner_text().startswith("9,5")
    assert page.locator("#distribution-chart .hist-bar").count() == 9
    expect(page.locator("#distribution-summary")).to_have_text(
        "Trên 30 ca: trung bình 73,5%, trung vị 75,0%; 80% số ca nằm trong khoảng 55,0%–92,0%; "
        "31,2% số ca dưới mục tiêu; độ lệch chuẩn 17,4 điểm %.")
    for empty in ("#overtime-empty", "#idle-empty", "#distribution-empty"):
        expect(page.locator(empty)).to_be_hidden()
    assert "Khác" not in page.locator("#idle-chart").inner_text()


def test_harness_overtime_scatter_skips_points_with_null_values(harness):
    nulls = [{"source_row": 1, "overtime": None, "actual": .5, "target": .8, "product": "A"}] + _points(5)
    _render(harness, _dashboard(overtime_vs_actual=nulls))
    assert harness.locator("#overtime-chart .scatter-dot").count() == 5


def test_harness_missing_or_empty_keys_show_empty_states_without_errors(harness):
    cases = ({}, {"overtime_vs_actual": [], "idle_by_product": [], "actual_distribution": {"bins": [], "stats": None}},
             {"overtime_vs_actual": None, "idle_by_product": None, "actual_distribution": None})
    for charts in cases:
        _render(harness, _dashboard(**charts))
        for empty in ("#overtime-empty", "#idle-empty", "#distribution-empty"):
            expect(harness.locator(empty)).to_be_visible()
        assert harness.locator(".scatter-dot, .donut-row, .hist-bar, #idle-chart svg").count() == 0
        assert harness.locator("#distribution-summary").inner_text() == ""
    assert harness.errors == []


def test_harness_zero_idle_total_shows_empty_state_not_a_donut(harness):
    _render(harness, _dashboard(idle_by_product=_idle(("A", 0), ("B", 0))))
    expect(harness.locator("#idle-empty")).to_be_visible()
    assert harness.locator("#idle-chart svg").count() == 0


def test_harness_dashboard_without_data_clears_all_three_charts(harness):
    _render(harness, _full_payload())
    assert harness.locator(".scatter-dot").count() == 40
    _render(harness, {"page": "management", "dashboard": None})
    for empty in ("#overtime-empty", "#idle-empty", "#distribution-empty"):
        expect(harness.locator(empty)).to_be_visible()
    assert harness.locator(".scatter-dot, .donut-row, .hist-bar").count() == 0
    assert harness.locator("#distribution-summary").inner_text() == ""
    assert harness.errors == []


def test_harness_many_products_group_the_tail_into_other(harness):
    pairs = [(f"SP {i}", 100 - i * 10) for i in range(8)]  # 100, 90, ..., 30
    _render(harness, _dashboard(idle_by_product=_idle(*pairs)))
    names = harness.locator("#idle-chart .donut-name").all_inner_texts()
    assert names == ["SP 0", "SP 1", "SP 2", "SP 3", "SP 4", "Khác"]
    other = harness.locator("#idle-chart .donut-row").last
    assert "3 sản phẩm" in (other.get_attribute("aria-label") or "")
    tail, total = 50 + 40 + 30, sum(m for _, m in pairs)  # SP 5..SP 7
    expect(other.locator(".donut-pct")).to_have_text(f"{tail / total * 100:.1f}".replace(".", ",") + "%")


def test_harness_zero_idle_products_are_dropped_before_grouping(harness):
    zeros = [(f"Z{i}", 0) for i in range(6)]
    _render(harness, _dashboard(idle_by_product=_idle(("A", 50), *zeros)))
    assert harness.locator("#idle-chart .donut-name").all_inner_texts() == ["A"]
    expect(harness.locator("#idle-chart .donut-pct")).to_have_text("100,0%")


def test_harness_tooltips_and_keyboard_focus_on_new_charts(harness):
    _render(harness, _full_payload())
    page = harness
    tip = page.locator("#chart-tooltip")
    page.locator("#idle-chart .donut-row").first.focus()
    expect(tip).to_contain_text("570")
    expect(tip).to_contain_text("Số ca")
    page.locator("#distribution-chart .hist-bar").nth(3).focus()
    expect(tip).to_contain_text("Số ca: 12")
    assert page.locator("#overtime-chart [tabindex]").count() == 1
    assert page.locator("#overtime-chart .xy-plot").get_attribute("aria-label")
    page.locator("#overtime-chart .scatter-dot").nth(10).hover(force=True)
    expect(tip).to_contain_text("Tăng ca: 600 phút")
    page.mouse.move(2, 2)
    expect(tip).to_be_hidden()


def test_harness_history_bonus_is_rounded_to_whole_vnd(harness):
    _render(harness, _full_payload())
    cells = harness.locator("#history-body tr td:nth-child(6)").all_inner_texts()
    assert cells == ["12.346", "0", "1.234.567", "—"]


@pytest.mark.parametrize("width, same_row", [(1280, True), (390, False)])
def test_harness_layout_rows_and_no_horizontal_overflow(harness, width, same_row):
    harness.set_viewport_size({"width": width, "height": 900})
    pairs = [(LONG, 570), ("Quần Jeans/Kaki - Mẫu 12", 268)] + [(f"{LONG} {i}", 5) for i in range(4)]
    _render(harness, _dashboard(overtime_vs_actual=_points(300, LONG), idle_by_product=_idle(*pairs),
                                actual_distribution=_distribution()))
    assert harness.evaluate("document.documentElement.scrollWidth - window.innerWidth") <= 0
    overflow = harness.locator(".charts-grid").evaluate(
        "grid => [...grid.querySelectorAll('.chart-card *')].filter(e => e.getBoundingClientRect().right"
        " > grid.getBoundingClientRect().right + 1).length")
    assert overflow == 0
    card = "xpath=ancestor::article"
    assert _rows_share_a_line(harness, f"#bonus-chart >> {card}", f"#overtime-chart >> {card}") is same_row
    assert _rows_share_a_line(harness, f"#comparison-chart >> {card}", f"#idle-chart >> {card}") is same_row
    wide = harness.locator(f"#distribution-chart >> {card}").bounding_box()
    grid = harness.locator(".charts-grid").bounding_box()
    assert abs(wide["width"] - grid["width"]) <= 1
    assert harness.errors == []
