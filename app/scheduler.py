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
dimulai. Hari kemarin tetap ikut diperiksa supaya Isya yang terlewat karena dyno
mati sesudah pukul 19:00 masih bisa menyusul selepas tengah malam.
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

    async def tick(self, now: datetime) -> None:
        if not self.s.autofill:
            return

        # Kemarin ikut diperiksa demi Isya yang ambangnya lewat sebelum tengah malam.
        for day in (now.date() - timedelta(days=1), now.date()):
            for prayer, start in self.times(day).items():
                if start > now:
                    continue
                if (now - start).total_seconds() > self.s.autofill_catchup:
                    continue
                if not await self.rt.cache.claim(k_prompt_sent(day.isoformat(), prayer),
                                                 ttl=CLAIM_TTL):
                    continue
                await self._fill(day, prayer, start)

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
        await self.rt.notify_owner(text, reply_markup=autofill_keyboard(day, prayer))
