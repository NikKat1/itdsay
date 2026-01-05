import os
import time
import sqlite3
from datetime import datetime

from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    MessageHandler,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters
)

TOKEN = os.getenv("TOKEN")
CHANNEL_ID = int(os.getenv("CHANNEL_ID"))
LOG_CHANNEL_ID = int(os.getenv("LOG_CHANNEL_ID"))

OWNER_ID = 985545005

WHITELIST = set()
BLACKLIST = set()

TEXT_COOLDOWN = 3 * 3600
PHOTO_COOLDOWN = 24 * 3600
VOICE_COOLDOWN = 24 * 3600
MAX_VOICE_DURATION = 15

conn = sqlite3.connect("database.db", check_same_thread=False)
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    last_sent INTEGER DEFAULT 0,
    photo_last_sent INTEGER DEFAULT 0,
    voice_last_sent INTEGER DEFAULT 0
)
""")
conn.commit()

def fmt(ts):
    return datetime.fromtimestamp(ts).strftime("%d.%m.%Y %H:%M")

HELP_TEXT = (
    "ℹ️ *Правила:*\n\n"
    "📝 Текст — 1 раз в 3 часа\n"
    "📸 Фото + текст — 1 раз в 24 часа\n"
    "🎤 Голос — 1 раз в 24 часа (до 15 сек)\n\n"
    "🕶️ Всё публикуется анонимно"
)

async def start(update, context):
    await update.message.reply_text(HELP_TEXT, parse_mode="Markdown")

# ---------- ПРИЁМ СООБЩЕНИЙ ----------
async def handle_message(update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    uid = user.id

    if uid in BLACKLIST:
        await update.message.reply_text("⛔ Вам запрещено отправлять сообщения.")
        return

    is_owner = uid == OWNER_ID
    is_whitelisted = uid in WHITELIST

    is_photo = bool(update.message.photo)
    is_voice = bool(update.message.voice)
    text = (update.message.text or update.message.caption or "").strip()
    now = int(time.time())

    cursor.execute("SELECT * FROM users WHERE user_id=?", (uid,))
    row = cursor.fetchone()

    if not row:
        cursor.execute("INSERT INTO users (user_id) VALUES (?)", (uid,))
        conn.commit()
        last_sent = photo_last_sent = voice_last_sent = 0
    else:
        _, last_sent, photo_last_sent, voice_last_sent = row

    # ---------- ЛИМИТЫ ----------
    if not is_owner and not is_whitelisted:
        if is_voice:
            if update.message.voice.duration > MAX_VOICE_DURATION:
                await update.message.reply_text("⛔ Голосовое больше 15 секунд.")
                return
            if now - voice_last_sent < VOICE_COOLDOWN:
                await update.message.reply_text(
                    f"🎤 Голос — раз в 24 часа.\n🕒 Можно снова: {fmt(voice_last_sent + VOICE_COOLDOWN)}"
                )
                return
        elif is_photo:
            if now - photo_last_sent < PHOTO_COOLDOWN:
                await update.message.reply_text(
                    f"📸 Фото — раз в 24 часа.\n🕒 Можно снова: {fmt(photo_last_sent + PHOTO_COOLDOWN)}"
                )
                return
        else:
            if now - last_sent < TEXT_COOLDOWN:
                await update.message.reply_text(
                    f"📝 Текст — раз в 3 часа.\n🕒 Можно снова: {fmt(last_sent + TEXT_COOLDOWN)}"
                )
                return

    # ---------- ПУБЛИКАЦИЯ В КАНАЛ ----------
    if is_voice:
        msg = await context.bot.send_voice(
            CHANNEL_ID,
            update.message.voice.file_id,
            caption=", итд..."
        )
        cursor.execute("UPDATE users SET voice_last_sent=? WHERE user_id=?", (now, uid))

    elif is_photo:
        msg = await context.bot.send_photo(
            CHANNEL_ID,
            update.message.photo[-1].file_id,
            caption=f"{text}, итд..." if text else ", итд..."
        )
        cursor.execute("UPDATE users SET photo_last_sent=? WHERE user_id=?", (now, uid))

    else:
        msg = await context.bot.send_message(
            CHANNEL_ID,
            f"{text}, итд..."
        )
        cursor.execute("UPDATE users SET last_sent=? WHERE user_id=?", (now, uid))

    conn.commit()

    await update.message.reply_text("✅ Опубликовано")

    # ---------- ЛОГ-КАНАЛ ----------
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("❌ Удалить из канала", callback_data=f"del:{msg.message_id}"),
            InlineKeyboardButton("🗑 Удалить лог", callback_data=f"logdel")
        ]
    ])

    await context.bot.send_message(
        LOG_CHANNEL_ID,
        f"🆕 Опубликовано\n"
        f"🕒 {fmt(now)}\n"
        f"Тип: {'voice' if is_voice else 'photo' if is_photo else 'text'}\n\n"
        f"{text}, итд...",
        reply_markup=keyboard
    )

# ---------- INLINE ----------
async def callbacks(update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.from_user.id != OWNER_ID:
        return

    data = query.data

    if data.startswith("del:"):
        msg_id = int(data.split(":")[1])
        await context.bot.delete_message(CHANNEL_ID, msg_id)
        await query.edit_message_text("❌ Удалено из канала")

    elif data == "logdel":
        await query.message.delete()

def main():
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(callbacks))
    app.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, handle_message))

    app.run_polling()

if __name__ == "__main__":
    main()
