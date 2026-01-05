import os
import time
import sqlite3
from datetime import datetime, timedelta
from telegram.ext import ApplicationBuilder, MessageHandler, ContextTypes, filters

TOKEN = os.getenv("TOKEN")
CHANNEL_ID = int(os.getenv("CHANNEL_ID"))

OWNER_USERNAME = "nikkat1"   # ты без ограничений

COOLDOWN = 3 * 3600          # 3 часа
SPAM_LIMIT = 3               # предупреждений
MUTE_TIME = 6 * 3600         # мут 6 часов

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

def format_time(ts: int) -> str:
    """Возвращает локальное время пользователя"""
    return datetime.fromtimestamp(ts).strftime("%d.%m.%Y %H:%M")

async def handle_message(update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id
    username = user.username
    now = int(time.time())

    # ---------- ТЫ (БЕЗ ОГРАНИЧЕНИЙ) ----------
    if username == OWNER_USERNAME:
        text = update.message.text.strip()
        final_text = f"{text}, итд..."
        await context.bot.send_message(chat_id=CHANNEL_ID, text=final_text)
        await update.message.reply_text("✅ Опубликовано (без ограничений)")
        return

    # ---------- ВСЕ ОСТАЛЬНЫЕ ----------
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

    # мут
    if mute_until > now:
        until = format_time(mute_until)
        await update.message.reply_text(
            f"🔇 Вы временно замьючены за спам.\n"
            f"⏳ Можно писать снова: {until}"
        )
        return

    # проверка кулдауна
    if now - last_sent < COOLDOWN:
        spam_count += 1
        next_time = last_sent + COOLDOWN
        next_time_str = format_time(next_time)

        if spam_count >= SPAM_LIMIT:
            mute_until = now + MUTE_TIME
            mute_str = format_time(mute_until)
            await update.message.reply_text(
                f"🚫 Слишком много сообщений.\n"
                f"🔇 Мут до: {mute_str}"
            )
        else:
            await update.message.reply_text(
                f"⚠️ Ограничение: 1 сообщение раз в 3 часа.\n"
                f"🕒 Можно отправить снова: {next_time_str}"
            )

        cursor.execute("""
            UPDATE users
            SET spam_count=?, mute_until=?
            WHERE user_id=?
        """, (spam_count, mute_until, user_id))
        conn.commit()
        return

    # публикация
    text = update.message.text.strip()
    final_text = f"{text}, итд..."

    await context.bot.send_message(chat_id=CHANNEL_ID, text=final_text)

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
