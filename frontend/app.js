let cachedCatalog = null;
let catalogRequestSent = false;
const runtimes = new WeakMap();

const moneyFormatter = new Intl.NumberFormat("vi-VN", { maximumFractionDigits: 0 });
const numberFormatter = new Intl.NumberFormat("vi-VN", { maximumFractionDigits: 6 });
const percentFormatter = new Intl.NumberFormat("vi-VN", { minimumFractionDigits: 1, maximumFractionDigits: 1 });

function element(root, selector) {
  return root.querySelector(selector);
}

function svgNode(name, attributes = {}) {
  const node = document.createElementNS("http://www.w3.org/2000/svg", name);
  for (const [key, value] of Object.entries(attributes)) node.setAttribute(key, String(value));
  return node;
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
  const integer = ["full_shift_workers", "overtime", "bonus", "idle"].includes(field);
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
    has_half_shift_worker: element(root, "#half-shift-input").checked,
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
    } else if (event.key === "Enter" && runtime.selectedOptionIndex >= 0 && options[runtime.selectedOptionIndex]) {
      event.preventDefault();
      options[runtime.selectedOptionIndex].click();
    } else if (event.key === "Escape") {
      closeProductOptions(runtime);
    }
  });
  search.addEventListener("blur", () => setTimeout(() => closeProductOptions(runtime), 120));

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

function renderLaborSummary(runtime, form) {
  const number = parseDraftNumber(form.full_shift_workers, true);
  const half = form.has_half_shift_worker;
  if (number === null || !Number.isInteger(number)) {
    setText(runtime.root, "#labor-summary", form.full_shift_workers ? "Nhập số nguyên người cả ca" : "Nhập số người làm cả ca");
    setText(runtime.root, "#labor-converted", "Quy đổi: — lao động/ca");
    return;
  }
  setText(runtime.root, "#labor-summary", `${formatNumber(number, 0)} người cả ca${half ? " + 1 người nửa ca" : ""}`);
  setText(runtime.root, "#labor-converted", `Quy đổi: ${formatNumber(number + (half ? 0.5 : 0), 1)} lao động/ca`);
}

