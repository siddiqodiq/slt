"""Agregasi di memori. Notion hanya menyerahkan baris mentah (§3, §7).

Semua angka di sini dihitung saat tampil, tidak pernah disimpan — rumusnya bebas
diubah tanpa menyentuh satu pun baris data lama.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta

from ..config import (
    BADIYAH_OPTIONS,
    CARA_OPTIONS,
    CHECKBOX_SUNNAH,
    PRAYERS,
    QABLIYAH_OPTIONS,
    WAKTU_OPTIONS,
)
from ..domain import day_quality
from ..notion import DayRecord

HARI_PENDEK = ("Sen", "Sel", "Rab", "Kam", "Jum", "Sab", "Min")
BERJAMAAH = ("Masjid", "Berjamaah")


@dataclass
class Filters:
    start: date
    end: date
    preset: str = "30"
    prayers: tuple[str, ...] = PRAYERS
    waktu: tuple[str, ...] = ()
    cara: tuple[str, ...] = ()
    weekdays: tuple[int, ...] = ()
    exclude_auto: bool = False

    @property
    def days(self) -> int:
        return (self.end - self.start).days + 1

    def day_allowed(self, rec: DayRecord) -> bool:
        if self.weekdays and rec.day.weekday() not in self.weekdays:
            return False
        if self.exclude_auto and rec.sumber == "Otomatis":
            return False
        return True

    def entry_allowed(self, waktu: str | None, cara: str | None) -> bool:
        if self.waktu and waktu not in self.waktu:
            return False
        if self.cara and cara not in self.cara:
            return False
        return True

    def label(self) -> str:
        return {
            "7": "7 hari terakhir",
            "30": "30 hari terakhir",
            "bulan": "Bulan ini",
        }.get(self.preset, f"{self.start.isoformat()} – {self.end.isoformat()}")


def make_filters(
    preset: str = "30",
    start: date | None = None,
    end: date | None = None,
    today: date | None = None,
    **kwargs,
) -> Filters:
    today = today or date.today()
    if preset == "kustom" and start and end:
        rng = (min(start, end), max(start, end))
    elif preset == "bulan":
        rng = (today.replace(day=1), today)
    elif preset == "7":
        rng = (today - timedelta(days=6), today)
    else:
        preset = preset if preset in {"30", "90", "365"} else "30"
        rng = (today - timedelta(days=int(preset) - 1), today)
    return Filters(start=rng[0], end=rng[1], preset=preset, **kwargs)


@dataclass
class Aggregate:
    filters: Filters
    summary: dict = field(default_factory=dict)
    heatmap: list[dict] = field(default_factory=list)
    per_prayer: list[dict] = field(default_factory=list)
    sunnah: list[dict] = field(default_factory=list)
    tilawah: list[dict] = field(default_factory=list)
    catatan: list[dict] = field(default_factory=list)


def _pct(part: int, whole: int) -> float:
    return round(100.0 * part / whole, 1) if whole else 0.0


def aggregate(records: list[DayRecord], filters: Filters) -> Aggregate:
    by_day = {r.day: r for r in records if filters.start <= r.day <= filters.end}
    days = [filters.start + timedelta(days=i) for i in range(filters.days)]

    total = awal = jamaah = with_cara = 0
    per_prayer_counts = {p: dict.fromkeys(WAKTU_OPTIONS, 0) for p in PRAYERS}
    per_prayer_missing = dict.fromkeys(PRAYERS, 0)
    sunnah_counts: dict[str, int] = {}
    tilawah_total = 0
    heatmap: list[dict] = []
    tilawah_series: list[dict] = []
    catatan: list[dict] = []
    days_recorded = 0

    for day in days:
        rec = by_day.get(day)
        allowed = bool(rec) and filters.day_allowed(rec)

        entries: dict[str, dict] = {}
        if rec and allowed:
            for prayer in PRAYERS:
                waktu, cara = rec.waktu(prayer), rec.cara(prayer)
                if prayer not in filters.prayers:
                    continue
                if not waktu:
                    per_prayer_missing[prayer] += 1
                    continue
                if not filters.entry_allowed(waktu, cara):
                    continue
                entries[prayer] = {"waktu": waktu, "cara": cara}
                total += 1
                per_prayer_counts[prayer][waktu] = per_prayer_counts[prayer].get(waktu, 0) + 1
                if waktu == "Awal waktu":
                    awal += 1
                if cara:
                    with_cara += 1
                    if cara in BERJAMAAH:
                        jamaah += 1
            if entries:
                days_recorded += 1
            for name in CHECKBOX_SUNNAH:
                if rec.checks.get(name):
                    sunnah_counts[name] = sunnah_counts.get(name, 0) + 1
            for p in rec.qabliyah:
                sunnah_counts[f"Qabliyah {p}"] = sunnah_counts.get(f"Qabliyah {p}", 0) + 1
            for p in rec.badiyah:
                sunnah_counts[f"Ba'diyah {p}"] = sunnah_counts.get(f"Ba'diyah {p}", 0) + 1
            tilawah_total += rec.tilawah
            if rec.catatan.strip():
                catatan.append({"date": day, "text": rec.catatan.strip()})
        elif rec is None:
            for prayer in filters.prayers:
                per_prayer_missing[prayer] += 1

        heatmap.append(
            {
                "date": day,
                "quality": day_quality(entries) if entries else None,
                "recorded": len(entries),
                "auto": bool(rec and rec.sumber == "Otomatis"),
                "tilawah": rec.tilawah if rec and allowed else 0,
                "catatan": bool(rec and rec.catatan.strip()),
            }
        )
        tilawah_series.append({"date": day, "pages": rec.tilawah if rec and allowed else 0})

    # Rata-rata bergerak 7 hari untuk tren tilawah (§7).
    for i, point in enumerate(tilawah_series):
        window = tilawah_series[max(0, i - 6) : i + 1]
        point["ma7"] = round(sum(p["pages"] for p in window) / len(window), 2)

    agg = Aggregate(filters=filters)
    agg.heatmap = heatmap
    agg.tilawah = tilawah_series
    agg.catatan = list(reversed(catatan))[:10]

    possible = len(days) * len(filters.prayers)
    agg.summary = {
        "pct_awal": _pct(awal, total),
        "pct_jamaah": _pct(jamaah, with_cara),
        "tilawah_total": tilawah_total,
        "tilawah_avg": round(tilawah_total / len(days), 1) if days else 0.0,
        "tercatat": total,
        "kemungkinan": possible,
        "pct_tercatat": _pct(total, possible),
        "hari_terisi": days_recorded,
        "hari_total": len(days),
        "streak": current_streak(by_day, filters.end),
        "hari_otomatis": sum(1 for h in heatmap if h["auto"]),
    }

    agg.per_prayer = []
    for prayer in PRAYERS:
        if prayer not in filters.prayers:
            continue
        counts = per_prayer_counts[prayer]
        recorded = sum(counts.values())
        agg.per_prayer.append(
            {
                "prayer": prayer,
                "counts": counts,
                "total": recorded,
                "belum": per_prayer_missing[prayer],
                "pct": {w: _pct(counts[w], recorded) for w in WAKTU_OPTIONS},
            }
        )

    all_items = (
        list(CHECKBOX_SUNNAH)
        + [f"Qabliyah {p}" for p in QABLIYAH_OPTIONS]
        + [f"Ba'diyah {p}" for p in BADIYAH_OPTIONS]
    )
    agg.sunnah = sorted(
        (
            {
                "name": name,
                "count": sunnah_counts.get(name, 0),
                "pct": _pct(sunnah_counts.get(name, 0), len(days)),
            }
            for name in all_items
        ),
        key=lambda item: (item["count"], item["name"]),
    )
    return agg


def current_streak(by_day: dict[date, DayRecord], end: date) -> int:
    """Hari berturut-turut dengan lima shalat tercatat dan tidak ada 'Lewat waktu'.

    Sengaja tidak ditampilkan sebagai target yang bisa 'putus' — lihat catatan
    motivasi di §7; angka ini hanya salah satu dari beberapa indikator.
    """
    streak = 0
    cursor = end
    while True:
        rec = by_day.get(cursor)
        if rec is None:
            break
        waktus = [rec.waktu(p) for p in PRAYERS]
        if any(w is None for w in waktus) or any(w == "Lewat waktu" for w in waktus):
            break
        streak += 1
        cursor -= timedelta(days=1)
    return streak


def cara_breakdown(records: list[DayRecord], filters: Filters) -> dict[str, int]:
    counts = dict.fromkeys(CARA_OPTIONS, 0)
    for rec in records:
        if not (filters.start <= rec.day <= filters.end) or not filters.day_allowed(rec):
            continue
        for prayer in filters.prayers:
            cara = rec.cara(prayer)
            if cara and rec.waktu(prayer) and filters.entry_allowed(rec.waktu(prayer), cara):
                counts[cara] = counts.get(cara, 0) + 1
    return counts
