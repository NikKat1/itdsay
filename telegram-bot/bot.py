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

conn = sqlite3.connect("database.db", check_same_thread=False)
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    last_sent INTEGER DEFAULT 0,
    photo_last_sent INTEGER DEFAULT 0
)
""")
conn.commit()

def fmt(ts):
    return datetime.fromtimestamp(ts).strftime("%d.%m.%Y %H:%M")

HELP_TEXT = (
    "ℹ️ *Как работает бот:*\n\n"
    "📝 *Текст* — можно отправлять раз в *3 часа*\n"
    "📸 *Фото + текст* — можно отправлять раз в *24 часа*\n\n"
    "⛔ Спам запрещён\n"
    "🕶️ Все сообщения публикуются *анонимно*\n"
    "➕ В конце сообщения автоматически добавляется `, итд...`\n\n"
    "👑 Владелец бота публикует без ограничений"
)

# ---------- /start ----------
async def start(update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        HELP_TEXT,
        parse_mode="Markdown"
    )

# ---------- сообщения ----------
async def handle_message(update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    uid = user.id
    username = user.username
    now = int(time.time())

    text = update.message.caption or update.message.text or ""
    text = text.strip()
    final_text = f"{text}, итд..." if text else None
    is_photo = bool(update.message.photo)

    cursor.execute("SELECT * FROM users WHERE user_id=?", (uid,))
    row = cursor.fetchone()

    if not row:
        cursor.execute(
            "INSERT INTO users (user_id) VALUES (?)",
            (uid,)
        )
        conn.commit()
        last_sent = photo_last_sent = 0
    else:
        _, last_sent, photo_last_sent = row

    # 👑 ты — без ограничений
    if username == OWNER_USERNAME:
        if is_photo:
            await context.bot.send_photo(
                chat_id=CHANNEL_ID,
                photo=update.message.photo[-1].file_id,
                caption=final_text
            )
        else:
            await context.bot.send_message(
                chat_id=CHANNEL_ID,
                text=final_text
            )
        return

    # 📸 фото
    if is_photo:
        if now - photo_last_sent < PHOTO_COOLDOWN:
            await update.message.reply_text(
                f"⚠️ Фото можно отправлять раз в 24 часа.\n"
                f"🕒 Можно снова: {fmt(photo_last_sent + PHOTO_COOLDOWN)}"
            )
            return

        await context.bot.send_photo(
            chat_id=CHANNEL_ID,
            photo=update.message.photo[-1].file_id,
            caption=final_text
        )

        cursor.execute(
            "UPDATE users SET photo_last_sent=? WHERE user_id=?",
            (now, uid)
        )
        conn.commit()

        await update.message.reply_text("✅ Фото опубликовано анонимно")
        return

    # 📝 текст
    if now - last_sent < TEXT_COOLDOWN:
        await update.message.reply_text(
            f"⚠️ Текст можно отправлять раз в 3 часа.\n"
            f"🕒 Можно снова: {fmt(last_sent + TEXT_COOLDOWN)}"
        )
        return

    await context.bot.send_message(
        chat_id=CHANNEL_ID,
        text=final_text
    )

    cursor.execute(
        "UPDATE users SET last_sent=? WHERE user_id=?",
        (now, uid)
    )
    conn.commit()

    await update.message.reply_text("✅ Опубликовано анонимно")

def main():
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, handle_message))

    app.run_polling()

if __name__ == "__main__":
    main()
