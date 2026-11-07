"""Sedekah: parsing input `/sedekah` dan XP-nya. Bebas I/O.

Dua lapis:
* **Rutin** — donasi otomatis harian. Saklar ON/OFF disimpan di `state.json`;
  penjadwal mencentang kolom `Sedekah Rutin` tiap hari selama ON.
* **Tambahan** — dicatat manual lewat `/sedekah`, boleh beberapa kali sehari,
  masing-masing dengan keterangan.

Sengaja **tanpa nominal**, di Notion maupun di mana pun: yang dicatat hanya
"ada sedekah", dan XP dihitung dari frekuensi — yang dihargai kebiasaannya,
bukan besarnya uang.
"""
from __future__ import annotations

from dataclasses import dataclass

XP_RUTIN = 1  # per hari rutin tercatat
XP_TAMBAHAN_PERTAMA = 3
XP_TAMBAHAN_BERIKUT = 1
TAMBAHAN_BERIKUT_MAKS = 2  # sedekah ke-2 dan ke-3 yang masih dapat XP


@dataclass
class InputSedekah:
    kemarin: bool
    keterangan: str


def parse_input(args: list[str]) -> InputSedekah:
    """`/sedekah [kemarin] keterangan…`"""
    tokens = [t for t in args if t.strip()]
    kemarin = bool(tokens) and tokens[0].lower() == "kemarin"
    if kemarin:
        tokens = tokens[1:]
    return InputSedekah(kemarin, " ".join(tokens).strip())


def baris_ket(inp: InputSedekah) -> str:
    """Satu baris di kolom `Keterangan Sedekah`."""
    return inp.keterangan or "Sedekah"


def xp_ke(n: int) -> int:
    """XP yang didapat sedekah tambahan ke-n hari itu."""
    if n == 1:
        return XP_TAMBAHAN_PERTAMA
    if 2 <= n <= 1 + TAMBAHAN_BERIKUT_MAKS:
        return XP_TAMBAHAN_BERIKUT
    return 0


def hari_berjalan(st: dict, today) -> int | None:
    """Sudah berapa hari sedekah rutin berjalan tanpa putus (termasuk hari ini)."""
    from datetime import date

    if not st.get("rutin_aktif") or not st.get("rutin_mulai"):
        return None
    return (today - date.fromisoformat(st["rutin_mulai"])).days + 1


def xp_hari(rec) -> int:
    xp = XP_RUTIN if rec.sedekah_rutin else 0
    return xp + sum(xp_ke(i) for i in range(1, rec.sedekah_n + 1))
