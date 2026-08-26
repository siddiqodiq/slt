from datetime import date, timedelta

from app.miniapp.aggregate import aggregate, current_streak, make_filters
from app.notion import DayRecord

HARI_INI = date(2026, 8, 24)  # Senin


def rec(day, *, waktu="Awal waktu", cara="Masjid", prayers=None, **kwargs) -> DayRecord:
    prayers = prayers or {
        p: {"waktu": waktu, "cara": cara} for p in ("Subuh", "Dzuhur", "Ashar", "Maghrib", "Isya")
    }
    return DayRecord(day=day, page_id="x", prayers=prayers, **kwargs)


def test_persentase_awal_dan_berjamaah():
    records = [
        rec(HARI_INI - timedelta(days=1)),
        rec(HARI_INI, waktu="Akhir waktu", cara="Munfarid"),
    ]
    agg = aggregate(records, make_filters("7", today=HARI_INI))
    assert agg.summary["tercatat"] == 10
    assert agg.summary["pct_awal"] == 50.0
    assert agg.summary["pct_jamaah"] == 50.0
    assert agg.summary["kemungkinan"] == 35


def test_filter_hari_dalam_pekan():
    records = [rec(HARI_INI - timedelta(days=i)) for i in range(7)]
    senin = make_filters("7", today=HARI_INI, weekdays=(0,))
    agg = aggregate(records, senin)
    assert agg.summary["tercatat"] == 5  # hanya satu hari Senin dalam 7 hari


def test_filter_per_shalat_dan_kategori_waktu():
    records = [
        rec(
            HARI_INI,
            prayers={
                "Subuh": {"waktu": "Lewat waktu", "cara": "Munfarid"},
                "Dzuhur": {"waktu": "Awal waktu", "cara": "Masjid"},
                "Ashar": {"waktu": "Awal waktu", "cara": "Masjid"},
                "Maghrib": {"waktu": None, "cara": None},
                "Isya": {"waktu": "Tengah waktu", "cara": "Berjamaah"},
            },
        )
    ]
    hanya_subuh = aggregate(records, make_filters("7", today=HARI_INI, prayers=("Subuh",)))
    assert hanya_subuh.summary["tercatat"] == 1
    assert hanya_subuh.per_prayer[0]["counts"]["Lewat waktu"] == 1

    hanya_awal = aggregate(records, make_filters("7", today=HARI_INI, waktu=("Awal waktu",)))
    assert hanya_awal.summary["tercatat"] == 2


def test_hari_otomatis_bisa_dikecualikan():
    records = [rec(HARI_INI, sumber="Otomatis"), rec(HARI_INI - timedelta(days=1), sumber="Konfirmasi")]
    ikut = aggregate(records, make_filters("7", today=HARI_INI))
    tanpa = aggregate(records, make_filters("7", today=HARI_INI, exclude_auto=True))
    assert ikut.summary["tercatat"] == 10
    assert tanpa.summary["tercatat"] == 5
    assert ikut.summary["hari_otomatis"] == 1


def test_sunnah_diurutkan_dari_yang_paling_jarang():
    records = [
        rec(HARI_INI, checks={"Dhuha": True, "Tahajud": False}, qabliyah=["Subuh"], badiyah=[]),
        rec(HARI_INI - timedelta(days=1), checks={"Dhuha": True}, qabliyah=["Subuh"], badiyah=[]),
    ]
    agg = aggregate(records, make_filters("7", today=HARI_INI))
    counts = {item["name"]: item["count"] for item in agg.sunnah}
    assert counts["Dhuha"] == 2
    assert counts["Tahajud"] == 0
    assert agg.sunnah[0]["count"] <= agg.sunnah[-1]["count"]
    assert agg.sunnah[-1]["name"] in {"Dhuha", "Qabliyah Subuh"}


def test_tren_tilawah_dengan_rata_rata_bergerak():
    records = [rec(HARI_INI - timedelta(days=i), tilawah=7) for i in range(3)]
    agg = aggregate(records, make_filters("7", today=HARI_INI))
    assert agg.summary["tilawah_total"] == 21
    assert agg.tilawah[-1]["ma7"] == 3.0  # 21 halaman tersebar di 7 hari terakhir
    assert len(agg.tilawah) == 7


def test_streak_putus_saat_ada_lewat_waktu():
    by_day = {HARI_INI - timedelta(days=i): rec(HARI_INI - timedelta(days=i)) for i in range(4)}
    assert current_streak(by_day, HARI_INI) == 4
    by_day[HARI_INI - timedelta(days=2)] = rec(HARI_INI - timedelta(days=2), waktu="Lewat waktu")
    assert current_streak(by_day, HARI_INI) == 2


def test_deret_harian_menutupi_seluruh_rentang_termasuk_hari_kosong():
    agg = aggregate([rec(HARI_INI)], make_filters("30", today=HARI_INI))
    assert len(agg.harian) == 30
    assert agg.harian[0]["recorded"] == 0
    assert agg.harian[-1]["recorded"] > 0
