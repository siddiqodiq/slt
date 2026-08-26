"""Aturan domain murni: kualitas hari, asal data, dan tanggal baris.

Modul ini sengaja bebas I/O supaya bisa diuji langsung (lihat tests/).
"""
from __future__ import annotations

from datetime import date, datetime, timedelta

from .config import PRAYERS, Settings, get_settings

def sumber_merge(existing: str | None, incoming: str) -> str:
    """Sumber level-hari (§8). Prioritas: Manual > Konfirmasi > Otomatis.

    Urutannya sengaja terbalik dari versi lama. Dulu `Otomatis` menang karena ia
    langka. Sekarang auto-fill menyentuh setiap hari, jadi kalau ia tetap menang
    semua hari akan bertanda Otomatis dan filter "sembunyikan yang terisi
    otomatis" kehilangan gunanya. Yang ingin dijawab kolom ini adalah "apakah
    hari ini sudah saya sentuh sendiri" — maka tindakanmu yang menang.
    """
    order = {"Otomatis": 0, "Konfirmasi": 1, "Manual": 2}
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

