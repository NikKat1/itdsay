import os
import time
import sqlite3
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    MessageHandler,
    CommandHandler,
    ContextTypes,
    filters
)

load_dotenv()

TOKEN = os.getenv("TOKEN")
CHANNEL_ID = int(os.getenv("CHANNEL_ID"))
ADMINS = [123456789]  # ← ТВОЙ user_id

COOLDOWN = 3600
SPAM_LIMIT = 3
MUTE_TIME = 6 * 3600

conn = sqlite3.connect("database.db", check_same_thread=False)
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    last_sent INTEGER,
    spam_count INTEGER DEFAULT 0,
    mute_until INTEGER DEFAULT 0,
    banned INTEGER DEFAULT 0
)
""")
conn.commit()


def is_admin(user_id):
    return user_id in ADMINS


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id
    now = int(time.time())

    cursor.execute("SELECT * FROM users WHERE user_id=?", (user_id,))
    row = cursor.fetchone()

    if not row:
        cursor.execute(
            "INSERT INTO users (user_id, last_sent) VALUES (?, ?)",
            (user_id, 0)
        )
        conn.commit()
        last_sent = 0
        spam_count = 0
        mute_until = 0
        banned = 0
    else:
        _, last_sent, spam_count, mute_until, banned = row

    if banned:
        return

    if mute_until > now:
        await update.message.reply_text("🔇 Вы временно замьючены за спам")
        return

    if now - last_sent < COOLDOWN:
        spam_count += 1

        if spam_count >= SPAM_LIMIT:
            mute_until = now + MUTE_TIME
            await update.message.reply_text("🚫 Мут на 6 часов")
        else:
            await update.message.reply_text("⏳ Можно писать раз в час")

        cursor.execute("""
            UPDATE users
            SET spam_count=?, mute_until=?
            WHERE user_id=?
        """, (spam_count, mute_until, user_id))
        conn.commit()
        return

    await context.bot.send_message(
        chat_id=CHANNEL_ID,
        text=f"📨 @{user.username or user.first_name}:\n\n{update.message.text}"
    )

    cursor.execute("""
        UPDATE users
        SET last_sent=?, spam_count=0
        WHERE user_id=?
    """, (now, user_id))
    conn.commit()

    await update.message.reply_text("✅ Сообщение опубликовано")


# ---------- АДМИН КОМАНДЫ ----------

async def ban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    try:
        user_id = int(context.args[0])
        cursor.execute("UPDATE users SET banned=1 WHERE user_id=?", (user_id,))
        conn.commit()
        await update.message.reply_text(f"🚫 Забанен: {user_id}")
    except:
        await update.message.reply_text("Используй: /ban user_id")


async def unban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    try:
        user_id = int(context.args[0])
        cursor.execute("UPDATE users SET banned=0 WHERE user_id=?", (user_id,))
        conn.commit()
        await update.message.reply_text(f"✅ Разбанен: {user_id}")
    except:
        await update.message.reply_text("Используй: /unban user_id")


def main():
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("ban", ban))
    app.add_handler(CommandHandler("unban", unban))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    app.run_polling()


if __name__ == "__main__":
    main()
