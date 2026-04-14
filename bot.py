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

# --- НАСТРОЙКИ ---
TOKEN = os.getenv("TOKEN")
CHANNEL_ID = int(os.getenv("CHANNEL_ID"))
OWNER_ID = 985545005 

# Путь к БД в папке data для BotHost
DB_PATH = "data/database.db"

# Создаем папку data, если пользователь забыл
if not os.path.exists("data"):
    os.makedirs("data")

# ⏱ ЛИМИТЫ (в секундах)
TEXT_COOLDOWN = 3600
PHOTO_COOLDOWN = 24 * 3600
VOICE_COOLDOWN = 24 * 3600
VIDEO_COOLDOWN = 24 * 3600
GIF_COOLDOWN = 24 * 3600
AUDIO_COOLDOWN = 24 * 3600

MAX_VOICE_DURATION = 15
MAX_VIDEO_DURATION = 60
MAX_GIF_DURATION = 60

# --- БАЗА ДАННЫХ ---
conn = sqlite3.connect(DB_PATH, check_same_thread=False)
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    last_sent INTEGER DEFAULT 0,
    photo_last_sent INTEGER DEFAULT 0,
    voice_last_sent INTEGER DEFAULT 0,
    video_last_sent INTEGER DEFAULT 0,
    gif_last_sent INTEGER DEFAULT 0,
    audio_last_sent INTEGER DEFAULT 0,
    banned INTEGER DEFAULT 0
)
""")

cursor.execute("PRAGMA table_info(users)")
existing_columns = [column[1] for column in cursor.fetchall()]
for col in ["gif_last_sent", "audio_last_sent"]:
    if col not in existing_columns:
        cursor.execute(f"ALTER TABLE users ADD COLUMN {col} INTEGER DEFAULT 0")
conn.commit()

# --- ТЕКСТЫ ---
HELP_TEXT = (
    "ℹ️ *Правила:*\n\n"
    "📝 Текст — 1 раз в 1 час\n"
    "📸 Фото — 1 раз в 24 часа\n"
    "🎤 Голос — 1 раз в 24 часа (до 15 сек)\n"
    "🎬 Видео — 1 раз в 24 часа (до 1 мин)\n"
    "🖼 GIF — 1 раз в 24 часа (до 1 мин)\n"
    "🎵 Музыка — 1 раз в 24 часа\n\n"
    "🕶️ Все сообщения анонимны\n"
    "🚫 За нарушения — бан\n"
    "➕ Добавляется `, итд...`"
)

# --- ФУНКЦИИ ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(HELP_TEXT, parse_mode="Markdown")

async def log_to_owner(context, user, content_type):
    username = f"@{user.username}" if user.username else "нет"
    text = (
        f"👁 Новый анонимный пост\n\n"
        f"👤 Имя: {user.first_name}\n"
        f"🆔 ID: {user.id}\n"
        f"🔗 Username: {username}\n"
        f"📦 Тип: {content_type}"
    )
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🚫 Заблокировать", callback_data=f"ban:{user.id}")],
        [InlineKeyboardButton("🔓 Разблокировать", callback_data=f"unban:{user.id}")]
    ])
    await context.bot.send_message(OWNER_ID, text, reply_markup=keyboard)

async def handle_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.from_user.id != OWNER_ID: return
    
    action, uid = query.data.split(":")
    is_banned = 1 if action == "ban" else 0
    cursor.execute("UPDATE users SET banned=? WHERE user_id=?", (is_banned, uid))
    conn.commit()
    await query.edit_message_text(f"✅ Пользователь {uid}: {'забанен' if is_banned else 'разбанен'}")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    m = update.message
    if not m or not m.from_user: return
    user = m.from_user
    uid = user.id
    now = int(time.time())

    cursor.execute("SELECT * FROM users WHERE user_id=?", (uid,))
    row = cursor.fetchone()
    
    if not row:
        cursor.execute("INSERT INTO users (user_id) VALUES (?)", (uid,))
        conn.commit()
        user_data = {"last_sent": 0, "photo_last_sent": 0, "voice_last_sent": 0, 
                     "video_last_sent": 0, "gif_last_sent": 0, "audio_last_sent": 0, "banned": 0}
    else:
        cursor.execute("PRAGMA table_info(users)")
        cols = [c[1] for c in cursor.fetchall()]
        user_data = dict(zip(cols, row))

    if user_data.get("banned"): return

    is_admin = (uid == OWNER_ID)
    text_content = (m.text or m.caption or "").strip()
    caption = f"{text_content}, итд..." if text_content else ", итд..."

    sent_flag = False
    content_name = ""

    # ГОЛОС
    if m.voice:
        if not is_admin:
            if m.voice.duration > MAX_VOICE_DURATION:
                return await m.reply_text("⛔ Голос больше 15 секунд.")
            if now - user_data.get('voice_last_sent', 0) < VOICE_COOLDOWN:
                return await m.reply_text("⏳ Голос можно раз в 24 часа.")
        await context.bot.send_voice(CHANNEL_ID, m.voice.file_id, caption=", итд...")
        cursor.execute("UPDATE users SET voice_last_sent=? WHERE user_id=?", (now, uid))
        sent_flag, content_name = True, "Голос"

    # МУЗЫКА
    elif m.audio:
        if not is_admin and (now - user_data.get('audio_last_sent', 0) < AUDIO_COOLDOWN):
            return await m.reply_text("⏳ Музыку можно раз в 24 часа.")
        await context.bot.send_audio(CHANNEL_ID, m.audio.file_id, caption=caption)
        cursor.execute("UPDATE users SET audio_last_sent=? WHERE user_id=?", (now, uid))
        sent_flag, content_name = True, "Музыка"

    # ВИДЕО
    elif m.video:
        if not is_admin:
            if m.video.duration > MAX_VIDEO_DURATION:
                return await m.reply_text("⛔ Видео больше 1 минуты.")
            if now - user_data.get('video_last_sent', 0) < VIDEO_COOLDOWN:
                return await m.reply_text("⏳ Видео можно раз в 24 часа.")
        await context.bot.send_video(CHANNEL_ID, m.video.file_id, caption=caption)
        cursor.execute("UPDATE users SET video_last_sent=? WHERE user_id=?", (now, uid))
        sent_flag, content_name = True, "Видео"

    # GIF
    elif m.animation:
        if not is_admin and (now - user_data.get('gif_last_sent', 0) < GIF_COOLDOWN):
            return await m.reply_text("⏳ GIF можно раз в 24 часа.")
        await context.bot.send_animation(CHANNEL_ID, m.animation.file_id, caption=caption)
        cursor.execute("UPDATE users SET gif_last_sent=? WHERE user_id=?", (now, uid))
        sent_flag, content_name = True, "GIF"

    # ФОТО
    elif m.photo:
        if not is_admin and (now - user_data.get('photo_last_sent', 0) < PHOTO_COOLDOWN):
            return await m.reply_text("⏳ Фото можно раз в 24 часа.")
        await context.bot.send_photo(CHANNEL_ID, m.photo[-1].file_id, caption=caption)
        cursor.execute("UPDATE users SET photo_last_sent=? WHERE user_id=?", (now, uid))
        sent_flag, content_name = True, "Фото"

    # ПРОСТО ТЕКСТ
    elif text_content:
        if not is_admin and (now - user_data.get('last_sent', 0) < TEXT_COOLDOWN):
            return await m.reply_text("⏳ Текст можно раз в 1 час.")
        await context.bot.send_message(CHANNEL_ID, f"{text_content}, итд...")
        cursor.execute("UPDATE users SET last_sent=? WHERE user_id=?", (now, uid))
        sent_flag, content_name = True, "Текст"

    if sent_flag:
        conn.commit()
        if not is_admin: 
            await log_to_owner(context, user, content_name)
        await m.reply_text(f"✅ {content_name} опубликовано")

def main():
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(handle_buttons))
    app.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, handle_message))
    app.run_polling()

if __name__ == "__main__":
    main()
