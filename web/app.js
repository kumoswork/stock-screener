/* KUMO$ screener SPA */
const FAV_KEY = "kumo_favorites";
const FILTER_KEY = "kumo_filters";
let autosaveTimer = null;
let suppressAutosave = false;
let sidebarHistoryPushed = false;
let favSyncTimer = null;
const GRADE_CLASS = { A: "hot", B: "watch", C: "neutral", D: "warn" };

const state = {
  mode: "filter",
  market: "ALL",
  meta: null,
  selectedCode: null,
  selectedLabel: "",
  rows: [],
  sortKey: "attractiveness",
  sortDir: "desc",
  resultsByMode: {
    filter: null,
    search: null,
    favorites: null,
  },
};

function $(id) {
  return document.getElementById(id);
}

function escapeHtml(s) {
  return String(s ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function padCode(code) {
  return String(code ?? "").replace(/\D/g, "").padStart(6, "0");
}

function loadFavorites() {
  try {
    const raw = localStorage.getItem(FAV_KEY);
    const arr = raw ? JSON.parse(raw) : [];
    return Array.isArray(arr) ? arr.map((c) => padCode(c)) : [];
  } catch {
    return [];
  }
}

function saveFavoritesLocal(codes) {
  const uniq = [...new Set(codes.map((c) => padCode(c)))];
  try {
    localStorage.setItem(FAV_KEY, JSON.stringify(uniq));
  } catch (_) {}
  return uniq;
}

function isFav(code) {
  return loadFavorites().includes(padCode(code));
}

async function syncFavoritesToServer(codes) {
  const uniq = [...new Set(codes.map((c) => padCode(c)))];
  saveFavoritesLocal(uniq);
  try {
    const res = await api("/api/favorites", {
      method: "POST",
      body: JSON.stringify({ codes: uniq }),
    });
    if (Array.isArray(res.codes)) saveFavoritesLocal(res.codes);
    return res.codes || uniq;
  } catch (_) {
    return uniq;
  }
}

function scheduleFavoritesSync(codes) {
  clearTimeout(favSyncTimer);
  favSyncTimer = setTimeout(() => {
    syncFavoritesToServer(codes);
  }, 200);
}

async function toggleFav(code) {
  const c = padCode(code);
  let favs = loadFavorites();
  if (favs.includes(c)) favs = favs.filter((x) => x !== c);
  else favs.push(c);
  saveFavoritesLocal(favs);
  scheduleFavoritesSync(favs);
  if (state.mode === "favorites") {
    runScreen();
  } else {
    renderList(state.rows);
  }
  // 상세가 열려 있으면 별 상태 갱신
  const modal = $("detail-modal");
  const star = modal?.querySelector?.("[data-detail-fav]");
  if (star && padCode(star.dataset.detailFav) === c) {
    const on = favs.includes(c);
    star.textContent = on ? "★" : "☆";
    star.classList.toggle("on", on);
  }
}

async function loadFavoritesFromServer() {
  try {
    const res = await api("/api/favorites");
    if (Array.isArray(res.codes)) {
      saveFavoritesLocal(res.codes);
      return res.codes.map((c) => padCode(c));
    }
  } catch (_) {}
  return loadFavorites();
}

function setStatus(msg) {
  $("status").textContent = msg;
}

function isMobileLayout() {
  return window.matchMedia("(max-width: 980px)").matches;
}

function closeSidebar(fromPopstate = false) {
  if (!isMobileLayout()) return;
  $("sidebar").classList.remove("open");
  $("sidebar-overlay").hidden = true;
  if (!fromPopstate && sidebarHistoryPushed) {
    sidebarHistoryPushed = false;
    history.back();
  } else {
    sidebarHistoryPushed = false;
  }
}

function openSidebar() {
  if (!isMobileLayout()) {
    $("sidebar").classList.remove("open");
    $("sidebar-overlay").hidden = true;
    document.querySelector(".app").classList.remove("sidebar-collapsed");
    return;
  }
  $("sidebar").classList.add("open");
  $("sidebar-overlay").hidden = false;
  if (!sidebarHistoryPushed) {
    history.pushState({ kumoSidebar: 1 }, "");
    sidebarHistoryPushed = true;
  }
}

function toggleSidebar() {
  if (!isMobileLayout()) return;
  if ($("sidebar").classList.contains("open")) closeSidebar();
  else openSidebar();
}

function restoreSidebar() {
  document.querySelector(".app").classList.remove("sidebar-collapsed");
  $("sidebar").classList.remove("open");
  $("sidebar-overlay").hidden = true;
}

async function api(path, opts) {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json", ...(opts?.headers || {}) },
    ...opts,
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const j = await res.json();
      detail = j.detail || detail;
    } catch (_) {}
    throw new Error(detail);
  }
  return res.json();
}

function unitFor(spec) {
  if (spec.key === "cash_flow_match") return "%";
  return spec.unit_hint || "";
}

function defaultBounds(spec) {
  let lo = null;
  let hi = null;
  if (spec.direction === "min" && spec.excellent_min != null) {
    lo = spec.key === "cash_flow_match" ? spec.excellent_min * 100 : spec.excellent_min;
  } else if ((spec.direction === "max" || spec.direction === "max_change") && spec.excellent_max != null) {
    hi = spec.excellent_max;
  } else if (spec.direction === "range") {
    lo = spec.excellent_min;
    hi = spec.excellent_max;
  }
  return { lo, hi };
}

