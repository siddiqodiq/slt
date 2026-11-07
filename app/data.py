"""Alur baca: Redis dulu, kalau meleset tarik seluruh baris dari Notion (§3).

Cache di sini bukan optimasi — tanpa ini dashboard menembus batas ~3 req/s Notion
dalam hitungan detik saat filter diganti berkali-kali.
"""
from __future__ import annotations

import logging
from datetime import date

from .cache import Cache, get_cache, k_rows
from .config import get_settings
from .notion import DayRecord, NotionRepo, get_repo

log = logging.getLogger(__name__)


def rec_to_dict(rec: DayRecord) -> dict:
    return {
        "day": rec.day.isoformat(),
        "page_id": rec.page_id,
        "prayers": rec.prayers,
        "qabliyah": rec.qabliyah,
        "badiyah": rec.badiyah,
        "checks": rec.checks,
        "tilawah": rec.tilawah,
        "catatan": rec.catatan,
        "sumber": rec.sumber,
        "sedekah_rutin": rec.sedekah_rutin,
        "sedekah_n": rec.sedekah_n,
        "sedekah_ket": rec.sedekah_ket,
    }


def rec_from_dict(data: dict) -> DayRecord:
    return DayRecord(
        day=date.fromisoformat(data["day"]),
        page_id=data.get("page_id", ""),
        prayers=data.get("prayers", {}),
        qabliyah=data.get("qabliyah", []),
        badiyah=data.get("badiyah", []),
        checks=data.get("checks", {}),
        tilawah=data.get("tilawah", 0),
        catatan=data.get("catatan", ""),
        sumber=data.get("sumber"),
        sedekah_rutin=bool(data.get("sedekah_rutin", False)),
        sedekah_n=data.get("sedekah_n", 0),
        sedekah_ket=data.get("sedekah_ket", ""),
    )


async def load_records(
    start: date,
    end: date,
    repo: NotionRepo | None = None,
    cache: Cache | None = None,
) -> list[DayRecord]:
    repo = repo or get_repo()
    cache = cache or get_cache()
    key = k_rows(start.isoformat(), end.isoformat())
    cached = await cache.get_json(key)
    if cached is not None:
        return [rec_from_dict(item) for item in cached]
    records = await repo.fetch_range(start, end)
    await cache.set_json(
        key, [rec_to_dict(r) for r in records], ttl=get_settings().ttl_rows
    )
    log.debug("Ambil %d baris Notion untuk %s..%s", len(records), start, end)
    return records


# Riwayat untuk streak & rekor. Satu rentang tetap supaya semua pemanggil
# (bot, penjadwal) berbagi satu entri cache.
HISTORY_DAYS = 365


async def load_history(today: date, repo: NotionRepo | None = None, cache: Cache | None = None) -> list[DayRecord]:
    from datetime import timedelta

    return await load_records(today - timedelta(days=HISTORY_DAYS - 1), today, repo, cache)
