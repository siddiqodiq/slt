"""Grafik sebagai SVG yang dirakit di Python — tanpa toolchain JavaScript (§2).

Warna diambil dari CSS custom property supaya ikut tema Telegram (terang/gelap).
"""
from __future__ import annotations

from datetime import date
from html import escape

from ..config import WAKTU_OPTIONS

WAKTU_CLASS = {
    "Awal waktu": "c-awal",
    "Tengah waktu": "c-tengah",
    "Akhir waktu": "c-akhir",
    "Lewat waktu": "c-lewat",
}
HARI_PENDEK = ("Sen", "Sel", "Rab", "Kam", "Jum", "Sab", "Min")
BULAN_PENDEK = ("Jan", "Feb", "Mar", "Apr", "Mei", "Jun", "Jul", "Agu", "Sep", "Okt", "Nov", "Des")


def _fmt_tgl(day: date) -> str:
    return f"{day.day} {BULAN_PENDEK[day.month - 1]}"


def quality_bucket(quality: float | None) -> str:
    if quality is None:
        return "q0"
    if quality >= 0.85:
        return "q4"
    if quality >= 0.6:
        return "q3"
    if quality >= 0.35:
        return "q2"
    return "q1"


def heatmap_svg(cells: list[dict]) -> str:
    """Satu kotak per hari; polanya terbaca tanpa membaca angka (§7)."""
    if not cells:
        return '<p class="kosong">Belum ada data pada rentang ini.</p>'
    size, gap, left, top = 13, 3, 26, 16
    start = cells[0]["date"]
    offset = start.weekday()
    weeks = (offset + len(cells) + 6) // 7
    width = left + weeks * (size + gap)
    height = top + 7 * (size + gap) + 4

    parts = [
        f'<svg class="chart heatmap" viewBox="0 0 {width} {height}" '
        f'preserveAspectRatio="xMinYMin meet" role="img" aria-label="Heatmap kualitas shalat harian">'
    ]
    for row in (0, 2, 4):
        y = top + row * (size + gap) + size - 2
        parts.append(f'<text class="tick" x="0" y="{y}">{HARI_PENDEK[row]}</text>')

    last_month = None
    for index, cell in enumerate(cells):
        pos = offset + index
        col, row = divmod(pos, 7)
        x = left + col * (size + gap)
        y = top + row * (size + gap)
        day: date = cell["date"]
        if day.month != last_month and row <= 1:
            parts.append(f'<text class="tick" x="{x}" y="10">{BULAN_PENDEK[day.month - 1]}</text>')
            last_month = day.month
        klass = quality_bucket(cell["quality"])
        extra = " auto" if cell.get("auto") else ""
        tip = (
            f"{_fmt_tgl(day)} · {cell['recorded']}/5 tercatat"
            + (" · otomatis" if cell.get("auto") else "")
            + (" · ada catatan" if cell.get("catatan") else "")
        )
        parts.append(
            f'<rect class="cell {klass}{extra}" x="{x}" y="{y}" width="{size}" height="{size}" rx="3">'
            f"<title>{escape(tip)}</title></rect>"
        )
    parts.append("</svg>")
    return "".join(parts)


def per_prayer_svg(rows: list[dict]) -> str:
    """Lima baris, tiap baris dipecah jadi proporsi Awal/Tengah/Akhir/Lewat (§7)."""
    if not rows:
        return '<p class="kosong">Tidak ada shalat tercatat pada filter ini.</p>'
    bar_h, gap, label_w = 22, 12, 62
    width, height = 320, len(rows) * (bar_h + gap)
    bar_w = width - label_w - 34
    parts = [
        f'<svg class="chart bars" viewBox="0 0 {width} {height}" preserveAspectRatio="xMinYMin meet" '
        f'role="img" aria-label="Rincian per shalat">'
    ]
    for i, row in enumerate(rows):
        y = i * (bar_h + gap)
        parts.append(f'<text class="label" x="0" y="{y + bar_h - 6}">{escape(row["prayer"])}</text>')
        total = row["total"]
        if not total:
            parts.append(
                f'<rect class="cell q0" x="{label_w}" y="{y}" width="{bar_w}" height="{bar_h}" rx="4"/>'
                f'<text class="tick" x="{label_w + 6}" y="{y + bar_h - 7}">belum ada data</text>'
            )
            continue
        x = label_w
        for waktu in WAKTU_OPTIONS:
            count = row["counts"].get(waktu, 0)
            if not count:
                continue
            seg = bar_w * count / total
            parts.append(
                f'<rect class="{WAKTU_CLASS[waktu]}" x="{x:.1f}" y="{y}" width="{seg:.1f}" '
                f'height="{bar_h}" rx="2"><title>{escape(f"{row["prayer"]} · {waktu}: {count}")}</title></rect>'
            )
            x += seg
        pct_awal = row["pct"].get("Awal waktu", 0)
        parts.append(f'<text class="tick" x="{width - 30}" y="{y + bar_h - 7}">{pct_awal:.0f}%</text>')
    parts.append("</svg>")
    return "".join(parts)