function suffixFor(spec) {
  const u = unitFor(spec);
  if (spec.direction === "min") return u ? `${u} 이상` : "이상";
  if (spec.direction === "max" || spec.direction === "max_change") return u ? `${u} 이하` : "이하";
  if (spec.direction === "range") return u || "";
  return u;
}

const ABS_HELP = {
  market_cap: "회사 시총(억원). 이상·이하로 구간을 정할 수 있어요.",
  revenue: "한 해 매출 규모. 이 금액 이상만 볼게요.",
  operating_profit: "본업으로 번 이익 규모예요. 이 금액 이상만 볼게요.",
  net_income: "세금 등까지 반영한 최종 이익 규모예요. 이상·이하로 구간을 정할 수 있어요.",
};

function infoBtnHtml(text) {
  const t = (text || "").trim();
  if (!t) return "";
  return `<button type="button" class="info-btn" aria-label="설명" aria-expanded="false" data-info="${escapeHtml(t)}"></button>`;
}

let _infoPop = null;
let _infoBtn = null;
let _infoHideTimer = null;

function tipHostFor(btn) {
  return btn.closest("dialog") || document.body;
}

function hideInfoPop() {
  clearTimeout(_infoHideTimer);
  _infoHideTimer = null;
  if (_infoPop) {
    try {
      if (typeof _infoPop.hidePopover === "function") _infoPop.hidePopover();
    } catch (_) {}
    _infoPop.remove();
    _infoPop = null;
  }
  if (_infoBtn) {
    _infoBtn.classList.remove("open");
    _infoBtn.setAttribute("aria-expanded", "false");
    _infoBtn = null;
  }
}

function placeInfoPop(btn, pop) {
  const r = btn.getBoundingClientRect();
  const pad = 10;
  pop.style.visibility = "hidden";
  const pw = pop.offsetWidth;
  const ph = pop.offsetHeight;
  let top = r.bottom + 8;
  let left = r.left;
  if (top + ph > window.innerHeight - pad) top = Math.max(pad, r.top - ph - 8);
  if (left + pw > window.innerWidth - pad) left = window.innerWidth - pw - pad;
  if (left < pad) left = pad;
  pop.style.top = `${Math.round(top)}px`;
  pop.style.left = `${Math.round(left)}px`;
  pop.style.visibility = "visible";
}

function showInfoPop(btn) {
  const text = (btn.dataset.info || "").trim();
  if (!text) return;
  clearTimeout(_infoHideTimer);
  if (_infoBtn === btn && _infoPop) {
    placeInfoPop(btn, _infoPop);
    return;
  }
  hideInfoPop();
  const pop = document.createElement("div");
  pop.className = "info-pop-float";
  pop.setAttribute("role", "tooltip");
  pop.textContent = text;
  // dialog(showModal)는 top layer라 body에 붙이면 툴팁이 모달 뒤에 가려짐
  tipHostFor(btn).appendChild(pop);
  if (typeof pop.showPopover === "function") {
    try {
      pop.setAttribute("popover", "manual");
      pop.showPopover();
    } catch (_) {}
  }
  _infoPop = pop;
  _infoBtn = btn;
  btn.classList.add("open");
  btn.setAttribute("aria-expanded", "true");
  placeInfoPop(btn, pop);
}

function scheduleHideInfoPop() {
  clearTimeout(_infoHideTimer);
  _infoHideTimer = setTimeout(() => hideInfoPop(), 160);
}

function wireInfoTips() {
  document.addEventListener(
    "click",
    (e) => {
      const btn = e.target.closest(".info-btn");
      if (btn) {
        e.preventDefault();
        e.stopPropagation();
        if (_infoBtn === btn) hideInfoPop();
        else showInfoPop(btn);
        return;
      }
      if (_infoPop && !e.target.closest(".info-pop-float")) hideInfoPop();
    },
    true
  );
  document.addEventListener("pointerover", (e) => {
    if (!window.matchMedia("(hover: hover) and (pointer: fine)").matches) return;
    const btn = e.target.closest(".info-btn");
    if (btn) showInfoPop(btn);
  });
  document.addEventListener("pointerout", (e) => {
    if (!window.matchMedia("(hover: hover) and (pointer: fine)").matches) return;
    const btn = e.target.closest(".info-btn");
    if (!btn) return;
    const to = e.relatedTarget;
    if (to && (btn.contains(to) || _infoPop?.contains(to))) return;
    scheduleHideInfoPop();
  });
  document.addEventListener(
    "pointerover",
    (e) => {
      if (!_infoPop || !e.target.closest(".info-pop-float")) return;
      clearTimeout(_infoHideTimer);
    },
    true
  );
  document.addEventListener(
    "pointerout",
    (e) => {
      if (!_infoPop || !e.target.closest(".info-pop-float")) return;
      const to = e.relatedTarget;
      if (to && (_infoBtn?.contains(to) || _infoPop.contains(to))) return;
      scheduleHideInfoPop();
    },
    true
  );
  window.addEventListener("scroll", () => hideInfoPop(), true);
  window.addEventListener("resize", () => hideInfoPop());
}

