"""Bantuan waktu: satu sumber zona waktu untuk seluruh aplikasi (§3)."""
from __future__ import annotations

from datetime import date, datetime

from .config import BULAN_ID, HARI_ID, get_settings


def tz():
    return get_settings().tz


def now_local() -> datetime:
    return datetime.now(tz())






def label_hari(day: date) -> str:
    """Judul baris Notion: 'Senin, 24 Agu'."""
    return f"{HARI_ID[day.weekday()]}, {day.day} {BULAN_ID[day.month - 1]}"



def fmt_tanggal(day: date) -> str:
    return f"{day.day} {BULAN_ID[day.month - 1]} {day.year}"


def fmt_jam(dt: datetime) -> str:
    return dt.astimezone(tz()).strftime("%H:%M")
