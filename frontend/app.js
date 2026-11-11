// FONT_FACES do frontend_component.build_script() chèn phía trên; tệp nằm ở static/fonts.
// @font-face không hoạt động trong shadow DOM, nên đăng ký bằng FontFace API ở cấp tài liệu, một lần cho mỗi trang.
if (typeof FONT_FACES !== "undefined" && !window.__garmentFontsLoaded) {
  window.__garmentFontsLoaded = true;
  for (const spec of FONT_FACES) {
    const url = new URL(`app/static/fonts/${spec.file}`, document.baseURI).href;
    const face = new FontFace(spec.family, `url(${url})`, {
      weight: spec.weight,
      unicodeRange: spec.unicode_range,
      display: "swap",
    });
    document.fonts.add(face);
    face.load().catch(() => {});
  }
}

let cachedCatalog = null;
let catalogRequestSent = false;
const runtimes = new WeakMap();

const moneyFormatter = new Intl.NumberFormat("vi-VN", { maximumFractionDigits: 0 });
const numberFormatter = new Intl.NumberFormat("vi-VN", { maximumFractionDigits: 6 });
const percentFormatter = new Intl.NumberFormat("vi-VN", { minimumFractionDigits: 1, maximumFractionDigits: 1 });

function element(root, selector) {
  return root.querySelector(selector);
}

function finite(value) {
  if (value === null || value === undefined || value === "") return null;
  const number = Number(value);
  return Number.isFinite(number) ? number : null;
}

function formatNumber(value, maximumFractionDigits = 2) {
  const number = finite(value);
  if (number === null) return "—";
  return new Intl.NumberFormat("vi-VN", { maximumFractionDigits }).format(number);
}

function formatPercent(value) {
  const number = finite(value);
  return number === null ? "—" : `${percentFormatter.format(number * 100)}%`;
}

function signed(value, maximumFractionDigits = 1) {
  const number = finite(value);
  if (number === null) return "—";
  const sign = number > 0 ? "+" : number < 0 ? "−" : "";
  return `${sign}${formatNumber(Math.abs(number), maximumFractionDigits)}`;
}

function parseDraftNumber(raw, integerField = false) {
  if (raw === null || raw === undefined) return null;
  let value = String(raw).trim().replace(/[\s\u00a0]/g, "");
  if (!value || !/^[+-]?(?:\d+(?:[.,]\d*)?|[.,]\d+)(?:[.,]\d+)*$/.test(value)) return null;
  if (integerField && !value.includes(",") && /^\d{1,3}(?:\.\d{3})+$/.test(value)) {
    value = value.replace(/\./g, "");
  } else if (value.includes(".") && value.includes(",")) {
    const decimal = value.lastIndexOf(".") > value.lastIndexOf(",") ? "." : ",";
    const group = decimal === "." ? "," : ".";
    const split = value.lastIndexOf(decimal);
    const whole = value.slice(0, split).replaceAll(group, "");
    const fraction = value.slice(split + 1);
    if (fraction.includes(group) || !/^[-+]?\d+$/.test(whole) || (fraction && !/^\d+$/.test(fraction))) return null;
    value = fraction ? `${whole}.${fraction}` : whole;
  } else {
    value = value.replace(",", ".");
  }
  const number = Number(value);
  return Number.isFinite(number) ? number : null;
}

function equivalentDraft(left, right, field) {
  if (String(left ?? "") === String(right ?? "")) return true;
  const integer = ["full_shift_workers", "half_shift_workers", "overtime", "bonus", "idle"].includes(field);
  const first = parseDraftNumber(left, integer);
  const second = parseDraftNumber(right, integer);
  return first !== null && second !== null && first === second;
}

function formatBonusDraft(value) {
  const number = parseDraftNumber(value, true);
  if (number === null || !Number.isInteger(number)) return String(value ?? "");
  return moneyFormatter.format(number);
}

function runtimeFor(component, root) {
  let runtime = runtimes.get(root);
  if (runtime) {
    runtime.component = component;
    return runtime;
  }
  runtime = {
    component,
    root,
    clientId: globalThis.crypto?.randomUUID?.() || `${Date.now()}-${Math.random().toString(16).slice(2)}`,
    sequence: 0,
    localRevision: 0,
    serverRevision: 0,
    dashboardPage: 0,
    dashboardLastPage: 0,
    draftDirty: false,
    debounceTimer: null,
    catalog: cachedCatalog,
    catalogReadySent: false,
    requestedRecommendationRevision: null,
    lastRenderedPredictionRevision: null,
    predictionReceivedAt: null,
    serverForm: null,
    selectedItemKey: null,
    selectedOptionIndex: -1,
    pendingChartData: null,
  };
  runtimes.set(root, runtime);
  attachEvents(runtime);
  return runtime;
}

function sendEvent(runtime, kind, detail = {}) {
  runtime.sequence += 1;
  runtime.component.setStateValue("event", {
    client_id: runtime.clientId,
    seq: runtime.sequence,
    kind,
    catalog_ready: Array.isArray(runtime.catalog),
    ...detail,
  });
}

function collectForm(runtime) {
  const root = runtime.root;
  return {
    target: element(root, "#target-input").value,
    full_shift_workers: element(root, "#workers-input").value,
    half_shift_workers: element(root, "#half-shift-input").value,
    overtime: element(root, "#overtime-input").value,
    bonus: element(root, "#bonus-input").value,
    idle: element(root, "#idle-input").value,
  };
}

function clearResultForEdit(runtime) {
  const root = runtime.root;
  element(root, "#prediction-block").hidden = true;
  element(root, "#result-empty").hidden = true;
  element(root, "#result-message").hidden = false;
  element(root, "#result-message").className = "result-message is-pending";
  element(root, "#result-message").textContent = "Thông số đã thay đổi. Đang chờ cập nhật dự báo…";
  element(root, "#updated-at").hidden = true;
  element(root, "#result-bar").hidden = true;
  element(root, "#options-summary").hidden = true;
  element(root, "#option-grid").hidden = true;
  element(root, "#options-message").hidden = true;
  element(root, "#options-placeholder").hidden = false;
  element(root, "#options-placeholder").textContent = "Đang chờ kết quả dự báo hiện tại.";
  runtime.requestedRecommendationRevision = null;
  runtime.predictionReceivedAt = null;
}

function scheduleFormEvent(runtime, immediate = false) {
  if (runtime.debounceTimer) clearTimeout(runtime.debounceTimer);
  const send = () => {
    runtime.debounceTimer = null;
    sendEvent(runtime, "form", {
      revision: runtime.localRevision,
      item_key: runtime.selectedItemKey || "",
      form: collectForm(runtime),
    });
  };
  if (immediate) send();
  else runtime.debounceTimer = setTimeout(send, 300);
}

function markFormChanged(runtime, immediate = false) {
  runtime.localRevision += 1;
  runtime.draftDirty = true;
  clearResultForEdit(runtime);
  scheduleFormEvent(runtime, immediate);
  renderLaborSummary(runtime, collectForm(runtime));
  renderOvertimeTotal(runtime, collectForm(runtime));
}

