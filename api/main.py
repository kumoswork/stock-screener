"""FastAPI backend for KUMO stock screener web UI."""

from __future__ import annotations

import math
import sys
from pathlib import Path
from typing import Any

import pandas as pd
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
WEB = ROOT / "web"
ASSETS = ROOT / "assets"
sys.path.insert(0, str(SRC))

from criteria import (  # noqa: E402
    ABS_SPECS,
    CATEGORY_LABELS,
    CATEGORY_WEIGHTS,
    FILTER_SPECS,
    MARGIN_BADGE_THRESHOLDS,
    PRICE_ABS_KEYS,
    REVENUE_GROWTH_KEY,
    categories_order,
    score_row,
    specs_in_category,
)
from filter_store import load_saved_filters, persist_filters  # noqa: E402
from price import load_price_metrics, price_cache_caption  # noqa: E402
from screener import (  # noqa: E402
    apply_range_filters,
    attach_scores,
    format_cell,
    format_metric_value,
    merge_financial_and_price,
    split_filters,
)
from snapshot import financials_basis_caption, load_financials  # noqa: E402
from tv import tradingview_chart_url  # noqa: E402
from ui_theme import GRADE_UI  # noqa: E402

DETAIL_SECTION_ORDER: list[tuple[str, str | None]] = [
    ("손익 요약", None),
    ("주가 현위치", "주가 현위치"),
    ("B경제", "B경제"),
    ("안전성", "안전성 check!"),
    ("수익/성장성", "수익/성장성 check!"),
    ("효율성", "효율성 check!"),
    ("매출증가율−부채증가율", "check!!"),
]

DETAIL_HELP: dict[str, str] = {
    "매출액": "당기 매출액",
    "영업이익": "당기 영업이익",
    "당기순이익": "당기 당기순이익",
    "현재가": "최근 종가 (주가 캐시)",
    "시가총액": "상장주식수 × 현재가 (KRX, 주가 캐시)",
    "52주위치(%)": "52주 저가~고가 구간에서 현재가 위치 (0%=저가, 100%=고가)",
    "52주 평균가": "최근 52주 종가 평균",
    "52주 저가/고가": "최근 52주 최저가 / 최고가",
    "판관비율(판관비÷매출)": "판관비 ÷ 매출액 (절대 비율)",
}


def _excellent_hint(spec) -> str:
    if spec.key == REVENUE_GROWTH_KEY:
        return "0%↑양호 · 40%↑우수 · 80%↑매우우수"
    if spec.key in MARGIN_BADGE_THRESHOLDS:
        good, excellent, very = MARGIN_BADGE_THRESHOLDS[spec.key]
        return f"{good:g}%↑양호 · {excellent:g}%↑우수 · {very:g}%↑매우우수"
    if spec.key == "pct_from_avg_52w":
        return "-50%↓ 매우우수 · -20%↓ 우수 · 구간 필터"
    if spec.key == "debt_ratio":
        return "50~200% 우수 · 50%↓ 중립 · 200%↑ 위험"
    if spec.key == "sga_ratio_change":
        return "0%p↓ 우수 · +10%p↑ 위험"
    if spec.key == "cash_flow_match":
        return "1배(100%)↑ 우수 · 적자는 점수 제외"
    if spec.direction == "min" and spec.excellent_min is not None:
        v = spec.excellent_min
        return f"{v:g}{spec.unit_hint} 이상 우수"
    if spec.direction in ("max", "max_change") and spec.excellent_max is not None:
        return f"{spec.excellent_max:g}{spec.unit_hint} 이하 우수"
    if spec.direction == "range" and spec.excellent_min is not None and spec.excellent_max is not None:
        return f"{spec.excellent_min:g}~{spec.excellent_max:g}{spec.unit_hint} 우수"
    return ""


