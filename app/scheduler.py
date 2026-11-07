"""Penjadwal auto-fill shalat fardhu (§5).

Begitu ambang waktu shalat lewat, barisnya diisi `Awal waktu + Munfarid` dan
ditandai `Sumber = Otomatis`, lalu bot mengirim pesan berisi tombol koreksi satu
ketukan.

Ambangnya jam datar dari `JAM_SHALAT`, bukan jadwal adzan yang diambil online.
Itu keputusan sadar: presisi menit tidak mengubah apa pun di sini — yang ditulis
selalu "Awal waktu" dan tetap dikoreksi sesudahnya — sementara API jadwal
membawa 403, cache bulanan, dan pergantian bulan yang semuanya harus diurus.

Dua hal yang tetap membuat ini bukan sekadar "pasang timer":

* **Dyno di-restart minimal sekali sehari (§3).** Timer di memori hilang. Karena
  itu jadwalnya tidak dipasang sekali di boot, melainkan diperiksa ulang tiap
  beberapa detik terhadap jam dinding — restart kapan pun tidak mengubah apa pun.
* **Restart tidak boleh menulis dua kali.** Setiap (hari, shalat) diklaim di
  Redis sebelum ditulis. Klaim gagal-tertutup: kalau cache bermasalah, ia menolak
  menulis, bukan menulis ulang.

Isya tidak menyeberangi tengah malam pada mode ini — penulisan terjadi saat
ambang lewat, bukan di akhir rentang, jadi Isya selalu jatuh pada tanggal ia
dimulai. Hari kemarin tetap diperiksa sampai ambang Subuh hari ini, supaya Isya
yang terlewat karena dyno mati sesudah pukul 19:00 masih bisa menyusul.

Tidak ada batas umur di dalam hari berjalan: boot pukul 15:00 mengisi Subuh,
Dzuhur, dan apa pun yang ambangnya sudah lewat hari itu.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import date, datetime, timedelta

from .cache import k_prompt_sent
from .config import PRAYERS
from .timeutil import fmt_jam, label_hari, now_local, tz

log = logging.getLogger(__name__)

CLAIM_TTL = 3 * 86400


class PrayerScheduler:
    """Loop yang memeriksa jam dinding, bukan rantai timer."""

    def __init__(self, runtime) -> None:
        self.rt = runtime
        self.s = runtime.settings

    async def run(self) -> None:
        jadwal = " · ".join(f"{p} {self.s.jam_shalat[p]}" for p in PRAYERS if p in self.s.jam_shalat)
        log.info("Penjadwal auto-fill aktif (%s + %s) — %s",
                 self.s.autofill_waktu, self.s.autofill_cara, jadwal)
        while True:
            try:
                await self.tick(now_local())
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001
                # Satu tick yang gagal tidak boleh mematikan penjadwal seharian.
                log.exception("Tick penjadwal gagal")
            await asyncio.sleep(self.s.tick_seconds)

    def times(self, day: date) -> dict[str, datetime]:
        """Ambang tiap shalat pada `day`, sudah berzona lokal."""
        out: dict[str, datetime] = {}
        for prayer in PRAYERS:
            raw = self.s.jam_shalat.get(prayer)
            if not raw:
                continue
            try:
                jam, menit = (int(x) for x in raw.split(":"))
            except ValueError:
                log.error("JAM_SHALAT[%s] = %r tidak terbaca, shalat itu dilewati", prayer, raw)
                continue
            out[prayer] = datetime(day.year, day.month, day.day, jam, menit, tzinfo=tz())
        return out

    def _jam(self, day: date, hhmm: str) -> datetime:
        jam, menit = (int(x) for x in hhmm.split(":"))
        return datetime(day.year, day.month, day.day, jam, menit, tzinfo=tz())

    async def tick(self, now: datetime) -> None:
        await self.sedekah_tick(now)
        if not self.s.autofill:
            return

        # Hari ini: apa pun yang ambangnya sudah lewat, tanpa batas umur — boot
        # tengah hari harus tetap menyusul Subuh dan Dzuhur.
        rencana = [(now.date(), p) for p in PRAYERS]

        # Kemarin: hanya Isya, dan hanya sampai ambang Subuh hari ini. Isya satu-
        # satunya yang sah menyeberang tengah malam; membuka seluruh hari kemarin
        # berarti restart dini hari menambal sehari penuh yang tidak pernah terjadi.
        subuh = self.times(now.date()).get(PRAYERS[0])
        if subuh is not None and now < subuh:
            rencana.insert(0, (now.date() - timedelta(days=1), PRAYERS[-1]))

        for day, prayer in rencana:
            start = self.times(day).get(prayer)
            if start is None or start > now:
                continue
            if not await self.rt.cache.claim(k_prompt_sent(day.isoformat(), prayer),
                                             ttl=CLAIM_TTL):
                continue
            await self._fill(day, prayer, start)

    async def sedekah_tick(self, now: datetime) -> None:
        """Nominal rutin ke baris hari ini, dan pengingat bulanan "masih aktif?".

        Seperti auto-fill shalat: diperiksa ulang tiap tick terhadap jam dinding,
        jadi restart kapan pun tetap menyusul. Nilai yang sudah ada di baris tidak
        pernah ditimpa — termasuk yang kamu ubah sendiri di Notion.
        """
        from . import state

        st = state.load()
        today = now.date()
        if (
            st["rutin_aktif"]
            and now >= self._jam(today, self.s.sedekah_rutin_jam)
            and await self.rt.cache.claim(f"sedekah-rutin:{today.isoformat()}", ttl=CLAIM_TTL)
        ):
            rec = await self.rt.repo.get_day(today)
            if rec is None or not rec.sedekah_rutin:
                await self.rt.repo.set_sedekah_rutin(today, True)
                log.info("Sedekah rutin %s dicentang", today)

        bulan = today.strftime("%Y-%m")
        if (
            st["rutin_aktif"]
            and today.day == 1
            and st["pengingat_bulan"] != bulan
            and now >= self._jam(today, self.s.sedekah_pengingat_jam)
        ):
            from .bot.keyboards import sedekah_rutin_cek_keyboard

            state.update(pengingat_bulan=bulan)
            # Japri, bukan topik grup — sedekah urusan pribadi.
            await self.rt.notify_private(
                "🗓 Awal bulan — sudah isi saldo untuk sedekah otomatis harian bulan ini?",
                reply_markup=sedekah_rutin_cek_keyboard(),
            )

    async def _fill(self, day: date, prayer: str, start: datetime) -> None:
        rec = await self.rt.repo.get_day(day)
        if rec and (rec.waktu(prayer) or rec.cara(prayer)):
            # Sudah kamu catat sendiri lebih dulu. Auto-fill tidak pernah menimpa
            # tindakanmu — itu akan menghapus data yang lebih benar.
            #
            # Cara ikut diperiksa, bukan hanya Waktu: lewat bot keduanya selalu
            # terisi bersama, tapi Notion boleh kamu edit langsung dan di sana
            # Cara bisa berdiri sendiri.
            log.info("%s %s sudah terisi, auto-fill dilewati", day, prayer)
            return

        await self.rt.repo.set_prayer(
            day, prayer, self.s.autofill_waktu, self.s.autofill_cara, "Otomatis"
        )
        log.info("Auto-fill %s %s → %s + %s", day, prayer,
                 self.s.autofill_waktu, self.s.autofill_cara)
        await self._announce(day, prayer, start)

    async def _announce(self, day: date, prayer: str, start: datetime) -> None:
        from .bot.keyboards import autofill_keyboard

        text = (
            f"🕌 <b>{prayer}</b> — {label_hari(day)} (ambang {fmt_jam(start)})\n"
            f"Terisi otomatis: <b>{self.s.autofill_waktu} · {self.s.autofill_cara}</b>.\n"
            "Koreksi kalau berbeda."
        )
        extra, rawan = await self._gamify_lines(day, prayer)
        if extra:
            text += "\n\n" + extra
        # Senyap: lima kali sehari, tiap hari. Pesannya tetap masuk lengkap dengan
        # tombol koreksi, hanya tidak berbunyi — kecuali shalat ini sedang sering
        # lewat waktu: saat itu pesannya memang dimaksudkan sebagai pengingat.
        await self.rt.notify_owner(
            text, reply_markup=autofill_keyboard(day, prayer), silent=not rawan
        )

    async def _gamify_lines(self, day: date, prayer: str) -> tuple[str, bool]:
        """Pengingat untuk shalat yang rawan lewat waktu, dan streak di pesan Subuh.

        Gagal di sini tidak boleh menahan pesan auto-fill — paling buruk pesannya
        terkirim tanpa tambahan.
        """
        from .data import load_history
        from .gamify import (
            baris_level,
            baris_streak,
            baris_tahajud,
            compute_level,
            level_of,
            compute_streak,
            lewat_info,
            malam_pekan_ini,
            pengingat_rawan,
            sedekah_pekan_ini,
            tahajud_streak,
        )
        def baris_sedekah_pagi(records, day):
            rec = next((r for r in records if r.day == day), None)
            rutin = "💧 Sedekah rutin tercatat · " if rec and rec.sedekah_rutin else ""
            return f"{rutin}🤲 Sedekah {sedekah_pekan_ini(records, day)}/7 hari pekan ini"

        try:
            records = await load_history(day, self.rt.repo, self.rt.cache)
            lines: list[str] = []
            if prayer == PRAYERS[0]:
                # Naik level dinilai dari hari yang sudah tutup (kemarin), jadi
                # tidak perlu menyimpan "level terakhir yang diumumkan" di mana pun.
                kemarin = day - timedelta(days=1)
                lv_kemarin = compute_level(records, kemarin)
                sebelum = level_of(compute_level(records, kemarin - timedelta(days=1)).xp)
                lines.append(baris_level(lv_kemarin, naik_dari=sebelum))
                lines.append(baris_streak(compute_streak(records, day), day))
                lines.append(baris_sedekah_pagi(records, day))
                lines.append(baris_tahajud(tahajud_streak(records, day), malam_pekan_ini(records, day)))
            info = lewat_info(records, prayer, day)
            if info.rawan:
                lines.append(pengingat_rawan(info, day))
            return "\n\n".join(lines), info.rawan
        except Exception:  # noqa: BLE001
            log.exception("Gamifikasi gagal; pesan auto-fill dikirim tanpa tambahan")
            return "", False