function attachEvents(runtime) {
  const root = runtime.root;
  for (const input of root.querySelectorAll("[data-form-field]")) {
    const field = input.dataset.formField;
    const eventName = input.type === "checkbox" ? "change" : "input";
    input.addEventListener(eventName, () => markFormChanged(runtime, input.type === "checkbox"));
    if (field === "bonus") {
      input.addEventListener("blur", () => {
        const formatted = formatBonusDraft(input.value);
        if (formatted !== input.value) input.value = formatted;
      });
      input.addEventListener("focus", () => {
        const parsed = parseDraftNumber(input.value, true);
        if (parsed !== null && Number.isInteger(parsed)) input.value = String(parsed);
      });
    }
    // Giá trị mặc định 0: chọn sẵn để số gõ vào thay thế nó thay vì nối đuôi.
    if (["target", "overtime", "bonus", "idle"].includes(field)) {
      input.addEventListener("focus", () => {
        if (input.value === "0") input.select();
      });
      // Chrome/Safari bỏ chọn khi nhả chuột sau khi focus; chặn đúng lần đó.
      input.addEventListener("mouseup", (event) => {
        if (input.value === "0" && input.selectionStart === 0 && input.selectionEnd === 1) event.preventDefault();
      });
    }
  }

  const search = element(root, "#product-search");
  search.addEventListener("focus", () => renderProductOptions(runtime, search.value, true));
  search.addEventListener("input", () => {
    runtime.selectedOptionIndex = -1;
    renderProductOptions(runtime, search.value, true);
  });
  search.addEventListener("keydown", (event) => {
    const options = root.querySelectorAll(".combobox-option");
    if (event.key === "ArrowDown" && options.length) {
      event.preventDefault();
      runtime.selectedOptionIndex = Math.min(runtime.selectedOptionIndex + 1, options.length - 1);
      updateOptionHighlight(runtime, options);
    } else if (event.key === "ArrowUp" && options.length) {
      event.preventDefault();
      runtime.selectedOptionIndex = Math.max(runtime.selectedOptionIndex - 1, 0);
      updateOptionHighlight(runtime, options);
    } else if (event.key === "Enter" && !element(root, "#product-options").hidden) {
      const pick = options[runtime.selectedOptionIndex] ?? (options.length === 1 ? options[0] : null);
      if (pick) {
        event.preventDefault();
        pick.click();
      }
    } else if (event.key === "Escape") {
      closeProductOptions(runtime);
    }
  });
  const clear = element(root, "#product-clear");
  clear.addEventListener("mousedown", (event) => event.preventDefault());
  clear.addEventListener("click", () => clearProduct(runtime));
  search.addEventListener("blur", () => setTimeout(() => {
    closeProductOptions(runtime);
    restoreProductText(runtime);
  }, 120));

  root.querySelectorAll("[data-page]").forEach((button) => {
    button.addEventListener("click", () => navigate(runtime, button.dataset.page));
  });
  root.querySelectorAll("[data-page-link]").forEach((link) => {
    link.addEventListener("click", (event) => {
      event.preventDefault();
      navigate(runtime, link.dataset.pageLink);
    });
  });
  element(root, "#product-filter").addEventListener("change", (event) => {
    sendEvent(runtime, "filter", { product: event.target.value || null });
  });
  element(root, "#page-prev").addEventListener("click", () => {
    const page = runtime.dashboardPage;
    if (page > 0) sendEvent(runtime, "page", { page: page - 1 });
  });
  element(root, "#page-next").addEventListener("click", () => {
    const page = runtime.dashboardPage;
    const last = runtime.dashboardLastPage;
    if (page < last) sendEvent(runtime, "page", { page: page + 1 });
  });
  root.addEventListener("pointermove", (event) => {
    const target = event.target.closest?.("[data-chart-index]");
    if (!target) return;
    showChartTooltip(runtime, target, event.clientX, event.clientY);
  });
  root.addEventListener("pointerout", (event) => {
    if (event.target.closest?.("[data-chart-index]") && !event.relatedTarget?.closest?.("[data-chart-index]")) {
      element(root, "#chart-tooltip").hidden = true;
    }
  });
  root.addEventListener("focusin", (event) => {
    const target = event.target.closest?.("[data-chart-index]");
    if (target) showChartTooltip(runtime, target, 18, 18);
  });
  root.addEventListener("focusout", (event) => {
    if (event.target.closest?.("[data-chart-index]")) element(root, "#chart-tooltip").hidden = true;
  });
}

function navigate(runtime, page) {
  if (page !== "forecast" && page !== "management") return;
  if (runtime.debounceTimer) clearTimeout(runtime.debounceTimer);
  runtime.debounceTimer = null;
  sendEvent(runtime, "navigate", {
    page,
    revision: runtime.localRevision,
    item_key: runtime.selectedItemKey || "",
    form: collectForm(runtime),
  });
}

function setText(root, selector, value) {
  element(root, selector).textContent = value === null || value === undefined ? "" : String(value);
}

function syncInput(runtime, field, incoming) {
  const root = runtime.root;
  const map = {
    target: "#target-input",
    full_shift_workers: "#workers-input",
    half_shift_workers: "#half-shift-input",
    overtime: "#overtime-input",
    bonus: "#bonus-input",
    idle: "#idle-input",
  };
  const input = element(root, map[field]);
  const value = String(incoming ?? "");
  if (runtime.draftDirty && runtime.localRevision > runtime.serverRevision) return;
  if (activeElement(runtime) !== input && !equivalentDraft(input.value, value, field)) input.value = value;
}

function activeElement(runtime) {
  return runtime.root.activeElement || document.activeElement;
}

function renderProductOptions(runtime, query, open) {
  const root = runtime.root;
  const list = element(root, "#product-options");
  const search = element(root, "#product-search");
  const normalized = String(query || "").trim().toLocaleLowerCase("vi-VN");
  const items = (runtime.catalog || []).filter((item) => {
    if (!normalized) return true;
    return `${item.sku} ${item.product}`.toLocaleLowerCase("vi-VN").includes(normalized);
  });
  list.replaceChildren();
  const shown = items.slice(0, 80);
  if (!shown.length) {
    const empty = document.createElement("div");
    empty.className = "combobox-empty";
    empty.textContent = runtime.catalog?.length ? "Không tìm thấy mẫu hàng phù hợp." : "Danh mục chưa sẵn sàng.";
    list.appendChild(empty);
  } else {
    shown.forEach((item, index) => {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "combobox-option";
      button.id = `product-option-${index}`;
      button.setAttribute("role", "option");
      button.setAttribute("aria-selected", item.key === runtime.selectedItemKey ? "true" : "false");
      const sku = document.createElement("strong");
      sku.textContent = item.sku;
      const product = document.createElement("small");
      product.textContent = `${item.product} · SMV ${formatNumber(item.smv, 2)}`;
      button.append(sku, product);
      button.addEventListener("mousedown", (event) => event.preventDefault());
      button.addEventListener("click", () => selectProduct(runtime, item));
      list.appendChild(button);
    });
    if (items.length > shown.length) {
      const note = document.createElement("div");
      note.className = "combobox-empty";
      note.textContent = `Đang hiển thị ${shown.length} trong ${items.length} kết quả; hãy nhập thêm để lọc.`;
      list.appendChild(note);
    }
  }
  list.hidden = !open;
  search.setAttribute("aria-expanded", open ? "true" : "false");
}

function updateOptionHighlight(runtime, options) {
  options.forEach((option, index) => {
    option.setAttribute("aria-selected", index === runtime.selectedOptionIndex ? "true" : "false");
  });
  const current = options[runtime.selectedOptionIndex];
  if (current) element(runtime.root, "#product-search").setAttribute("aria-activedescendant", current.id);
  else element(runtime.root, "#product-search").removeAttribute("aria-activedescendant");
}

// Chữ lạ trong ô tìm kiếm không được lệch với mẫu hàng đang được tính.
function restoreProductText(runtime) {
  const search = element(runtime.root, "#product-search");
  const item = (runtime.catalog || []).find((row) => row.key === runtime.selectedItemKey);
  if (!item && runtime.selectedItemKey) return;
  const expected = item ? `${item.sku} · ${item.product}` : "";
  if (search.value !== expected) search.value = expected;
}

function closeProductOptions(runtime) {
  const list = element(runtime.root, "#product-options");
  list.hidden = true;
  element(runtime.root, "#product-search").setAttribute("aria-expanded", "false");
}

function selectProduct(runtime, item) {
  runtime.selectedItemKey = item.key;
  const search = element(runtime.root, "#product-search");
  search.value = `${item.sku} · ${item.product}`;
  search.removeAttribute("aria-activedescendant");
  setText(runtime.root, "#smv-display", formatNumber(item.smv, 2));
  element(runtime.root, "#smv-help").hidden = !item.has_multiple_smv;
  closeProductOptions(runtime);
  runtime.localRevision += 1;
  runtime.draftDirty = true;
  clearResultForEdit(runtime);
  scheduleFormEvent(runtime, true);
}

function clearProduct(runtime) {
  const root = runtime.root;
  const search = element(root, "#product-search");
  if (runtime.selectedItemKey) {
    runtime.selectedItemKey = "";
    setText(root, "#smv-display", "—");
    element(root, "#smv-help").hidden = true;
    runtime.localRevision += 1;
    runtime.draftDirty = true;
    clearResultForEdit(runtime);
    scheduleFormEvent(runtime, true);
  }
  search.value = "";
  search.removeAttribute("aria-activedescendant");
  runtime.selectedOptionIndex = -1;
  renderProductOptions(runtime, "", true);
  search.focus();
}

