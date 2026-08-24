"""Rute Mini App: satu halaman shell + partial htmx yang dirender server (§7)."""
from __future__ import annotations

import logging
from datetime import date
from pathlib import Path

from fastapi import APIRouter, Header, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from ..config import CARA_OPTIONS, PRAYERS, WAKTU_OPTIONS, get_settings
from ..data import load_records
from ..runtime import get_runtime
from ..timeutil import now_local
from . import charts
from .aggregate import aggregate, make_filters
from .auth import InitDataError, user_id_of, validate_init_data

log = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent.parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
router = APIRouter()

HARI_PILIHAN = [(0, "Sen"), (1, "Sel"), (2, "Rab"), (3, "Kam"), (4, "Jum"), (5, "Sab"), (6, "Min")]


def require_owner(init_data: str | None, dev_token: str | None) -> int:
    """Jangan pernah percaya user_id dari klien tanpa verifikasi hash (§7)."""
    s = get_settings()
    if dev_token and s.dev_bypass_token and dev_token == s.dev_bypass_token:
        return s.owner_id
    try:
        parsed = validate_init_data(init_data or "", s.bot_token, s.miniapp_max_age)
        uid = user_id_of(parsed)
    except InitDataError as exc:
        log.warning("initData ditolak: %s", exc)
        raise HTTPException(status_code=401, detail=f"initData tidak valid: {exc}") from exc
    if s.owner_id and uid != s.owner_id:
        raise HTTPException(status_code=403, detail="Mini app ini hanya untuk pemiliknya")
    return uid


@router.get("/app", response_class=HTMLResponse)
async def shell(request: Request):
    """Kerangka halaman. Tidak memuat data apa pun sebelum initData tervalidasi."""
    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {
            "prayers": PRAYERS,
            "waktu_options": WAKTU_OPTIONS,
            "cara_options": CARA_OPTIONS,
            "hari_pilihan": HARI_PILIHAN,
            "today": now_local().date().isoformat(),
        },
    )


@router.get("/app/panel", response_class=HTMLResponse)
async def panel(
    request: Request,
    preset: str = "30",
    start: str | None = None,
    end: str | None = None,
    prayer: list[str] = Query(default=[]),
    waktu: list[str] = Query(default=[]),
    cara: list[str] = Query(default=[]),
    hari: list[str] = Query(default=[]),
    tanpa_otomatis: str | None = None,
    x_telegram_init_data: str | None = Header(default=None, alias="X-Telegram-Init-Data"),
    x_dev_token: str | None = Header(default=None, alias="X-Dev-Token"),
):
    require_owner(x_telegram_init_data, x_dev_token)
    rt = get_runtime()
    today = now_local().date()

    filters = make_filters(
        preset=preset,
        start=_parse_date(start),
        end=_parse_date(end),
        today=today,
        prayers=tuple(p for p in PRAYERS if p in prayer) or PRAYERS,
        waktu=tuple(w for w in WAKTU_OPTIONS if w in waktu),
        cara=tuple(c for c in CARA_OPTIONS if c in cara),
        weekdays=tuple(int(h) for h in hari if h.isdigit() and 0 <= int(h) <= 6),
        exclude_auto=bool(tanpa_otomatis),
    )
    records = await load_records(filters.start, filters.end, rt.repo, rt.cache)
    agg = aggregate(records, filters)

    return templates.TemplateResponse(
        request,
        "partials/panel.html",
        {
            "agg": agg,
            "filters": filters,
            "svg_heatmap": charts.heatmap_svg(agg.heatmap),
            "svg_prayer": charts.per_prayer_svg(agg.per_prayer),
            "svg_sunnah": charts.sunnah_svg(agg.sunnah, filters.days),
            "svg_tilawah": charts.tilawah_svg(agg.tilawah),
            "waktu_options": WAKTU_OPTIONS,
        },
    )


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None