function buildFiltersUI(meta) {
  const absRoot = $("abs-filters");
  const listRoot = $("filter-list");
  absRoot.innerHTML = `<div class="cat-title">규모 (이상·이하)</div>`;
  for (const a of meta.abs_specs) {
    const row = document.createElement("div");
    row.className = "filter-row";
    row.dataset.absKey = a.key;
    const unitFixed = a.key === "market_cap";
    const unitHtml = unitFixed
      ? `<span class="unit">억원</span>`
      : `<select data-abs-unit="${escapeHtml(a.key)}">
          <option value="억원">억원</option>
          <option value="조원">조원</option>
        </select>`;
    const minOnly = a.key === "revenue" || a.key === "operating_profit";
    const inputsHtml = minOnly
      ? `<div class="filter-inputs abs">
        <input type="number" data-abs-lo="${escapeHtml(a.key)}" step="any" placeholder="이상" title="이상" />
        ${unitHtml}
        <span class="unit">이상</span>
      </div>`
      : `<div class="filter-inputs abs range">
        <input type="number" data-abs-lo="${escapeHtml(a.key)}" step="any" placeholder="이상" title="이상 (비우면 제한 없음)" />
        <span class="tilde">～</span>
        <input type="number" data-abs-hi="${escapeHtml(a.key)}" step="any" placeholder="이하" title="이하 (비우면 제한 없음)" />
        ${unitHtml}
      </div>`;
    const help = ABS_HELP[a.key] || a.label;
    row.innerHTML = `
      <div class="filter-lab">
        <label>
          <input type="checkbox" data-abs="${escapeHtml(a.key)}" /> ${escapeHtml(a.label)}
        </label>
        ${infoBtnHtml(help)}
      </div>
      ${inputsHtml}
    `;
    absRoot.appendChild(row);
  }

  listRoot.innerHTML = "";
  for (const cat of meta.categories) {
    const title = document.createElement("div");
    title.className = "cat-title";
    title.textContent = cat;
    listRoot.appendChild(title);

    const specs = meta.filter_specs.filter((s) => s.category === cat);
    for (const spec of specs) {
      const { lo, hi } = defaultBounds(spec);
      const row = document.createElement("div");
      const isRange = spec.direction === "range";
      row.className = "filter-row";
      row.dataset.key = spec.key;

      let inputsHtml = "";
      if (isRange) {
        inputsHtml = `
          <div class="filter-inputs range">
            <input type="number" data-f-min="${escapeHtml(spec.key)}" step="any" value="${lo ?? ""}" />
            <span class="tilde">～</span>
            <input type="number" data-f-max="${escapeHtml(spec.key)}" step="any" value="${hi ?? ""}" />
            <span class="unit">${escapeHtml(suffixFor(spec))}</span>
          </div>`;
      } else if (spec.direction === "min") {
        inputsHtml = `
          <div class="filter-inputs">
            <input type="number" data-f-min="${escapeHtml(spec.key)}" step="any" value="${lo ?? ""}" />
            <span class="unit">${escapeHtml(suffixFor(spec))}</span>
          </div>`;
      } else {
        inputsHtml = `
          <div class="filter-inputs">
            <input type="number" data-f-max="${escapeHtml(spec.key)}" step="any" value="${hi ?? ""}" />
            <span class="unit">${escapeHtml(suffixFor(spec))}</span>
          </div>`;
      }

      row.innerHTML = `
        <div class="filter-lab">
          <label>
            <input type="checkbox" data-f-on="${escapeHtml(spec.key)}" />
            ${escapeHtml(spec.label)}
          </label>
          ${infoBtnHtml(spec.help_text)}
        </div>
        ${inputsHtml}
      `;
      listRoot.appendChild(row);
    }
  }

  listRoot.addEventListener("change", (e) => {
    const t = e.target;
    if (t instanceof HTMLInputElement && t.type === "checkbox" && t.dataset.fOn) {
      const row = listRoot.querySelector(`[data-key="${CSS.escape(t.dataset.fOn)}"]`);
      if (row) row.classList.toggle("on", t.checked);
    }
    scheduleAutosaveFilters();
  });
  listRoot.addEventListener("input", () => scheduleAutosaveFilters());

  absRoot.addEventListener("change", (e) => {
    const t = e.target;
    if (t instanceof HTMLInputElement && t.type === "checkbox" && t.dataset.abs) {
      const row = absRoot.querySelector(`[data-abs-key="${CSS.escape(t.dataset.abs)}"]`);
      if (row) row.classList.toggle("on", t.checked);
    }
    scheduleAutosaveFilters();
  });
  absRoot.addEventListener("input", () => scheduleAutosaveFilters());
}

function collectFilters() {
  const filters = {};
  const abs = {};
  if (!state.meta) return { filters, abs };

  for (const spec of state.meta.filter_specs) {
    const on = document.querySelector(`[data-f-on="${CSS.escape(spec.key)}"]`);
    if (!on || !on.checked) continue;
    const minEl = document.querySelector(`[data-f-min="${CSS.escape(spec.key)}"]`);
    const maxEl = document.querySelector(`[data-f-max="${CSS.escape(spec.key)}"]`);
    const parse = (el) => {
      if (!el || el.value === "" || el.value == null) return null;
      const n = Number(el.value);
      return Number.isFinite(n) ? n : null;
    };
    filters[spec.key] = [parse(minEl), parse(maxEl)];
  }

  for (const a of state.meta.abs_specs) {
    const on = document.querySelector(`[data-abs="${CSS.escape(a.key)}"]`);
    if (!on || !on.checked) continue;
    const loEl = document.querySelector(`[data-abs-lo="${CSS.escape(a.key)}"]`);
    const hiEl = document.querySelector(`[data-abs-hi="${CSS.escape(a.key)}"]`);
    const unitEl = document.querySelector(`[data-abs-unit="${CSS.escape(a.key)}"]`);
    const lo = loEl && loEl.value !== "" ? Number(loEl.value) : null;
    const hi = hiEl && hiEl.value !== "" ? Number(hiEl.value) : null;
    const loOk = lo != null && Number.isFinite(lo);
    const hiOk = hi != null && Number.isFinite(hi);
    if (!loOk && !hiOk) continue;
    abs[a.key] = {
      on: true,
      lo: loOk ? lo : null,
      hi: a.key === "revenue" || a.key === "operating_profit" ? null : hiOk ? hi : null,
      unit: a.key === "market_cap" ? "억원" : unitEl?.value || "억원",
    };
  }
  return { filters, abs };
}