function renderLaborSummary(runtime, form) {
  const number = parseDraftNumber(form.full_shift_workers, true);
  // Ô nửa ca để trống nghĩa là 0 người.
  const half = String(form.half_shift_workers ?? "").trim() === "" ? 0 : parseDraftNumber(form.half_shift_workers, true);
  if ((number !== null && number < 0) || (half !== null && half < 0)) {
    setText(runtime.root, "#labor-summary", "Số người không được âm.");
    setText(runtime.root, "#labor-converted", "Quy đổi: — lao động/ca");
    return;
  }
  if (half === null || !Number.isInteger(half)) {
    setText(runtime.root, "#labor-summary", "Nhập số nguyên người nửa ca");
    setText(runtime.root, "#labor-converted", "Quy đổi: — lao động/ca");
    return;
  }
  if (number === null || !Number.isInteger(number)) {
    setText(runtime.root, "#labor-summary", form.full_shift_workers ? "Nhập số nguyên người cả ca" : "Nhập số người làm cả ca");
    setText(runtime.root, "#labor-converted", "Quy đổi: — lao động/ca");
    return;
  }
  setText(runtime.root, "#labor-summary", `${formatNumber(number, 0)} người cả ca${half ? ` + ${formatNumber(half, 0)} người nửa ca` : ""}`);
  setText(runtime.root, "#labor-converted", `Quy đổi: ${formatNumber(number + half * 0.5, 1)} lao động/ca`);
}

// Tăng ca nhập theo từng người; mô hình nhận tổng cả tổ = số người làm cả ca × phút mỗi người.
function renderOvertimeTotal(runtime, form) {
  const workers = parseDraftNumber(form.full_shift_workers, true);
  const minutes = parseDraftNumber(form.overtime);
  if (workers === null || !Number.isInteger(workers) || workers < 0 || minutes === null || minutes < 0) {
    setText(runtime.root, "#overtime-total", "Tổng cả tổ: — phút");
    return;
  }
  setText(runtime.root, "#overtime-total",
    `Tổng cả tổ: ${formatNumber(workers, 0)} × ${formatNumber(minutes, 2)} = ${formatNumber(workers * minutes, 0)} phút`);
}

function renderFieldErrors(runtime, errors) {
  const root = runtime.root;
  const mappings = {
    product: ["#error-product", ".product-field"],
    target: ["#error-target", "#target-input"],
    full_shift_workers: ["#error-full_shift_workers", "#workers-input"],
    half_shift_workers: ["#error-half_shift_workers", "#half-shift-input"],
    overtime: ["#error-overtime", "#overtime-input"],
    bonus: ["#error-bonus", "#bonus-input"],
    idle: ["#error-idle", "#idle-input"],
  };
  for (const [field, [messageSelector, inputSelector]] of Object.entries(mappings)) {
    setText(root, messageSelector, errors?.[field] || "");
    const node = inputSelector.startsWith(".") ? element(root, inputSelector) : element(root, inputSelector).closest(".field-group");
    if (node) node.classList.toggle("has-error", Boolean(errors?.[field]));
  }
}

function renderHeader(runtime, page) {
  const root = runtime.root;
  element(root, "#forecast-page").hidden = page !== "forecast";
  element(root, "#management-page").hidden = page !== "management";
  root.querySelectorAll("[data-page]").forEach((button) => {
    const active = button.dataset.page === page;
    button.classList.toggle("is-active", active);
    if (active) button.setAttribute("aria-current", "page");
    else button.removeAttribute("aria-current");
  });
}

function renderRanges(runtime, data) {
  const limits = data.input_limits || {};
  const labor = data.labor_entry || {};
  const show = (selector, min, max, suffix) => {
    if (finite(min) === null || finite(max) === null) return;
    setText(runtime.root, selector, `Cho phép ${moneyFormatter.format(min)}–${moneyFormatter.format(max)}${suffix}`);
  };
  show("#range-target", finite(limits.target?.min) === null ? null : limits.target.min * 100,
    finite(limits.target?.max) === null ? null : limits.target.max * 100, "%");
  show("#range-workers", labor.full_shift_workers_min, labor.converted_workers_max, " người");
  show("#range-overtime", limits.overtime_per_worker?.min, limits.overtime_per_worker?.max, " phút");
  show("#range-idle", limits.idle?.min, limits.idle?.max, " phút");
  show("#range-bonus", limits.bonus?.min, limits.bonus?.max, " VNĐ");
  const typical = limits.bonus?.typical;
  const typicalLow = finite(typical?.min);
  const typicalHigh = finite(typical?.max);
  const paidShare = finite(typical?.paid_share);
  const hint = element(runtime.root, "#typical-bonus");
  hint.hidden = typicalLow === null || typicalHigh === null || paidShare === null;
  if (!hint.hidden) {
    hint.textContent = `Thường gặp ${moneyFormatter.format(typicalLow)}–${moneyFormatter.format(typicalHigh)} VNĐ khi có thưởng. ${Math.round(paidShare * 100)}% ca có thưởng.`;
  }
}

function renderForecast(runtime, data, current) {
  const root = runtime.root;
  renderRanges(runtime, data);
  const form = data.form || {};
  const serverRevision = finite(data.revision) ?? finite(data.prediction_revision) ?? 0;
  runtime.serverRevision = serverRevision;
  if (runtime.localRevision < serverRevision) runtime.localRevision = serverRevision;
  if (runtime.localRevision <= serverRevision) runtime.draftDirty = false;

  if (runtime.selectedItemKey !== data.selected_item_key) {
    runtime.selectedItemKey = data.selected_item_key || "";
    const selected = data.selected_item;
    const search = element(root, "#product-search");
    if (activeElement(runtime) !== search) {
      search.value = selected ? `${selected.sku} · ${selected.product}` : "";
    }
    setText(root, "#smv-display", selected ? formatNumber(selected.smv, 2) : "—");
    element(root, "#smv-help").hidden = !selected?.has_multiple_smv;
  }

  if (Array.isArray(runtime.catalog)) {
    for (const field of ["target", "full_shift_workers", "half_shift_workers", "overtime", "bonus", "idle"]) syncInput(runtime, field, form[field]);
    runtime.serverForm = form;
    renderLaborSummary(runtime, collectForm(runtime));
    renderOvertimeTotal(runtime, collectForm(runtime));
    renderFieldErrors(runtime, current && data.prediction_revision === runtime.localRevision ? data.prediction_errors : {});
    renderProductOptions(runtime, element(root, "#product-search").value, !element(root, "#product-options").hidden);
  } else {
    renderFieldErrors(runtime, {});
  }

  const isStale = current && finite(data.prediction_revision) !== null && data.prediction_revision < runtime.localRevision;
  const status = isStale ? "pending" : data.prediction_status;
  const prediction = isStale ? null : data.prediction;
  const errors = current && !isStale ? data.prediction_errors || {} : {};
  renderFieldErrors(runtime, errors);
  renderPrediction(runtime, data, status, prediction, isStale);
  renderOptions(runtime, data, status, prediction, isStale);

  if (!current) return;
  if (status === "success" && prediction && !prediction.achieved && data.recommendation_status === "waiting") {
    const revision = finite(data.prediction_revision);
    if (revision !== null && runtime.requestedRecommendationRevision !== revision) {
      runtime.requestedRecommendationRevision = revision;
      setTimeout(() => {
        if (runtime.localRevision === revision && runtime.requestedRecommendationRevision === revision) {
          sendEvent(runtime, "recommend", { revision });
        }
      }, 0);
    }
  }
}

