"""Render dashboard dengan data contoh ke satu file HTML mandiri.

Untuk melihat tata letak & grafik tanpa deploy atau membuka Telegram:

    python -m tools.preview [keluaran.html]
"""
from __future__ import annotations

import random
import sys
from datetime import date, timedelta
from pathlib import Path

from app.config import CHECKBOX_SUNNAH, PRAYERS, QABLIYAH_OPTIONS, WAKTU_OPTIONS
from app.miniapp import charts
from app.miniapp.aggregate import aggregate, make_filters
from app.notion import DayRecord

STATIC = Path(__file__).resolve().parent.parent / "app" / "static"


def contoh(hari: int = 60) -> list[DayRecord]:
    rng = random.Random(7)
    hari_ini = date.today()
    records = []
    for i in range(hari):
        day = hari_ini - timedelta(days=i)
        if rng.random() < 0.08:
            continue  # hari yang tidak tercatat sama sekali
        prayers = {}
        for prayer in PRAYERS:
            if rng.random() < 0.1:
                prayers[prayer] = {"waktu": None, "cara": None}
                continue
            prayers[prayer] = {
                "waktu": rng.choices(WAKTU_OPTIONS, weights=[5, 3, 2, 1])[0],
                "cara": rng.choices(["Masjid", "Berjamaah", "Munfarid"], weights=[3, 2, 4])[0],
            }
        records.append(
            DayRecord(
                day=day,
                page_id="contoh",
                prayers=prayers,
                qabliyah=[p for p in QABLIYAH_OPTIONS if rng.random() < 0.4],
                badiyah=[p for p in ("Dzuhur", "Maghrib", "Isya") if rng.random() < 0.3],
                checks={name: rng.random() < 0.35 for name in CHECKBOX_SUNNAH},
                tilawah=rng.choice([0, 0, 2, 3, 5, 8, 12]),
                catatan="contoh catatan refleksi" if rng.random() < 0.15 else "",
                sumber=rng.choice(["Konfirmasi", "Konfirmasi", "Otomatis", "Manual"]),
            )
        )
    return records


def main(out: str) -> int:
    from jinja2 import Environment, FileSystemLoader

    filters = make_filters("30")
    agg = aggregate(contoh(), filters)
    env = Environment(loader=FileSystemLoader(str(STATIC.parent / "templates")), autoescape=True)
    panel = env.get_template("partials/panel.html").render(
        agg=agg,
        filters=filters,
        svg_heatmap=charts.heatmap_svg(agg.heatmap),
        svg_prayer=charts.per_prayer_svg(agg.per_prayer),
        svg_sunnah=charts.sunnah_svg(agg.sunnah, filters.days),
        svg_tilawah=charts.tilawah_svg(agg.tilawah),
        waktu_options=WAKTU_OPTIONS,
    )
    css = (STATIC / "styles.css").read_text(encoding="utf-8")
    html = (
        "<!doctype html><html lang='id'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width, initial-scale=1'>"
        f"<title>Pratinjau Dashboard Ibadah</title><style>{css}</style></head><body>"
        "<header class='topbar'><h1>Dashboard Ibadah</h1>"
        f"<p class='sub'>Pratinjau data contoh · {filters.label()}</p></header>"
        f"{panel}</body></html>"
    )
    Path(out).write_text(html, encoding="utf-8")
    print(f"Ditulis ke {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1] if len(sys.argv) > 1 else "preview.html"))