function marketToSaved(market) {
  return { ALL: "전체", KOSPI: "코스피", KOSDAQ: "코스닥" }[market] || "전체";
}

function marketFromSaved(label) {
  return { 전체: "ALL", 코스피: "KOSPI", 코스닥: "KOSDAQ" }[label] || "ALL";
}

function applySavedFilters(saved) {
  if (!saved || !state.meta) return;
  suppressAutosave = true;
  try {
    if (saved.market) {
      state.market = marketFromSaved(saved.market);
      $("market-seg").querySelectorAll("button").forEach((b) => {
        b.classList.toggle("active", b.dataset.market === state.market);
      });
    }

    const enabled = new Set(saved.enabled || []);
    const ranges = saved.ranges || {};
    for (const spec of state.meta.filter_specs) {
      const chk = document.querySelector(`[data-f-on="${CSS.escape(spec.key)}"]`);
      const row = document.querySelector(`[data-key="${CSS.escape(spec.key)}"]`);
      if (!chk || !row) continue;
      const on = enabled.has(spec.key);
      chk.checked = on;
      row.classList.toggle("on", on);
      const bounds = ranges[spec.key] || [];
      const minEl = document.querySelector(`[data-f-min="${CSS.escape(spec.key)}"]`);
      const maxEl = document.querySelector(`[data-f-max="${CSS.escape(spec.key)}"]`);
      if (minEl && bounds[0] != null) minEl.value = bounds[0];
      if (maxEl && bounds[1] != null) maxEl.value = bounds[1];
    }

    for (const a of state.meta.abs_specs) {
      const conf = (saved.abs || {})[a.key] || {};
      const chk = document.querySelector(`[data-abs="${CSS.escape(a.key)}"]`);
      const row = document.querySelector(`[data-abs-key="${CSS.escape(a.key)}"]`);
      if (!chk || !row) continue;
      const on = !!conf.on;
      chk.checked = on;
      row.classList.toggle("on", on);
      const loEl = document.querySelector(`[data-abs-lo="${CSS.escape(a.key)}"]`);
      const hiEl = document.querySelector(`[data-abs-hi="${CSS.escape(a.key)}"]`);
      const unitEl = document.querySelector(`[data-abs-unit="${CSS.escape(a.key)}"]`);
      if (loEl && conf.lo != null && conf.lo !== "") loEl.value = conf.lo;
      if (hiEl && conf.hi != null && conf.hi !== "") hiEl.value = conf.hi;
      if (unitEl && conf.unit && a.key !== "market_cap") unitEl.value = conf.unit;
    }
  } finally {
    suppressAutosave = false;
  }
}

function persistFiltersLocal() {
  if (!state.meta) return;
  try {
    localStorage.setItem(FILTER_KEY, JSON.stringify(collectSavedFilterState()));
  } catch (_) {}
}

function scheduleAutosaveFilters() {
  if (suppressAutosave) return;
  clearTimeout(autosaveTimer);
  autosaveTimer = setTimeout(persistFiltersLocal, 250);
}

function collectSavedFilterState() {
  const { filters, abs } = collectFilters();
  const enabled = Object.keys(filters);
  const absOut = {};
  for (const a of state.meta?.abs_specs || []) {
    const on = document.querySelector(`[data-abs="${CSS.escape(a.key)}"]`);
    const loEl = document.querySelector(`[data-abs-lo="${CSS.escape(a.key)}"]`);
    const hiEl = document.querySelector(`[data-abs-hi="${CSS.escape(a.key)}"]`);
    const unitEl = document.querySelector(`[data-abs-unit="${CSS.escape(a.key)}"]`);
    const lo = loEl && loEl.value !== "" ? Number(loEl.value) : null;
    const hi = hiEl && hiEl.value !== "" ? Number(hiEl.value) : null;
    absOut[a.key] = {
      on: !!(on && on.checked),
      lo: lo != null && Number.isFinite(lo) ? lo : null,
      hi: hi != null && Number.isFinite(hi) ? hi : null,
      unit: a.key === "market_cap" ? "억원" : unitEl?.value || "억원",
    };
  }
  return {
    market: marketToSaved(state.market),
    search: state.selectedLabel || "",
    enabled,
    ranges: filters,
    abs: absOut,
  };
}

