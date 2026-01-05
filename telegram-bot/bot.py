import os
import time
import sqlite3
from telegram.ext import (
    ApplicationBuilder,
    MessageHandler,
    CommandHandler,
    ContextTypes,
    filters
)

TOKEN = os.getenv("TOKEN")
CHANNEL_ID = int(os.getenv("CHANNEL_ID"))

OWNER_ID = 985545005

TEXT_COOLDOWN = 1 * 3600
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

HELP_TEXT = (
    "ℹ️ *Правила:*\n\n"
    "📝 Текст — 1 раз в 3 часа\n"
    "📸 Фото + текст — 1 раз в 24 часа\n"
    "🎤 Голос — 1 раз в 24 часа (до 15 сек)\n\n"
    "🕶️ Все сообщения публикуются анонимно\n"
    "➕ К сообщениям добавляется `, итд...`"
)

async def start(update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(HELP_TEXT, parse_mode="Markdown")

async def handle_message(update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    uid = user.id
    now = int(time.time())

    is_photo = bool(update.message.photo)
    is_voice = bool(update.message.voice)
    text = (update.message.text or update.message.caption or "").strip()

    cursor.execute("SELECT * FROM users WHERE user_id=?", (uid,))
    row = cursor.fetchone()

    if not row:
        cursor.execute("INSERT INTO users (user_id) VALUES (?)", (uid,))
        conn.commit()
        last_sent = photo_last_sent = voice_last_sent = 0
    else:
        _, last_sent, photo_last_sent, voice_last_sent = row

    # 👑 ТЫ — БЕЗ ОГРАНИЧЕНИЙ
    if uid == OWNER_ID:
        if is_voice:
            await context.bot.send_voice(
                CHANNEL_ID,
                update.message.voice.file_id,
                caption=", итд..."
            )
        elif is_photo:
            await context.bot.send_photo(
                CHANNEL_ID,
                update.message.photo[-1].file_id,
                caption=f"{text}, итд..." if text else ", итд..."
            )
        else:
            await context.bot.send_message(
                CHANNEL_ID,
                f"{text}, итд..."
            )
        await update.message.reply_text("✅ Опубликовано")
        return

    # 🎤 ГОЛОС
    if is_voice:
        if update.message.voice.duration > MAX_VOICE_DURATION:
            await update.message.reply_text("⛔ Голосовое больше 15 секунд.")
            return

        if now - voice_last_sent < VOICE_COOLDOWN:
            await update.message.reply_text("⏳ Голос можно отправлять раз в 24 часа.")
            return

        await context.bot.send_voice(
            CHANNEL_ID,
            update.message.voice.file_id,
            caption=", итд..."
        )

        cursor.execute(
            "UPDATE users SET voice_last_sent=? WHERE user_id=?",
            (now, uid)
        )
        conn.commit()

        await update.message.reply_text("✅ Голосовое опубликовано")
        return

    # 📸 ФОТО
    if is_photo:
        if now - photo_last_sent < PHOTO_COOLDOWN:
            await update.message.reply_text("⏳ Фото можно отправлять раз в 24 часа.")
            return

        await context.bot.send_photo(
            CHANNEL_ID,
            update.message.photo[-1].file_id,
            caption=f"{text}, итд..." if text else ", итд..."
        )

        cursor.execute(
            "UPDATE users SET photo_last_sent=? WHERE user_id=?",
            (now, uid)
        )
        conn.commit()

        await update.message.reply_text("✅ Фото опубликовано")
        return

    # 📝 ТЕКСТ
    if now - last_sent < TEXT_COOLDOWN:
        await update.message.reply_text("⏳ Текст можно отправлять раз в 3 часа.")
        return

    await context.bot.send_message(
        CHANNEL_ID,
        f"{text}, итд..."
    )

    cursor.execute(
        "UPDATE users SET last_sent=? WHERE user_id=?",
        (now, uid)
    )
    conn.commit()

    await update.message.reply_text("✅ Опубликовано")

def main():
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, handle_message))
    app.run_polling()

if __name__ == "__main__":
    main()
