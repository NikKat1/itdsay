import os
import time
import sqlite3
from telegram.ext import ApplicationBuilder, MessageHandler, ContextTypes, filters

TOKEN = os.getenv("TOKEN")
CHANNEL_ID = int(os.getenv("CHANNEL_ID"))

COOLDOWN = 3600          # 1 час
SPAM_LIMIT = 3           # попытки
MUTE_TIME = 6 * 3600     # мут 6 часов

conn = sqlite3.connect("database.db", check_same_thread=False)
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    last_sent INTEGER,
    spam_count INTEGER DEFAULT 0,
    mute_until INTEGER DEFAULT 0
)
""")
conn.commit()

async def handle_message(update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    now = int(time.time())

    cursor.execute("SELECT * FROM users WHERE user_id=?", (user_id,))
    row = cursor.fetchone()

    if not row:
        cursor.execute(
            "INSERT INTO users (user_id, last_sent) VALUES (?, ?)",
            (user_id, 0)
        )
        conn.commit()
        last_sent = spam_count = mute_until = 0
    else:
        _, last_sent, spam_count, mute_until = row

    if mute_until > now:
        await update.message.reply_text("🔇 Вы временно замьючены")
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

    # --- АНОНИМНАЯ ПУБЛИКАЦИЯ ---
    text = update.message.text.strip()

    # добавляем ", итд..." в конец
    final_text = f"{text}, итд..."

    await context.bot.send_message(
        chat_id=CHANNEL_ID,
        text=final_text
    )

    cursor.execute("""
        UPDATE users
        SET last_sent=?, spam_count=0
        WHERE user_id=?
    """, (now, user_id))
    conn.commit()

    await update.message.reply_text("✅ Опубликовано анонимно")

def main():
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.run_polling()

if __name__ == "__main__":
    main()