function resetFilters() {
  suppressAutosave = true;
  try {
    state.market = "ALL";
    $("market-seg").querySelectorAll("button").forEach((b) => {
      b.classList.toggle("active", b.dataset.market === "ALL");
    });

    document.querySelectorAll("#filter-list [data-f-on]").forEach((chk) => {
      chk.checked = false;
      const row = chk.closest(".filter-row");
      if (row) row.classList.remove("on");
    });
    document.querySelectorAll("#abs-filters [data-abs]").forEach((chk) => {
      chk.checked = false;
      const row = chk.closest(".filter-row");
      if (row) row.classList.remove("on");
    });
    document.querySelectorAll("#abs-filters [data-abs-lo]").forEach((el) => {
      el.value = "";
    });
    document.querySelectorAll("#abs-filters [data-abs-hi]").forEach((el) => {
      el.value = "";
    });
    document.querySelectorAll("#abs-filters [data-abs-unit]").forEach((el) => {
      el.value = "억원";
    });
    if (!state.meta) return;
    for (const spec of state.meta.filter_specs) {
      const { lo, hi } = defaultBounds(spec);
      const minEl = document.querySelector(`[data-f-min="${CSS.escape(spec.key)}"]`);
      const maxEl = document.querySelector(`[data-f-max="${CSS.escape(spec.key)}"]`);
      if (minEl) minEl.value = lo != null ? lo : "";
      if (maxEl) maxEl.value = hi != null ? hi : "";
    }
  } finally {
    suppressAutosave = false;
    persistFiltersLocal();
  }
}

function confirmResetFilters() {
  const ok = window.confirm("필터를 모두 초기화할까요?\n체크·수치·시장 설정이 기본값으로 돌아갑니다.");
  if (!ok) return;
  resetFilters();
  state.resultsByMode.filter = null;
  state.rows = [];
  renderList([]);
  setStatus("필터가 초기화되었습니다.");
}

function sortValue(row, key) {
  if (!key || key === "chart") return null;
  if (key === "grade" || key === "attractiveness") {
    const n = Number(row.attractiveness);
    return Number.isFinite(n) ? n : null;
  }
  if (key === "corp_name" || key === "market" || key === "stock_code") {
    return String(row[key] ?? "");
  }
  const num = row[`${key}_num`];
  if (num != null && num !== "" && Number.isFinite(Number(num))) return Number(num);
  const raw = row[key];
  if (raw == null || raw === "-") return null;
  const s = String(raw).replace(/,/g, "").trim();
  if (s.endsWith("조")) {
    const n = parseFloat(s);
    return Number.isFinite(n) ? n * 1e12 : null;
  }
  if (s.endsWith("억")) {
    const n = parseFloat(s);
    return Number.isFinite(n) ? n * 1e8 : null;
  }
  const n = parseFloat(s);
  return Number.isFinite(n) ? n : String(raw);
}

function applySort(rows) {
  const list = rows || [];
  const key = state.sortKey;
  if (!key || !list.length) return list;
  const dir = state.sortDir === "asc" ? 1 : -1;
  return [...list].sort((a, b) => {
    const va = sortValue(a, key);
    const vb = sortValue(b, key);
    if (va == null && vb == null) return 0;
    if (va == null) return 1;
    if (vb == null) return -1;
    if (typeof va === "string" || typeof vb === "string") {
      return String(va).localeCompare(String(vb), "ko") * dir;
    }
    return (va - vb) * dir;
  });
}

function setSort(key) {
  if (!key || key === "chart") return;
  if (state.sortKey === key) {
    state.sortDir = state.sortDir === "asc" ? "desc" : "asc";
  } else {
    state.sortKey = key;
    state.sortDir =
      key === "corp_name" || key === "stock_code" || key === "market" ? "asc" : "desc";
  }
  if (state.meta) renderListHead(state.meta);
  const sorted = applySort(state.rows);
  renderList(sorted);
  const cached = state.resultsByMode[state.mode];
  if (cached) {
    state.resultsByMode[state.mode] = { ...cached, rows: sorted };
  }
}

function gradeBadge(grade, label) {
  const cls = GRADE_CLASS[grade] || "neutral";
  return `<span class="badge ${cls}">${escapeHtml(label || grade || "-")}</span>`;
}

function colVal(row, key) {
  if (key === "corp_name") return row.corp_name;
  if (key === "stock_code") return row.stock_code;
  if (key === "market") return row.market;
  if (key === "attractiveness") return row.attractiveness ?? "-";
  if (key === "grade") return gradeBadge(row.grade, row.grade_label);
  return row[key] ?? "-";
}

function renderListHead(meta) {
  const labels = meta.list_labels || {};
  const cols = meta.list_columns || [];
  const cells = [
    `<span></span>`,
    ...cols.map((c) => {
      const cls = c === "corp_name" ? "c-name" : "c-center";
      if (c === "chart") {
        return `<span class="${cls}">${escapeHtml(labels[c] || c)}</span>`;
      }
      const active = state.sortKey === c;
      const arrow = active ? (state.sortDir === "asc" ? " ↑" : " ↓") : "";
      return `<button type="button" class="sort-head ${cls}${active ? " active" : ""}" data-sort="${escapeHtml(
        c
      )}">${escapeHtml(labels[c] || c)}${arrow}</button>`;
    }),
  ];
  $("list-head").innerHTML = `<div class="head-row">${cells.join("")}</div>`;
}

