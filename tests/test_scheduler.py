"""Auto-fill shalat fardhu (§5).

Yang diuji di sini bukan "apakah ia menulis", melainkan kapan ia menolak
menulis — itu bagian yang merusak data kalau salah.
"""
from datetime import date, datetime, timedelta

import pytest

from app.cache import Cache, k_prompt_sent
from app.config import Settings
from app.scheduler import PrayerScheduler
from app.timeutil import tz

HARI = date(2026, 8, 26)


def dt(day: date, hhmm: str) -> datetime:
    jam, menit = (int(x) for x in hhmm.split(":"))
    return datetime(day.year, day.month, day.day, jam, menit, tzinfo=tz())


class FakeRepo:
    def __init__(self, existing=None):
        self.existing = existing or {}
        self.writes = []

    async def get_day(self, day):
        return self.existing.get(day)

    async def fetch_range(self, start, end):
        return [r for d, r in self.existing.items() if start <= d <= end]

    async def set_prayer(self, day, prayer, waktu, cara, sumber):
        self.writes.append((day, prayer, waktu, cara, sumber))


class FakeRec:
    def __init__(self, prayers):
        self.prayers = prayers

    def waktu(self, prayer):
        return (self.prayers.get(prayer) or {}).get("waktu")

    def cara(self, prayer):
        return (self.prayers.get(prayer) or {}).get("cara")


class FakeRuntime:
    def __init__(self, repo=None, settings=None):
        self.settings = settings or Settings()
        self.cache = Cache("")
        self.repo = repo or FakeRepo()
        self.sent = []

    async def notify_owner(self, text, reply_markup=None, *, silent=False):
        self.sent.append((text, silent))

    async def notify_private(self, text, reply_markup=None):
        self.sent.append((text, "japri"))


@pytest.fixture
def rt():
    return FakeRuntime()


def test_ambang_dibaca_dari_config(rt):
    times = PrayerScheduler(rt).times(HARI)
    assert times["Subuh"] == dt(HARI, "04:30")
    assert times["Isya"] == dt(HARI, "19:00")


async def test_mengisi_saat_ambang_lewat(rt):
    await PrayerScheduler(rt).tick(dt(HARI, "17:50"))
    assert (HARI, "Maghrib", "Awal waktu", "Munfarid", "Otomatis") in rt.repo.writes
    assert any("Maghrib" in teks for teks, _ in rt.sent)


async def test_pesan_autofill_dikirim_senyap(rt):
    """Lima kali sehari — pesannya tetap masuk, tapi tidak berbunyi."""
    await PrayerScheduler(rt).tick(dt(HARI, "17:50"))
    assert rt.sent and all(silent for _, silent in rt.sent)


async def test_tidak_menulis_sebelum_ambang(rt):
    await PrayerScheduler(rt).tick(dt(HARI, "17:49"))
    assert "Maghrib" not in [w[1] for w in rt.repo.writes]


async def test_tick_kedua_tidak_menulis_ulang(rt):
    sched = PrayerScheduler(rt)
    await sched.tick(dt(HARI, "11:50"))
    jumlah = len(rt.repo.writes)
    await sched.tick(dt(HARI, "11:50"))
    await sched.tick(dt(HARI, "12:30"))
    assert len(rt.repo.writes) == jumlah


@pytest.mark.parametrize(
    "isi",
    [
        {"waktu": "Akhir waktu", "cara": "Masjid"},
        {"waktu": "Tengah waktu"},
        # Lewat bot, Cara tidak pernah berdiri sendiri — tapi Notion boleh kamu
        # edit langsung, dan di sana bentuk ini mungkin.
        {"cara": "Masjid"},
    ],
)
async def test_tidak_menimpa_yang_sudah_kamu_catat(isi):
    repo = FakeRepo({HARI: FakeRec({"Maghrib": isi})})
    rt = FakeRuntime(repo=repo)
    await PrayerScheduler(rt).tick(dt(HARI, "18:00"))
    assert not any(w[1] == "Maghrib" for w in repo.writes)


async def test_boot_tengah_hari_menyusul_semua_yang_ambangnya_sudah_lewat(rt):
    """Deploy pukul 15:05 harus tetap mengisi Subuh dan Dzuhur hari itu.

    Ini yang dulu gagal: jendela umur 6 jam membuang Subuh (04:30) diam-diam.
    """
    await PrayerScheduler(rt).tick(dt(HARI, "15:05"))
    assert [w[1] for w in rt.repo.writes] == ["Subuh", "Dzuhur"]


async def test_isya_selepas_tengah_malam_masuk_ke_tanggal_ia_mulai(rt):
    kemarin = HARI - timedelta(days=1)
    await PrayerScheduler(rt).tick(dt(HARI, "00:20"))
    assert rt.repo.writes == [(kemarin, "Isya", "Awal waktu", "Munfarid", "Otomatis")]


async def test_kemarin_ditutup_setelah_ambang_subuh_hari_ini(rt):
    """Lewat Subuh, hari kemarin bukan lagi urusan auto-fill.

    Tanpa batas ini, tiap tick sepanjang hari akan terus menawarkan lima shalat
    kemarin untuk ditambal.
    """
    await PrayerScheduler(rt).tick(dt(HARI, "04:31"))
    assert {w[0] for w in rt.repo.writes} == {HARI}


async def test_klaim_gagal_berarti_tidak_menulis(rt):
    """Klaim gagal-tertutup: cache bermasalah menahan tulisan, bukan mendobelnya."""
    await rt.cache.claim(k_prompt_sent(HARI.isoformat(), "Dzuhur"))
    await PrayerScheduler(rt).tick(dt(HARI, "11:50"))
    assert not any(w[1] == "Dzuhur" for w in rt.repo.writes)


async def test_autofill_mati_tidak_menulis_apa_pun():
    rt = FakeRuntime(settings=Settings(autofill=False))
    await PrayerScheduler(rt).tick(dt(HARI, "20:00"))
    assert rt.repo.writes == []


async def test_ambang_salah_tulis_dilewati_bukan_menjatuhkan_tick():
    """Salah ketik di JAM_SHALAT tidak boleh mematikan empat shalat lainnya."""
    jam = dict(Settings().jam_shalat, Ashar="tigasore")
    rt = FakeRuntime(settings=Settings(jam_shalat=jam))
    await PrayerScheduler(rt).tick(dt(HARI, "19:30"))
    tertulis = [w[1] for w in rt.repo.writes]
    assert "Ashar" not in tertulis
    assert "Maghrib" in tertulis and "Isya" in tertulis
