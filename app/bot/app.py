"""Perakitan Application python-telegram-bot (mode webhook, dilayani FastAPI)."""
from __future__ import annotations

import logging

from telegram import BotCommand
from telegram.ext import Application, ApplicationBuilder

from ..config import Settings
from . import handlers

log = logging.getLogger(__name__)

COMMANDS = [
    BotCommand("hariini", "Ringkasan hari ini"),
    BotCommand("isi", "Centang sunnah"),
    BotCommand("tilawah", "Tambah halaman tilawah"),
    BotCommand("catatan", "Catatan refleksi hari ini"),
    BotCommand("edit", "Koreksi shalat hari ini/kemarin"),
    BotCommand("rekap", "Ringkasan 7 & 30 hari"),
    BotCommand("dashboard", "Buka Mini App"),
]

WEBHOOK_PATH = "/telegram/webhook"


def build_application(runtime, polling: bool = False) -> Application:
    builder = ApplicationBuilder().token(runtime.settings.bot_token)
    if not polling:
        builder = builder.updater(None)  # update masuk lewat webhook FastAPI
    application = builder.build()
    application.bot_data["runtime"] = runtime
    handlers.register(application)
    return application


async def register_commands(application: Application) -> None:
    try:
        await application.bot.set_my_commands(COMMANDS)
    except Exception:  # noqa: BLE001
        log.exception("Gagal mendaftarkan daftar perintah")


async def install_webhook(application: Application, settings: Settings) -> None:
    if not settings.base_url:
        log.warning("BASE_URL kosong — webhook tidak dipasang; bot tidak akan menerima update")
        return
    url = f"{settings.base_url}{WEBHOOK_PATH}"
    await application.bot.set_webhook(
        url=url,
        secret_token=settings.webhook_secret or None,
        allowed_updates=["message", "callback_query"],
        drop_pending_updates=False,
    )
    await register_commands(application)
    log.info("Webhook dipasang di %s", url)
