"""Perekat singleton: cache, jadwal, Notion, bot Telegram, penjadwal.

Dipakai bersama oleh proses `web` dan `clock` supaya keduanya berbagi kode yang
sama — bedanya hanya siapa yang menjalankan penjadwal.
"""
from __future__ import annotations

import logging

from .cache import get_cache
from .config import get_settings
from .notion import get_repo


log = logging.getLogger(__name__)


class Runtime:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.cache = get_cache()
        self.repo = get_repo()
        self.telegram = None  # telegram.ext.Application

    # --- bot ---------------------------------------------------------------

    async def start_bot(self, *, with_webhook: bool) -> None:
        from .bot.app import build_application, install_webhook, register_commands

        if not self.settings.bot_token:
            log.warning("TELEGRAM_BOT_TOKEN kosong — bot tidak dijalankan")
            return
        polling = self.settings.use_polling
        application = build_application(self, polling=polling)
        try:
            await application.initialize()
            await application.start()
            if polling:
                # Webhook dan polling saling meniadakan — lepas dulu yang lama.
                await application.bot.delete_webhook(drop_pending_updates=True)
                await application.updater.start_polling(
                    allowed_updates=["message", "callback_query"]
                )
                await register_commands(application)
                log.info("Bot berjalan dengan long polling (mode uji lokal)")
            elif with_webhook:
                await install_webhook(application, self.settings)
        except Exception:
            # Token salah atau Telegram tak terjangkau saat boot: web tetap hidup
            # supaya /health terbaca dan penyebabnya kelihatan di log.
            log.exception("Bot Telegram gagal dijalankan")
            try:
                await application.shutdown()
            except Exception:  # noqa: BLE001
                pass
            return
        self.telegram = application

    async def stop_bot(self) -> None:
        if self.telegram is None:
            return
        if self.telegram.updater is not None and self.telegram.updater.running:
            await self.telegram.updater.stop()
        await self.telegram.stop()
        await self.telegram.shutdown()
        self.telegram = None



    # --- pemeriksaan skema saat boot (§10) ---------------------------------

    async def check_schema(self) -> None:
        if not self.settings.notion_token:
            log.warning("NOTION_TOKEN kosong — pemeriksaan skema dilewati")
            return
        try:
            issues = await self.repo.validate_schema()
        except Exception as exc:  # noqa: BLE001
            log.exception("Pemeriksaan skema Notion gagal")
            await self.notify_owner(f"⚠️ Tidak bisa membaca skema Notion saat boot:\n{exc}")
            return
        if issues:
            body = "\n".join(f"• {i}" for i in issues)
            log.error("Skema Notion tidak sesuai:\n%s", body)
            await self.notify_owner(
                "⚠️ Skema Notion tidak sesuai harapan — penulisan bisa gagal senyap:\n" + body
            )
        else:
            log.info("Skema Notion cocok")

    async def notify_owner(self, text: str) -> None:
        target = self.settings.prompt_target
        if self.telegram is None or not target:
            return
        thread = self.settings.prompt_thread
        try:
            await self.telegram.bot.send_message(
                chat_id=target,
                text=text,
                **({"message_thread_id": thread} if thread else {}),
            )
        except Exception:  # noqa: BLE001
            log.exception("Gagal mengirim pesan ke owner")

    async def aclose(self) -> None:
        await self.stop_bot()
        await self.repo.client.close()
        await self.cache.close()


_runtime: Runtime | None = None


def get_runtime() -> Runtime:
    global _runtime
    if _runtime is None:
        _runtime = Runtime()
    return _runtime


def set_runtime(runtime: Runtime | None) -> None:  # dipakai test
    global _runtime
    _runtime = runtime
