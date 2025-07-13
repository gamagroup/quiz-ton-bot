import sqlite3
import logging
import random
import asyncio
import os
from datetime import datetime, timedelta
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
    KeyboardButton,
    WebAppInfo
)
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
    MessageHandler,
    filters
)
from dotenv import load_dotenv

load_dotenv()
TOKEN = os.getenv("TOKEN")

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', 
    level=logging.INFO
)
logger = logging.getLogger(__name__)

def init_db():
    conn = sqlite3.connect('quiz_bot.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        telegram_id INTEGER UNIQUE,
        username TEXT,
        first_name TEXT,
        tokens INTEGER DEFAULT 100
    )''')
    conn.commit()
    conn.close()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    with sqlite3.connect('quiz_bot.db') as conn:
        c = conn.cursor()
        c.execute('''INSERT OR IGNORE INTO users (telegram_id, username, first_name)
                     VALUES (?, ?, ?)''', 
                  (user.id, user.username, user.first_name))
        conn.commit()

    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton("📝 شروع کوییز"), KeyboardButton("🏆 جدول رده‌بندی")],
            [KeyboardButton("💼 پروفایل من")],
            [KeyboardButton("🎮 اجرای بازی WebApp", web_app=WebAppInfo(url="https://game.gamagraphic.com"))]
        ],
        resize_keyboard=True
    )

    await update.message.reply_text(
        f"👋 سلام {user.first_name}!\n"
        "به ربات کوییز خوش آمدید!",
        reply_markup=keyboard
    )

async def start_quiz(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        keyboard = [
            [InlineKeyboardButton("تهران", callback_data="ans_1")],
            [InlineKeyboardButton("اصفهان", callback_data="ans_2")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_text(
            "❓ سوال آزمایشی: پایتخت ایران کدام است؟",
            reply_markup=reply_markup
        )
        logger.info("Quiz started successfully")
    except Exception as e:
        logger.error(f"Error in start_quiz: {e}")
        await update.message.reply_text("⚠️ خطا در شروع کوییز!")

async def button_click(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "ans_1":
        await query.edit_message_text("✅ پاسخ صحیح! +10 امتیاز")
    else:
        await query.edit_message_text("❌ پاسخ اشتباه!")

async def handle_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text

    if text == "📝 شروع کوییز":
        await start_quiz(update, context)
    elif text == "💼 پروفایل من":
        await update.message.reply_text("پروفایل کاربری")


def main():
    logger.info("Starting bot...")
    init_db()
    logger.info("Database initialized")

    if not TOKEN:
        logger.error("Bot token not found! Make sure .env file is correct.")
        return

    application = Application.builder().token(TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("quiz", start_quiz))
    application.add_handler(CallbackQueryHandler(button_click))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_messages))

    logger.info("Polling started...")
    print("Polling started with token:", TOKEN)
    application.run_polling()


if __name__ == '__main__':
    main()
