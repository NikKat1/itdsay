import os
import time
import sqlite3
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
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

OWNER_ID = 985545005  # твой Telegram ID

# ⏱ ЛИМИТЫ
TEXT_COOLDOWN = 3600
PHOTO_COOLDOWN = 24 * 3600
VOICE_COOLDOWN = 24 * 3600
VIDEO_COOLDOWN = 24 * 3600
MAX_VOICE_DURATION = 15
MAX_VIDEO_DURATION = 10

# 📦 БАЗА
conn = sqlite3.connect("database.db", check_same_thread=False)
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    last_sent INTEGER DEFAULT 0,
    photo_last_sent INTEGER DEFAULT 0,
    voice_last_sent INTEGER DEFAULT 0,
    video_last_sent INTEGER DEFAULT 0,
    banned INTEGER DEFAULT 0
)
""")
conn.commit()

# 📜 ПРАВИЛА
HELP_TEXT = (
    "ℹ️ *Правила:*\n\n"
    "📝 Текст — 1 раз в 1 час\n"
    "📸 Фото — 1 раз в 24 часа\n"
    "🎤 Голос — 1 раз в 24 часа (до 15 сек)\n"
    "🎵 Аудио — 1 раз в 24 часа (до 15 сек)\n"
    "🎬 Видео — 1 раз в 24 часа (до 10 сек)\n\n"
    "🕶️ Все сообщения публикуются анонимно\n"
    "🚫 За нарушения пользователь блокируется\n"
    "➕ К сообщениям добавляется `, итд...`"
)

async def start(update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(HELP_TEXT, parse_mode="Markdown")

# 👑 ПРОВЕРКА БАНА
def is_banned(uid):
    cursor.execute("SELECT banned FROM users WHERE user_id=?", (uid,))
    row = cursor.fetchone()
    return row and row[0] == 1

# 👁 ЛОГ ВЛАДЕЛЬЦУ + КНОПКА
async def log_to_owner(context, user, content_type):
    username = f"@{user.username}" if user.username else "нет"
    text = (
        "👁 Новый анонимный пост\n\n"
        f"👤 Имя: {user.first_name}\n"
        f"🆔 ID: {user.id}\n"
        f"🔗 Username: {username}\n"
        f"📦 Тип: {content_type}"
    )

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🚫 Заблокировать", callback_data=f"ban:{user.id}")],
        [InlineKeyboardButton("🔓 Разблокировать", callback_data=f"unban:{user.id}")]
    ])

    await context.bot.send_message(
        OWNER_ID,
        text,
        reply_markup=keyboard
    )

# 🚫 ОБРАБОТКА КНОПОК
async def handle_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.from_user.id != OWNER_ID:
        return

    data = query.data
    action, uid = data.split(":")
    uid = int(uid)

    if action == "ban":
        cursor.execute("UPDATE users SET banned=1 WHERE user_id=?", (uid,))
        conn.commit()
        await query.edit_message_text(f"🚫 Пользователь {uid} заблокирован")

    elif action == "unban":
        cursor.execute("UPDATE users SET banned=0 WHERE user_id=?", (uid,))
        conn.commit()
        await query.edit_message_text(f"🔓 Пользователь {uid} разблокирован")

async def handle_message(update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    uid = user.id
    now = int(time.time())

    is_photo = bool(update.message.photo)
    is_voice = bool(update.message.voice)
    is_audio = bool(update.message.audio)
    is_video = bool(update.message.video)
    text = (update.message.text or update.message.caption or "").strip()

    cursor.execute("SELECT * FROM users WHERE user_id=?", (uid,))
    row = cursor.fetchone()

    if not row:
        cursor.execute("INSERT INTO users (user_id) VALUES (?)", (uid,))
        conn.commit()
        last_sent = photo_last_sent = voice_last_sent = video_last_sent = banned = 0
    else:
        _, last_sent, photo_last_sent, voice_last_sent, video_last_sent, banned = row

    # 🚫 ЕСЛИ ЗАБАНЕН
    if banned:
        return

    # 👑 ВЛАДЕЛЕЦ БЕЗ ОГРАНИЧЕНИЙ
    if uid == OWNER_ID:
        if is_voice:
            await context.bot.send_voice(CHANNEL_ID, update.message.voice.file_id, caption=", итд...")
        elif is_audio:
            await context.bot.send_audio(CHANNEL_ID, update.message.audio.file_id, caption=", итд...")
        elif is_video:
            await context.bot.send_video(CHANNEL_ID, update.message.video.file_id, caption=f"{text}, итд..." if text else ", итд...")
        elif is_photo:
            await context.bot.send_photo(CHANNEL_ID, update.message.photo[-1].file_id, caption=f"{text}, итд..." if text else ", итд...")
        else:
            await context.bot.send_message(CHANNEL_ID, f"{text}, итд...")
        await update.message.reply_text("✅ Опубликовано")
        return

    # 🎤 ГОЛОС
    if is_voice:
        if update.message.voice.duration > MAX_VOICE_DURATION:
            await update.message.reply_text("⛔ Голос больше 15 секунд.")
            return
        if now - voice_last_sent < VOICE_COOLDOWN:
            await update.message.reply_text("⏳ Голос можно раз в 24 часа.")
            return

        await context.bot.send_voice(CHANNEL_ID, update.message.voice.file_id, caption=", итд...")
        await log_to_owner(context, user, "Голос")

        cursor.execute("UPDATE users SET voice_last_sent=? WHERE user_id=?", (now, uid))
        conn.commit()
        await update.message.reply_text("✅ Голосовое опубликовано")
        return

    # 🎵 АУДИО
    if is_audio:
        if update.message.audio.duration > MAX_VOICE_DURATION:
            await update.message.reply_text("⛔ Аудио больше 15 секунд.")
            return
        if now - voice_last_sent < VOICE_COOLDOWN:
            await update.message.reply_text("⏳ Аудио можно раз в 24 часа.")
            return

        await context.bot.send_audio(CHANNEL_ID, update.message.audio.file_id, caption=", итд...")
        await log_to_owner(context, user, "Аудио")

        cursor.execute("UPDATE users SET voice_last_sent=? WHERE user_id=?", (now, uid))
        conn.commit()
        await update.message.reply_text("✅ Аудио опубликовано")
        return

    # 🎬 ВИДЕО
    if is_video:
        if update.message.video.duration > MAX_VIDEO_DURATION:
            await update.message.reply_text("⛔ Видео больше 10 секунд.")
            return
        if now - video_last_sent < VIDEO_COOLDOWN:
            await update.message.reply_text("⏳ Видео можно раз в 24 часа.")
            return

        await context.bot.send_video(CHANNEL_ID, update.message.video.file_id, caption=f"{text}, итд..." if text else ", итд...")
        await log_to_owner(context, user, "Видео")

        cursor.execute("UPDATE users SET video_last_sent=? WHERE user_id=?", (now, uid))
        conn.commit()
        await update.message.reply_text("✅ Видео опубликовано")
        return

    # 📸 ФОТО
    if is_photo:
        if now - photo_last_sent < PHOTO_COOLDOWN:
            await update.message.reply_text("⏳ Фото можно раз в 24 часа.")
            return

        await context.bot.send_photo(CHANNEL_ID, update.message.photo[-1].file_id, caption=f"{text}, итд..." if text else ", итд...")
        await log_to_owner(context, user, "Фото")

        cursor.execute("UPDATE users SET photo_last_sent=? WHERE user_id=?", (now, uid))
        conn.commit()
        await update.message.reply_text("✅ Фото опубликовано")
        return

    # 📝 ТЕКСТ
    if now - last_sent < TEXT_COOLDOWN:
        await update.message.reply_text("⏳ Текст можно раз в 1 час.")
        return

    await context.bot.send_message(CHANNEL_ID, f"{text}, итд...")
    await log_to_owner(context, user, "Текст")

    cursor.execute("UPDATE users SET last_sent=? WHERE user_id=?", (now, uid))
    conn.commit()
    await update.message.reply_text("✅ Опубликовано")

def main():
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(handle_buttons))
    app.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, handle_message))
    app.run_polling()

if __name__ == "__main__":
    main()
