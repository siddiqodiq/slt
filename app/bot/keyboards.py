"""Inline keyboard + encoding callback data (batas Telegram 64 byte)."""
from __future__ import annotations

from datetime import date

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup, WebAppInfo

from ..config import (
    BADIYAH_OPTIONS,
    CARA_OPTIONS,
    CHECKBOX_SUNNAH,
    PRAYERS,
    QABLIYAH_OPTIONS,
    WAKTU_OPTIONS,
)
from ..notion import DayRecord

CARA_LABEL = {"Masjid": "🕌 Masjid", "Berjamaah": "👥 Berjamaah", "Munfarid": "🧍 Sendiri"}
WAKTU_LABEL = {
    "Awal waktu": "🟢 Awal",
    "Tengah waktu": "🟡 Tengah",
    "Akhir waktu": "🟠 Akhir",
    "Lewat waktu": "🔴 Lewat",
}
PRAYER_SHORT = {"Subuh": "Sub", "Dzuhur": "Dzu", "Ashar": "Ash", "Maghrib": "Mag", "Isya": "Isy"}
NOOP = "noop"


def d2s(day: date) -> str:
    return day.strftime("%Y%m%d")


def s2d(value: str) -> date:
    return date(int(value[0:4]), int(value[4:6]), int(value[6:8]))


def mark(flag: bool) -> str:
    return "✅" if flag else "⬜"



# --- /isi -------------------------------------------------------------------

def isi_keyboard(day: date, rec: DayRecord) -> InlineKeyboardMarkup:
    ds = d2s(day)
    rows: list[list[InlineKeyboardButton]] = []
    pair: list[InlineKeyboardButton] = []
    for idx, name in enumerate(CHECKBOX_SUNNAH):
        pair.append(
            InlineKeyboardButton(
                f"{mark(rec.checks.get(name, False))} {name}", callback_data=f"isi|c|{ds}|{idx}"
            )
        )
        if len(pair) == 2:
            rows.append(pair)
            pair = []
    if pair:
        rows.append(pair)

    rows.append([InlineKeyboardButton("— Qabliyah —", callback_data=NOOP)])
    rows.append(
        [
            InlineKeyboardButton(
                f"{mark(p in rec.qabliyah)}{PRAYER_SHORT[p]}", callback_data=f"isi|q|{ds}|{i}"
            )
            for i, p in enumerate(QABLIYAH_OPTIONS)
        ]
    )
    rows.append([InlineKeyboardButton("— Ba'diyah —", callback_data=NOOP)])
    rows.append(
        [
            InlineKeyboardButton(
                f"{mark(p in rec.badiyah)}{PRAYER_SHORT[p]}", callback_data=f"isi|b|{ds}|{i}"
            )
            for i, p in enumerate(BADIYAH_OPTIONS)
        ]
    )
    rows.append([InlineKeyboardButton("✖ Tutup", callback_data="close")])
    return InlineKeyboardMarkup(rows)


# --- /edit ------------------------------------------------------------------

def edit_day_keyboard(today: date, yesterday: date) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("Hari ini", callback_data=f"ed|p|{d2s(today)}")],
            [InlineKeyboardButton("Kemarin", callback_data=f"ed|p|{d2s(yesterday)}")],
            [InlineKeyboardButton("✖ Tutup", callback_data="close")],
        ]
    )


def edit_prayer_keyboard(day: date, rec: DayRecord | None) -> InlineKeyboardMarkup:
    ds = d2s(day)
    rows = []
    for i, prayer in enumerate(PRAYERS):
        waktu = rec.waktu(prayer) if rec else None
        cara = rec.cara(prayer) if rec else None
        status = f"{WAKTU_LABEL.get(waktu, '⬜')} · {cara}" if waktu else "⬜ kosong"
        rows.append([InlineKeyboardButton(f"{prayer} — {status}", callback_data=f"ed|w|{ds}|{i}")])
    rows.append([InlineKeyboardButton("↩ Ganti hari", callback_data="ed|d"), InlineKeyboardButton("✖ Tutup", callback_data="close")])
    return InlineKeyboardMarkup(rows)


def edit_waktu_keyboard(day: date, prayer: str) -> InlineKeyboardMarkup:
    ds, pi = d2s(day), PRAYERS.index(prayer)
    rows = [
        [
            InlineKeyboardButton(WAKTU_LABEL[w], callback_data=f"ed|sw|{ds}|{pi}|{wi}")
            for wi, w in enumerate(WAKTU_OPTIONS[:2])
        ],
        [
            InlineKeyboardButton(WAKTU_LABEL[w], callback_data=f"ed|sw|{ds}|{pi}|{wi + 2}")
            for wi, w in enumerate(WAKTU_OPTIONS[2:])
        ],
        [InlineKeyboardButton("🧹 Kosongkan", callback_data=f"ed|clr|{ds}|{pi}")],
        [InlineKeyboardButton("↩ Kembali", callback_data=f"ed|p|{ds}")],
    ]
    return InlineKeyboardMarkup(rows)


def edit_cara_keyboard(day: date, prayer: str) -> InlineKeyboardMarkup:
    ds, pi = d2s(day), PRAYERS.index(prayer)
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(CARA_LABEL[c], callback_data=f"ed|sc|{ds}|{pi}|{ci}")
                for ci, c in enumerate(CARA_OPTIONS)
            ],
            [InlineKeyboardButton("↩ Kembali", callback_data=f"ed|p|{ds}")],
        ]
    )



def dashboard_keyboard(url: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton("📊 Buka Dashboard", web_app=WebAppInfo(url=url))]])


def main_menu_keyboard(url: str | None = None) -> ReplyKeyboardMarkup:
    rows = [
        [KeyboardButton("/hariini"), KeyboardButton("/edit")],
        [KeyboardButton("/isi"), KeyboardButton("/rekap")]
    ]
    if url and url.startswith("https://"):
        rows.append([KeyboardButton("?? Dashboard", web_app=WebAppInfo(url=url))])
    else:
        rows.append([KeyboardButton("/dashboard")])

    return ReplyKeyboardMarkup(
        rows,
        resize_keyboard=True,
        is_persistent=True,
        input_field_placeholder="Pilih menu..."
    )

