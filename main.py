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
from flask import Flask, render_template, request, redirect, url_for
from dotenv import load_dotenv
import openai

load_dotenv()
TOKEN = os.getenv("TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
openai.api_key = OPENAI_API_KEY

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', 
    level=logging.INFO
)
logger = logging.getLogger(__name__)

app = Flask(__name__)

@app.route('/')
def dashboard():
    with sqlite3.connect('quiz_bot.db') as conn:
        c = conn.cursor()
        c.execute("SELECT first_name, tokens, total_played, total_correct, last_played FROM users ORDER BY tokens DESC")
        users = c.fetchall()
    return render_template('dashboard.html', users=users)

@app.route('/questions')
def questions():
    with sqlite3.connect('quiz_bot.db') as conn:
        c = conn.cursor()
        c.execute("SELECT * FROM quizzes")
        questions = c.fetchall()
    return render_template('questions.html', questions=questions)

@app.route('/add-question', methods=['GET', 'POST'])
def add_question():
    if request.method == 'POST':
        question = request.form['question']
        options = [request.form[f'option{i}'] for i in range(1, 5)]
        correct = int(request.form['correct_option'])
        with sqlite3.connect('quiz_bot.db') as conn:
            c = conn.cursor()
            c.execute('''INSERT INTO quizzes (question, option1, option2, option3, option4, correct_option) 
                         VALUES (?, ?, ?, ?, ?, ?)''', (question, *options, correct))
            conn.commit()
        return redirect(url_for('questions'))
    return render_template('add_question.html')

def init_db():
    conn = sqlite3.connect('quiz_bot.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        telegram_id INTEGER UNIQUE,
        username TEXT,
        first_name TEXT,
        tokens INTEGER DEFAULT 100,
        total_played INTEGER DEFAULT 0,
        total_correct INTEGER DEFAULT 0,
        last_played TIMESTAMP,
        group_id INTEGER,
        avatar_url TEXT
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS quizzes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        question TEXT,
        option1 TEXT,
        option2 TEXT,
        option3 TEXT,
        option4 TEXT,
        correct_option INTEGER
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS groups (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT,
        owner_id INTEGER
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS group_members (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        group_id INTEGER,
        user_id INTEGER
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS followers (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        follower_id INTEGER,
        following_id INTEGER
    )''')
    conn.commit()
    conn.close()

async def generate_question():
    response = openai.ChatCompletion.create(
        model="gpt-4",
        messages=[
            {"role": "system", "content": "تو یک تولیدکننده سوال چندگزینه‌ای برای بازی هستی. یک سوال عمومی و چهار گزینه تولید کن که یکی از آن‌ها صحیح باشد و گزینه درست را مشخص کن."},
            {"role": "user", "content": "یک سوال تولید کن"}
        ]
    )
    return response.choices[0].message.content.strip()

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
            [KeyboardButton("🎮 اجرای بازی WebApp", web_app=WebAppInfo(url="https://gamagroup.github.io/quiz-ton-bot/"))]
        ],
        resize_keyboard=True
    )

    await update.message.reply_text(
        f"👋 سلام {user.first_name}!\n"
        "به ربات کوییز خوش آمدید!",
        reply_markup=keyboard
    )

async def ask_gpt_question(update, context, question_index):
    gpt_question = await generate_question()
    lines = gpt_question.split('\n')
    question_text = lines[0]
    options = lines[1:5]
    correct_option = next((i+1 for i, o in enumerate(options) if o.endswith('*')), None)
    clean_options = [o.replace('*', '').strip() for o in options]

    keyboard = [
        [InlineKeyboardButton(opt, callback_data=f"ans_{question_index}_{i+1}")]
        for i, opt in enumerate(clean_options)
    ]

    context.user_data[f'correct_{question_index}'] = correct_option

    await update.message.reply_text(
        f"❓ سوال {question_index+1}:\n{question_text}",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def start_quiz(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['score'] = 0
    context.user_data['current'] = 0
    await ask_gpt_question(update, context, 0)

async def button_click(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    data = query.data
    if not data.startswith("ans_"):
        return

    _, q_index, selected = data.split("_")
    q_index = int(q_index)
    selected = int(selected)
    correct = context.user_data.get(f"correct_{q_index}")

    user_id = query.from_user.id

    with sqlite3.connect('quiz_bot.db') as conn:
        c = conn.cursor()
        c.execute('''UPDATE users SET total_played = total_played + 1, last_played = CURRENT_TIMESTAMP WHERE telegram_id = ?''', (user_id,))

        if selected == correct:
            context.user_data['score'] += 10
            c.execute('''UPDATE users SET tokens = tokens + 10, total_correct = total_correct + 1 WHERE telegram_id = ?''', (user_id,))
            conn.commit()
            await query.edit_message_text("✅ پاسخ صحیح! +10 امتیاز")
        else:
            await query.edit_message_text("❌ پاسخ اشتباه!")

    await asyncio.sleep(2)
    context.user_data['current'] += 1
    if context.user_data['current'] < 5:
        await ask_gpt_question(query.message, context, context.user_data['current'])
    else:
        score = context.user_data['score']
        await query.message.reply_text(f"🎉 بازی تمام شد!\nامتیاز نهایی شما: {score}")

async def handle_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    user_id = update.effective_user.id

    if text == "📝 شروع کوییز":
        await start_quiz(update, context)

    elif text == "💼 پروفایل من":
        with sqlite3.connect('quiz_bot.db') as conn:
            c = conn.cursor()
            c.execute('''SELECT tokens, total_played, total_correct, last_played, avatar_url FROM users WHERE telegram_id = ?''', (user_id,))
            row = c.fetchone()
            tokens, played, correct, last, avatar = row if row else (0, 0, 0, "-", "")

        await update.message.reply_text(
            f"👤 نام: {update.effective_user.first_name}\n"
            f"🪙 امتیاز: {tokens}\n"
            f"📊 کل بازی‌ها: {played}\n"
            f"✅ پاسخ‌های درست: {correct}\n"
            f"🕒 آخرین بازی: {last}\n"
            f"🖼 آواتار: {avatar or 'ثبت نشده'}"
        )

    elif text == "🏆 جدول رده‌بندی":
        with sqlite3.connect('quiz_bot.db') as conn:
            c = conn.cursor()
            c.execute('SELECT first_name, tokens FROM users ORDER BY tokens DESC LIMIT 5')
            top_users = c.fetchall()

        leaderboard_text = "🏆 برترین کاربران:\n\n"
        for i, (name, score) in enumerate(top_users, start=1):
            leaderboard_text += f"{i}. {name} - {score} امتیاز\n"

        await update.message.reply_text(leaderboard_text)

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
    import threading
    threading.Thread(target=lambda: app.run(debug=True, port=5001)).start()
    main()
