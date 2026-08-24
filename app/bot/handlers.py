"""Perintah bot & handler tombol (§6)."""
from __future__ import annotations

import html
import logging
from datetime import date, timedelta
from functools import wraps

from telegram import Update
from telegram.constants import ChatType, ParseMode
from telegram.ext import CallbackQueryHandler, CommandHandler, ContextTypes

from ..config import (
    BADIYAH_OPTIONS,
    CARA_OPTIONS,
    CHECKBOX_SUNNAH,
    PRAYERS,
    QABLIYAH_OPTIONS,
    WAKTU_OPTIONS,
)
from ..data import load_records
from ..domain import catatan_day
from ..miniapp.aggregate import aggregate, make_filters
from ..timeutil import fmt_tanggal, label_hari, now_local
from .keyboards import (
    WAKTU_LABEL,
    dashboard_keyboard,
    dashboard_link_keyboard,
    edit_cara_keyboard,
    edit_day_keyboard,
    edit_prayer_keyboard,
    edit_waktu_keyboard,
    isi_keyboard,
    main_menu_keyboard,
    s2d,
)

log = logging.getLogger(__name__)

HELP = """<b>Bot Ibadah</b>

/hariini — ringkasan hari ini
/isi — centang sunnah (multi-pilih)
/tilawah &lt;n&gt; — tambah halaman (mis. <code>/tilawah 5</code>, <code>/tilawah =12</code> untuk menimpa)
/catatan &lt;teks&gt; — catatan refleksi hari ini
/edit — koreksi shalat hari ini atau kemarin
/rekap — ringkasan 7 &amp; 30 hari
/dashboard — buka Mini App"""


def is_private(update: Update) -> bool:
    """Tombol web_app hanya sah di chat pribadi — Telegram menolaknya di grup."""
    chat = update.effective_chat
    return chat is not None and chat.type == ChatType.PRIVATE


def rt_of(context: ContextTypes.DEFAULT_TYPE):
    return context.application.bot_data["runtime"]


def owner_only(func):
    @wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        rt = rt_of(context)
        owner = rt.settings.owner_id
        user = update.effective_user
        if owner and (user is None or user.id != owner):
            if update.callback_query:
                await update.callback_query.answer("Bot ini hanya untuk satu orang.", show_alert=True)
            return None
        if not owner:
            chat = update.effective_chat
            log.warning(
                "TELEGRAM_OWNER_ID belum diset — bot menerima siapa saja. "
                "Set TELEGRAM_OWNER_ID=%s (chat id pesan ini: %s)",
                getattr(user, "id", "?"),
                getattr(chat, "id", "?"),
            )
        return await func(update, context)

    return wrapper


def today_of(rt) -> date:
    return now_local().astimezone(rt.settings.tz).date()


async def hari_catatan(rt) -> date:
    """Baris tujuan untuk input manual — mengikuti konvensi tahajud (§11.4)."""
    now = now_local()
    return catatan_day(now, rt.settings)


def label_kalau_bukan_hari_ini(day: date, today: date) -> str:
    return "" if day == today else f" <i>(baris {label_hari(day)})</i>"


async def reply(update: Update, text: str, **kwargs):
    if update.callback_query:
        return await update.callback_query.edit_message_text(
            text, parse_mode=ParseMode.HTML, **kwargs
        )
    return await update.effective_message.reply_text(text, parse_mode=ParseMode.HTML, **kwargs)


# --- perintah ---------------------------------------------------------------

@owner_only
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    rt = rt_of(context)
    url = rt.settings.webapp_url
    # Deep link dari tombol grup: t.me/<bot>?start=dashboard
    if context.args and context.args[0] == "dashboard":
        await cmd_dashboard(update, context)
        return
    if update.effective_message:
        await update.effective_message.reply_text(
            HELP,
            parse_mode=ParseMode.HTML,
            reply_markup=main_menu_keyboard(url, private=is_private(update)),
        )