def sunnah_svg(items: list[dict], days: int) -> str:
    """Diurutkan dari yang paling jarang — yang paling layak diperbaiki di atas (§7)."""
    if not items:
        return '<p class="kosong">Belum ada sunnah tercatat.</p>'
    row_h, gap, label_w = 18, 6, 108
    width = 320
    height = len(items) * (row_h + gap)
    bar_w = width - label_w - 30
    top = max([i["count"] for i in items] + [1])
    parts = [
        f'<svg class="chart sunnah" viewBox="0 0 {width} {height}" preserveAspectRatio="xMinYMin meet" '
        f'role="img" aria-label="Frekuensi sunnah">'
    ]
    for i, item in enumerate(items):
        y = i * (row_h + gap)
        parts.append(f'<text class="label" x="0" y="{y + row_h - 5}">{escape(item["name"])}</text>')
        w = bar_w * item["count"] / top
        parts.append(
            f'<rect class="track" x="{label_w}" y="{y + 3}" width="{bar_w}" height="{row_h - 6}" rx="3"/>'
            f'<rect class="fill" x="{label_w}" y="{y + 3}" width="{max(w, 0):.1f}" height="{row_h - 6}" rx="3">'
            f'<title>{escape(f"{item['name']}: {item['count']} dari {days} hari")}</title></rect>'
            f'<text class="tick" x="{width - 26}" y="{y + row_h - 5}">{item["count"]}</text>'
        )
    parts.append("</svg>")
    return "".join(parts)


def tilawah_svg(points: list[dict]) -> str:
    """Halaman per hari + garis rata-rata bergerak 7 hari (§7)."""
    if not points:
        return '<p class="kosong">Belum ada tilawah tercatat.</p>'
    width, height = 320, 120
    pad_l, pad_b, pad_t = 24, 16, 8
    plot_w, plot_h = width - pad_l - 6, height - pad_b - pad_t
    top = max([p["pages"] for p in points] + [p["ma7"] for p in points] + [1])
    n = len(points)
    step = plot_w / max(n, 1)

    def y_of(value: float) -> float:
        return pad_t + plot_h - (value / top) * plot_h

    parts = [
        f'<svg class="chart line" viewBox="0 0 {width} {height}" preserveAspectRatio="xMinYMin meet" '
        f'role="img" aria-label="Tren tilawah">'
    ]
    parts.append(f'<line class="axis" x1="{pad_l}" y1="{pad_t + plot_h}" x2="{width - 4}" y2="{pad_t + plot_h}"/>')
    parts.append(f'<text class="tick" x="0" y="{pad_t + 8}">{top:g}</text>')
    parts.append(f'<text class="tick" x="0" y="{pad_t + plot_h}">0</text>')

    bar_w = max(step * 0.62, 1.2)
    for i, point in enumerate(points):
        if not point["pages"]:
            continue
        x = pad_l + i * step + (step - bar_w) / 2
        y = y_of(point["pages"])
        parts.append(
            f'<rect class="fill" x="{x:.1f}" y="{y:.1f}" width="{bar_w:.1f}" '
            f'height="{(pad_t + plot_h - y):.1f}" rx="1">'
            f'<title>{escape(f"{_fmt_tgl(point["date"])}: {point["pages"]} halaman")}</title></rect>'
        )
    ma = " ".join(
        f"{pad_l + i * step + step / 2:.1f},{y_of(p['ma7']):.1f}" for i, p in enumerate(points)
    )
    parts.append(f'<polyline class="ma" points="{ma}"/>')
    parts.append(f'<text class="tick" x="{pad_l}" y="{height - 4}">{_fmt_tgl(points[0]["date"])}</text>')
    parts.append(
        f'<text class="tick" text-anchor="end" x="{width - 4}" y="{height - 4}">'
        f'{_fmt_tgl(points[-1]["date"])}</text>'
    )
    parts.append("</svg>")
    return "".join(parts)
