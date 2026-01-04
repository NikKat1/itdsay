import os
import time
import sqlite3
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, CommandHandler, ContextTypes, filters

load_dotenv()

TOKEN = os.getenv("TOKEN")  # Bothost подставляет сам
CHANNEL_ID = -1003542757830  # ← ID ТВОЕГО КАНАЛА


ADMINS = [985545005]  # ← твой user_id

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

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id
    now = int(time.time())

    cursor.execute("SELECT * FROM users WHERE user_id=?", (user_id,))
    row = cursor.fetchone()

    if not row:
        cursor.execute("INSERT INTO users (user_id, last_sent) VALUES (?, ?)", (user_id, 0))
        conn.commit()
        last_sent = spam_count = mute_until = banned = 0
    else:
        _, last_sent, spam_count, mute_until, banned = row

    if banned:
        return

    if mute_until > now:
        await update.message.reply_text("🔇 Вы замьючены за спам")
        return

    if now - last_sent < COOLDOWN:
        spam_count += 1
        if spam_count >= SPAM_LIMIT:
            mute_until = now + MUTE_TIME
            await update.message.reply_text("🚫 Мут на 6 часов")
        else:
            await update.message.reply_text("⏳ Можно писать раз в час")

        cursor.execute("UPDATE users SET spam_count=?, mute_until=? WHERE user_id=?",
                       (spam_count, mute_until, user_id))
        conn.commit()
        return

    await context.bot.send_message(
        chat_id=CHANNEL_ID,
        text=f"📨 @{user.username or user.first_name}:\n\n{update.message.text}"
    )

    cursor.execute("UPDATE users SET last_sent=?, spam_count=0 WHERE user_id=?",
                   (now, user_id))
    conn.commit()

    await update.message.reply_text("✅ Опубликовано")

def main():
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.run_polling()

if __name__ == "__main__":
    main()