function renderPrediction(runtime, data, status, prediction, isStale) {
  const root = runtime.root;
  const empty = element(root, "#result-empty");
  const block = element(root, "#prediction-block");
  const message = element(root, "#result-message");
  const updated = element(root, "#updated-at");
  const noProduct = status === "no_product" || (!data.selected_item_key && status !== "pending");
  const bar = element(root, "#result-bar");
  block.hidden = true;
  updated.hidden = true;
  message.hidden = true;
  empty.hidden = true;
  bar.hidden = true;

  if (status === "success" && prediction) {
    empty.hidden = true;
    block.hidden = false;
    message.hidden = true;
    if (runtime.lastRenderedPredictionRevision !== data.prediction_revision) {
      runtime.lastRenderedPredictionRevision = data.prediction_revision;
      runtime.predictionReceivedAt = new Date();
    }
    const value = finite(prediction.value);
    const target = finite(prediction.inputs?.target);
    const gap = finite(prediction.difference_to_target);
    setText(root, "#prediction-value", formatPercent(value));
    element(root, "#prediction-value").className = `prediction-value numeric${prediction.achieved ? "" : " is-below"}`;
    bar.hidden = false;
    setText(root, "#bar-value", formatPercent(value));
    const barStatus = element(root, "#bar-status");
    barStatus.className = `status-chip${prediction.achieved ? "" : " is-below"}`;
    barStatus.textContent = prediction.achieved ? "Đạt" : "Chưa đạt";
    const chip = element(root, "#prediction-status");
    chip.className = `status-chip${prediction.achieved ? "" : " is-below"}`;
    chip.textContent = prediction.achieved ? "✓ Đạt mục tiêu" : "! Chưa đạt mục tiêu";
    setText(root, "#prediction-target", formatPercent(target));
    const gapElement = element(root, "#target-gap");
    gapElement.textContent = `${signed(gap === null ? null : gap * 100, 1)} điểm %`;
    gapElement.classList.toggle("is-positive", gap !== null && gap >= 0);
    gapElement.classList.toggle("is-negative", gap !== null && gap < 0);
    const trend = finite(data.prediction_delta);
    const trendElement = element(root, "#prediction-trend");
    if (trend === null) {
      trendElement.textContent = "Chưa có mốc so sánh";
      trendElement.className = "numeric is-neutral";
    } else if (Math.abs(trend) < 1e-12) {
      trendElement.textContent = "→ 0,0 điểm %";
      trendElement.className = "numeric is-neutral";
    } else {
      trendElement.textContent = `${trend > 0 ? "↑" : "↓"} ${signed(trend * 100, 1)} điểm %`;
      trendElement.className = "numeric is-neutral";
    }
    const width = value === null ? 0 : Math.max(0, Math.min(value * 100, 100));
    const targetPosition = target === null ? 0 : Math.max(0, Math.min(target * 100, 100));
    element(root, "#progress-fill").style.width = `${width}%`;
    element(root, "#progress-fill").classList.toggle("is-below", !prediction.achieved);
    element(root, "#target-marker").style.left = `${targetPosition}%`;
    setText(root, "#progress-value", `${formatPercent(value)} / ${formatPercent(target)}`);
    setText(root, "#target-legend", `▲ Mục tiêu ${formatPercent(target)}`);
    element(root, "#progress-track").setAttribute("aria-label", `Năng suất ${formatPercent(value)}, mục tiêu ${formatPercent(target)}`);
    const note = element(root, "#prediction-note");
    note.hidden = !prediction.clipped;
    note.textContent = prediction.clipped ? "Dự báo gốc dưới 0%; kết quả được hiển thị là 0%." : "";
    if (runtime.predictionReceivedAt) {
      updated.hidden = false;
      updated.textContent = `Nhận lúc ${new Intl.DateTimeFormat("vi-VN", { hour: "2-digit", minute: "2-digit" }).format(runtime.predictionReceivedAt)}`;
    }
    return;
  }

  if (noProduct || status === "incomplete" || status === "invalid") {
    empty.hidden = false;
    const title = element(root, "#result-empty strong");
    const description = element(root, "#result-empty p");
    if (noProduct && data.catalog_error) {
      title.textContent = "Danh mục chưa sẵn sàng";
      description.textContent = data.catalog_error;
    } else if (noProduct) {
      title.textContent = "Chưa chọn sản phẩm";
      description.textContent = "Chọn mẫu hàng và nhập đủ thông số để xem dự báo.";
    } else if (status === "incomplete") {
      title.textContent = "Chưa nhập đủ thông số";
      description.textContent = "Hoàn thành các trường bắt buộc; giá trị 0 vẫn được chấp nhận ở phút và tiền thưởng.";
    } else {
      title.textContent = "Cần kiểm tra thông số";
      description.textContent = "Sửa các trường đang báo lỗi để tiếp tục dự báo.";
    }
    return;
  }

  message.hidden = false;
  message.className = "result-message";
  if (status === "pending" || isStale) {
    message.classList.add("is-pending");
    message.textContent = "Đang cập nhật dự báo theo thông số hiện tại…";
  } else if (status === "model_unavailable") {
    message.classList.add("is-error");
    message.textContent = data.prediction_message || "Model hoặc dữ liệu chưa sẵn sàng dự báo.";
  } else if (status === "backend_error") {
    message.classList.add("is-error");
    message.textContent = data.prediction_message || "Dự báo đang gặp lỗi. Vui lòng thử lại sau.";
  } else {
    message.textContent = "Chưa có kết quả dự báo cho bộ thông số hiện tại.";
  }
}

function renderOptions(runtime, data, status, prediction, stale) {
  const root = runtime.root;
  const placeholder = element(root, "#options-placeholder");
  const grid = element(root, "#option-grid");
  const message = element(root, "#options-message");
  const summary = element(root, "#options-summary");
  grid.hidden = true;
  message.hidden = true;
  summary.hidden = true;
  if (status === "success" && prediction?.achieved && !stale) {
    placeholder.hidden = false;
    placeholder.textContent = "Ca đã đạt mục tiêu; không cần tăng thông số.";
    return;
  }
  if (status !== "success" || stale || prediction?.achieved) {
    placeholder.hidden = false;
    placeholder.textContent = "Phương án sẽ xuất hiện khi dự báo hiện tại cho thấy ca chưa đạt mục tiêu.";
    return;
  }
  const recStatus = data.recommendation_status;
  if (recStatus === "waiting" || recStatus === "loading") {
    placeholder.hidden = false;
    placeholder.textContent = "Đang tìm phương án trong giới hạn vận hành…";
    return;
  }
  if (recStatus === "error") {
    placeholder.hidden = true;
    message.hidden = false;
    message.textContent = data.recommendation_message || "Chưa thể tạo phương án lúc này.";
    return;
  }
  if (recStatus !== "success" || !data.recommendations) {
    placeholder.hidden = false;
    placeholder.textContent = "Chưa có phương án cho dự báo này.";
    return;
  }
  placeholder.hidden = true;
  grid.hidden = false;
  grid.replaceChildren();
  const titles = {
    workers: ["PHƯƠNG ÁN 1", "Bổ sung nhân lực"],
    overtime: ["PHƯƠNG ÁN 2", "Điều chỉnh tăng ca"],
    bonus: ["PHƯƠNG ÁN 3", "Tăng tiền thưởng"],
    idle: ["PHƯƠNG ÁN 4", "Giảm thời gian máy dừng"],
    combined: ["PHƯƠNG ÁN 5", "Phương án kết hợp"],
  };
  const options = Array.isArray(data.recommendations.options) ? data.recommendations.options : [];
  for (const optionId of ["workers", "overtime", "bonus", "idle", "combined"]) {
    const option = options.find((row) => row.id === optionId);
    if (!option) continue;
    grid.appendChild(buildOptionCard(runtime, option, titles[optionId], optionId === "combined"));
  }
  const usable = options.filter((row) => row.available && row.status !== "unavailable" && finite(row.prediction?.value) !== null);
  if (usable.length) {
    const reached = usable.filter((row) => row.achieved);
    if (reached.length) {
      summary.textContent = `${reached.length} trong ${usable.length} phương án đạt mục tiêu.`;
    } else {
      const best = usable.reduce((a, b) => (b.prediction.value > a.prediction.value ? b : a));
      const shortfall = finite(best.difference_to_target);
      summary.textContent = `Chưa phương án nào đạt mục tiêu. Cao nhất: ${formatPercent(best.prediction.value)}`
        + (shortfall === null ? "." : ` (thiếu ${formatNumber(Math.abs(shortfall * 100), 1)} điểm %).`);
    }
    summary.hidden = false;
  }
}

// Chép phương án vào biểu mẫu để dự báo lại đúng theo phương án đó.
function applyOption(runtime, option) {
  const root = runtime.root;
  const workers = finite(option.inputs?.workers);
  const overtime = finite(option.inputs?.overtime);
  const bonus = finite(option.inputs?.bonus);
  const idle = finite(option.inputs?.idle);
  if (workers === null || overtime === null || bonus === null || idle === null) return;
  // Giữ số người nửa ca đang nhập nếu phần còn lại là số nguyên người cả ca; không thì tách 0 hoặc 1 người nửa ca.
  const keptHalf = parseDraftNumber(element(root, "#half-shift-input").value || "0", true);
  const keptWhole = keptHalf === null ? null : workers - keptHalf / 2;
  const keep = keptWhole !== null && Number.isInteger(keptHalf) && keptHalf >= 0
    && Number.isInteger(keptWhole) && keptWhole >= 1;
  const whole = keep ? keptWhole : Math.floor(workers);
  element(root, "#workers-input").value = String(whole);
  element(root, "#half-shift-input").value = String(keep ? keptHalf : (workers - whole >= 0.5 - 1e-9 ? 1 : 0));
  // Phương án trả tổng cả tổ; ô nhập là phút mỗi người (làm tròn 2 chữ số vẫn khôi phục đúng tổng).
  const perPerson = whole > 0 ? Math.round((overtime / whole) * 100) / 100 : 0;
  element(root, "#overtime-input").value = String(perPerson).replace(".", ",");
  element(root, "#bonus-input").value = String(Math.round(bonus));
  element(root, "#idle-input").value = String(Math.round(idle));
  markFormChanged(runtime, true);
}