for _spec in FILTER_SPECS:
    hint = _excellent_hint(_spec)
    base = (_spec.help_text or "").strip()
    if not hint:
        DETAIL_HELP[_spec.label] = base
    elif hint in base or base.endswith(hint):
        DETAIL_HELP[_spec.label] = base
    else:
        # help에 이미 '우수' 구간이 있으면 중복 덧붙이지 않음
        if "우수" in base and (
            "↑" in base or "~" in base or "이상" in base or "이하" in base
        ):
            DETAIL_HELP[_spec.label] = base
        else:
            DETAIL_HELP[_spec.label] = f"{base} · {hint}"


def _tile(label: str, value: str, badge: str = "해당없음") -> dict[str, str]:
    return {
        "label": label,
        "value": value,
        "badge": badge,
        "help": DETAIL_HELP.get(label, ""),
    }

app = FastAPI(title="KUMO Stock Screener", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

_financials: pd.DataFrame | None = None
_prices: pd.DataFrame | None = None


def _clean_num(v: Any) -> Any:
    if v is None:
        return None
    try:
        if pd.isna(v):
            return None
    except Exception:
        pass
    if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
        return None
    if hasattr(v, "item"):
        try:
            return v.item()
        except Exception:
            pass
    return v


def get_financials() -> pd.DataFrame:
    global _financials
    if _financials is None:
        _financials = load_financials()
        if not _financials.empty and "stock_code" in _financials.columns:
            _financials = _financials.copy()
            _financials["stock_code"] = _financials["stock_code"].astype(str).str.zfill(6)
    return _financials


def get_prices() -> pd.DataFrame:
    global _prices
    if _prices is None:
        _prices = load_price_metrics()
        if not _prices.empty and "stock_code" in _prices.columns:
            _prices = _prices.copy()
            _prices["stock_code"] = _prices["stock_code"].astype(str).str.zfill(6)
    return _prices


def reload_data() -> None:
    global _financials, _prices
    _financials = None
    _prices = None
    get_financials()
    get_prices()


class ScreenBody(BaseModel):
    mode: str = "filter"  # filter | search | favorites
    market: str = "ALL"
    code: str | None = None
    codes: list[str] = Field(default_factory=list)
    filters: dict[str, list[float | None]] = Field(default_factory=dict)
    abs: dict[str, dict[str, Any]] = Field(default_factory=dict)
    limit: int = 200


def _apply_abs(df: pd.DataFrame, abs_filters: dict[str, dict[str, Any]]) -> pd.DataFrame:
    out = df
    for key, conf in (abs_filters or {}).items():
        if not conf.get("on"):
            continue
        if key not in out.columns:
            continue
        lo = conf.get("lo")
        if lo is None:
            continue
        unit = conf.get("unit") or "억원"
        mult = 1e8 if unit == "억원" else 1e12
        thr = float(lo) * mult
        out = out[out[key].fillna(-float("inf")) >= thr]
    return out


def _market_label(m: Any) -> str:
    return {"KOSPI": "코스피", "KOSDAQ": "코스닥"}.get(
        str(m), str(m) if m is not None and str(m) != "nan" else "-"
    )


def _row_list_item(r: pd.Series) -> dict[str, Any]:
    code = str(r.get("stock_code", "")).zfill(6)
    item: dict[str, Any] = {
        "stock_code": code,
        "corp_name": str(r.get("corp_name", "") or ""),
        "market": _market_label(r.get("market")),
        "tradingview": tradingview_chart_url(code),
        "attractiveness": _clean_num(r.get("attractiveness")),
        "grade": str(r.get("grade", "") or ""),
        "grade_label": GRADE_UI.get(str(r.get("grade", "")), (str(r.get("grade", "")), ""))[0],
    }
    extra_cols = [
        "market_cap",
        "current_price",
        "revenue",
        "operating_profit",
        "net_income",
        "range_position",
        "pct_from_avg_52w",
        "operating_margin",
        "revenue_growth",
    ]
    for col in extra_cols:
        item[col] = format_cell(r, col) if col in r.index else "-"
        item[f"{col}_num"] = _clean_num(r.get(col)) if col in r.index else None
    return item


WEB_LIST_COLUMNS = [
    "corp_name",
    "stock_code",
    "market",
    "chart",
    "grade",
    "attractiveness",
    "market_cap",
    "current_price",
    "revenue",
    "operating_profit",
    "net_income",
    "pct_from_avg_52w",
]

WEB_LIST_LABELS = {
    "corp_name": "종목명",
    "stock_code": "코드",
    "market": "시장",
    "grade": "등급",
    "attractiveness": "점수",
    "chart": "차트",
    "market_cap": "시가총액",
    "current_price": "현재가",
    "revenue": "매출액",
    "operating_profit": "영업이익",
    "net_income": "당기순이익",
    "pct_from_avg_52w": "주가현위치",
}


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/meta")
def api_meta() -> dict[str, Any]:
    fin = get_financials()
    prices = get_prices()
    specs = []
    for s in FILTER_SPECS:
        specs.append(
            {
                "key": s.key,
                "label": s.label,
                "category": s.category,
                "help_text": s.help_text,
                "direction": s.direction,
                "excellent_min": s.excellent_min,
                "excellent_max": s.excellent_max,
                "unit_hint": s.unit_hint,
                "higher_better": s.higher_better,
            }
        )
    cats = categories_order()
    return {
        "financials_caption": financials_basis_caption(),
        "price_caption": price_cache_caption(),
        "financials_rows": int(len(fin)),
        "price_rows": int(len(prices)),
        "categories": cats,
        "filter_specs": specs,
        "abs_specs": [{"key": k, "label": lab} for k, lab in ABS_SPECS],
        "list_columns": WEB_LIST_COLUMNS,
        "list_labels": WEB_LIST_LABELS,
        "saved_filters": load_saved_filters(),
    }


@app.get("/api/stocks")
def api_stocks(q: str = Query("", max_length=80), limit: int = 30) -> dict[str, Any]:
    fin = get_financials()
    if fin.empty:
        return {"items": []}
    q = (q or "").strip()
    df = fin[["stock_code", "corp_name", "market"]].copy()
    if q:
        mask = df["corp_name"].astype(str).str.contains(q, case=False, na=False) | df[
            "stock_code"
        ].astype(str).str.contains(q, na=False)
        df = df[mask]
    df = df.head(max(1, min(limit, 100)))
    items = [
        {
            "stock_code": str(r.stock_code).zfill(6),
            "corp_name": str(r.corp_name),
            "market": _market_label(r.market) if "market" in df.columns else "",
            "label": f"{r.corp_name} ({str(r.stock_code).zfill(6)})",
        }
        for r in df.itertuples()
    ]
    return {"items": items}


@app.post("/api/screen")
def api_screen(body: ScreenBody) -> dict[str, Any]:
    fin = get_financials()
    if fin.empty:
        raise HTTPException(503, "재무 스냅샷이 없습니다.")
    prices = get_prices()
    view = fin.copy()
    market = (body.market or "ALL").upper()
    if market not in ("ALL", "KOSPI", "KOSDAQ"):
        market = "ALL"
    if market != "ALL" and "market" in view.columns:
        view = view[view["market"] == market].copy()

    mode = body.mode or "filter"
    price_f: dict[str, tuple[float | None, float | None]] = {}
    price_abs: dict[str, dict[str, Any]] = {}
    if mode == "search":
        code = str(body.code or "").zfill(6)
        if not code or code == "000000":
            return {"count": 0, "shown": 0, "rows": [], "warning": "종목을 선택하세요."}
        candidates = view[view["stock_code"].astype(str).str.zfill(6) == code].copy()
    elif mode == "favorites":
        codes = [str(c).zfill(6) for c in body.codes if str(c).strip()]
        if not codes:
            return {"count": 0, "shown": 0, "rows": [], "warning": "즐겨찾기한 종목이 없습니다."}
        candidates = view[view["stock_code"].astype(str).str.zfill(6).isin(codes)].copy()
    else:
        raw_filters: dict[str, tuple[float | None, float | None]] = {}
        for k, bounds in (body.filters or {}).items():
            if not isinstance(bounds, (list, tuple)) or len(bounds) < 2:
                continue
            lo, hi = bounds[0], bounds[1]
            raw_filters[k] = (
                float(lo) if lo is not None else None,
                float(hi) if hi is not None else None,
            )
        fin_f, price_f = split_filters(raw_filters)
        candidates = apply_range_filters(view, fin_f)
        fin_abs = {k: v for k, v in (body.abs or {}).items() if k not in PRICE_ABS_KEYS}
        price_abs = {k: v for k, v in (body.abs or {}).items() if k in PRICE_ABS_KEYS}
        candidates = _apply_abs(candidates, fin_abs)

    warning = None
    if candidates.empty:
        return {"count": 0, "shown": 0, "rows": [], "warning": warning}

    if prices is None or prices.empty:
        warning = "주가 캐시가 없습니다. scripts/build_price_cache.py 또는 GitHub Actions를 확인하세요."
        merged = candidates.copy()
    else:
        merged = merge_financial_and_price(candidates, prices)

    if mode == "filter":
        if price_abs:
            merged = _apply_abs(merged, price_abs)
        if price_f:
            merged = apply_range_filters(merged, price_f)

    scored = attach_scores(merged)
    scored = scored.sort_values("attractiveness", ascending=False, na_position="last")
    total = int(len(scored))
    limit = max(1, min(int(body.limit or 200), 500))
    show = scored.head(limit)
    rows = [_row_list_item(r) for _, r in show.iterrows()]
    return {
        "count": total,
        "shown": len(rows),
        "rows": rows,
        "warning": warning,
        "price_rows": int(len(prices)) if prices is not None else 0,
    }


def _has(v: Any) -> bool:
    if v is None:
        return False
    try:
        return not pd.isna(v)
    except Exception:
        return True


def _build_detail(row: pd.Series) -> dict[str, Any]:
    sc = score_row(row)
    code = str(row.get("stock_code", "") or "").zfill(6)
    name = str(row.get("corp_name", "") or "")
    grade = str(sc["grade"])
    cat_scores = sc.get("category_scores") or {}
    badges = sc.get("badges") or {}

    chips = []
    for title, cat_key in DETAIL_SECTION_ORDER:
        if not cat_key:
            continue
        label = CATEGORY_LABELS.get(cat_key, title)
        cs = cat_scores.get(cat_key)
        chips.append(
            {
                "key": cat_key,
                "label": label,
                "weight_pct": int(round(CATEGORY_WEIGHTS.get(cat_key, 0) * 100)),
                "score": int(cs) if cs is not None else None,
            }
        )

    sections = []
    for title, cat_key in DETAIL_SECTION_ORDER:
        tiles: list[dict[str, str]] = []
        if cat_key is None:
            for key, label in [
                ("revenue", "매출액"),
                ("operating_profit", "영업이익"),
                ("net_income", "당기순이익"),
            ]:
                if key in row.index and _has(row.get(key)):
                    tiles.append(_tile(label, format_cell(row, key)))
        else:
            if cat_key == "주가 현위치":
                if _has(row.get("market_cap")):
                    tiles.append(
                        _tile(
                            "시가총액",
                            format_metric_value("market_cap", row.get("market_cap")),
                        )
                    )
                if _has(row.get("current_price")):
                    tiles.append(
                        _tile(
                            "현재가",
                            format_metric_value("current_price", row.get("current_price")),
                        )
                    )
                if _has(row.get("range_position")):
                    tiles.append(
                        _tile(
                            "52주위치(%)",
                            format_metric_value("range_position", row.get("range_position")),
                        )
                    )
                if _has(row.get("avg_52w")):
                    tiles.append(
                        _tile(
                            "52주 평균가",
                            format_metric_value("current_price", row.get("avg_52w")),
                        )
                    )
                if _has(row.get("low_52w")):
                    lo = format_metric_value("current_price", row.get("low_52w"))
                    hi = format_metric_value("current_price", row.get("high_52w"))
                    tiles.append(_tile("52주 저가/고가", f"{lo} / {hi}"))
            if cat_key == "B경제" and _has(row.get("sga_ratio")):
                tiles.append(
                    _tile(
                        "판관비율(판관비÷매출)",
                        format_metric_value("sga_ratio", row.get("sga_ratio")),
                    )
                )
            for spec in specs_in_category(cat_key):
                tiles.append(
                    _tile(
                        spec.label,
                        format_metric_value(spec.key, row.get(spec.key)),
                        str(badges.get(spec.key, "해당없음")),
                    )
                )
        sections.append(
            {
                "title": title,
                "category_key": cat_key,
                "score": (
                    int(cat_scores[cat_key])
                    if cat_key and cat_scores.get(cat_key) is not None
                    else None
                ),
                "tiles": tiles,
            }
        )

    return {
        "stock_code": code,
        "corp_name": name,
        "tradingview": tradingview_chart_url(code),
        "attractiveness": int(sc["attractiveness"]),
        "grade": grade,
        "grade_label": GRADE_UI.get(grade, (grade, ""))[0],
        "category_chips": chips,
        "sections": sections,
    }


@app.get("/api/detail/{code}")
def api_detail(code: str) -> dict[str, Any]:
    code = str(code).zfill(6)
    fin = get_financials()
    if fin.empty:
        raise HTTPException(503, "재무 스냅샷이 없습니다.")
    hit = fin[fin["stock_code"].astype(str).str.zfill(6) == code]
    if hit.empty:
        raise HTTPException(404, f"종목을 찾을 수 없습니다 ({code})")
    row = hit.iloc[0].copy()
    prices = get_prices()
    if prices is not None and not prices.empty:
        ph = prices[prices["stock_code"].astype(str).str.zfill(6) == code]
        if not ph.empty:
            for c in (
                "current_price",
                "market_cap",
                "low_52w",
                "high_52w",
                "avg_52w",
                "pct_from_avg_52w",
                "range_position",
                "bottom_dwell_ratio",
            ):
                if c in ph.columns:
                    row[c] = ph.iloc[0][c]
    # attach score fields onto row for consistency
    scored = attach_scores(pd.DataFrame([row]))
    return _build_detail(scored.iloc[0])


@app.post("/api/reload")
def api_reload() -> dict[str, str]:
    reload_data()
    return {"status": "ok"}


class FiltersBody(BaseModel):
    market: str = "전체"
    search: str = ""
    enabled: list[str] = Field(default_factory=list)
    ranges: dict[str, list[float | None]] = Field(default_factory=dict)
    abs: dict[str, dict[str, Any]] = Field(default_factory=dict)


@app.get("/api/filters")
def api_get_filters() -> dict[str, Any]:
    return load_saved_filters() or {}


@app.post("/api/filters")
def api_save_filters(body: FiltersBody) -> dict[str, Any]:
    state = {
        "market": body.market,
        "search": body.search or "",
        "enabled": list(body.enabled or []),
        "ranges": body.ranges or {},
        "abs": body.abs or {},
    }
    where = persist_filters(state)
    return {"status": "ok", "where": where, "saved": state}


@app.get("/")
def index() -> FileResponse:
    index_path = WEB / "index.html"
    if not index_path.exists():
        raise HTTPException(404, "web/index.html 없음")
    return FileResponse(index_path)


if ASSETS.exists():
    app.mount("/assets", StaticFiles(directory=str(ASSETS)), name="assets")

if WEB.exists():
    app.mount("/static", StaticFiles(directory=str(WEB)), name="static")
