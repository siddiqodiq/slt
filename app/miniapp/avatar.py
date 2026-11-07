"""Avatar "Pohon Amal": SVG yang tumbuh mengikuti level.

“Perumpamaan kalimat yang baik seperti pohon yang baik, akarnya teguh dan
cabangnya menjulang ke langit; ia memberikan buahnya pada setiap musim.”
(QS Ibrahim: 24–25)

Dirakit di Python seperti grafik lain — tidak ada aset gambar atau JS pihak
ketiga. Semua posisi tetap (bukan acak), jadi pohon yang sama selalu tampak sama
dan tes bisa membandingkan keluarannya.

Yang memengaruhi gambar:
* **level** → tahap tumbuh (benih … pohon bercahaya)
* **progres di dalam level** → kerimbunan daun di tahap yang sama
* **sunnah 7 hari** → jumlah buah (mulai tahap Berbuah) / bunga (sebelumnya)
* **streak tahajud** → bulan sabit & bintang di langit
* **streak shalat** → matahari pagi di belakang pohon
* **sedekah rutin aktif** → mata air kecil di kaki pohon (amal jariyah)
* **hari bersedekah tambahan 7 hari** → burung yang hinggap / terbang
"""
from __future__ import annotations

from math import cos, pi, sin

# Skala pohon per tahap (Pohon Muda … Rindang lebih kecil, sisanya penuh).
_SKALA = {3: 0.74, 4: 0.86, 5: 0.94}

# Titik-titik gumpalan daun (cx, cy, r) dari dalam ke luar. Tahap yang lebih
# tinggi memakai lebih banyak titik; progres di dalam level menambah sisanya.
_KANOPI = [
    (100, 78, 30), (76, 90, 24), (124, 90, 24), (100, 56, 24), (82, 64, 20),
    (118, 64, 20), (60, 104, 18), (140, 104, 18), (100, 36, 18), (66, 76, 16),
    (134, 76, 16), (88, 44, 15), (112, 44, 15), (48, 92, 14), (152, 92, 14),
    (100, 102, 22),
]
_BUAH = [
    (84, 92), (116, 96), (100, 70), (70, 104), (132, 104), (92, 54), (110, 52),
    (62, 84), (140, 84), (100, 98), (78, 70), (124, 70),
]


def _f(x: float) -> str:
    return f"{x:.1f}".rstrip("0").rstrip(".")


def _langit(streak_tahajud: int, streak_shalat: int) -> list[str]:
    out: list[str] = []
    if streak_shalat > 0:
        r = min(14 + streak_shalat * 0.6, 26)
        out.append(f'<circle class="av-matahari" cx="160" cy="40" r="{_f(r)}"/>')
    if streak_tahajud > 0:
        out.append(
            '<path class="av-bulan" d="M44 23 A12 12 0 1 0 44 45 A10 10 0 1 1 44 23 Z"/>'
        )
        bintang = [(22, 60), (60, 18), (70, 46), (16, 20), (52, 66), (80, 24)]
        for i, (x, y) in enumerate(bintang[: min(streak_tahajud, len(bintang))]):
            out.append(
                f'<circle class="av-bintang" style="animation-delay:{i * 0.4:.1f}s" '
                f'cx="{x}" cy="{y}" r="1.6"/>'
            )
    return out


# Tempat burung hinggap di tepi kanopi (pohon) atau terbang di langit (tahap awal).
_HINGGAP = [(72, 56), (128, 60), (100, 30), (52, 86), (148, 88), (86, 38), (116, 40)]
_TERBANG = [(120, 30), (140, 52), (96, 22), (150, 22), (78, 40), (112, 58), (132, 14)]


def _burung(x: float, y: float, hinggap: bool, i: int) -> str:
    if hinggap:
        return (
            f'<g class="av-burung hinggap" style="animation-delay:{i * 0.5:.1f}s" '
            f'transform="translate({_f(x)} {_f(y)})">'
            '<ellipse cx="0" cy="0" rx="5" ry="3.6"/><circle cx="4" cy="-3" r="2.4"/>'
            '<path class="av-paruh" d="M6.2 -3.2 l2.6 0.8 l-2.6 0.8 Z"/></g>'
        )
    return (
        f'<path class="av-burung terbang" style="animation-delay:{i * 0.3:.1f}s" '
        f'd="M{_f(x - 6)} {_f(y)} q3 -4 6 0 q3 -4 6 0"/>'
    )


def _mata_air() -> list[str]:
    return [
        '<ellipse class="av-air" cx="148" cy="177" rx="18" ry="4.5"/>',
        '<ellipse class="av-air-kilau" cx="143" cy="176" rx="6" ry="1.4"/>',
        '<circle class="av-tetes" cx="150" cy="168" r="1.8"/>',
        '<circle class="av-tetes" style="animation-delay:.7s" cx="144" cy="166" r="1.4"/>',
    ]


def _tanah() -> str:
    return '<ellipse class="av-tanah" cx="100" cy="176" rx="70" ry="10"/>'


def _benih() -> list[str]:
    return [
        '<path class="av-tanah" d="M70 176 Q100 150 130 176 Z"/>',
        '<ellipse class="av-batang" cx="100" cy="162" rx="7" ry="5"/>',
        '<path class="av-daun" d="M100 158 q-2 -8 4 -12 q2 8 -4 12 Z"/>',
    ]