function renderCell(r, c) {
  if (c === "corp_name") {
    return `<span class="c-name">${escapeHtml(r.corp_name)}</span>`;
  }
  if (c === "grade") {
    return `<span class="c-center">${gradeBadge(r.grade, r.grade_label)}</span>`;
  }
  if (c === "stock_code") {
    return `<span class="c-center code">${escapeHtml(r.stock_code)}</span>`;
  }
  if (c === "attractiveness") {
    return `<span class="c-center">${escapeHtml(String(r.attractiveness ?? "-"))}</span>`;
  }
  if (c === "chart") {
    return `<span class="c-center"><a class="chart-btn" href="${escapeHtml(
      r.tradingview
    )}" target="_blank" rel="noopener" data-chart>차트</a></span>`;
  }
  return `<span class="c-center">${escapeHtml(String(colVal(r, c)))}</span>`;
}

function renderList(rows) {
  state.rows = applySort(rows || []);
  const meta = state.meta;
  const cols = meta?.list_columns || [];
  const body = $("list-body");
  const cards = $("cards-body");

  if (!state.rows.length) {
    body.innerHTML = `<p class="empty">결과가 없습니다.</p>`;
    cards.innerHTML = `<p class="empty">결과가 없습니다.</p>`;
    return;
  }

  body.innerHTML = state.rows
    .map((r) => {
      const on = isFav(r.stock_code);
      const fav = on ? "★" : "☆";
      const cells = cols.map((c) => renderCell(r, c)).join("");
      return `<div class="row" data-code="${escapeHtml(r.stock_code)}" data-detail="${escapeHtml(r.stock_code)}" role="button" tabindex="0">
        <button type="button" class="btn star${on ? " on" : ""}" data-fav="${escapeHtml(r.stock_code)}" title="즐겨찾기">${fav}</button>
        ${cells}
      </div>`;
    })
    .join("");

  cards.innerHTML = state.rows
    .map((r) => {
      const on = isFav(r.stock_code);
      const fav = on ? "★" : "☆";
      return `<div class="mcard" data-code="${escapeHtml(r.stock_code)}" data-detail="${escapeHtml(r.stock_code)}" role="button" tabindex="0">
        <div class="mcard-main">
          <div class="mcard-head">
            <div class="mcard-name-row">
              <p class="mcard-name">${escapeHtml(r.corp_name)}</p>
              <button type="button" class="btn star${on ? " on" : ""}" data-fav="${escapeHtml(r.stock_code)}" aria-label="즐겨찾기">${fav}</button>
            </div>
            <p class="mcard-meta">${escapeHtml(r.stock_code)} · ${escapeHtml(r.market)}</p>
          </div>
          <div class="mcard-side">
            <div class="mcard-score">${escapeHtml(String(r.attractiveness ?? "-"))}<span>점</span></div>
            ${gradeBadge(r.grade, r.grade_label)}
          </div>
        </div>
      </div>`;
    })
    .join("");
}

function badgeClass(badge) {
  if (["매우우수", "우수", "보통", "양호"].includes(badge)) return "tile-good";
  if (["주의", "위험", "약세"].includes(badge)) return "tile-bad";
  return "tile-muted";
}

function badgeLabel(badge) {
  if (badge === "보통") return "양호";
  if (badge === "위험") return "약세";
  if (badge === "해당없음") return "—";
  return badge || "—";
}

async function openDetail(code) {
  const modal = $("detail-modal");
  const box = $("detail-content");
  box.innerHTML = `<p class="muted">불러오는 중…</p>`;
  modal.showModal();
  try {
    const d = await api(`/api/detail/${encodeURIComponent(code)}`);
    const chips = (d.category_chips || [])
      .map(
        (c) => `<div class="d-chip">
          <div class="lab">${escapeHtml(c.label)} (${c.weight_pct}%)</div>
          <div class="val">${c.score == null ? "—" : `${c.score}점`}</div>
        </div>`
      )
      .join("");
    const sections = (d.sections || [])
      .map((sec) => {
        const tiles = (sec.tiles || [])
          .map((t) => {
            const tip = infoBtnHtml(t.help);
            return `<div class="d-tile">
              <div class="lab">${escapeHtml(t.label)}${tip}</div>
              <div class="val">${escapeHtml(t.value)}</div>
              <div class="badge-line ${badgeClass(t.badge)}">${escapeHtml(badgeLabel(t.badge))}</div>
            </div>`;
          })
          .join("");
        const showScore = sec.category_key != null;
        const scoreText = sec.score != null ? `${sec.score}점` : "—";
        const head = `<div class="d-cat-head">
            <div class="d-cat-title">${escapeHtml(sec.title)}</div>
            <div class="d-cat-line"></div>
            ${showScore ? `<div class="d-cat-score">${escapeHtml(scoreText)}</div><div class="d-cat-line-end"></div>` : ""}
          </div>`;
        return `<section class="d-section">
          ${head}
          <div class="d-tiles">${tiles || `<p class="muted">데이터 없음</p>`}</div>
        </section>`;
      })
      .join("");
    box.innerHTML = `
      <div class="d-title">
        <span class="name">${escapeHtml(d.corp_name)}</span>
        <button type="button" class="btn star${isFav(d.stock_code) ? " on" : ""}" data-detail-fav="${escapeHtml(
          d.stock_code
        )}" title="즐겨찾기">${isFav(d.stock_code) ? "★" : "☆"}</button>
        <span class="code">${escapeHtml(d.stock_code)}</span>
        ${gradeBadge(d.grade, d.grade_label)}
        <a class="d-tv-btn" href="${escapeHtml(d.tradingview)}" target="_blank" rel="noopener">TradingView</a>
      </div>
      <div class="d-score-block">
        <div class="d-score-label">통합 점수 (카테고리 가중)</div>
        <div class="d-score">${d.attractiveness ?? "—"}점</div>
      </div>
      <div class="d-chips">${chips}</div>
      ${sections}
    `;
  } catch (err) {
    box.innerHTML = `<p class="empty">${escapeHtml(err.message)}</p>`;
  }
}

