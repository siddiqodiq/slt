from datetime import date, timedelta

from app.config import PRAYERS
from app.gamify import (
    baris_streak,
    compute_streak,
    lewat_info,
    pesan_lewat,
    rawan_semua,
)
from app.notion import DayRecord

HARI_INI = date(2026, 8, 24)


def rec(day, waktu="Awal waktu", **override) -> DayRecord:
    prayers = {p: {"waktu": waktu, "cara": "Masjid"} for p in PRAYERS}
    for p, w in override.items():
        prayers[p] = {"waktu": w, "cara": "Munfarid"} if w else {}
    return DayRecord(day=day, page_id="x", prayers=prayers)


def hari(n: int) -> date:
    return HARI_INI - timedelta(days=n)


def test_hari_berjalan_tidak_memutus_streak():
    records = [rec(hari(i)) for i in range(1, 5)] + [rec(HARI_INI, Isya=None)]
    info = compute_streak(records, HARI_INI)
    assert info.current == 4  # hari ini belum lengkap: tidak menambah, tidak memutus
    assert info.hari_ini == "berjalan"


def test_hari_ini_lengkap_ikut_dihitung():
    records = [rec(hari(i)) for i in range(5)]
    assert compute_streak(records, HARI_INI).current == 5


def test_satu_hari_bolong_dimaafkan_jatah_udzur():
    records = [rec(hari(i)) for i in range(6)]
    records[2] = rec(hari(2), Ashar="Lewat waktu")
    info = compute_streak(records, HARI_INI)
    assert info.current == 5
    assert info.udzur_terakhir == hari(2)


def test_dua_bolong_dalam_seminggu_memutus_tapi_rekor_tetap():
    records = [rec(hari(i)) for i in range(10)]
    records[5] = rec(hari(5), Subuh="Lewat waktu")
    records[2] = rec(hari(2), Subuh="Lewat waktu")
    info = compute_streak(records, HARI_INI)
    assert info.current == 2
    assert info.best == 6  # hari 9..6 (4) + hari 4..3 (2), udzur di hari 5
    assert info.putus_tanggal == hari(2)


def test_jatah_udzur_pulih_setelah_seminggu():
    records = [rec(hari(i)) for i in range(20)]
    records[15] = rec(hari(15), Isya="Lewat waktu")
    records[5] = rec(hari(5), Isya="Lewat waktu")
    assert compute_streak(records, HARI_INI).current == 18


def test_hari_tanpa_baris_dianggap_bolong():
    records = [rec(hari(i)) for i in range(5) if i not in (1, 2)]
    info = compute_streak(records, HARI_INI)
    assert info.current == 1


def test_lewat_beruntun_dan_sering():
    records = [rec(hari(i), Ashar="Lewat waktu" if i in (0, 1, 4) else "Awal waktu") for i in range(7)]
    info = lewat_info(records, "Ashar", HARI_INI)
    assert info.pekan_ini == 3
    assert info.beruntun == 2
    assert info.rawan
    assert [i.prayer for i in rawan_semua(records, HARI_INI)] == ["Ashar"]


def test_beruntun_dihitung_dari_kemarin_kalau_hari_ini_belum_lewat():
    records = [rec(hari(1), Subuh="Lewat waktu"), rec(hari(2), Subuh="Lewat waktu"), rec(HARI_INI, Subuh=None)]
    assert lewat_info(records, "Subuh", HARI_INI).beruntun == 2


def test_pesan_lewat_menyebut_pola_hanya_kalau_rawan():
    sekali = lewat_info([rec(HARI_INI, Dzuhur="Lewat waktu")], "Dzuhur", HARI_INI)
    assert "⚠️" not in pesan_lewat(sekali, HARI_INI)
    sering = lewat_info([rec(hari(i), Dzuhur="Lewat waktu") for i in range(3)], "Dzuhur", HARI_INI)
    teks = pesan_lewat(sering, HARI_INI)
    assert "3 hari berturut" in teks and "💡" in teks


def test_baris_streak_putus_kemarin_tetap_menyebut_rekor():
    records = [rec(hari(i)) for i in range(2, 12)]
    records[3] = rec(hari(5), Maghrib="Lewat waktu")  # udzur terpakai
    records.append(rec(hari(1), Maghrib="Lewat waktu"))
    info = compute_streak(records, HARI_INI)
    assert info.current == 0
    assert "Rekormu tetap" in baris_streak(info, HARI_INI)


def test_streak_tahajud_hari_ini_belum_dicentang_tidak_memutus():
    from app.gamify import malam_pekan_ini, tahajud_streak

    records = [DayRecord(day=hari(i), checks={"Tahajud": i != 0}) for i in range(5)]
    info = tahajud_streak(records, HARI_INI)
    assert info.current == 4
    assert malam_pekan_ini(records, HARI_INI) == 4
    records[0] = DayRecord(day=HARI_INI, checks={"Tahajud": True})
    assert tahajud_streak(records, HARI_INI).current == 5


def test_xp_lewat_waktu_nol_dan_otomatis_separuh():
    from app.gamify import xp_hari

    penuh = xp_hari(rec(HARI_INI))  # 5x awal waktu di masjid
    assert penuh["shalat"] == 15 and penuh["jamaah"] == 10 and penuh["bonus"] == 5
    lewat = xp_hari(rec(HARI_INI, Ashar="Lewat waktu"))
    assert lewat["shalat"] == 12 and lewat["bonus"] == 0
    oto = DayRecord(day=HARI_INI, prayers=rec(HARI_INI).prayers, sumber="Otomatis")
    assert xp_hari(oto)["shalat"] == 7


def test_level_naik_dan_progres():
    from app.gamify import LEVELS, compute_level

    records = [DayRecord(day=hari(i), tilawah=20) for i in range(6)]  # 120 XP
    lv = compute_level(records, HARI_INI)
    assert lv.xp == 120 and lv.nama == LEVELS[1][1]
    assert 0 < lv.progres < 1 and lv.kurang == LEVELS[2][0] - 120
    assert lv.xp_hari_ini == 20 and lv.xp_kemarin == 100


def test_avatar_tiap_level_valid():
    import xml.etree.ElementTree as ET

    from app.gamify import LEVELS
    from app.miniapp.avatar import pohon_svg

    for i in range(len(LEVELS)):
        ET.fromstring(pohon_svg(i, 0.5, sunnah_pekan=8, streak_tahajud=3, streak_shalat=4))


def test_hanya_awal_waktu_berxp_tapi_jamaah_tetap():
    from app.gamify import xp_hari

    x = xp_hari(rec(HARI_INI, waktu="Tengah waktu"))  # 5x tengah waktu di masjid
    assert x["shalat"] == 0 and x["jamaah"] == 10 and "catatan" not in x
