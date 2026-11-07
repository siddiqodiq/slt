"""Gamifikasi: streak yang memaafkan + kata motivasi saat shalat sering lewat waktu.

Bebas I/O seperti `domain.py` — semua dihitung dari baris mentah saat dibutuhkan,
tidak ada yang disimpan di Notion.

**Kenapa streak-nya "memaafkan".** §7 brief memperingatkan bahwa streak yang putus
bisa terasa seperti kegagalan dan membuat orang berhenti mencatat. Maka:

* Satu hari "bolong" (ada shalat Lewat waktu / tidak lengkap) dimaafkan sebagai
  **jatah udzur** — streak tidak bertambah hari itu, tapi juga tidak putus. Jatahnya
  satu per `UDZUR_JEDA` hari.
* **Rekor terbaik** selalu ikut ditampilkan, jadi yang terasa saat putus adalah
  "rekor kamu 23 hari", bukan "kembali ke 0".
* **Hari berjalan tidak pernah memutus streak**: Isya yang belum masuk bukan
  kegagalan. Hari ini hanya ikut dihitung kalau sudah lengkap tanpa Lewat waktu.

Baris auto-fill (`Awal waktu`) dihitung apa adanya: alurnya memang "terisi
otomatis, koreksi kalau berbeda", jadi yang tidak dikoreksi dianggap benar.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from . import sedekah
from .config import PRAYERS

LEWAT = "Lewat waktu"
UDZUR_JEDA = 7  # satu jatah udzur per sekian hari
SERING_LEWAT = 3  # >= sekian kali dalam 7 hari = "sering"
BERUNTUN_LEWAT = 2  # >= sekian hari berturut = "sedang beruntun"
MILESTONES = (3, 7, 14, 21, 30, 40, 60, 100, 150, 200, 365)


# --- status harian ------------------------------------------------------------

def day_status(rec, *, partial: bool = False) -> str:
    """'tepat' | 'lewat' | 'kosong' | 'berjalan'.

    `partial=True` untuk hari ini: shalat yang belum tercatat tidak dihitung
    kosong, sehingga hari yang masih berjalan menjadi 'berjalan', bukan bolong.
    """
    waktus = [rec.waktu(p) if rec else None for p in PRAYERS]
    if any(w == LEWAT for w in waktus):
        return "lewat"
    if any(w is None for w in waktus):
        return "berjalan" if partial else "kosong"
    return "tepat"


@dataclass
class StreakInfo:
    current: int = 0
    best: int = 0
    udzur_terakhir: date | None = None  # hari bolong yang dimaafkan dalam streak berjalan
    putus_tanggal: date | None = None  # hari streak terakhir kali putus
    putus_panjang: int = 0  # panjang streak yang putus waktu itu
    hari_ini: str = "berjalan"

    @property
    def milestone(self) -> int | None:
        return self.current if self.current in MILESTONES else None

    @property
    def berikutnya(self) -> int | None:
        return next((m for m in MILESTONES if m > self.current), None)


def tahajud_status(rec, *, partial: bool = False) -> str:
    """Tahajud tercatat di baris tanggal bangun (TAHAJUD_DAY=wake), jadi baris
    hari ini yang belum tercentang masih 'berjalan' — mungkin dicentang nanti."""
    if rec and rec.checks.get("Tahajud"):
        return "tepat"
    return "berjalan" if partial else "kosong"


def compute_streak(records, today: date, status_fn=day_status) -> StreakInfo:
    """Hitung streak berjalan dan rekor dari seluruh riwayat sampai `today`.

    Dihitung maju dari baris tertua supaya rekor dan streak berjalan memakai
    aturan yang persis sama. `status_fn` menentukan apa yang dihitung: shalat
    wajib tepat waktu (default) atau tahajud.
    """
    by_day = {r.day: r for r in records if r.day <= today}
    info = StreakInfo()
    if not by_day:
        return info

    run = 0
    udzur: date | None = None
    day = min(by_day)
    while day <= today:
        status = status_fn(by_day.get(day), partial=(day == today))
        if day == today:
            info.hari_ini = status
        if status == "tepat":
            run += 1
        elif status == "berjalan":
            pass
        elif run > 0 and (udzur is None or (day - udzur).days >= UDZUR_JEDA):
            udzur = day  # dimaafkan: tidak menambah, tidak memutus
        else:
            if run > 0:
                info.putus_tanggal, info.putus_panjang = day, run
            run, udzur = 0, None
        info.best = max(info.best, run)
        day += timedelta(days=1)

    info.current = run
    info.udzur_terakhir = udzur
    return info


# --- pola lewat waktu ---------------------------------------------------------

@dataclass
class LewatInfo:
    prayer: str
    pekan_ini: int  # kali Lewat waktu dalam 7 hari terakhir (termasuk hari ini)
    beruntun: int  # hari berturut-turut terakhir shalat ini Lewat waktu

    @property
    def rawan(self) -> bool:
        return self.pekan_ini >= SERING_LEWAT or self.beruntun >= BERUNTUN_LEWAT


def lewat_info(records, prayer: str, today: date) -> LewatInfo:
    by_day = {r.day: r for r in records}
    pekan = sum(
        1
        for i in range(7)
        if (r := by_day.get(today - timedelta(days=i))) and r.waktu(prayer) == LEWAT
    )
    # Beruntun dihitung dari hari ini kalau hari ini sudah Lewat, kalau belum dari kemarin.
    cursor = today
    rec_today = by_day.get(today)
    if not (rec_today and rec_today.waktu(prayer) == LEWAT):
        cursor = today - timedelta(days=1)
    beruntun = 0
    while (r := by_day.get(cursor)) and r.waktu(prayer) == LEWAT:
        beruntun += 1
        cursor -= timedelta(days=1)
    return LewatInfo(prayer, pekan, beruntun)


def rawan_semua(records, today: date) -> list[LewatInfo]:
    """Shalat yang sedang/sering lewat waktu, paling parah di atas."""
    infos = [lewat_info(records, p, today) for p in PRAYERS]
    return sorted((i for i in infos if i.rawan), key=lambda i: (-i.pekan_ini, -i.beruntun))


# --- kata-kata ----------------------------------------------------------------
# Dipilih deterministik per tanggal (bukan acak) supaya tes stabil dan pesan
# berganti tiap hari tanpa perlu menyimpan apa pun.

DALIL_WAKTU = (
    "“Sesungguhnya shalat itu kewajiban yang ditentukan waktunya atas orang-orang beriman.” (QS An-Nisa: 103)",
    "Ditanya amal apa yang paling dicintai Allah, Nabi ﷺ menjawab: “Shalat pada waktunya.” (HR Bukhari & Muslim)",
    "“Amal yang paling dicintai Allah adalah yang paling konsisten, walaupun sedikit.” (HR Bukhari & Muslim)",
    "“Jagalah shalat-shalat dan shalat wustha.” (QS Al-Baqarah: 238)",
)

TIPS_LEWAT = {
    "Subuh": "Coba tidur lebih awal dan taruh alarm agak jauh dari kasur, biar harus bangun untuk mematikannya.",
    "Dzuhur": "Blok 15 menit di kalender kerja tepat setelah adzan, anggap itu rapat yang tidak bisa digeser.",
    "Ashar": "Ashar sering kalah oleh sisa kerjaan sore — shalat dulu, baru selesaikan; kerjaannya tetap menunggu.",
    "Maghrib": "Waktunya pendek. Usahakan sudah di tempat (atau dekat masjid) sebelum 17:50.",
    "Isya": "Jangan tunggu ngantuk — shalat Isya dulu sebelum mulai nonton, scroll, atau makan malam.",
}

PENYEMANGAT = (
    "Tidak apa, yang penting tetap dicatat dengan jujur. Besok kesempatan baru.",
    "Satu yang terlewat bukan akhir. Yang dihitung Allah juga usahamu untuk kembali.",
    "Catatan jujur seperti ini justru yang bikin pola kelihatan — dan bisa diperbaiki.",
)


def _pilih(items: tuple[str, ...], day: date, salt: int = 0) -> str:
    return items[(day.toordinal() + salt) % len(items)]


def pesan_lewat(info: LewatInfo, day: date) -> str:
    """Respons saat kamu baru saja menandai sebuah shalat Lewat waktu."""
    lines = [f"🤍 {_pilih(PENYEMANGAT, day)}"]
    if info.beruntun >= BERUNTUN_LEWAT:
        lines.append(f"⚠️ {info.prayer} sudah <b>{info.beruntun} hari berturut</b> lewat waktu.")
    elif info.pekan_ini >= SERING_LEWAT:
        lines.append(f"⚠️ {info.prayer} lewat waktu <b>{info.pekan_ini}× dalam 7 hari</b>.")
    if info.rawan:
        lines.append(f"💡 {TIPS_LEWAT.get(info.prayer, '')}")
        lines.append(f"<i>{_pilih(DALIL_WAKTU, day, PRAYERS.index(info.prayer))}</i>")
    return "\n".join(lines)


def pengingat_rawan(info: LewatInfo, day: date) -> str:
    """Tambahan untuk pesan saat waktu shalat masuk, khusus shalat yang rawan."""
    if info.beruntun >= BERUNTUN_LEWAT:
        sebab = f"{info.beruntun} hari terakhir {info.prayer} lewat waktu"
    else:
        sebab = f"pekan ini {info.prayer} {info.pekan_ini}× lewat waktu"
    return (
        f"⏰ <b>Sudah masuk waktu {info.prayer}.</b> Catatan: {sebab} — yuk sekarang, "
        "sebelum kesibukan menyela.\n"
        f"💡 {TIPS_LEWAT.get(info.prayer, '')}"
    )


def baris_streak(info: StreakInfo, today: date) -> str:
    """Satu-dua baris streak untuk /hariini, /rekap, dan sapaan Subuh."""
    if info.current == 0:
        if info.putus_panjang and info.putus_tanggal and (today - info.putus_tanggal).days <= 1:
            return (
                f"🌱 Streak {info.putus_panjang} hari kemarin berhenti — tidak apa. "
                f"Rekormu tetap <b>{info.best}</b> hari. Mulai lagi hari ini."
            )
        teks = "🌱 Streak: mulai hari ini — lima shalat tepat waktu."
        return teks + (f" Rekor: <b>{info.best}</b> hari." if info.best else "")

    lines = [f"🔥 Streak: <b>{info.current}</b> hari · rekor <b>{info.best}</b>"]
    if info.milestone:
        lines.append(f"🎉 MasyaAllah, <b>{info.milestone} hari</b> berturut-turut terjaga!")
    elif info.berikutnya:
        lines.append(f"🎯 {info.berikutnya - info.current} hari lagi menuju {info.berikutnya} hari.")
    if info.udzur_terakhir and (today - info.udzur_terakhir).days < UDZUR_JEDA:
        siap = info.udzur_terakhir + timedelta(days=UDZUR_JEDA)
        lines.append(
            f"🛡 Jatah udzur dipakai {info.udzur_terakhir.day}/{info.udzur_terakhir.month}; "
            f"siap lagi {siap.day}/{siap.month}."
        )
    else:
        lines.append("🛡 Jatah udzur tersedia — satu hari bolong tidak memutus streak.")
    return "\n".join(lines)


def tahajud_streak(records, today: date) -> StreakInfo:
    return compute_streak(records, today, tahajud_status)


def malam_pekan_ini(records, today: date) -> int:
    by_day = {r.day: r for r in records}
    return sum(
        1 for i in range(7) if (r := by_day.get(today - timedelta(days=i))) and r.checks.get("Tahajud")
    )


def baris_tahajud(info: StreakInfo, pekan: int) -> str:
    """Streak tahajud — sengaja satu baris dan tanpa nada menagih: ini sunnah."""
    if info.current == 0:
        teks = f"🌙 Tahajud: {pekan}/7 malam pekan ini"
        return teks + (f" · rekor {info.best} malam" if info.best else "")
    teks = f"🌙 Tahajud: <b>{info.current}</b> malam beruntun · rekor {info.best} · {pekan}/7 pekan ini"
    if info.milestone:
        teks += f"\n🎉 {info.milestone} malam qiyamul lail — semoga istiqamah!"
    return teks


# --- XP & level ---------------------------------------------------------------
# XP hanya naik, tidak pernah dikurangi: Lewat waktu bernilai 0, bukan minus —
# mencatat dengan jujur tidak boleh terasa seperti dihukum. Semua dihitung ulang
# dari riwayat, jadi tabel di bawah bebas diubah kapan saja.

# Hanya awal waktu yang dihargai — tengah/akhir/lewat sama-sama 0 (keputusan owner).
XP_WAKTU = {"Awal waktu": 3, "Tengah waktu": 0, "Akhir waktu": 0, LEWAT: 0}
XP_CARA = {"Masjid": 2, "Berjamaah": 1}
XP_SUNNAH = 2  # tiap checkbox sunnah
XP_TAHAJUD = 3  # tahajud menggantikan XP_SUNNAH
XP_RAWATIB = 1  # tiap qabliyah / ba'diyah
TILAWAH_CAP = 20  # 1 XP per halaman, maksimal sekian per hari
XP_HARI_TEPAT = 5  # bonus hari lima shalat lengkap tanpa Lewat waktu

# Hari yang tak tersentuh (Sumber = Otomatis) hanya dapat separuh XP shalat:
# auto-fill tidak boleh menaikkan level tanpa kamu membuka bot sama sekali.
FAKTOR_OTOMATIS = 0.5

# (ambang XP, nama, makna) — nama mengikuti tahap tumbuh "Pohon Amal".
LEVELS: tuple[tuple[int, str, str], ...] = (
    (0, "Benih", "Niat yang baru ditanam."),
    (100, "Tunas", "Akar pertama mulai mencengkeram."),
    (300, "Semai", "Daun-daun kecil mencari cahaya."),
    (700, "Pohon Muda", "Batangnya mulai tegak."),
    (1500, "Pohon Rindang", "Cabangnya meneduhkan."),
    (3000, "Pohon Berbuah", "Amal yang konsisten mulai berbuah."),
    (5500, "Pohon Thayyibah", "Akarnya teguh, cabangnya menjulang ke langit."),
    (9000, "Pohon Bercahaya", "Nur di atas nur."),
)

XP_LABEL = {
    "shalat": "Shalat (waktu)",
    "jamaah": "Berjamaah / masjid",
    "sunnah": "Sunnah",
    "tilawah": "Tilawah",
    "bonus": "Bonus hari tepat",
    "sedekah": "Sedekah",
}


def xp_hari(rec, *, partial: bool = False) -> dict[str, int]:
    out = dict.fromkeys(XP_LABEL, 0)
    if rec is None:
        return out
    for p in PRAYERS:
        w, c = rec.waktu(p), rec.cara(p)
        if w:
            out["shalat"] += XP_WAKTU.get(w, 0)
            out["jamaah"] += XP_CARA.get(c or "", 0)
    if rec.sumber == "Otomatis":
        out["shalat"] = int(out["shalat"] * FAKTOR_OTOMATIS)
        out["jamaah"] = int(out["jamaah"] * FAKTOR_OTOMATIS)
    for name, checked in rec.checks.items():
        if checked:
            out["sunnah"] += XP_TAHAJUD if name == "Tahajud" else XP_SUNNAH
    out["sunnah"] += XP_RAWATIB * (len(rec.qabliyah) + len(rec.badiyah))
    out["tilawah"] = min(rec.tilawah or 0, TILAWAH_CAP)
    if day_status(rec, partial=partial) == "tepat":
        out["bonus"] = XP_HARI_TEPAT
    out["sedekah"] = sedekah.xp_hari(rec)
    return out


def level_of(xp: int) -> int:
    """Indeks level (0-based) untuk total XP."""
    idx = 0
    for i, (ambang, _, _) in enumerate(LEVELS):
        if xp >= ambang:
            idx = i
    return idx


@dataclass
class LevelInfo:
    xp: int
    idx: int  # 0-based
    xp_hari_ini: int
    rincian: dict[str, int]  # total per sumber XP
    hari_ini: dict[str, int]
    xp_kemarin: int  # total XP sampai akhir kemarin — untuk deteksi naik level

    @property
    def level(self) -> int:
        return self.idx + 1

    @property
    def nama(self) -> str:
        return LEVELS[self.idx][1]

    @property
    def makna(self) -> str:
        return LEVELS[self.idx][2]

    @property
    def ambang(self) -> int:
        return LEVELS[self.idx][0]

    @property
    def berikut(self) -> tuple[int, str, str] | None:
        return LEVELS[self.idx + 1] if self.idx + 1 < len(LEVELS) else None

    @property
    def kurang(self) -> int:
        return self.berikut[0] - self.xp if self.berikut else 0

    @property
    def progres(self) -> float:
        """0..1 di dalam level berjalan."""
        if not self.berikut:
            return 1.0
        return (self.xp - self.ambang) / (self.berikut[0] - self.ambang)


def compute_level(records, today: date) -> LevelInfo:
    rincian = dict.fromkeys(XP_LABEL, 0)
    hari_ini = dict.fromkeys(XP_LABEL, 0)
    for r in records:
        if r.day > today:
            continue
        x = xp_hari(r, partial=(r.day == today))
        for k, v in x.items():
            rincian[k] += v
        if r.day == today:
            hari_ini = x
    total = sum(rincian.values())
    hi = sum(hari_ini.values())
    return LevelInfo(
        xp=total, idx=level_of(total), xp_hari_ini=hi, rincian=rincian,
        hari_ini=hari_ini, xp_kemarin=total - hi,
    )


def baris_level(info: LevelInfo, *, naik_dari: int | None = None) -> str:
    """Baris level untuk bot. `naik_dari` = indeks level sebelumnya kalau baru naik."""
    if naik_dari is not None and naik_dari < info.idx:
        return (
            f"⬆️ <b>Naik level!</b> Pohon amalmu kini <b>{info.nama}</b> (Lv {info.level}).\n"
            f"<i>{info.makna}</i>"
        )
    teks = f"🌳 Lv {info.level} · <b>{info.nama}</b> — {info.xp} XP"
    if info.berikut:
        teks += f" · {info.kurang} lagi menuju {info.berikut[1]}"
    return teks


# Tabel "cara dapat XP" untuk dashboard — dirakit dari konstanta di atas supaya
# tidak pernah berbeda dengan rumus yang sebenarnya dipakai.
XP_ATURAN: tuple[tuple[str, str], ...] = (
    ("Shalat di awal waktu", f"+{XP_WAKTU['Awal waktu']}"),
    ("Shalat tengah / akhir / lewat waktu", "0"),
    ("Di masjid / berjamaah", f"+{XP_CARA['Masjid']} / +{XP_CARA['Berjamaah']}"),
    ("Tahajud", f"+{XP_TAHAJUD}"),
    ("Sunnah lain (Dhuha, Al-Mulk, …)", f"+{XP_SUNNAH}"),
    ("Tiap qabliyah / ba'diyah", f"+{XP_RAWATIB}"),
    ("Tilawah per halaman", f"+1 (maks {TILAWAH_CAP}/hari)"),
    ("Hari lima shalat tanpa lewat waktu", f"+{XP_HARI_TEPAT}"),
    ("Sedekah rutin aktif", f"+{sedekah.XP_RUTIN}/hari"),
    ("Sedekah tambahan pertama hari itu", f"+{sedekah.XP_TAMBAHAN_PERTAMA}"),
    ("Sedekah tambahan ke-2 & ke-3", f"+{sedekah.XP_TAMBAHAN_BERIKUT} masing-masing"),
    ("Hari yang tidak kamu sentuh (otomatis)", "XP shalat ×½"),
)


def sedekah_pekan_ini(records, today: date) -> int:
    """Hari bersedekah (rutin atau tambahan) dalam 7 hari terakhir."""
    by_day = {r.day: r for r in records}
    return sum(1 for i in range(7) if (r := by_day.get(today - timedelta(days=i))) and r.sedekah_ada)


def tambahan_pekan_ini(records, today: date) -> int:
    """Hari dengan sedekah tambahan dalam 7 hari terakhir — jadi burung di avatar."""
    by_day = {r.day: r for r in records}
    return sum(1 for i in range(7) if (r := by_day.get(today - timedelta(days=i))) and r.sedekah_n > 0)
