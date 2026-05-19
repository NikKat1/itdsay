import os
import time
import sqlite3
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

# =========================
# CONFIG
# =========================
BOT_TOKEN = os.getenv("BOT_TOKEN")
CHANNEL_ID = -1003542757830
OWNER_ID = 985545005
DATABASE = "suggestions.db"

TEXT_LIMIT = 3600
MEDIA_LIMIT = 86400

MAX_VOICE = 15
MAX_VIDEO = 60

HELP_MESSAGE = """
ℹ️ *Правила:*

📝 Текст — 1 раз в 1 час
📸 Фото — 1 раз в 24 часа
🎤 Голос — 1 раз в 24 часа (до 15 сек)
🎬 Видео — 1 раз в 24 часа (до 1 мин)
🖼 GIF — 1 раз в 24 часа
🎵 Музыка — 1 раз в 24 часа

🕶️ Все сообщения анонимны
🚫 За нарушения — бан
➕ Добавляется `, итд...`
"""

# =========================
# DATABASE
# =========================
db = sqlite3.connect(DATABASE, check_same_thread=False)
cursor = db.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    banned INTEGER DEFAULT 0,
    text_time INTEGER DEFAULT 0,
    photo_time INTEGER DEFAULT 0,
    voice_time INTEGER DEFAULT 0,
    video_time INTEGER DEFAULT 0,
    gif_time INTEGER DEFAULT 0,
    audio_time INTEGER DEFAULT 0
)
""")
db.commit()


def get_user(uid: int):
    cursor.execute("SELECT * FROM users WHERE user_id=?", (uid,))
    row = cursor.fetchone()

    if row:
        return {
            "banned": row[1],
            "text_time": row[2],
            "photo_time": row[3],
            "voice_time": row[4],
            "video_time": row[5],
            "gif_time": row[6],
            "audio_time": row[7],
        }

    cursor.execute("INSERT INTO users (user_id) VALUES (?)", (uid,))
    db.commit()

    return {
        "banned": 0,
        "text_time": 0,
        "photo_time": 0,
        "voice_time": 0,
        "video_time": 0,
        "gif_time": 0,
        "audio_time": 0,
    }


def set_time(uid: int, field: str):
    cursor.execute(f"UPDATE users SET {field}=? WHERE user_id=?", (int(time.time()), uid))
    db.commit()


def set_ban(uid: int, value: int):
    cursor.execute("UPDATE users SET banned=? WHERE user_id=?", (value, uid))
    db.commit()


def cooldown_left(last: int, limit: int):
    return int(limit - (time.time() - last))


# =========================
# BOT
# =========================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        HELP_MESSAGE,
        parse_mode="Markdown"
    )


async def notify_owner(context, user, content_type):
    username = f"@{user.username}" if user.username else "нет"

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🚫 Заблокировать", callback_data=f"ban:{user.id}")],
        [InlineKeyboardButton("🔓 Разблокировать", callback_data=f"unban:{user.id}")]
    ])

    text = (
        f"👁 Новый анонимный пост\n\n"
        f"👤 Имя: {user.first_name}\n"
        f"🆔 ID: {user.id}\n"
        f"🔗 Username: {username}\n"
        f"📦 Тип: {content_type}"
    )

    await context.bot.send_message(
        OWNER_ID,
        text,
        reply_markup=keyboard
    )


async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.from_user.id != OWNER_ID:
        return

    action, uid = query.data.split(":")
    uid = int(uid)

    if action == "ban":
        set_ban(uid, 1)
        await query.edit_message_text(f"🚫 Пользователь {uid} заблокирован")
    else:
        set_ban(uid, 0)
        await query.edit_message_text(f"🔓 Пользователь {uid} разблокирован")


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return

    msg = update.message
    user = msg.from_user
    uid = user.id
    now = int(time.time())

    user_data = get_user(uid)

    if user_data["banned"]:
        await msg.reply_text("🚫 Вы заблокированы")
        return

    is_admin = uid == OWNER_ID

    text = (msg.text or msg.caption or "").strip()
    caption = f"{text}, итд..." if text else ", итд..."

    try:
        # TEXT
        if text and not any([msg.photo, msg.voice, msg.video, msg.animation, msg.audio]):
            if not is_admin and now - user_data["text_time"] < TEXT_LIMIT:
                await msg.reply_text("⏳ Текст можно раз в 1 час")
                return

            await context.bot.send_message(CHANNEL_ID, caption)
            set_time(uid, "text_time")

            if not is_admin:
                await notify_owner(context, user, "Текст")

            await msg.reply_text("✅ Текст опубликован")
            return

        # PHOTO
        if msg.photo:
            if not is_admin and now - user_data["photo_time"] < MEDIA_LIMIT:
                await msg.reply_text("⏳ Фото можно раз в 24 часа")
                return

            await context.bot.send_photo(
                CHANNEL_ID,
                msg.photo[-1].file_id,
                caption=caption
            )
            set_time(uid, "photo_time")

            if not is_admin:
                await notify_owner(context, user, "Фото")

            await msg.reply_text("✅ Фото опубликовано")
            return

        # VOICE
        if msg.voice:
            if msg.voice.duration > MAX_VOICE:
                await msg.reply_text("⛔ Голос больше 15 секунд")
                return

            if not is_admin and now - user_data["voice_time"] < MEDIA_LIMIT:
                await msg.reply_text("⏳ Голос можно раз в 24 часа")
                return

            await context.bot.send_voice(
                CHANNEL_ID,
                msg.voice.file_id,
                caption=", итд..."
            )
            set_time(uid, "voice_time")

            if not is_admin:
                await notify_owner(context, user, "Голос")

            await msg.reply_text("✅ Голос опубликован")
            return

        # VIDEO
        if msg.video:
            if msg.video.duration > MAX_VIDEO:
                await msg.reply_text("⛔ Видео больше 1 минуты")
                return

            if not is_admin and now - user_data["video_time"] < MEDIA_LIMIT:
                await msg.reply_text("⏳ Видео можно раз в 24 часа")
                return

            await context.bot.send_video(
                CHANNEL_ID,
                msg.video.file_id,
                caption=caption
            )
            set_time(uid, "video_time")

            if not is_admin:
                await notify_owner(context, user, "Видео")

            await msg.reply_text("✅ Видео опубликовано")
            return

        # GIF
        if msg.animation:
            if not is_admin and now - user_data["gif_time"] < MEDIA_LIMIT:
                await msg.reply_text("⏳ GIF можно раз в 24 часа")
                return

            await context.bot.send_animation(
                CHANNEL_ID,
                msg.animation.file_id,
                caption=caption
            )
            set_time(uid, "gif_time")

            if not is_admin:
                await notify_owner(context, user, "GIF")

            await msg.reply_text("✅ GIF опубликован")
            return

        # AUDIO
        if msg.audio:
            if not is_admin and now - user_data["audio_time"] < MEDIA_LIMIT:
                await msg.reply_text("⏳ Музыку можно раз в 24 часа")
                return

            await context.bot.send_audio(
                CHANNEL_ID,
                msg.audio.file_id,
                caption=caption
            )
            set_time(uid, "audio_time")

            if not is_admin:
                await notify_owner(context, user, "Музыка")

            await msg.reply_text("✅ Музыка опубликована")
            return

        await msg.reply_text("❌ Этот тип сообщения не поддерживается")

    except Exception as e:
        await msg.reply_text(f"Ошибка: {e}")


def main():
    if not BOT_TOKEN:
        raise ValueError("BOT_TOKEN не найден")

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, handle_message))

    print("Bot started")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