def _tunas(progres: float) -> list[str]:
    tinggi = 30 + 14 * progres
    top = 172 - tinggi
    return [
        f'<path class="av-batang-garis" d="M100 172 Q98 {_f(172 - tinggi / 2)} 100 {_f(top)}"/>',
        f'<path class="av-daun" d="M100 {_f(top + 6)} q-20 -6 -24 -20 q18 0 24 20 Z"/>',
        f'<path class="av-daun" d="M100 {_f(top + 2)} q20 -6 24 -20 q-18 0 -24 20 Z"/>',
    ]


def _semai(progres: float) -> list[str]:
    tinggi = 56 + 20 * progres
    top = 172 - tinggi
    out = [f'<path class="av-batang-garis tebal" d="M100 172 Q96 {_f(172 - tinggi / 2)} 100 {_f(top)}"/>']
    pasang = 2 + round(2 * progres)
    for i in range(pasang):
        y = top + 8 + i * 16
        s = 1 - i * 0.12
        out.append(f'<path class="av-daun" d="M100 {_f(y)} q{_f(-24 * s)} -4 {_f(-30 * s)} -18 q{_f(22 * s)} -2 {_f(30 * s)} 18 Z"/>')
        out.append(f'<path class="av-daun" d="M100 {_f(y + 6)} q{_f(24 * s)} -4 {_f(30 * s)} -18 q{_f(-22 * s)} -2 {_f(-30 * s)} 18 Z"/>')
    return out


def _pohon(stage: int, progres: float, buah: int) -> list[str]:
    """stage 3..7 (Pohon Muda … Bercahaya)."""
    skala = _SKALA.get(stage, 1.0)
    dasar = {3: 5, 4: 9, 5: 11, 6: 13, 7: 14}[stage]
    n = min(len(_KANOPI), dasar + round(progres * 3))

    out: list[str] = [f'<g transform="translate(100 176) scale({skala}) translate(-100 -176)">']
    if stage >= 6:  # akar teguh
        out.append('<path class="av-akar" d="M100 170 q-18 6 -36 8 M100 170 q16 7 34 8 M100 172 q-4 6 -10 8"/>')
    # batang & dua cabang
    out.append('<path class="av-batang" d="M92 176 Q96 130 94 104 L106 104 Q104 130 108 176 Z"/>')
    out.append('<path class="av-batang-garis tebal" d="M98 118 Q84 106 74 96 M102 112 Q116 100 126 92"/>')

    out.append('<g class="av-kanopi">')
    for cx, cy, r in _KANOPI[:n]:
        out.append(f'<circle class="av-daun" cx="{cx}" cy="{cy}" r="{r}"/>')
    # kilau di beberapa gumpalan supaya tidak datar
    for cx, cy, r in _KANOPI[: max(3, n // 3)]:
        out.append(f'<circle class="av-daun-terang" cx="{_f(cx - r * 0.3)}" cy="{_f(cy - r * 0.35)}" r="{_f(r * 0.45)}"/>')
    if stage >= 5:
        for i, (x, y) in enumerate(_BUAH[:buah]):
            out.append(f'<circle class="av-buah" style="animation-delay:{i * 0.15:.2f}s" cx="{x}" cy="{y}" r="5"/>')
    else:
        for i, (x, y) in enumerate(_BUAH[: min(buah, 6)]):
            out.append(f'<circle class="av-bunga" cx="{x}" cy="{y}" r="3"/>')
    out.append("</g></g>")
    return out


def _cahaya() -> list[str]:
    sinar = []
    for i in range(12):
        a = i * pi / 6
        x1, y1 = 100 + 70 * cos(a), 90 + 70 * sin(a)
        x2, y2 = 100 + 84 * cos(a), 90 + 84 * sin(a)
        sinar.append(f"M{_f(x1)} {_f(y1)} L{_f(x2)} {_f(y2)}")
    return [
        '<circle class="av-halo" cx="100" cy="90" r="72"/>',
        f'<path class="av-sinar" d="{" ".join(sinar)}"/>',
    ]


def pohon_svg(
    level_idx: int,
    progres: float,
    *,
    sunnah_pekan: int = 0,
    streak_tahajud: int = 0,
    streak_shalat: int = 0,
    mata_air: bool = False,
    burung: int = 0,
) -> str:
    progres = max(0.0, min(1.0, progres))
    buah = min(sunnah_pekan, len(_BUAH))
    langit: list[str] = _langit(streak_tahajud, streak_shalat)
    if level_idx >= 7:
        langit += _cahaya()
    if level_idx == 0:
        pohon = _benih()
    elif level_idx == 1:
        pohon = _tunas(progres)
    elif level_idx == 2:
        pohon = _semai(progres)
    else:
        pohon = _pohon(min(level_idx, 7), progres, buah)
    hinggap = level_idx >= 3
    titik = _HINGGAP if hinggap else _TERBANG
    skala = _SKALA.get(level_idx, 1.0)
    burung_svg = []
    for i, (x, y) in enumerate(titik[: max(0, min(burung, len(titik)))]):
        if hinggap:  # ikut mengecil bersama pohon di tahap awal
            x, y = 100 + (x - 100) * skala, 176 - (176 - y) * skala
        burung_svg.append(_burung(x, y, hinggap, i))
    air = "".join(_mata_air()) if mata_air else ""
    return (
        '<svg class="avatar" viewBox="0 0 200 190" role="img" '
        f'aria-label="Pohon amal tahap {level_idx + 1}">'
        f'{"".join(langit)}{_tanah()}{air}'
        f'<g class="av-goyang">{"".join(pohon)}{"".join(burung_svg) if hinggap else ""}</g>'
        f'{"" if hinggap else "".join(burung_svg)}</svg>'
    )
