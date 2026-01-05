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
LOG_CHANNEL_ID = int(os.getenv("LOG_CHANNEL_ID"))

OWNER_USERNAME = "nikkat1"

WHITELIST = {"nikkat1"}
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

cursor.execute("""
CREATE TABLE IF NOT EXISTS queue (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    type TEXT,
    file_id TEXT,
    text TEXT,
    created_at INTEGER
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
    "⛔ Спам запрещён\n"
    "🕶️ Все сообщения публикуются анонимно\n"
)

# ---------- /start ----------
async def start(update, context):
    await update.message.reply_text(HELP_TEXT, parse_mode="Markdown")

# ---------- сообщения ----------
async def handle_message(update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    uid = user.id
    username = user.username or ""

    if username in BLACKLIST:
        await update.message.reply_text("⛔ Вам запрещено отправлять сообщения.")
        return

    is_owner = username == OWNER_USERNAME
    is_whitelisted = username in WHITELIST

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

    # ---------- ЛИМИТЫ (НЕ ДЛЯ ТЕБЯ И WHITELIST) ----------
    if not is_owner and not is_whitelisted:
        if is_voice:
            if update.message.voice.duration > MAX_VOICE_DURATION:
                await update.message.reply_text("⛔ Голосовое больше 15 секунд.")
                return
            if now - voice_last_sent < VOICE_COOLDOWN:
                await update.message.reply_text(
                    f"🎤 Голос можно раз в 24 часа.\n🕒 Можно снова: {fmt(voice_last_sent + VOICE_COOLDOWN)}"
                )
                return
        elif is_photo:
            if now - photo_last_sent < PHOTO_COOLDOWN:
                await update.message.reply_text(
                    f"📸 Фото можно раз в 24 часа.\n🕒 Можно снова: {fmt(photo_last_sent + PHOTO_COOLDOWN)}"
                )
                return
        else:
            if now - last_sent < TEXT_COOLDOWN:
                await update.message.reply_text(
                    f"📝 Текст можно раз в 3 часа.\n🕒 Можно снова: {fmt(last_sent + TEXT_COOLDOWN)}"
                )
                return

    # ---------- В ОЧЕРЕДЬ НА МОДЕРАЦИЮ ----------
    msg_type = "text"
    file_id = None

    if is_voice:
        msg_type = "voice"
        file_id = update.message.voice.file_id
    elif is_photo:
        msg_type = "photo"
        file_id = update.message.photo[-1].file_id

    cursor.execute(
        "INSERT INTO queue (type, file_id, text, created_at) VALUES (?, ?, ?, ?)",
        (msg_type, file_id, text, now)
    )
    qid = cursor.lastrowid
    conn.commit()

    # ---------- УВЕДОМЛЕНИЕ ПОЛЬЗОВАТЕЛЮ ----------
    await update.message.reply_text("📥 Сообщение отправлено на модерацию.")

    # ---------- ЛОГ-КАНАЛ ----------
    caption = (
        f"🆕 Новое сообщение\n"
        f"🕒 {fmt(now)}\n"
        f"ID: {qid}\n"
        f"Тип: {msg_type}\n\n"
        f"{text}, итд...\n\n"
        f"/approve {qid}\n"
        f"/reject {qid}"
    )

    if msg_type == "text":
        await context.bot.send_message(LOG_CHANNEL_ID, caption)
    elif msg_type == "photo":
        await context.bot.send_photo(LOG_CHANNEL_ID, file_id, caption=caption)
    elif msg_type == "voice":
        await context.bot.send_voice(LOG_CHANNEL_ID, file_id, caption=", итд...\n\n/approve " + str(qid) + "\n/reject " + str(qid))

# ---------- /approve ----------
async def approve(update, context):
    if update.effective_user.username != OWNER_USERNAME:
        return

    try:
        qid = int(context.args[0])
    except:
        return

    cursor.execute("SELECT type, file_id, text FROM queue WHERE id=?", (qid,))
    row = cursor.fetchone()
    if not row:
        return

    msg_type, file_id, text = row

    if msg_type == "text":
        await context.bot.send_message(CHANNEL_ID, f"{text}, итд...")
    elif msg_type == "photo":
        await context.bot.send_photo(CHANNEL_ID, file_id, caption=f"{text}, итд...")
    elif msg_type == "voice":
        await context.bot.send_voice(CHANNEL_ID, file_id, caption=", итд...")

    cursor.execute("DELETE FROM queue WHERE id=?", (qid,))
    conn.commit()

# ---------- /reject ----------
async def reject(update, context):
    if update.effective_user.username != OWNER_USERNAME:
        return
    try:
        qid = int(context.args[0])
    except:
        return
    cursor.execute("DELETE FROM queue WHERE id=?", (qid,))
    conn.commit()

def main():
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("approve", approve))
    app.add_handler(CommandHandler("reject", reject))
    app.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, handle_message))

    app.run_polling()

if __name__ == "__main__":
    main()
