"""Perakitan Application python-telegram-bot (mode webhook, dilayani FastAPI)."""
from __future__ import annotations

import asyncio
import logging

from telegram import BotCommand, MenuButtonWebApp, WebAppInfo
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
    BotCommand("sedekah", "Catat sedekah tambahan"),
    BotCommand("sedekahrutin", "Atur sedekah otomatis harian"),
    BotCommand("dashboard", "Buka Mini App"),
]

WEBHOOK_PATH = "/telegram/webhook"
WEBHOOK_ATTEMPTS = 3


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


async def install_menu_button(application: Application, settings: Settings) -> None:
    """Tombol Mini App permanen di sebelah kolom ketik.

    Tombol inline dari /dashboard hanya sah di chat pribadi dan basi begitu
    pesannya tergulung ke atas. Tombol menu selalu ada, selalu chat pribadi,
    dan karena itu selalu membawa initData yang sah.
    """
    if not settings.webapp_url.startswith("https://"):
        return
    try:
        await application.bot.set_chat_menu_button(
            menu_button=MenuButtonWebApp(
                text="Dashboard",
                web_app=WebAppInfo(url=settings.webapp_url),
            )
        )
        log.info("Tombol menu Mini App dipasang ke %s", settings.webapp_url)
    except Exception:  # noqa: BLE001
        log.exception("Gagal memasang tombol menu Mini App")


async def install_webhook(application: Application, settings: Settings) -> None:
    """Daftarkan webhook, tombol menu, dan daftar perintah.

    Dijalankan sebagai task latar belakang: uvicorn baru mengikat $PORT setelah
    lifespan selesai, sementara Telegram menghubungi URL-nya saat setWebhook.
    Mendaftar dari dalam lifespan berarti Telegram mengetuk pintu yang belum
    dibuka — karena itu ada jeda dan percobaan ulang.
    """
    if not settings.base_url:
        log.warning("BASE_URL kosong — webhook tidak dipasang; bot tidak akan menerima update")
        return
    url = f"{settings.base_url}{WEBHOOK_PATH}"
    for attempt in range(1, WEBHOOK_ATTEMPTS + 1):
        await asyncio.sleep(3 if attempt == 1 else 5 * attempt)
        try:
            await application.bot.set_webhook(
                url=url,
                secret_token=settings.webhook_secret or None,
                allowed_updates=["message", "callback_query"],
                drop_pending_updates=False,
            )
            log.info("Webhook dipasang di %s (percobaan %s)", url, attempt)
            break
        except Exception as exc:  # noqa: BLE001
            log.warning("Percobaan %s memasang webhook gagal: %s", attempt, exc)
    else:
        log.error("Webhook tidak berhasil dipasang setelah %s percobaan", WEBHOOK_ATTEMPTS)
        return

    await install_menu_button(application, settings)
    await register_commands(application)