async function runScreen(extra = {}) {
  const mode = state.mode;
  const reqId = (state.screenReqId = (state.screenReqId || 0) + 1);
  setStatus("조회 중…");
  try {
    const body = {
      mode,
      market: state.market,
      limit: 200,
      ...extra,
    };
    if (mode === "filter") {
      const { filters, abs } = collectFilters();
      body.filters = filters;
      body.abs = abs;
      persistFiltersLocal();
    } else if (mode === "search") {
      body.code = state.selectedCode;
    } else if (mode === "favorites") {
      body.codes = loadFavorites();
    }
    const data = await api("/api/screen", {
      method: "POST",
      body: JSON.stringify(body),
    });
    const rows = data.rows || [];
    let msg = "";
    if (mode === "favorites") msg = `즐겨찾기 ${data.count}개`;
    else if (mode === "search") msg = data.count ? "1개 조회" : "결과 없음";
    else {
      msg = `조건 충족 ${data.count}개`;
      if (data.count > data.shown) msg += ` · 상위 ${data.shown}개 표시`;
    }
    if (data.warning) msg += ` · ${data.warning}`;
    state.resultsByMode[mode] = {
      rows: rows.slice(),
      status: msg,
    };
    // 탭을 이미 바꿨으면 DOM/캐시는 건드리지 않음 (다른 모드 결과로 덮어쓰지 않음)
    if (reqId !== state.screenReqId || state.mode !== mode) return;
    renderList(rows);
    setStatus(msg);
  } catch (err) {
    state.resultsByMode[mode] = { rows: [], status: err.message };
    if (reqId !== state.screenReqId || state.mode !== mode) return;
    setStatus(err.message);
    renderList([]);
  }
  if (isMobileLayout()) closeSidebar();
}

function setMode(mode) {
  if (state.mode === mode) {
    // 같은 탭 재클릭: 캐시가 있으면 유지
    if (mode === "favorites") runScreen();
    return;
  }
  // 진행 중 조회 결과를 무시하도록 무효화
  state.screenReqId = (state.screenReqId || 0) + 1;
  state.mode = mode;
  document.querySelectorAll(".tab").forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.mode === mode);
  });
  $("panel-search").hidden = mode !== "search";
  $("panel-filter").hidden = mode !== "filter";
  $("panel-favorites").hidden = mode !== "favorites";
  $("filter-actions").hidden = mode !== "filter";

  if (mode === "favorites") {
    runScreen();
    return;
  }

  const cached = state.resultsByMode[mode];
  if (cached) {
    renderList(cached.rows);
    setStatus(cached.status);
  } else {
    state.rows = [];
    renderList([]);
    setStatus("준비됨");
  }
}