function renderFieldErrors(runtime, errors) {
  const root = runtime.root;
  const mappings = {
    product: ["#error-product", ".product-field"],
    target: ["#error-target", "#target-input"],
    full_shift_workers: ["#error-full_shift_workers", "#workers-input"],
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

function renderForecast(runtime, data, current) {
  const root = runtime.root;
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
    for (const field of ["target", "full_shift_workers", "overtime", "bonus", "idle"]) syncInput(runtime, field, form[field]);
    const checkbox = element(root, "#half-shift-input");
    if (activeElement(runtime) !== checkbox) checkbox.checked = form.has_half_shift_worker === true;
    runtime.serverForm = form;
    renderLaborSummary(runtime, collectForm(runtime));
    renderFieldErrors(runtime, current && data.prediction_revision === runtime.localRevision ? data.prediction_errors : {});
    renderProductOptions(runtime, element(root, "#product-search").value, false);
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
  block.hidden = true;
  updated.hidden = true;
  message.hidden = true;
  empty.hidden = true;

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
      trendElement.className = `numeric ${trend > 0 ? "is-positive" : "is-negative"}`;
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
    note.textContent = prediction.clipped ? "Dự báo gốc dưới 0%; backend đã giới hạn kết quả hiển thị về 0%." : "";
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
  grid.hidden = true;
  message.hidden = true;
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
    placeholder.textContent = "Đang tìm phương án trong giới hạn backend…";
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
    combined: ["PHƯƠNG ÁN 3", "Phương án kết hợp"],
  };
  const options = Array.isArray(data.recommendations.options) ? data.recommendations.options : [];
  for (const optionId of ["workers", "overtime", "combined"]) {
    const option = options.find((row) => row.id === optionId);
    if (!option) continue;
    grid.appendChild(buildOptionCard(option, titles[optionId], optionId === "combined"));
  }
}

function buildOptionCard(option, titleInfo, featured) {
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
    reason.textContent = option.reason || "Backend không trả phương án khả dụng trong giới hạn hiện tại.";
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
    ["overtime", "Tăng ca", " phút", 0],
    ["bonus", "Tiền thưởng", " VNĐ", 0],
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
      valueText.classList.add(difference > 0 ? "is-increase" : "is-decrease");
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

  const reason = document.createElement("p");
  reason.className = "option-reason";
  reason.textContent = option.achieved ? "Đạt mục tiêu trong phạm vi tìm kiếm của backend." : "Cải thiện nhưng chưa đạt mục tiêu trong phạm vi tìm kiếm.";
  card.appendChild(reason);
  return card;
}

function dataBaseline(option) {
  // The backend's deltas compare against the original shift. The baseline inputs
  // are not repeated on every option, so derive them from inputs minus deltas.
  const baseline = {};
  for (const field of ["workers", "overtime", "bonus"]) {
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
  const validRows = rows.filter((row) => finite(row.target_mean) !== null || finite(row.actual_mean) !== null);
  empty.hidden = validRows.length > 0;
  if (!validRows.length) return;
  const sorted = [...validRows].sort((a, b) => (finite(b.observations) ?? 0) - (finite(a.observations) ?? 0) || String(a.product).localeCompare(String(b.product), "vi"));
  const visible = sorted.slice(0, 10);
  setText(root, "#comparison-caption", validRows.length > 10
    ? `10 sản phẩm có nhiều quan sát nhất trong ${formatNumber(validRows.length, 0)} sản phẩm.`
    : `So sánh năng suất trung bình theo ${formatNumber(validRows.length, 0)} sản phẩm.`);

  const width = 720, height = 292;
  const margin = { top: 12, right: 12, bottom: 57, left: 48 };
  const plotWidth = width - margin.left - margin.right;
  const plotHeight = height - margin.top - margin.bottom;
  const maximumValue = Math.max(1, ...visible.flatMap((row) => [finite(row.target_mean) ?? 0, finite(row.actual_mean) ?? 0]));
  const maximum = Math.ceil(maximumValue * 4) / 4;
  const svg = svgNode("svg", { viewBox: `0 0 ${width} ${height}`, role: "group", "aria-label": "So sánh năng suất trung bình mục tiêu và thực tế" });
  for (let tick = 0; tick <= 4; tick += 1) {
    const value = maximum * tick / 4;
    const y = margin.top + plotHeight * (1 - tick / 4);
    svg.appendChild(svgNode("line", { x1: margin.left, x2: width - margin.right, y1: y, y2: y, class: "grid-line" }));
    const label = svgNode("text", { x: margin.left - 7, y: y + 3, "text-anchor": "end", class: "axis-label" });
    label.textContent = `${formatNumber(value * 100, 0)}%`;
    svg.appendChild(label);
  }
  svg.appendChild(svgNode("line", { x1: margin.left, x2: width - margin.right, y1: margin.top + plotHeight, y2: margin.top + plotHeight, class: "axis-line" }));
  const groupWidth = plotWidth / visible.length;
  const barWidth = Math.min(22, groupWidth * .27);
  visible.forEach((row, index) => {
    const center = margin.left + groupWidth * (index + .5);
    const bars = [["target_mean", "#94a3b8", -barWidth * .56], ["actual_mean", "#0f766e", barWidth * .56]];
    for (const [field, color, offset] of bars) {
      const value = finite(row[field]);
      if (value === null) continue;
      const barHeight = Math.max(0, (value / maximum) * plotHeight);
      const rect = svgNode("rect", {
        x: center + offset - barWidth / 2,
        y: margin.top + plotHeight - barHeight,
        width: barWidth,
        height: barHeight,
        rx: 2,
        fill: color,
        class: "data-bar",
        tabindex: 0,
        "data-chart-index": `product-${index}`,
        "data-chart-series": field,
        "aria-label": `${row.product}, ${field === "target_mean" ? "năng suất mục tiêu trung bình" : "năng suất thực tế trung bình"} ${formatPercent(value)}, ${formatNumber(row.observations, 0)} quan sát`,
      });
      const title = svgNode("title");
      title.textContent = `${row.product} · ${field === "target_mean" ? "Mục tiêu TB" : "Thực tế TB"}: ${formatPercent(value)} · ${formatNumber(row.observations, 0)} quan sát`;
      rect.appendChild(title);
      svg.appendChild(rect);
    }
    const productLabel = String(row.product ?? "");
    const label = svgNode("text", { x: center, y: height - 27, "text-anchor": "middle", class: "axis-label" });
    label.textContent = productLabel.length > 15 ? `${productLabel.slice(0, 14)}…` : productLabel;
    label.setAttribute("aria-label", productLabel);
    svg.appendChild(label);
  });
  runtime.pendingChartData = { productComparison: visible };
  area.appendChild(svg);
}

function renderBonusChart(runtime, rows) {
  const root = runtime.root;
  const area = element(root, "#bonus-chart");
  const empty = element(root, "#bonus-empty");
  area.replaceChildren();
  const points = rows.filter((row) => finite(row.bonus) !== null && finite(row.actual) !== null && finite(row.target) !== null);
  empty.hidden = points.length > 0;
  if (!points.length) return;
  const width = 720, height = 292;
  const margin = { top: 13, right: 13, bottom: 47, left: 48 };
  const plotWidth = width - margin.left - margin.right;
  const plotHeight = height - margin.top - margin.bottom;
  const xMaxValue = Math.max(1, ...points.map((point) => finite(point.bonus)));
  const xMax = niceMaximum(xMaxValue);
  const yMax = niceMaximum(Math.max(1, ...points.flatMap((point) => [finite(point.actual), finite(point.target)])));
  const svg = svgNode("svg", { viewBox: `0 0 ${width} ${height}`, role: "group", "aria-label": "Phân bố tiền thưởng theo năng suất thực tế" });
  for (let tick = 0; tick <= 4; tick += 1) {
    const yValue = yMax * tick / 4;
    const y = margin.top + plotHeight * (1 - tick / 4);
    svg.appendChild(svgNode("line", { x1: margin.left, x2: width - margin.right, y1: y, y2: y, class: "grid-line" }));
    const label = svgNode("text", { x: margin.left - 7, y: y + 3, "text-anchor": "end", class: "axis-label" });
    label.textContent = `${formatNumber(yValue * 100, 0)}%`;
    svg.appendChild(label);
    const xValue = xMax * tick / 4;
    const x = margin.left + plotWidth * tick / 4;
    svg.appendChild(svgNode("line", { x1: x, x2: x, y1: margin.top, y2: margin.top + plotHeight, class: "grid-line" }));
    const xLabel = svgNode("text", { x, y: height - 24, "text-anchor": "middle", class: "axis-label" });
    xLabel.textContent = compactMoney(xValue);
    svg.appendChild(xLabel);
  }
  svg.appendChild(svgNode("line", { x1: margin.left, x2: width - margin.right, y1: margin.top + plotHeight, y2: margin.top + plotHeight, class: "axis-line" }));
  points.forEach((point, index) => {
    const xValue = finite(point.bonus), actual = finite(point.actual), target = finite(point.target);
    if (xValue === null || actual === null || target === null) return;
    const x = margin.left + (xValue / xMax) * plotWidth;
    const y = margin.top + plotHeight * (1 - actual / yMax);
    const circle = svgNode("circle", {
      cx: x, cy: y, r: 3.6,
      fill: actual >= target ? "#167b70" : "#c64b4b",
      class: "data-point",
      tabindex: 0,
      "data-chart-index": `bonus-${index}`,
      "aria-label": `${point.product}, tiền thưởng ${moneyFormatter.format(xValue)} VNĐ, mục tiêu ${formatPercent(target)}, thực tế ${formatPercent(actual)}`,
    });
    const title = svgNode("title");
    title.textContent = `${point.product} · Thưởng ${moneyFormatter.format(xValue)} VNĐ · Mục tiêu ${formatPercent(target)} · Thực tế ${formatPercent(actual)}`;
    circle.appendChild(title);
    svg.appendChild(circle);
  });
  runtime.pendingChartData = { ...(runtime.pendingChartData || {}), bonusPoints: points };
  area.appendChild(svg);
}

function niceMaximum(value) {
  if (!Number.isFinite(value) || value <= 0) return 1;
  const step = value <= 1 ? .25 : value <= 2 ? .5 : Math.pow(10, Math.floor(Math.log10(value))) / 2;
  return Math.max(step, Math.ceil(value / step) * step);
}

function compactMoney(value) {
  if (!Number.isFinite(value)) return "—";
  if (value >= 1_000_000) return `${formatNumber(value / 1_000_000, 1)} tr`;
  if (value >= 10_000) return `${formatNumber(value / 1_000, 0)}k`;
  if (value >= 1_000) return `${formatNumber(value / 1_000, 1)}k`;
  return moneyFormatter.format(value);
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
    const row = data.bonusPoints?.[index];
    if (!row) return;
    heading.textContent = row.product;
    lines.push(`Tiền thưởng: ${formatNumber(row.bonus, 6)} VNĐ`);
    lines.push(`Mục tiêu: ${formatPercent(row.target)}`);
    lines.push(`Thực tế: ${formatPercent(row.actual)}`);
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
    appendCell(tr, row.bonus === null ? "—" : formatNumber(row.bonus, 6), true);
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