function buildOptionCard(runtime, option, titleInfo, featured) {
  const card = document.createElement("article");
  card.className = `option-card${featured ? " is-featured" : ""}`;
  const top = document.createElement("div");
  top.className = "option-top";
  const title = document.createElement("div");
  const kicker = document.createElement("div");
  kicker.className = "option-kicker";
  kicker.textContent = titleInfo[0];
  const heading = document.createElement("h3");
  heading.textContent = titleInfo[1];
  title.append(kicker, heading);
  const status = document.createElement("span");
  status.className = "option-status";
  if (!option.available || option.status === "unavailable") {
    status.classList.add("is-unavailable");
    status.textContent = "Chưa khả dụng";
  } else if (option.achieved) {
    status.textContent = "✓ Đạt mục tiêu";
  } else {
    status.classList.add("is-below");
    status.textContent = "! Chưa đạt";
  }
  top.append(title, status);
  card.appendChild(top);
  if (!option.available || option.status === "unavailable") {
    const reason = document.createElement("p");
    reason.className = "option-reason";
    reason.textContent = option.reason || "Không có phương án khả dụng trong giới hạn hiện tại.";
    card.appendChild(reason);
    return card;
  }

  const prediction = document.createElement("div");
  prediction.className = `option-prediction${option.achieved ? "" : " is-below"}`;
  const value = document.createElement("strong");
  value.className = "numeric";
  value.textContent = formatPercent(option.prediction?.value);
  const delta = document.createElement("span");
  delta.textContent = `Δ ${signed(finite(option.productivity_delta) * 100, 1)} điểm %`;
  prediction.append(value, delta);
  card.appendChild(prediction);

  const changes = document.createElement("div");
  changes.className = "option-changes";
  const base = dataBaseline(option);
  const changedValues = option.inputs || {};
  const deltas = option.deltas || {};
  const fieldSpecs = [
    ["workers", "Nhân công", " lao động/ca", 1],
    ["overtime", "Tăng ca cả tổ", " phút", 0],
    ["bonus", "Tiền thưởng", " VNĐ", 0],
    ["idle", "Máy dừng", " phút", 0],
  ];
  for (const [field, label, unit, decimals] of fieldSpecs) {
    const row = document.createElement("div");
    row.className = "option-change";
    const name = document.createElement("span");
    name.textContent = label;
    const valueText = document.createElement("strong");
    valueText.className = "numeric";
    const before = finite(base[field]);
    const after = finite(changedValues[field]);
    const difference = finite(deltas[field]);
    if (before === null || after === null || difference === null) {
      valueText.textContent = "—";
      valueText.classList.add("is-neutral");
    } else if (Math.abs(difference) < 1e-10) {
      valueText.textContent = `Giữ ${formatNumber(before, decimals)}${unit}`;
      valueText.classList.add("is-neutral");
    } else {
      const unitSuffix = field === "bonus" ? " VNĐ" : unit;
      valueText.textContent = `${formatNumber(before, decimals)} → ${formatNumber(after, decimals)} (${signed(difference, decimals)}${unitSuffix})`;
      // Máy dừng giảm là cải thiện nên tô xanh.
      valueText.classList.add((difference > 0) !== (field === "idle") ? "is-increase" : "is-decrease");
    }
    row.append(name, valueText);
    changes.appendChild(row);
  }
  card.appendChild(changes);

  const difference = finite(option.difference_to_target);
  const gap = document.createElement("p");
  gap.className = "option-gap";
  if (difference === null) gap.textContent = "Chênh lệch mục tiêu chưa có.";
  else if (difference < 0) gap.textContent = `Còn thiếu ${formatNumber(Math.abs(difference * 100), 1)} điểm % mục tiêu.`;
  else gap.textContent = `Vượt mục tiêu ${formatNumber(difference * 100, 1)} điểm %.`;
  card.appendChild(gap);

  const apply = document.createElement("button");
  apply.type = "button";
  apply.className = "option-apply";
  apply.textContent = "Áp dụng vào biểu mẫu";
  apply.addEventListener("click", () => applyOption(runtime, option));
  card.appendChild(apply);
  return card;
}

function dataBaseline(option) {
  // The backend's deltas compare against the original shift. The baseline inputs
  // are not repeated on every option, so derive them from inputs minus deltas.
  const baseline = {};
  for (const field of ["workers", "overtime", "bonus", "idle"]) {
    const input = finite(option.inputs?.[field]);
    const delta = finite(option.deltas?.[field]);
    baseline[field] = input === null || delta === null ? null : input - delta;
  }
  return baseline;
}

function renderManagement(runtime, data) {
  const root = runtime.root;
  const dashboard = data.dashboard;
  const error = element(root, "#dashboard-error");
  error.hidden = !data.dashboard_error;
  error.textContent = data.dashboard_error || "";
  if (!dashboard) {
    setText(root, "#filter-summary", "Chưa có dữ liệu thống kê.");
    if (!data.dashboard_error) setText(root, "#filter-summary", "Đang tải dữ liệu thống kê…");
    renderDashboardEmpty(runtime);
    return;
  }

  const products = Array.isArray(dashboard.filter?.products) ? dashboard.filter.products : [];
  const filter = element(root, "#product-filter");
  const desiredFilter = data.filter_product || "";
  const currentProducts = Array.from(filter.options).slice(1).map((option) => option.value);
  if (currentProducts.length !== products.length || currentProducts.some((value, index) => value !== products[index])) {
    const all = document.createElement("option");
    all.value = "";
    all.textContent = "Tất cả sản phẩm";
    const options = [all];
    for (const product of products) {
      const option = document.createElement("option");
      option.value = product;
      option.textContent = product;
      options.push(option);
    }
    filter.replaceChildren(...options);
  }
  if (document.activeElement !== filter && filter.value !== desiredFilter) filter.value = desiredFilter;

  const kpis = dashboard.kpis || {};
  const count = finite(kpis.shift_count) ?? 0;
  setText(root, "#kpi-shifts", moneyFormatter.format(count));
  setText(root, "#kpi-shifts-foot", data.filter_product ? "Bản ghi hợp lệ cho sản phẩm đang chọn" : "Bản ghi hợp lệ trong toàn bộ lịch sử");
  setText(root, "#kpi-actual", formatPercent(kpis.actual_mean));
  setText(root, "#kpi-achievement", formatPercent(kpis.target_achievement_rate));
  const achievedCount = kpis.target_achievement_rate === null || count === 0
    ? null : Math.round(kpis.target_achievement_rate * count);
  setText(root, "#kpi-achievement-foot", achievedCount === null ? "Tỷ lệ bản ghi có năng suất từ mục tiêu trở lên" : `${moneyFormatter.format(achievedCount)} / ${moneyFormatter.format(count)} bản ghi đạt mục tiêu`);
  setText(root, "#kpi-idle", kpis.idle_minutes_total === null ? "—" : moneyFormatter.format(kpis.idle_minutes_total));

  const label = data.filter_product || "Toàn bộ sản phẩm";
  setText(root, "#filter-summary", `${label} · ${moneyFormatter.format(count)} ca`);
  const quality = dashboard.quality || {};
  const excluded = finite(quality.excluded_rows) ?? 0;
  const qualityNote = element(root, "#quality-note");
  qualityNote.hidden = excluded <= 0;
  qualityNote.textContent = excluded > 0 ? `${moneyFormatter.format(excluded)} dòng nguồn không hợp lệ đã được loại khỏi thống kê.` : "";

  renderComparisonChart(runtime, dashboard.charts?.product_comparison || []);
  renderBonusChart(runtime, dashboard.charts?.bonus_vs_actual || []);
  renderIdleChart(runtime, dashboard.charts?.idle_by_product);
  renderOvertimeChart(runtime, dashboard.charts?.overtime_vs_actual);
  renderDistributionChart(runtime, dashboard.charts?.actual_distribution);
  renderHistory(runtime, dashboard.history || [], data.dashboard_page || 0);
}

function renderDashboardEmpty(runtime) {
  const root = runtime.root;
  setText(root, "#kpi-shifts", "0");
  setText(root, "#kpi-actual", "—");
  setText(root, "#kpi-achievement", "—");
  setText(root, "#kpi-idle", "—");
  element(root, "#quality-note").hidden = true;
  element(root, "#comparison-chart").replaceChildren();
  element(root, "#bonus-chart").replaceChildren();
  element(root, "#comparison-empty").hidden = false;
  element(root, "#bonus-empty").hidden = false;
  renderIdleChart(runtime, []);
  renderOvertimeChart(runtime, []);
  renderDistributionChart(runtime, null);
  element(root, "#history-body").replaceChildren();
  element(root, "#history-empty").hidden = false;
  setText(root, "#page-summary", "Hiển thị 0 bản ghi");
  setText(root, "#page-current", "1");
  element(root, "#page-prev").disabled = true;
  element(root, "#page-next").disabled = true;
}

