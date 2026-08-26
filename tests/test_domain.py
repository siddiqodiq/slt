from datetime import date, datetime

import pytest

from app.config import Settings
from app.domain import sumber_merge
from app.timeutil import tz


def test_sentuhan_manual_menang_atas_autofill():
    """Auto-fill menyentuh tiap hari, jadi ia tidak boleh menutupi jejakmu.

    Kalau Otomatis yang menang, semua hari bertanda Otomatis dan filter
    "sembunyikan hari yang terisi otomatis" tidak menyaring apa pun.
    """
    assert sumber_merge(None, "Otomatis") == "Otomatis"
    assert sumber_merge("Otomatis", "Konfirmasi") == "Konfirmasi"
    assert sumber_merge("Otomatis", "Manual") == "Manual"
    assert sumber_merge("Manual", "Otomatis") == "Manual"
    assert sumber_merge("Konfirmasi", "Manual") == "Manual"


def test_konvensi_tahajud_wake_selalu_tanggal_saat_itu(jadwal_harian):
    from app.domain import catatan_day

    dini_hari = datetime(2026, 8, 25, 3, 10, tzinfo=tz())
    assert catatan_day(dini_hari, Settings(tahajud_day="wake")) == date(2026, 8, 25)


def test_konvensi_tahajud_previous_masuk_baris_kemarin_sebelum_subuh(jadwal_harian):
    from app.domain import catatan_day

    s = Settings(tahajud_day="previous")
    sebelum_subuh = datetime(2026, 8, 25, 3, 10, tzinfo=tz())
    sesudah_subuh = datetime(2026, 8, 25, 6, 0, tzinfo=tz())
    assert catatan_day(sebelum_subuh, s) == date(2026, 8, 24)
    assert catatan_day(sesudah_subuh, s) == date(2026, 8, 25)


def test_konvensi_tahajud_previous_tanpa_jadwal_pakai_batas_05_00():
    from app.domain import catatan_day

    s = Settings(tahajud_day="previous")
    assert catatan_day(datetime(2026, 8, 25, 4, 0, tzinfo=tz()), s) == date(2026, 8, 24)
    assert catatan_day(datetime(2026, 8, 25, 5, 30, tzinfo=tz()), s) == date(2026, 8, 25)


def test_topik_forum_hanya_dipakai_untuk_chat_grup():
    grup = Settings(prompt_chat_id=-1003966896650, prompt_thread_id=2704)
    japri = Settings(owner_id=42, prompt_thread_id=2704)
    assert grup.prompt_thread == 2704
    assert japri.prompt_thread is None  # Telegram menolak thread di chat pribadi
