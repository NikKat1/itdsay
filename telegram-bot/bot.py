import os
import time
import sqlite3
from datetime import datetime
from telegram.ext import (
    ApplicationBuilder,
    MessageHandler,
    CommandHandler,
    ContextTypes,
    filters
)

TOKEN = os.getenv("TOKEN")
CHANNEL_ID = int(os.getenv("CHANNEL_ID"))

OWNER_USERNAME = "nikkat1"

TEXT_COOLDOWN = 3 * 3600
PHOTO_COOLDOWN = 24 * 3600
VOICE_COOLDOWN = 24 * 3600
MAX_VOICE_DURATION = 15  # секунд

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

def fmt(ts: int) -> str:
    return datetime.fromtimestamp(ts).strftime("%d.%m.%Y %H:%M")

HELP_TEXT = (
    "ℹ️ *Как работает бот:*\n\n"
    "📝 Текст — 1 раз в 3 часа\n"
    "📸 Фото + текст — 1 раз в 24 часа\n"
    "🎤 Голос — 1 раз в 24 часа (до 15 секунд)\n\n"
    "🕶️ Всё публикуется анонимно\n"
    "➕ Подпись у фото и голоса: `, итд...`"
)

# ---------- /start ----------
async def start(update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(HELP_TEXT, parse_mode="Markdown")

# ---------- сообщения ----------
async def handle_message(update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    uid = user.id
    username = user.username
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

    # 👑 ВЛАДЕЛЕЦ — БЕЗ ОГРАНИЧЕНИЙ
    if username == OWNER_USERNAME:
        if is_voice:
            await context.bot.send_voice(
                chat_id=CHANNEL_ID,
                voice=update.message.voice.file_id,
                caption=", итд..."
            )
        elif is_photo:
            await context.bot.send_photo(
                chat_id=CHANNEL_ID,
                photo=update.message.photo[-1].file_id,
                caption=f"{text}, итд..." if text else ", итд..."
            )
        else:
            await context.bot.send_message(
                chat_id=CHANNEL_ID,
                text=f"{text}, итд..."
            )
        return

    # 🎤 ГОЛОС
    if is_voice:
        duration = update.message.voice.duration

        if duration > MAX_VOICE_DURATION:
            await update.message.reply_text(
                "⛔ Голосовое слишком длинное.\n"
                "Максимум — 15 секунд."
            )
            return

        if now - voice_last_sent < VOICE_COOLDOWN:
            await update.message.reply_text(
                f"🎤 Голос можно отправлять раз в 24 часа.\n"
                f"🕒 Можно снова: {fmt(voice_last_sent + VOICE_COOLDOWN)}"
            )
            return

        await context.bot.send_voice(
            chat_id=CHANNEL_ID,
            voice=update.message.voice.file_id,
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
            await update.message.reply_text(
                f"📸 Фото можно отправлять раз в 24 часа.\n"
                f"🕒 Можно снова: {fmt(photo_last_sent + PHOTO_COOLDOWN)}"
            )
            return

        await context.bot.send_photo(
            chat_id=CHANNEL_ID,
            photo=update.message.photo[-1].file_id,
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
        await update.message.reply_text(
            f"📝 Текст можно отправлять раз в 3 часа.\n"
            f"🕒 Можно снова: {fmt(last_sent + TEXT_COOLDOWN)}"
        )
        return

    await context.bot.send_message(
        chat_id=CHANNEL_ID,
        text=f"{text}, итд..."
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