function renderComparisonChart(runtime, rows) {
  const root = runtime.root;
  const area = element(root, "#comparison-chart");
  const empty = element(root, "#comparison-empty");
  area.replaceChildren();
  element(root, "#chart-tooltip").hidden = true;
  const validRows = rows.filter((row) => finite(row.target_mean) !== null || finite(row.actual_mean) !== null);
  empty.hidden = validRows.length > 0;
  if (!validRows.length) return;
  const sorted = [...validRows].sort((a, b) => (finite(b.observations) ?? 0) - (finite(a.observations) ?? 0) || String(a.product).localeCompare(String(b.product), "vi"));
  const visible = sorted.slice(0, 10);
  setText(root, "#comparison-caption", validRows.length > 10
    ? `10 sản phẩm có nhiều quan sát nhất trong ${formatNumber(validRows.length, 0)} sản phẩm.`
    : `So sánh năng suất trung bình theo ${formatNumber(validRows.length, 0)} sản phẩm.`);

  const maximum = Math.max(1, ...visible.flatMap((row) => [finite(row.target_mean) ?? 0, finite(row.actual_mean) ?? 0]));
  const list = document.createElement("div");
  list.className = "bar-list";
  visible.forEach((row, index) => {
    const item = document.createElement("div");
    item.className = "bar-row";
    item.tabIndex = 0;
    item.setAttribute("role", "img");
    item.dataset.chartIndex = `product-${index}`;
    item.setAttribute("aria-label", `${row.product}: mục tiêu trung bình ${formatPercent(row.target_mean)}, thực tế trung bình ${formatPercent(row.actual_mean)}, ${formatNumber(row.observations, 0)} quan sát`);
    const name = document.createElement("div");
    name.className = "row-label";
    name.textContent = String(row.product ?? "");
    const pair = document.createElement("div");
    pair.className = "bar-pair";
    for (const [field, kind, label] of [["target_mean", "is-target", "Mục tiêu"], ["actual_mean", "is-actual", "Thực tế"]]) {
      const value = finite(row[field]);
      const track = document.createElement("div");
      track.className = "bar-track";
      const lane = document.createElement("span");
      lane.className = "bar-lane";
      const fill = document.createElement("span");
      fill.className = `bar-fill ${kind}`;
      fill.style.width = `${value === null ? 0 : Math.max(0, Math.min(value / maximum * 100, 100))}%`;
      lane.appendChild(fill);
      const text = document.createElement("span");
      text.className = "bar-value";
      text.textContent = `${label} ${formatPercent(value)}`;
      track.append(lane, text);
      pair.appendChild(track);
    }
    item.append(name, pair);
    list.appendChild(item);
  });
  runtime.pendingChartData = { productComparison: visible };
  area.appendChild(list);
}

// Các mức thưởng (VNĐ/ca) để gom ca thành vài nhóm dễ đọc; nhóm không có ca nào thì bỏ qua.
const BONUS_BANDS = [
  { label: "Không thưởng", min: 0, max: 0 },
  { label: "Dưới 8.000", min: 0, max: 8000 },
  { label: "8.000 – 12.000", min: 8000, max: 12000 },
  { label: "12.000 – 18.000", min: 12000, max: 18000 },
  { label: "Từ 18.000", min: 18000, max: Infinity },
];

function groupByBonus(rows) {
  const valid = rows.filter((row) => finite(row.bonus) !== null && finite(row.actual) !== null && finite(row.target) !== null);
  const groups = BONUS_BANDS.map((band, index) => {
    const inBand = valid.filter((row) => {
      const bonus = finite(row.bonus);
      return index === 0 ? bonus === 0 : bonus > 0 && bonus >= band.min && bonus < band.max;
    });
    const achieved = inBand.filter((row) => finite(row.actual) >= finite(row.target)).length;
    const actualSum = inBand.reduce((sum, row) => sum + finite(row.actual), 0);
    return {
      label: band.label, count: inBand.length, achieved,
      rate: inBand.length ? achieved / inBand.length : null,
      actualMean: inBand.length ? actualSum / inBand.length : null,
    };
  }).filter((group) => group.count > 0);
  const achievedAll = groups.reduce((sum, group) => sum + group.achieved, 0);
  return { groups, overall: valid.length ? achievedAll / valid.length : null };
}

function renderBonusChart(runtime, rows) {
  const root = runtime.root;
  const area = element(root, "#bonus-chart");
  const empty = element(root, "#bonus-empty");
  area.replaceChildren();
  element(root, "#chart-tooltip").hidden = true;
  const { groups, overall } = groupByBonus(rows);
  empty.hidden = groups.length > 0;
  if (!groups.length) return;

  const list = document.createElement("div");
  list.className = "dot-list";
  list.style.setProperty("--avg", `${overall * 100}%`);
  groups.forEach((group, index) => {
    const row = document.createElement("div");
    row.className = "dot-row";
    row.tabIndex = 0;
    row.setAttribute("role", "img");
    row.dataset.chartIndex = `bonus-${index}`;
    row.setAttribute("aria-label", `${group.label} VNĐ mỗi ca: ${formatNumber(group.count, 0)} ca, ${formatPercent(group.rate)} đạt mục tiêu`);
    const name = document.createElement("div");
    name.className = "row-label";
    const title = document.createElement("span");
    title.textContent = group.label;
    const count = document.createElement("small");
    count.textContent = `${formatNumber(group.count, 0)} ca`;
    name.append(title, count);
    const track = document.createElement("div");
    track.className = "dot-track";
    const pct = group.rate * 100;
    const dot = document.createElement("span");
    dot.className = "dot";
    dot.style.left = `${pct}%`;
    const value = document.createElement("span");
    value.className = pct > 78 ? "dot-value is-left" : "dot-value";
    value.style.left = `${pct}%`;
    value.textContent = formatPercent(group.rate);
    track.append(dot, value);
    row.append(name, track);
    list.appendChild(row);
  });
  const axis = document.createElement("div");
  axis.className = "dot-axis";
  axis.setAttribute("aria-hidden", "true");
  const ticks = document.createElement("div");
  ticks.className = "dot-ticks";
  for (const tick of [0, 50, 100]) {
    const label = document.createElement("span");
    label.style.left = `${tick}%`;
    label.textContent = `${tick}%`;
    ticks.appendChild(label);
  }
  axis.appendChild(ticks);
  list.appendChild(axis);
  runtime.pendingChartData = { ...(runtime.pendingChartData || {}), bonusGroups: groups };
  area.appendChild(list);
}

function setChartData(runtime, patch) {
  runtime.pendingChartData = { ...(runtime.pendingChartData || {}), ...patch };
}

