"""Uji tujuan prompt: kirim satu pesan ke chat & topik yang dikonfigurasi.

    python -m tools.ping

Berguna untuk memastikan TELEGRAM_PROMPT_CHAT_ID / TELEGRAM_PROMPT_THREAD_ID
benar sebelum menunggu waktu shalat berikutnya.
"""
from __future__ import annotations

import asyncio

from telegram import Bot
from telegram.error import TelegramError

from app.config import get_settings
from app.timeutil import now_local


async def main() -> int:
    s = get_settings()
    if not s.bot_token:
        print("TELEGRAM_BOT_TOKEN belum diset.")
        return 2
    target, thread = s.prompt_target, s.prompt_thread
    if not target:
        print("TELEGRAM_OWNER_ID / TELEGRAM_PROMPT_CHAT_ID belum diset.")
        return 2

    bot = Bot(s.bot_token)
    async with bot:
        me = await bot.get_me()
        print(f"Bot        : @{me.username} ({me.id})")
        try:
            chat = await bot.get_chat(target)
            forum = getattr(chat, "is_forum", False)
            print(f"Tujuan     : {target} · {chat.type} · {chat.title or chat.full_name}")
            print(f"Forum      : {'ya' if forum else 'tidak'}")
            if thread and not forum:
                print("⚠️  TELEGRAM_PROMPT_THREAD_ID diisi tapi grup ini bukan forum — topik diabaikan.")
        except TelegramError as exc:
            print(f"⚠️  get_chat gagal: {exc}")
            print("    Untuk grup: pastikan bot sudah jadi anggota dan chat id memakai prefix -100.")
        print(f"Topik      : {thread or '(tanpa topik)'}")

        try:
            msg = await bot.send_message(
                chat_id=target,
                text=f"✅ Uji koneksi bot ibadah — {now_local():%d %b %H:%M}. "
                "Kalau pesan ini muncul di tempat yang benar, prompt shalat juga akan ke sini.",
                **({"message_thread_id": thread} if thread else {}),
            )
        except TelegramError as exc:
            print(f"\n✗ Gagal mengirim: {exc}")
            return 1
    print(f"\n✓ Terkirim (message_id={msg.message_id}).")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