@owner_only
async def cmd_hariini(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    rt = rt_of(context)
    day = today_of(rt)
    rec = await rt.repo.get_day(day)

    lines = [f"<b>{label_hari(day)}</b>", ""]
    for prayer in PRAYERS:
        waktu = rec.waktu(prayer) if rec else None
        cara = rec.cara(prayer) if rec else None
        if waktu:
            lines.append(f"{WAKTU_LABEL.get(waktu, '•')} {prayer} — {waktu} · {cara or '—'}")
        else:
            lines.append(f"⬜ {prayer} — belum tercatat")

    checked = [n for n in CHECKBOX_SUNNAH if rec and rec.checks.get(n)]
    kosong = [n for n in CHECKBOX_SUNNAH if not (rec and rec.checks.get(n))]
    lines += ["", "<b>Sunnah</b>"]
    lines.append("✅ " + ", ".join(checked) if checked else "✅ —")
    lines.append("⬜ " + ", ".join(kosong) if kosong else "⬜ —")
    lines.append(f"Qabliyah: {', '.join(rec.qabliyah) if rec and rec.qabliyah else '—'}")
    lines.append(f"Ba'diyah: {', '.join(rec.badiyah) if rec and rec.badiyah else '—'}")
    lines += ["", f"📖 Tilawah: <b>{rec.tilawah if rec else 0}</b> halaman"]
    if rec and rec.catatan:
        lines.append(f"📝 {html.escape(rec.catatan)}")
    if rec and rec.sumber:
        lines.append(f"<i>Sumber: {rec.sumber}</i>")
    await reply(update, "\n".join(lines))


@owner_only
async def cmd_isi(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    rt = rt_of(context)
    day = await hari_catatan(rt)
    rec = await rt.repo.get_or_create(day)
    await update.effective_message.reply_text(
        f"Sunnah <b>{label_hari(day)}</b> — tekan untuk mengubah:",
        parse_mode=ParseMode.HTML,
        reply_markup=isi_keyboard(day, rec),
    )


@owner_only
async def cmd_tilawah(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    rt = rt_of(context)
    day = await hari_catatan(rt)
    suffix = label_kalau_bukan_hari_ini(day, today_of(rt))
    arg = (context.args[0] if context.args else "").strip()
    if not arg:
        rec = await rt.repo.get_day(day)
        await reply(update, f"Tilawah hari ini: <b>{rec.tilawah if rec else 0}</b> halaman.\nTambah: /tilawah 5")
        return
    overwrite = arg.startswith("=")
    try:
        value = int(arg.lstrip("="))
    except ValueError:
        await reply(update, "Format: <code>/tilawah 5</code> atau <code>/tilawah =12</code>")
        return
    if overwrite:
        total = await rt.repo.set_tilawah(day, value)
        await reply(update, f"📖 Tilawah ditimpa jadi <b>{total}</b> halaman.{suffix}")
    else:
        total = await rt.repo.add_tilawah(day, value)
        await reply(update, f"📖 +{value} halaman. Total: <b>{total}</b>.{suffix}")


@owner_only
async def cmd_catatan(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    rt = rt_of(context)
    text = " ".join(context.args).strip()
    if not text:
        await reply(update, "Format: <code>/catatan hari ini terasa berat tapi jalan</code>")
        return
    day = await hari_catatan(rt)
    merged = await rt.repo.append_catatan(day, text)
    suffix = label_kalau_bukan_hari_ini(day, today_of(rt))
    await reply(update, f"📝 Tersimpan.{suffix}\n\n<i>{html.escape(merged)}</i>")


@owner_only
async def cmd_edit(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    rt = rt_of(context)
    day = today_of(rt)
    await update.effective_message.reply_text(
        "Hari mana yang mau dikoreksi?",
        reply_markup=edit_day_keyboard(day, day - timedelta(days=1)),
    )



@owner_only
async def cmd_rekap(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    rt = rt_of(context)
    day = today_of(rt)
    records = await load_records(day - timedelta(days=29), day, rt.repo, rt.cache)
    parts = [f"<b>Rekap</b> · {fmt_tanggal(day)}"]
    for days in (7, 30):
        filters = make_filters(str(days), today=day)
        agg = aggregate(records, filters)
        s = agg.summary
        parts.append(
            f"\n<b>{days} hari</b>\n"
            f"• Awal waktu: <b>{s['pct_awal']}%</b>\n"
            f"• Berjamaah/masjid: <b>{s['pct_jamaah']}%</b>\n"
            f"• Shalat tercatat: {s['tercatat']}/{s['kemungkinan']} ({s['pct_tercatat']}%)\n"
            f"• Tilawah: {s['tilawah_total']} hal (rata-rata {s['tilawah_avg']}/hari)\n"
            f"• Hari terisi otomatis: {s['hari_otomatis']}"
        )
        if days == 30:
            jarang = ", ".join(item["name"] for item in agg.sunnah[:3])
            parts.append(f"• Sunnah paling jarang: {jarang}")
    parts.append(f"\n🔥 Streak berjalan: <b>{aggregate(records, make_filters('30', today=day)).summary['streak']}</b> hari")
    await reply(update, "\n".join(parts))


@owner_only
async def cmd_dashboard(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    rt = rt_of(context)
    url = rt.settings.webapp_url
    if not url.startswith("https://"):
        await reply(update, "BASE_URL belum diset ke URL https publik, jadi Mini App belum bisa dibuka.")
        return
    if not is_private(update):
        await update.effective_message.reply_text(
            "Mini App hanya bisa dibuka di chat pribadi — Telegram melarang tombol web app di grup.",
            reply_markup=dashboard_link_keyboard(context.bot.username),
        )
        return
    await update.effective_message.reply_text(
        "Dashboard ibadah — filter rentang, per shalat, dan hari dalam pekan.",
        reply_markup=dashboard_keyboard(url),
    )



# --- callback ---------------------------------------------------------------

@owner_only
async def on_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    data = query.data or ""
    rt = rt_of(context)
    try:
        if data == "noop":
            await query.answer()
        elif data == "close":
            await query.answer()
            await query.edit_message_reply_markup(reply_markup=None)
        elif data.startswith("isi|"):
            await _on_isi(update, context, data)
        elif data.startswith("ed|"):
            await _on_edit(update, context, data)
        else:
            await query.answer()
    except Exception as exc:  # noqa: BLE001
        log.exception("Callback gagal: %s", data)
        try:
            await query.answer(f"Gagal: {exc}"[:190], show_alert=True)
        except Exception:  # noqa: BLE001
            pass
        await rt.notify_owner(f"⚠️ Callback <code>{html.escape(data)}</code> gagal: {exc}")



async def _on_isi(update: Update, context: ContextTypes.DEFAULT_TYPE, data: str) -> None:
    rt = rt_of(context)
    query = update.callback_query
    _, kind, ds, idx = data.split("|")
    day = s2d(ds)
    i = int(idx)
    if kind == "c":
        name = CHECKBOX_SUNNAH[i]
        value = await rt.repo.toggle_check(day, name)
        note = f"{name} {'✅' if value else 'dilepas'}"
    elif kind == "q":
        value_name = QABLIYAH_OPTIONS[i]
        current = await rt.repo.toggle_multi(day, rt.settings.prop_qabliyah, value_name)
        note = f"Qabliyah: {', '.join(current) or '—'}"
    else:
        value_name = BADIYAH_OPTIONS[i]
        current = await rt.repo.toggle_multi(day, rt.settings.prop_badiyah, value_name)
        note = f"Ba'diyah: {', '.join(current) or '—'}"
    rec = await rt.repo.get_or_create(day)
    await query.answer(note[:190])
    await query.edit_message_reply_markup(reply_markup=isi_keyboard(day, rec))


async def _on_edit(update: Update, context: ContextTypes.DEFAULT_TYPE, data: str) -> None:
    rt = rt_of(context)
    query = update.callback_query
    parts = data.split("|")
    action = parts[1]
    today = today_of(rt)

    if action == "d":
        await query.answer()
        await query.edit_message_text(
            "Hari mana yang mau dikoreksi?", reply_markup=edit_day_keyboard(today, today - timedelta(days=1))
        )
        return

    day = s2d(parts[2])
    if action == "p":
        rec = await rt.repo.get_day(day)
        await query.answer()
        await query.edit_message_text(
            f"<b>{label_hari(day)}</b> — pilih shalat:",
            parse_mode=ParseMode.HTML,
            reply_markup=edit_prayer_keyboard(day, rec),
        )
        return

    prayer = PRAYERS[int(parts[3])]
    if action == "w":
        await query.answer()
        await query.edit_message_text(
            f"<b>{prayer}</b> · {label_hari(day)} — pilih Waktu:",
            parse_mode=ParseMode.HTML,
            reply_markup=edit_waktu_keyboard(day, prayer),
        )
    elif action == "sw":
        waktu = WAKTU_OPTIONS[int(parts[4])]
        await rt.repo.set_prayer(day, prayer, waktu, None, "Manual")
        await query.answer(f"{prayer}: {waktu}")
        await query.edit_message_text(
            f"<b>{prayer}</b> · {label_hari(day)} — Waktu: {WAKTU_LABEL[waktu]}\nSekarang pilih Cara:",
            parse_mode=ParseMode.HTML,
            reply_markup=edit_cara_keyboard(day, prayer),
        )
    elif action == "sc":
        cara = CARA_OPTIONS[int(parts[4])]
        await rt.repo.set_prayer(day, prayer, None, cara, "Manual")
        rec = await rt.repo.get_day(day)
        await query.answer(f"{prayer}: {cara}")
        await query.edit_message_text(
            f"✅ <b>{prayer}</b> · {label_hari(day)} diperbarui.",
            parse_mode=ParseMode.HTML,
            reply_markup=edit_prayer_keyboard(day, rec),
        )
    elif action == "clr":
        await rt.repo.clear_prayer(day, prayer)
        rec = await rt.repo.get_day(day)
        await query.answer(f"{prayer} dikosongkan")
        await query.edit_message_text(
            f"🧹 <b>{prayer}</b> · {label_hari(day)} dikosongkan.",
            parse_mode=ParseMode.HTML,
            reply_markup=edit_prayer_keyboard(day, rec),
        )



async def on_error(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    log.exception("Handler error", exc_info=context.error)
    try:
        rt = context.application.bot_data.get("runtime")
        if rt:
            await rt.notify_owner(f"⚠️ Error di bot: {context.error}")
    except Exception:  # noqa: BLE001
        pass


def register(application) -> None:
    application.add_handler(CommandHandler(["start", "help", "bantuan"], cmd_start))
    application.add_handler(CommandHandler("hariini", cmd_hariini))
    application.add_handler(CommandHandler("isi", cmd_isi))
    application.add_handler(CommandHandler("tilawah", cmd_tilawah))
    application.add_handler(CommandHandler("catatan", cmd_catatan))
    application.add_handler(CommandHandler("edit", cmd_edit))
    application.add_handler(CommandHandler("rekap", cmd_rekap))
    application.add_handler(CommandHandler("dashboard", cmd_dashboard))
    application.add_handler(CallbackQueryHandler(on_callback))
    application.add_error_handler(on_error)