function div(className, text) {
  const node = document.createElement("div");
  node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

// Làm tròn trục lên bậc 1/2/5 × 10^k để nhãn trục gọn; trả về các mốc từ 0 tới đỉnh trục.
function axisTicks(max, count, minStep = 0) {
  const raw = Math.max(max, 1e-9) / count;
  const power = 10 ** Math.floor(Math.log10(raw));
  const unit = raw / power;
  const step = Math.max(minStep, (unit <= 1 ? 1 : unit <= 2 ? 2 : unit <= 5 ? 5 : 10) * power);
  const top = Math.max(step, Math.ceil(max / step - 1e-9) * step);
  const values = [];
  for (let value = 0; value <= top + step / 1e6; value += step) values.push(value);
  return { top, values };
}

// Khung trục dùng chung cho biểu đồ phân tán và biểu đồ cột; mọi nhãn là HTML để giữ cỡ chữ ≥ 13 px.
function buildXY({ yTicks, xTicks, yTitle, xTitle, label }) {
  const wrap = div("xy");
  const yAxis = div("xy-y");
  yAxis.setAttribute("aria-hidden", "true");
  const plot = div("xy-plot");
  plot.tabIndex = 0;
  plot.setAttribute("role", "img");
  plot.setAttribute("aria-label", label);
  for (const tick of yTicks) {
    const text = document.createElement("span");
    text.style.bottom = `${tick.pos * 100}%`;
    text.textContent = tick.label;
    yAxis.appendChild(text);
    const line = document.createElement("span");
    line.className = "xy-grid";
    line.style.bottom = `${tick.pos * 100}%`;
    plot.appendChild(line);
  }
  const xAxis = div("xy-x");
  xAxis.setAttribute("aria-hidden", "true");
  for (const tick of xTicks) {
    const text = document.createElement("span");
    text.style.left = `${tick.pos * 100}%`;
    text.className = tick.pos < 0.06 ? "is-first" : tick.pos > 0.94 ? "is-last" : "";
    text.textContent = tick.label;
    xAxis.appendChild(text);
  }
  wrap.append(div("xy-title", yTitle), yAxis, plot, xAxis, div("xy-xtitle", xTitle));
  return { wrap, plot };
}

function renderOvertimeChart(runtime, rows) {
  const root = runtime.root;
  const area = element(root, "#overtime-chart");
  area.replaceChildren();
  element(root, "#chart-tooltip").hidden = true;
  const points = (Array.isArray(rows) ? rows : [])
    .map((row) => ({ ...row, overtime: finite(row?.overtime), actual: finite(row?.actual) }))
    .filter((row) => row.overtime !== null && row.actual !== null);
  element(root, "#overtime-empty").hidden = points.length > 0;
  setChartData(runtime, { overtimePoints: points });
  if (!points.length) {
    return;
  }
  const xAxis = axisTicks(Math.max(...points.map((p) => p.overtime), 60), 4);
  const yTop = Math.max(1, Math.ceil(Math.max(...points.map((p) => p.actual)) * 5) / 5);
  const yValues = Array.from({ length: Math.round(yTop * 5) + 1 }, (_, i) => i / 5);
  const { wrap, plot } = buildXY({
    yTicks: yValues.map((value) => ({ pos: value / yTop, label: `${Math.round(value * 100)}%` })),
    xTicks: xAxis.values.map((value) => ({ pos: value / xAxis.top, label: moneyFormatter.format(value) })),
    yTitle: "Năng suất thực tế",
    xTitle: "Phút tăng ca của cả tổ",
    label: `Biểu đồ phân tán của ${formatNumber(points.length, 0)} ca`,
  });
  const dots = document.createDocumentFragment();
  points.forEach((point, index) => {
    const dot = document.createElement("span");
    dot.className = "scatter-dot";
    dot.dataset.chartIndex = `overtime-${index}`;
    dot.style.left = `${point.overtime / xAxis.top * 100}%`;
    dot.style.bottom = `${Math.max(0, point.actual) / yTop * 100}%`;
    dots.appendChild(dot);
  });
  plot.appendChild(dots);
  area.appendChild(wrap);
}

// Màu phân biệt được cho người mù màu, không dùng tím; tên, phút và % luôn có chữ trong chú giải.
const IDLE_COLORS = ["#0f766e", "#c2570c", "#0072b2", "#8a6d00", "#b0305c", "#475569"];
const IDLE_OTHER_COLOR = "#708090";
const IDLE_MAX_SEGMENTS = 6;

function groupIdle(rows) {
  const valid = (Array.isArray(rows) ? rows : [])
    .map((row) => ({ name: String(row?.product ?? ""), minutes: finite(row?.idle_minutes) ?? 0, shifts: finite(row?.shifts) ?? 0 }))
    .filter((row) => row.minutes > 0)
    .sort((a, b) => b.minutes - a.minutes);
  const total = valid.reduce((sum, row) => sum + row.minutes, 0);
  let kept = valid;
  if (valid.length > IDLE_MAX_SEGMENTS) {
    const rest = valid.slice(IDLE_MAX_SEGMENTS - 1);
    kept = [...valid.slice(0, IDLE_MAX_SEGMENTS - 1), {
      name: "Khác", minutes: rest.reduce((sum, row) => sum + row.minutes, 0),
      shifts: rest.reduce((sum, row) => sum + row.shifts, 0), others: rest.length,
    }];
  }
  const segments = kept.map((row, index) => ({
    ...row, share: row.minutes / total, color: row.others ? IDLE_OTHER_COLOR : IDLE_COLORS[index],
  }));
  return { segments, total };
}

function renderIdleChart(runtime, rows) {
  const root = runtime.root;
  const area = element(root, "#idle-chart");
  area.replaceChildren();
  element(root, "#chart-tooltip").hidden = true;
  const { segments, total } = groupIdle(rows);
  element(root, "#idle-empty").hidden = segments.length > 0;
  setChartData(runtime, { idleSegments: segments });
  if (!segments.length) return;

  const SVG = "http://www.w3.org/2000/svg";
  const svg = document.createElementNS(SVG, "svg");
  svg.setAttribute("viewBox", "0 0 100 100");
  svg.setAttribute("class", "donut-svg");
  svg.setAttribute("aria-hidden", "true");
  let offset = 0;
  const gap = segments.length > 1 ? 0.6 : 0;
  segments.forEach((segment, index) => {
    const arc = document.createElementNS(SVG, "circle");
    const attributes = {
      cx: 50, cy: 50, r: 38, pathLength: 100, fill: "none", stroke: segment.color, "stroke-width": 18,
      transform: "rotate(-90 50 50)", "stroke-dasharray": `${Math.max(segment.share * 100 - gap, 0.1)} 100`,
      "stroke-dashoffset": -offset,
    };
    for (const [name, value] of Object.entries(attributes)) arc.setAttribute(name, String(value));
    arc.dataset.chartIndex = `idle-${index}`;
    svg.appendChild(arc);
    offset += segment.share * 100;
  });
  const center = div("donut-center");
  const totalText = document.createElement("strong");
  totalText.textContent = formatNumber(total, 1);
  const unit = document.createElement("span");
  unit.textContent = "phút dừng";
  center.append(totalText, unit);
  const figure = div("donut-figure");
  figure.append(svg, center);

  const legend = div("donut-legend");
  segments.forEach((segment, index) => {
    const row = div("donut-row");
    row.tabIndex = 0;
    row.setAttribute("role", "img");
    row.dataset.chartIndex = `idle-${index}`;
    const scope = segment.others ? ` (${formatNumber(segment.others, 0)} sản phẩm)` : "";
    row.setAttribute("aria-label", `${segment.name}${scope}: ${formatNumber(segment.minutes, 1)} phút máy dừng, ${formatPercent(segment.share)}`);
    const swatch = document.createElement("i");
    swatch.className = "donut-swatch";
    swatch.style.background = segment.color;
    row.append(swatch, div("donut-name", segment.name),
      div("donut-min", `${formatNumber(segment.minutes, 1)} phút`), div("donut-pct", formatPercent(segment.share)));
    legend.appendChild(row);
  });
  const wrap = div("donut-wrap");
  wrap.append(figure, legend);
  area.appendChild(wrap);
}

function describeDistribution(stats, total) {
  const parts = [];
  const count = finite(stats.count) ?? total;
  const mean = finite(stats.mean);
  const median = finite(stats.median);
  const p10 = finite(stats.p10);
  const p90 = finite(stats.p90);
  const below = finite(stats.below_target_share);
  const std = finite(stats.std);
  const centre = [];
  if (mean !== null) centre.push(`trung bình ${formatPercent(mean)}`);
  if (median !== null) centre.push(`trung vị ${formatPercent(median)}`);
  if (centre.length) parts.push(centre.join(", "));
  if (p10 !== null && p90 !== null) parts.push(`80% số ca nằm trong khoảng ${formatPercent(p10)}–${formatPercent(p90)}`);
  if (below !== null) parts.push(`${formatPercent(below)} số ca dưới mục tiêu`);
  if (std !== null) parts.push(`độ lệch chuẩn ${formatNumber(std * 100, 1)} điểm %`);
  return `Trên ${formatNumber(count, 0)} ca${parts.length ? `: ${parts.join("; ")}` : ""}.`;
}

function renderDistributionChart(runtime, distribution) {
  const root = runtime.root;
  const area = element(root, "#distribution-chart");
  area.replaceChildren();
  element(root, "#chart-tooltip").hidden = true;
  const bins = (Array.isArray(distribution?.bins) ? distribution.bins : [])
    .map((bin) => ({ low: finite(bin?.low), high: finite(bin?.high), count: finite(bin?.count) }))
    .filter((bin) => bin.low !== null && bin.high !== null && bin.count !== null && bin.high > bin.low)
    .sort((a, b) => a.low - b.low);
  const total = bins.reduce((sum, bin) => sum + bin.count, 0);
  const stats = distribution?.stats;
  const empty = !bins.length || total <= 0 || !stats;
  element(root, "#distribution-empty").hidden = !empty;
  if (empty) {
    setChartData(runtime, { distributionBins: [] });
    setText(root, "#distribution-summary", "");
    return;
  }
  bins.forEach((bin) => { bin.share = bin.count / total; });
  setChartData(runtime, { distributionBins: bins });

  const low = bins[0].low;
  const span = bins[bins.length - 1].high - low;
  const position = (value) => Math.max(0, Math.min((value - low) / span, 1));
  const yAxis = axisTicks(Math.max(...bins.map((bin) => bin.count)), 3, 1);
  const step = span > 0.6 ? 20 : span > 0.3 ? 10 : 5;
  const xTicks = [];
  for (let percent = Math.ceil(low * 100 / step - 1e-9) * step; percent <= (low + span) * 100 + 1e-9; percent += step) {
    xTicks.push({ pos: position(percent / 100), label: `${percent}%` });
  }
  const summary = describeDistribution(stats, total);
  const { wrap, plot } = buildXY({
    yTicks: yAxis.values.map((value) => ({ pos: value / yAxis.top, label: formatNumber(value, 0) })),
    xTicks,
    yTitle: "Số ca",
    xTitle: "Năng suất thực tế",
    label: `Biểu đồ cột phân bố năng suất thực tế. ${summary}`,
  });
  const p10 = finite(stats.p10);
  const p90 = finite(stats.p90);
  if (p10 !== null && p90 !== null && p90 > p10) {
    const band = div("hist-band");
    band.style.left = `${position(p10) * 100}%`;
    band.style.width = `${(position(p90) - position(p10)) * 100}%`;
    plot.appendChild(band);
  }
  bins.forEach((bin, index) => {
    const bar = div("hist-bar");
    bar.tabIndex = 0;
    bar.setAttribute("role", "img");
    bar.dataset.chartIndex = `dist-${index}`;
    bar.setAttribute("aria-label", `Năng suất ${formatPercent(bin.low)} đến ${formatPercent(bin.high)}: ${formatNumber(bin.count, 0)} ca, ${formatPercent(bin.share)}`);
    bar.style.left = `${position(bin.low) * 100}%`;
    bar.style.width = `${(position(bin.high) - position(bin.low)) * 100}%`;
    const fill = document.createElement("span");
    fill.style.height = `${bin.count / yAxis.top * 100}%`;
    bar.appendChild(fill);
    plot.appendChild(bar);
  });
  for (const [kind, value] of [["is-median", finite(stats.median)], ["is-mean", finite(stats.mean)]]) {
    if (value === null) continue;
    const line = div(`hist-line ${kind}`);
    line.style.left = `${position(value) * 100}%`;
    plot.appendChild(line);
  }
  area.appendChild(wrap);
  setText(root, "#distribution-summary", summary);
}

function showChartTooltip(runtime, target, x, y) {
  const root = runtime.root;
  const tooltip = element(root, "#chart-tooltip");
  const data = runtime.pendingChartData || {};
  const indexKey = target.dataset.chartIndex || "";
  const content = document.createElement("div");
  const heading = document.createElement("strong");
  const lines = [];
  if (indexKey.startsWith("product-")) {
    const index = Number(indexKey.slice("product-".length));
    const row = data.productComparison?.[index];
    if (!row) return;
    heading.textContent = row.product;
    lines.push(`Mục tiêu TB: ${formatPercent(row.target_mean)}`);
    lines.push(`Thực tế TB: ${formatPercent(row.actual_mean)}`);
    lines.push(`Số quan sát: ${formatNumber(row.observations, 0)}`);
  } else if (indexKey.startsWith("bonus-")) {
    const index = Number(indexKey.slice("bonus-".length));
    const row = data.bonusGroups?.[index];
    if (!row) return;
    heading.textContent = `${row.label} VNĐ mỗi ca`;
    lines.push(`Số ca: ${formatNumber(row.count, 0)}`);
    lines.push(`Đạt mục tiêu: ${formatNumber(row.achieved, 0)} ca (${formatPercent(row.rate)})`);
    lines.push(`Năng suất TB: ${formatPercent(row.actualMean)}`);
  } else if (indexKey.startsWith("overtime-")) {
    const row = data.overtimePoints?.[Number(indexKey.slice("overtime-".length))];
    if (!row) return;
    heading.textContent = String(row.product || "Ca sản xuất");
    lines.push(`Tăng ca: ${formatNumber(row.overtime, 0)} phút (cả tổ)`);
    lines.push(`Thực tế: ${formatPercent(row.actual)}`);
    if (finite(row.target) !== null) lines.push(`Mục tiêu: ${formatPercent(row.target)}`);
  } else if (indexKey.startsWith("idle-")) {
    const row = data.idleSegments?.[Number(indexKey.slice("idle-".length))];
    if (!row) return;
    heading.textContent = row.name;
    lines.push(`Máy dừng: ${formatNumber(row.minutes, 1)} phút (${formatPercent(row.share)})`);
    lines.push(`Số ca: ${formatNumber(row.shifts, 0)}`);
    lines.push(`Trung bình mỗi ca: ${formatNumber(row.shifts ? row.minutes / row.shifts : null, 1)} phút`);
  } else if (indexKey.startsWith("dist-")) {
    const row = data.distributionBins?.[Number(indexKey.slice("dist-".length))];
    if (!row) return;
    heading.textContent = `Năng suất ${formatPercent(row.low)}–${formatPercent(row.high)}`;
    lines.push(`Số ca: ${formatNumber(row.count, 0)} (${formatPercent(row.share)})`);
  } else return;
  content.appendChild(heading);
  for (const line of lines) {
    const span = document.createElement("span");
    span.textContent = line;
    content.appendChild(span);
  }
  tooltip.replaceChildren(content);
  tooltip.hidden = false;
  const left = Math.max(8, Math.min(x + 14, window.innerWidth - 285));
  const top = Math.max(8, Math.min(y + 14, window.innerHeight - 110));
  tooltip.style.left = `${left}px`;
  tooltip.style.top = `${top}px`;
}

function renderHistory(runtime, rows, requestedPage) {
  const root = runtime.root;
  const body = element(root, "#history-body");
  const empty = element(root, "#history-empty");
  const validRows = Array.isArray(rows) ? rows : [];
  const pageSize = 20;
  const lastPage = Math.max(0, Math.ceil(validRows.length / pageSize) - 1);
  const page = Math.max(0, Math.min(Number(requestedPage) || 0, lastPage));
  const start = page * pageSize;
  const visibleRows = validRows.slice(start, start + pageSize);
  body.replaceChildren();
  empty.hidden = validRows.length > 0;
  for (const row of visibleRows) {
    const tr = document.createElement("tr");
    tr.dataset.sourceRow = String(row.source_row ?? "");
    const achieved = finite(row.actual) !== null && finite(row.target) !== null && row.actual >= row.target;
    appendCell(tr, row.sku, false);
    appendCell(tr, row.product, false);
    appendCell(tr, formatPercent(row.target), true);
    appendCell(tr, formatNumber(row.smv, 3), true);
    appendCell(tr, formatNumber(row.overtime, 3), true);
    appendCell(tr, formatNumber(row.bonus, 0), true);
    appendCell(tr, formatNumber(row.idle, 3), true);
    appendCell(tr, formatNumber(row.workers, 8), true);
    const actualCell = appendCell(tr, formatPercent(row.actual), true);
    actualCell.classList.add("actual-cell", achieved ? "is-achieved" : "is-missed");
    body.appendChild(tr);
  }
  const end = Math.min(start + visibleRows.length, validRows.length);
  setText(root, "#page-summary", validRows.length
    ? `Hiển thị ${moneyFormatter.format(start + 1)}–${moneyFormatter.format(end)} trong ${moneyFormatter.format(validRows.length)} ca`
    : "Hiển thị 0 bản ghi");
  setText(root, "#page-current", `${page + 1} / ${lastPage + 1}`);
  element(root, "#page-prev").disabled = page === 0;
  element(root, "#page-next").disabled = page >= lastPage;
  runtime.dashboardPage = page;
  runtime.dashboardLastPage = lastPage;
}

function appendCell(row, value, numeric) {
  const cell = document.createElement("td");
  cell.textContent = value === null || value === undefined ? "—" : String(value);
  if (numeric) cell.classList.add("numeric-cell");
  row.appendChild(cell);
  return cell;
}

export default function garmentProductivityComponent(component) {
  const root = component.parentElement;
  const runtime = runtimeFor(component, root);
  const data = component.data || {};

  if (Array.isArray(data.catalog)) {
    cachedCatalog = data.catalog;
    runtime.catalog = cachedCatalog;
    catalogRequestSent = false;
  } else if (!Array.isArray(runtime.catalog) && Array.isArray(cachedCatalog)) {
    runtime.catalog = cachedCatalog;
  }

  if (!Array.isArray(runtime.catalog) && !data.catalog_error && !catalogRequestSent) {
    catalogRequestSent = true;
    sendEvent(runtime, "catalog_needed");
  } else if (Array.isArray(runtime.catalog) && !runtime.catalogReadySent) {
    runtime.catalogReadySent = true;
    sendEvent(runtime, "catalog_ready");
  }

  renderHeader(runtime, data.page || "forecast");
  const isCurrentForecast = data.page === "forecast";
  renderForecast(runtime, data, isCurrentForecast);
  if (data.page === "management") renderManagement(runtime, data);
  return undefined;
}