function wireEvents() {
  wireInfoTips();
  document.querySelectorAll(".tab").forEach((btn) => {
    btn.addEventListener("click", () => setMode(btn.dataset.mode));
  });

  $("list-head").addEventListener("click", (e) => {
    const btn = e.target.closest("button[data-sort]");
    if (!btn) return;
    setSort(btn.dataset.sort);
  });

  $("market-seg").addEventListener("click", (e) => {
    const btn = e.target.closest("button[data-market]");
    if (!btn) return;
    state.market = btn.dataset.market;
    $("market-seg").querySelectorAll("button").forEach((b) => {
      b.classList.toggle("active", b === btn);
    });
    scheduleAutosaveFilters();
  });

  $("btn-screen").addEventListener("click", () => runScreen());
  $("btn-reset").addEventListener("click", () => confirmResetFilters());
  $("btn-search").addEventListener("click", () => {
    if (!state.selectedCode) {
      setStatus("종목을 선택하세요.");
      return;
    }
    runScreen();
  });
  let suggestTimer = null;
  let suggestIndex = -1;

  function suggestItems() {
    return [...$("stock-suggest").querySelectorAll("li[data-code]")];
  }

  function setSuggestActive(idx) {
    const items = suggestItems();
    if (!items.length) {
      suggestIndex = -1;
      return;
    }
    suggestIndex = ((idx % items.length) + items.length) % items.length;
    items.forEach((li, i) => li.classList.toggle("active", i === suggestIndex));
    items[suggestIndex].scrollIntoView({ block: "nearest" });
  }

  function pickSuggest(li) {
    if (!li) return;
    state.selectedCode = li.dataset.code;
    state.selectedLabel = li.dataset.label;
    $("stock-picked").textContent = `선택: ${state.selectedLabel}`;
    $("stock-q").value = state.selectedLabel;
    $("stock-suggest").hidden = true;
    $("stock-suggest").innerHTML = "";
    suggestIndex = -1;
    runScreen();
  }

  $("stock-q").addEventListener("input", () => {
    clearTimeout(suggestTimer);
    suggestIndex = -1;
    state.selectedCode = null;
    state.selectedLabel = "";
    $("stock-picked").textContent = "";
    const q = $("stock-q").value.trim();
    suggestTimer = setTimeout(async () => {
      const box = $("stock-suggest");
      if (!q) {
        box.hidden = true;
        box.innerHTML = "";
        return;
      }
      try {
        const data = await api(`/api/stocks?q=${encodeURIComponent(q)}&limit=20`);
        const items = data.items || [];
        if (!items.length) {
          box.hidden = true;
          box.innerHTML = "";
          return;
        }
        box.hidden = false;
        box.innerHTML = items
          .map(
            (it) =>
              `<li data-code="${escapeHtml(it.stock_code)}" data-label="${escapeHtml(
                it.label
              )}">${escapeHtml(it.label)} · ${escapeHtml(it.market)}</li>`
          )
          .join("");
        // 키보드/마우스로 고르기 전엔 하이라이트 없음
      } catch {
        box.hidden = true;
      }
    }, 180);
  });

  $("stock-q").addEventListener("keydown", (e) => {
    const box = $("stock-suggest");
    const open = !box.hidden && suggestItems().length > 0;
    if (e.key === "ArrowDown") {
      if (!open) return;
      e.preventDefault();
      setSuggestActive(suggestIndex < 0 ? 0 : suggestIndex + 1);
    } else if (e.key === "ArrowUp") {
      if (!open) return;
      e.preventDefault();
      setSuggestActive(suggestIndex < 0 ? 0 : suggestIndex - 1);
    } else if (e.key === "Enter") {
      if (!open) return;
      e.preventDefault();
      const items = suggestItems();
      const li = items[suggestIndex] || items[0];
      pickSuggest(li);
    } else if (e.key === "Escape") {
      box.hidden = true;
      suggestIndex = -1;
    }
  });

  $("stock-suggest").addEventListener("click", (e) => {
    const li = e.target.closest("li[data-code]");
    if (!li) return;
    pickSuggest(li);
  });

  $("stock-suggest").addEventListener("mousemove", (e) => {
    const li = e.target.closest("li[data-code]");
    if (!li) return;
    const items = suggestItems();
    const idx = items.indexOf(li);
    if (idx >= 0 && idx !== suggestIndex) setSuggestActive(idx);
  });

  document.addEventListener("click", (e) => {
    const fav = e.target.closest("[data-fav]");
    if (fav) {
      e.preventDefault();
      e.stopPropagation();
      toggleFav(fav.dataset.fav);
      return;
    }
    const detailFav = e.target.closest("[data-detail-fav]");
    if (detailFav) {
      e.preventDefault();
      e.stopPropagation();
      toggleFav(detailFav.dataset.detailFav);
      return;
    }
    if (e.target.closest("[data-chart]")) {
      e.stopPropagation();
      return;
    }
    const row = e.target.closest("[data-detail]");
    if (row) {
      openDetail(row.dataset.detail);
    }
  });

  document.addEventListener("keydown", (e) => {
    if (e.key !== "Enter" && e.key !== " ") return;
    const row = e.target.closest(".row[data-detail], .mcard[data-detail]");
    if (!row || e.target.closest("[data-fav], [data-chart]")) return;
    e.preventDefault();
    openDetail(row.dataset.detail);
  });

  $("menu-btn").addEventListener("click", toggleSidebar);
  $("sidebar-close").addEventListener("click", closeSidebar);
  $("sidebar-overlay").addEventListener("click", closeSidebar);
  $("detail-modal").addEventListener("close", () => hideInfoPop());
  $("detail-modal").addEventListener("click", (e) => {
    if (e.target.closest(".info-btn, .info-pop-float")) return;
    const modal = $("detail-modal");
    const rect = modal.getBoundingClientRect();
    const inside =
      e.clientX >= rect.left &&
      e.clientX <= rect.right &&
      e.clientY >= rect.top &&
      e.clientY <= rect.bottom;
    if (!inside) modal.close();
  });
  window.addEventListener("popstate", () => {
    if (isMobileLayout() && $("sidebar").classList.contains("open")) {
      closeSidebar(true);
    }
  });
  window.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && isMobileLayout()) {
      const modal = $("detail-modal");
      if (modal.open) return;
      closeSidebar();
    }
  });
}

async function init() {
  wireEvents();
  restoreSidebar();
  setStatus("메타 로딩…");
  try {
    const localFavs = loadFavorites();
    const serverFavs = await loadFavoritesFromServer();
    if ((!serverFavs || !serverFavs.length) && localFavs.length) {
      await syncFavoritesToServer(localFavs);
    }
    const meta = await api("/api/meta");
    state.meta = meta;
    buildFiltersUI(meta);
    renderListHead(meta);
    let saved = null;
    try {
      const raw = localStorage.getItem(FILTER_KEY);
      if (raw) saved = JSON.parse(raw);
    } catch (_) {}
    if (!saved || !Object.keys(saved).length) {
      saved = meta.saved_filters;
    }
    applySavedFilters(saved);
    $("meta-cap").textContent = [
      meta.financials_caption,
      meta.price_caption,
      `재무 ${meta.financials_rows} · 주가캐시 ${meta.price_rows}`,
    ]
      .filter(Boolean)
      .join(" · ");
    setStatus("준비됨 — 필터를 고른 뒤 스크리닝하세요.");
  } catch (err) {
    setStatus(`초기화 실패: ${err.message}`);
  }
}

init();
