from datetime import date

from app import state
from app.gamify import xp_hari
from app.notion import DayRecord
from app.sedekah import baris_ket, parse_input, xp_ke
from tests.test_scheduler import FakeRuntime, dt

HARI = date(2026, 8, 26)


def test_parse_input_keterangan_dan_kemarin():
    a = parse_input(["kotak", "masjid"])
    assert (a.kemarin, a.keterangan) == (False, "kotak masjid")
    b = parse_input(["kemarin", "santunan", "anak", "yatim"])
    assert (b.kemarin, b.keterangan) == (True, "santunan anak yatim")
    assert baris_ket(parse_input([])) == "Sedekah"


def test_xp_sedekah_dari_frekuensi():
    assert [xp_ke(n) for n in range(1, 6)] == [3, 1, 1, 0, 0]
    assert xp_hari(DayRecord(day=HARI, sedekah_rutin=True, sedekah_n=1))["sedekah"] == 4
    assert xp_hari(DayRecord(day=HARI, sedekah_n=5))["sedekah"] == 5
    assert xp_hari(DayRecord(day=HARI))["sedekah"] == 0


class SedekahRepo:
    def __init__(self, rec=None):
        self.rec, self.writes = rec, []

    async def get_day(self, day):
        return self.rec

    async def set_sedekah_rutin(self, day, value=True):
        self.writes.append((day, value))


async def test_rutin_diisi_sekali_setelah_jamnya_dan_hanya_saat_on():
    from app.scheduler import PrayerScheduler

    rt = FakeRuntime(repo=SedekahRepo())
    sch = PrayerScheduler(rt)
    await sch.sedekah_tick(dt(HARI, "08:00"))
    assert rt.repo.writes == []  # masih OFF

    state.update(rutin_aktif=True)
    await sch.sedekah_tick(dt(HARI, "00:01"))
    assert rt.repo.writes == []  # belum 00:05
    await sch.sedekah_tick(dt(HARI, "00:06"))
    await sch.sedekah_tick(dt(HARI, "00:07"))
    assert rt.repo.writes == [(HARI, True)]


async def test_rutin_tidak_menimpa_nilai_yang_sudah_ada():
    from app.scheduler import PrayerScheduler

    state.update(rutin_aktif=True)
    rt = FakeRuntime(repo=SedekahRepo(DayRecord(day=HARI, sedekah_rutin=True)))
    await PrayerScheduler(rt).sedekah_tick(dt(HARI, "09:00"))
    assert rt.repo.writes == []


async def test_pengingat_bulanan_ke_japri_sekali_per_bulan():
    from app.scheduler import PrayerScheduler

    state.update(rutin_aktif=True)
    rt = FakeRuntime(repo=SedekahRepo(DayRecord(day=date(2026, 9, 1), sedekah_rutin=True)))
    sch = PrayerScheduler(rt)
    await sch.sedekah_tick(dt(date(2026, 9, 1), "07:59"))
    assert rt.sent == []
    await sch.sedekah_tick(dt(date(2026, 9, 1), "08:01"))
    await sch.sedekah_tick(dt(date(2026, 9, 1), "09:00"))
    assert len(rt.sent) == 1 and rt.sent[0][1] == "japri"


def test_hari_berjalan_sejak_tanggal_mulai():
    from app.sedekah import hari_berjalan

    assert hari_berjalan({"rutin_aktif": True, "rutin_mulai": "2026-01-01"}, date(2026, 11, 7)) == 311
    assert hari_berjalan({"rutin_aktif": False, "rutin_mulai": "2026-01-01"}, date(2026, 11, 7)) is None
