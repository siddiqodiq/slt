"""Konfigurasi.

Aturan: **config var hanya untuk rahasia, identitas, dan hal yang memang berbeda
antara laptop dan Heroku.** Sisanya dipatok di kode sebagai konstanta di bawah —
sistem ini untuk satu orang, dan setiap knob yang tidak pernah diputar hanya
menambah tempat untuk salah ketik.

Konstanta tetap menjadi *default* dataclass, bukan nilai yang ditempel langsung
di logika, sehingga tetap bisa dioper di test dan diubah satu baris kalau suatu
saat perlu (mis. `Settings(isya_end="midnight")`).
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from functools import lru_cache
from zoneinfo import ZoneInfo

if not os.getenv("DOTENV_DISABLE"):
    # Kenyamanan pengembangan lokal. python-dotenv hanya ada di requirements-dev,
    # jadi di Heroku baris ini tidak melakukan apa-apa.
    try:
        from dotenv import load_dotenv

        load_dotenv()
    except ModuleNotFoundError:
        pass

# --- Konstanta domain (mengikuti §8 peta data Notion) ----------------------

PRAYERS: tuple[str, ...] = ("Subuh", "Dzuhur", "Ashar", "Maghrib", "Isya")
WAKTU_OPTIONS: tuple[str, ...] = ("Awal waktu", "Tengah waktu", "Akhir waktu", "Lewat waktu")
CARA_OPTIONS: tuple[str, ...] = ("Masjid", "Berjamaah", "Munfarid")
QABLIYAH_OPTIONS: tuple[str, ...] = ("Subuh", "Dzuhur", "Ashar", "Maghrib", "Isya")
BADIYAH_OPTIONS: tuple[str, ...] = ("Dzuhur", "Maghrib", "Isya")
CHECKBOX_SUNNAH: tuple[str, ...] = ("Tahajud", "Dhuha", "Tahiyatul Masjid", "Al-Waqiah", "Al-Mulk")
SUMBER_OPTIONS: tuple[str, ...] = ("Konfirmasi", "Otomatis", "Manual")

# Nama hari & bulan untuk judul baris Notion: "Senin, 24 Agu"
HARI_ID = ("Senin", "Selasa", "Rabu", "Kamis", "Jumat", "Sabtu", "Minggu")
BULAN_ID = ("Jan", "Feb", "Mar", "Apr", "Mei", "Jun", "Jul", "Agu", "Sep", "Okt", "Nov", "Des")


# --- Konstanta yang dipatok di kode (dulu config var) ----------------------

TZ_NAME = "Asia/Jakarta"  # §3: hitung & tampilkan lokal, simpan UTC

# Identitas database (§8). Tanpa NOTION_TOKEN, id ini tidak membuka apa pun.
NOTION_VERSION = "2025-09-03"
NOTION_DATABASE_ID = "e77e9807-23d9-4fed-ac13-6b3cf8a015af"
NOTION_DATA_SOURCE_ID = "b35e1f4f-a5ec-4513-84b5-b46ae46bac27"
NOTION_RPS = 3.0  # §3: batas Notion ~3 permintaan/detik

# Nama properti Notion (§8). Kalau kolomnya di-rename di Notion, ubah di sini —
# bot melapor lewat Telegram saat boot kalau ada yang tidak cocok.
PROP_TITLE = "Hari"
PROP_DATE = "Tanggal"
PROP_QABLIYAH = "Qabliyah"
PROP_BADIYAH = "Ba'diyah"
PROP_TILAWAH = "Tilawah"
PROP_CATATAN = "Catatan"
PROP_SUMBER = "Sumber"
SUMBER_ENABLED = True  # §11.2

# Keputusan §11.4: baris mana yang dituju input manual dini hari.
TAHAJUD_DAY = "wake"  # "wake" (tanggal saat bangun) | "previous" (sebelum 05:00 = kemarin)

# --- Ambang waktu shalat & auto-fill (§5) ----------------------------------

# Ambang datar waktu Jakarta — bukan jadwal adzan sungguhan, dan sengaja begitu.
# Menariknya dari API berarti menanggung 403, cache bulanan, dan pergantian bulan
# demi presisi menit yang tidak mengubah apa pun di sini: yang ditulis selalu
# "Awal waktu" dan tetap kamu koreksi sesudahnya.
#
# Angkanya dipatok sedikit di bawah adzan tipikal Jakarta sepanjang tahun, jadi
# sesekali baris ditulis beberapa menit lebih awal. Ubah di sini kalau meleset —
# satu dict, tidak ada tempat lain yang perlu disentuh.
JAM_SHALAT: dict[str, str] = {
    "Subuh": "04:30",
    "Dzuhur": "11:50",
    "Ashar": "15:10",
    "Maghrib": "17:50",
    "Isya": "19:00",
}

# §5 memperingatkan bahwa menulis sebelum shalat terjadi mencatat sesuatu yang
# belum terjadi. Keputusanmu: tulis langsung, lalu koreksi. `Sumber = Otomatis`
# menjaga baris itu tetap bisa dibedakan dari yang kamu sentuh sendiri, dan
# dashboard punya filter untuk menyembunyikannya.
AUTOFILL = True
AUTOFILL_WAKTU = "Awal waktu"
AUTOFILL_CARA = "Munfarid"
# Kalau dyno mati lebih lama dari ini, shalat yang terlewat tidak diisi surut.
# Lebih baik kosong daripada mengarang lima shalat sekaligus saat boot.
AUTOFILL_CATCHUP = 6 * 3600
# Selang pemeriksaan penjadwal. Cukup rapat agar telat maksimal setengah menit,
# cukup jarang agar tidak membebani apa pun.
TICK_SECONDS = 20

# Cache & mini app
TTL_ROWS = 60  # detik; penulisan tetap menghapus cache yang terdampak
MINIAPP_MAX_AGE = 86400  # umur maksimum auth_date initData (§7)
LOG_LEVEL = "INFO"


def _str(name: str, default: str = "") -> str:
    """Ambil env var tanpa spasi di ujung — salah tempel di dashboard Heroku
    gampang menyelipkan spasi, dan itu diam-diam merusak URL & token."""
    raw = os.getenv(name)
    return raw.strip() if raw else default


def _bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None or raw == "":
        return default
    return raw.strip().lower() in {"1", "true", "yes", "y", "on"}


def _int(name: str, default: int) -> int:
    raw = os.getenv(name)
    try:
        return int(raw) if raw not in (None, "") else default
    except ValueError:
        return default


@dataclass(frozen=True)
class Settings:
    # === Dari config var: rahasia & identitas ==============================
    bot_token: str = field(default_factory=lambda: _str("TELEGRAM_BOT_TOKEN"))
    owner_id: int = field(default_factory=lambda: _int("TELEGRAM_OWNER_ID", 0))
    # Tujuan prompt otomatis (§6). Kosong = japri owner.
    prompt_chat_id: int = field(default_factory=lambda: _int("TELEGRAM_PROMPT_CHAT_ID", 0))
    prompt_thread_id: int = field(default_factory=lambda: _int("TELEGRAM_PROMPT_THREAD_ID", 0))
    webhook_secret: str = field(default_factory=lambda: _str("TELEGRAM_WEBHOOK_SECRET"))
    notion_token: str = field(default_factory=lambda: _str("NOTION_TOKEN"))
    dev_bypass_token: str = field(default_factory=lambda: _str("MINIAPP_DEV_TOKEN"))

    # === Dari config var: beda antara laptop dan Heroku ====================
    base_url: str = field(default_factory=lambda: _str("BASE_URL").rstrip("/"))
    redis_url: str = field(
        default_factory=lambda: _str("REDIS_URL") or _str("REDIS_TLS_URL")
    )
    use_polling: bool = field(default_factory=lambda: _bool("USE_POLLING", False))

    # === Dipatok di kode ===================================================
    tz_name: str = TZ_NAME

    notion_version: str = NOTION_VERSION
    notion_database_id: str = NOTION_DATABASE_ID
    notion_data_source_id: str = NOTION_DATA_SOURCE_ID
    notion_rps: float = NOTION_RPS

    prop_title: str = PROP_TITLE
    prop_date: str = PROP_DATE
    prop_qabliyah: str = PROP_QABLIYAH
    prop_badiyah: str = PROP_BADIYAH
    prop_tilawah: str = PROP_TILAWAH
    prop_catatan: str = PROP_CATATAN
    prop_sumber: str = PROP_SUMBER
    sumber_enabled: bool = SUMBER_ENABLED

    tahajud_day: str = TAHAJUD_DAY

    jam_shalat: dict[str, str] = field(default_factory=lambda: dict(JAM_SHALAT))
    autofill: bool = AUTOFILL
    autofill_waktu: str = AUTOFILL_WAKTU
    autofill_cara: str = AUTOFILL_CARA
    autofill_catchup: int = AUTOFILL_CATCHUP
    tick_seconds: int = TICK_SECONDS

    ttl_rows: int = TTL_ROWS
    miniapp_max_age: int = MINIAPP_MAX_AGE
    log_level: str = LOG_LEVEL

    # === Turunan ===========================================================

    @property
    def tz(self) -> ZoneInfo:
        return ZoneInfo(self.tz_name)

    @property
    def prompt_target(self) -> int:
        return self.prompt_chat_id or self.owner_id

    @property
    def prompt_thread(self) -> int | None:
        """message_thread_id yang valid — Telegram menolaknya untuk chat pribadi."""
        if self.prompt_thread_id and self.prompt_target < 0:
            return self.prompt_thread_id
        return None

    @property
    def webapp_url(self) -> str:
        return f"{self.base_url}/app" if self.base_url else ""

    def prop_waktu(self, prayer: str) -> str:
        return f"{prayer} Waktu"

    def prop_cara(self, prayer: str) -> str:
        return f"{prayer} Cara"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


def reset_settings_cache() -> None:
    """Dipakai test ketika env diubah di tengah proses."""
    get_settings.cache_clear()
