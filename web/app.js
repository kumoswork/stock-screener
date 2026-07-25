/* KUMO$ screener SPA */
const FAV_KEY = "kumo_favorites";
const FILTER_KEY = "kumo_filters";
let autosaveTimer = null;
let suppressAutosave = false;
const GRADE_CLASS = { A: "hot", B: "watch", C: "neutral", D: "warn" };

const state = {
  mode: "filter",
  market: "ALL",
  meta: null,
  selectedCode: null,
  selectedLabel: "",
  rows: [],
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

function saveFavorites(codes) {
  const uniq = [...new Set(codes.map((c) => padCode(c)))];
  localStorage.setItem(FAV_KEY, JSON.stringify(uniq));
  return uniq;
}

function isFav(code) {
  return loadFavorites().includes(padCode(code));
}

function toggleFav(code) {
  const c = padCode(code);
  let favs = loadFavorites();
  if (favs.includes(c)) favs = favs.filter((x) => x !== c);
  else favs.push(c);
  saveFavorites(favs);
  if (state.mode === "favorites") {
    runScreen();
  } else {
    renderList(state.rows);
  }
}

function setStatus(msg) {
  $("status").textContent = msg;
}

function isMobileLayout() {
  return window.matchMedia("(max-width: 980px)").matches;
}

function closeSidebar() {
  if (!isMobileLayout()) return;
  $("sidebar").classList.remove("open");
  $("sidebar-overlay").hidden = true;
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
  return u;
}

function buildFiltersUI(meta) {
  const absRoot = $("abs-filters");
  const listRoot = $("filter-list");
  absRoot.innerHTML = `<div class="cat-title">규모 (이상)</div>`;
  for (const a of meta.abs_specs) {
    const row = document.createElement("div");
    row.className = "filter-row";
    row.dataset.absKey = a.key;
    row.innerHTML = `
      <label><input type="checkbox" data-abs="${escapeHtml(a.key)}" /> ${escapeHtml(a.label)}</label>
      <div class="filter-inputs abs">
        <input type="number" data-abs-lo="${escapeHtml(a.key)}" step="any" />
        <select data-abs-unit="${escapeHtml(a.key)}">
          <option value="억원">억원</option>
          <option value="조원">조원</option>
        </select>
        <span class="unit">이상</span>
      </div>
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
        <label title="${escapeHtml(spec.help_text)}">
          <input type="checkbox" data-f-on="${escapeHtml(spec.key)}" />
          ${escapeHtml(spec.label)}
        </label>
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
    const unitEl = document.querySelector(`[data-abs-unit="${CSS.escape(a.key)}"]`);
    const lo = loEl && loEl.value !== "" ? Number(loEl.value) : null;
    if (lo == null || !Number.isFinite(lo)) continue;
    abs[a.key] = { on: true, lo, unit: unitEl?.value || "억원" };
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
      const unitEl = document.querySelector(`[data-abs-unit="${CSS.escape(a.key)}"]`);
      if (loEl && conf.lo != null) loEl.value = conf.lo;
      if (unitEl && conf.unit) unitEl.value = conf.unit;
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
    const unitEl = document.querySelector(`[data-abs-unit="${CSS.escape(a.key)}"]`);
    absOut[a.key] = {
      on: !!(on && on.checked),
      lo: loEl && loEl.value !== "" ? Number(loEl.value) : 0,
      hi: 0,
      unit: unitEl?.value || "억원",
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

async function saveFilters() {
  const payload = collectSavedFilterState();
  try {
    localStorage.setItem(FILTER_KEY, JSON.stringify(payload));
  } catch (_) {}
  try {
    const res = await api("/api/filters", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    setStatus(`서버에도 저장됨 (${res.where || "ok"})`);
  } catch (err) {
    setStatus(`브라우저는 자동 저장됨 · 서버 저장 실패: ${err.message}`);
  }
}

function resetFilters() {
  suppressAutosave = true;
  try {
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
    if (!state.meta) return;
    for (const spec of state.meta.filter_specs) {
      const { lo, hi } = defaultBounds(spec);
      const minEl = document.querySelector(`[data-f-min="${CSS.escape(spec.key)}"]`);
      const maxEl = document.querySelector(`[data-f-max="${CSS.escape(spec.key)}"]`);
      if (minEl && lo != null) minEl.value = lo;
      if (maxEl && hi != null) maxEl.value = hi;
    }
  } finally {
    suppressAutosave = false;
    scheduleAutosaveFilters();
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
      return `<span class="${cls}">${escapeHtml(labels[c] || c)}</span>`;
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
  state.rows = rows || [];
  const meta = state.meta;
  const cols = meta?.list_columns || [];
  const labels = meta?.list_labels || {};
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
            const tip = t.help
              ? ` data-tip="${escapeHtml(t.help)}" title="${escapeHtml(t.help)}"`
              : "";
            return `<div class="d-tile"${tip}>
              <div class="lab">${escapeHtml(t.label)}</div>
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
  document.querySelectorAll(".tab").forEach((btn) => {
    btn.addEventListener("click", () => setMode(btn.dataset.mode));
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
  $("btn-save").addEventListener("click", () => saveFilters());
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
        setSuggestActive(0);
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
  $("detail-modal").addEventListener("click", (e) => {
    const modal = $("detail-modal");
    const rect = modal.getBoundingClientRect();
    const inside =
      e.clientX >= rect.left &&
      e.clientX <= rect.right &&
      e.clientY >= rect.top &&
      e.clientY <= rect.bottom;
    if (!inside) modal.close();
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
