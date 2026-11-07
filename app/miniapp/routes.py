"""Rute Mini App: satu halaman shell + partial htmx yang dirender server (§7)."""
from __future__ import annotations

import logging
from datetime import date
from pathlib import Path

from fastapi import APIRouter, Header, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from ..config import CARA_OPTIONS, PRAYERS, WAKTU_OPTIONS, get_settings
from ..data import load_history, load_records
from ..gamify import (
    LEVELS,
    XP_ATURAN,
    XP_LABEL,
    compute_level,
    compute_streak,
    malam_pekan_ini,
    sedekah_pekan_ini,
    tambahan_pekan_ini,
    tahajud_streak,
)
from .. import state
from ..runtime import get_runtime
from ..timeutil import now_local
from ..sedekah import hari_berjalan
from . import avatar, charts
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


# Webview Telegram menyimpan cache dengan agresif — tanpa ini versi baru tidak
# muncul walau sudah di-deploy, dan halaman lama bisa terus dipakai berhari-hari
# dengan initData yang sudah kedaluwarsa.
NO_STORE = {"Cache-Control": "no-store"}


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
        headers=NO_STORE,
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
    # Streak selalu dari seluruh riwayat sampai hari ini — tidak ikut filter
    # rentang, kalau tidak rekornya ikut menyusut saat memilih "7 hari".
    streak = compute_streak(await load_history(today, rt.repo, rt.cache), today)
    agg.summary["streak"] = streak.current
    agg.summary["rekor"] = streak.best

    return templates.TemplateResponse(
        request,
        "partials/panel.html",
        {
            "agg": agg,
            "filters": filters,
            "svg_prayer": charts.per_prayer_svg(agg.per_prayer),
            "svg_sunnah": charts.sunnah_svg(agg.sunnah, filters.days),
            "svg_tilawah": charts.tilawah_svg(agg.tilawah),
            "waktu_options": WAKTU_OPTIONS,
        },
        headers=NO_STORE,
    )


def _sunnah_pekan(records, today: date) -> int:
    """Jumlah sunnah tercentang 7 hari terakhir — jadi buah di pohon."""
    awal = today.toordinal() - 6
    total = 0
    for r in records:
        if awal <= r.day.toordinal() <= today.toordinal():
            total += sum(1 for v in r.checks.values() if v) + len(r.qabliyah) + len(r.badiyah)
    return total


def _pesan_avatar(lv, streak, tahajud, malam: int) -> list[str]:
    """Kalimat yang bergiliran saat avatar diketuk."""
    out = [f"{lv.nama}: {lv.makna}"]
    if lv.xp_hari_ini:
        sumber = max(lv.hari_ini, key=lambda k: lv.hari_ini[k])
        out.append(f"Hari ini +{lv.xp_hari_ini} XP, terbanyak dari {XP_LABEL[sumber].lower()}.")
    else:
        out.append("Belum ada XP hari ini — satu shalat di awal waktu sudah menyiram pohonnya.")
    if streak.current:
        out.append(f"🔥 {streak.current} hari streak shalat tepat waktu. Rekormu {streak.best}.")
    else:
        out.append(f"🌱 Streak mulai lagi dari hari ini. Rekormu {streak.best} hari.")
    if tahajud.current:
        out.append(f"🌙 {tahajud.current} malam tahajud beruntun — bulan menemanimu.")
    elif malam:
        out.append(f"🌙 {malam} malam tahajud pekan ini.")
    # Saran langkah berikutnya dari sumber XP yang masih nol hari ini.
    if not lv.hari_ini["tilawah"]:
        out.append("📖 Baca 5 halaman hari ini = +5 XP.")
    if (jalan := hari_berjalan(state.load(), now_local().date())):
        out.append(f"💧 Mata air di kaki pohon: sedekah rutinmu mengalir {jalan} hari tanpa putus.")
    out.append("🐦 Tiap hari ada sedekah tambahan, seekor burung singgah di pohonmu (7 hari terakhir).")
    if lv.berikut:
        out.append(f"{lv.kurang} XP lagi sampai pohonmu menjadi {lv.berikut[1]}.")
    out.append("“Akarnya teguh dan cabangnya menjulang ke langit, memberikan buahnya setiap musim.” (QS Ibrahim: 24–25)")
    return out


@router.get("/app/level", response_class=HTMLResponse)
async def level(
    request: Request,
    x_telegram_init_data: str | None = Header(default=None, alias="X-Telegram-Init-Data"),
    x_dev_token: str | None = Header(default=None, alias="X-Dev-Token"),
):
    """Kartu Pohon Amal. Terpisah dari panel: tidak ikut filter rentang, jadi
    tidak perlu dirender ulang (dan dianimasikan ulang) tiap filter berubah."""
    require_owner(x_telegram_init_data, x_dev_token)
    rt = get_runtime()
    today = now_local().date()
    records = await load_history(today, rt.repo, rt.cache)
    lv = compute_level(records, today)
    streak = compute_streak(records, today)
    tahajud = tahajud_streak(records, today)
    malam = malam_pekan_ini(records, today)
    tangga = [
        {
            "idx": i,
            "nama": nama,
            "ambang": ambang,
            "terbuka": i <= lv.idx,
            "svg": avatar.pohon_svg(i, 1.0, sunnah_pekan=6),
        }
        for i, (ambang, nama, _) in enumerate(LEVELS)
    ]
    rincian_max = max(lv.rincian.values()) or 1
    return templates.TemplateResponse(
        request,
        "partials/level.html",
        {
            "lv": lv,
            "streak": streak,
            "tahajud": tahajud,
            "malam": malam,
            "svg": avatar.pohon_svg(
                lv.idx, lv.progres,
                sunnah_pekan=_sunnah_pekan(records, today),
                streak_tahajud=tahajud.current,
                streak_shalat=streak.current,
                mata_air=state.load()["rutin_aktif"],
                burung=tambahan_pekan_ini(records, today),
            ),
            "sedekah_pekan": sedekah_pekan_ini(records, today),
            "rutin_hari": hari_berjalan(state.load(), today),
            "pesan": _pesan_avatar(lv, streak, tahajud, malam),
            "aturan": XP_ATURAN,
            "tangga": tangga,
            "rincian": [
                {"label": XP_LABEL[k], "xp": v, "pct": round(100 * v / rincian_max)}
                for k, v in sorted(lv.rincian.items(), key=lambda kv: -kv[1])
            ],
        },
        headers=NO_STORE,
    )


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None
