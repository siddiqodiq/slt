"""Proses `web`: webhook Telegram + API & halaman Mini App dalam satu app FastAPI."""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from telegram import Update

from .bot.app import WEBHOOK_PATH
from .config import get_settings
from .miniapp.routes import router as miniapp_router
from .runtime import get_runtime
from .timeutil import now_local

log = logging.getLogger(__name__)


def setup_logging() -> None:
    logging.basicConfig(
        level=get_settings().log_level,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    settings = get_settings()
    runtime = get_runtime()
    app.state.runtime = runtime

    await runtime.start_bot(with_webhook=True)
    runtime.start_scheduler()
    await runtime.check_schema()
    log.info("Siap. Zona waktu %s, sekarang %s", settings.tz_name, now_local().isoformat(timespec="seconds"))
    try:
        yield
    finally:
        await runtime.aclose()


app = FastAPI(title="Bot Ibadah", lifespan=lifespan, docs_url=None, redoc_url=None)
app.mount("/static", StaticFiles(directory=str(Path(__file__).resolve().parent / "static")), name="static")
app.include_router(miniapp_router)


@app.post(WEBHOOK_PATH)
async def telegram_webhook(
    request: Request,
    x_telegram_bot_api_secret_token: str | None = Header(default=None),
):
    settings = get_settings()
    if settings.webhook_secret and x_telegram_bot_api_secret_token != settings.webhook_secret:
        raise HTTPException(status_code=403, detail="secret token tidak cocok")
    runtime = get_runtime()
    if runtime.telegram is None:
        raise HTTPException(status_code=503, detail="bot belum siap")
    payload = await request.json()
    update = Update.de_json(payload, runtime.telegram.bot)
    # Antrikan lalu balas cepat; Telegram tidak menunggu pekerjaan Notion selesai.
    await runtime.telegram.update_queue.put(update)
    return JSONResponse({"ok": True})


@app.get("/health")
async def health() -> dict:
    """Kesehatan + config var mana yang terbaca.

    Hanya melaporkan ada/tidaknya, tidak pernah nilainya — supaya endpoint ini
    aman dibuka dari mana saja sambil tetap menjawab "sudah diisi tapi kok tidak
    terbaca", keluhan yang paling sering muncul setelah salah tempel di Heroku.
    """
    runtime = get_runtime()
    s = runtime.settings
    return {
        "ok": True,
        "tz": s.tz_name,
        "waktu": now_local().isoformat(timespec="seconds"),
        "cache": runtime.cache.kind,
        "bot": "aktif" if runtime.telegram else "mati",
        "webapp_url": s.webapp_url,
        "config": {
            "TELEGRAM_BOT_TOKEN": bool(s.bot_token),
            "TELEGRAM_OWNER_ID": bool(s.owner_id),
            "TELEGRAM_WEBHOOK_SECRET": bool(s.webhook_secret),
            "NOTION_TOKEN": bool(s.notion_token),
            "BASE_URL": bool(s.base_url),
        },
    }


@app.get("/", response_class=PlainTextResponse)
async def root() -> str:
    return "Bot Ibadah. Dashboard hanya bisa dibuka lewat tombol di Telegram."
