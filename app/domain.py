"""Aturan domain murni: kualitas hari, asal data, dan tanggal baris.

Modul ini sengaja bebas I/O supaya bisa diuji langsung (lihat tests/).
"""
from __future__ import annotations

from datetime import date, datetime, timedelta

from .config import PRAYERS, Settings, get_settings

# Bobot kualitas untuk heatmap & ringkasan. Bukan "skor" yang disimpan —
# dihitung ulang saat tampil, jadi rumusnya bebas diubah kapan saja (§7).
WAKTU_WEIGHT = {"Awal waktu": 1.0, "Tengah waktu": 0.66, "Akhir waktu": 0.33, "Lewat waktu": 0.0}
CARA_WEIGHT = {"Masjid": 1.0, "Berjamaah": 0.75, "Munfarid": 0.4}


def day_quality(entries: dict[str, dict]) -> float | None:
    """0..1 dari lima shalat sehari; None kalau tidak ada satu pun tercatat."""
    scores = []
    for prayer in PRAYERS:
        entry = entries.get(prayer) or {}
        waktu = entry.get("waktu")
        if not waktu:
            continue
        cara = entry.get("cara")
        w = WAKTU_WEIGHT.get(waktu, 0.0)
        c = CARA_WEIGHT.get(cara, 0.4) if cara else 0.4
        scores.append(0.7 * w + 0.3 * c)
    if not scores:
        return None
    # Shalat yang tidak tercatat dihitung nol supaya hari bolong tidak terlihat sempurna.
    return sum(scores) / len(PRAYERS)


def sumber_merge(existing: str | None, incoming: str) -> str:
    """Sumber level-hari (§8). Prioritas: Otomatis > Manual > Konfirmasi.

    Nilai `Otomatis` hanya tersisa pada baris lama — sejak auto-fill dilepas,
    semua penulisan bot berasal dari tindakanmu sendiri. Dashboard tetap bisa
    memfilternya lewat "Sembunyikan hari yang terisi otomatis".
    """
    order = {"Konfirmasi": 0, "Manual": 1, "Otomatis": 2}
    if not existing:
        return incoming
    return existing if order.get(existing, 0) >= order.get(incoming, 0) else incoming


def catatan_day(now: datetime, settings: Settings | None = None) -> date:
    """Tanggal baris untuk input manual (§11.4).

    Dengan `TAHAJUD_DAY=previous`, jam sebelum 05:00 pagi masih dihitung sebagai hari
    kemarin. Default `wake`: apa pun yang kamu catat masuk ke tanggal saat itu juga.
    """
    s = settings or get_settings()
    if s.tahajud_day != "previous":
        return now.date()
    batas = now.replace(hour=5, minute=0, second=0, microsecond=0)
    return now.date() - timedelta(days=1) if now < batas else now.date()

