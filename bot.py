import os
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
import openai

# ================== ENV ==================

BOT_TOKEN = os.getenv("BOT_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

if not BOT_TOKEN or not OPENAI_API_KEY:
    raise ValueError("Не найдены переменные окружения BOT_TOKEN или OPENAI_API_KEY")

bot = telebot.TeleBot(BOT_TOKEN)
openai.api_key = OPENAI_API_KEY

# ================== ХРАНЕНИЕ ==================

used_payments = set()      # анти-фрод (1 оплата = 1 ответ)
user_service = {}          # user_id -> service_key

# ================== BASE PROMPT ==================

BASE_PROMPT = """
Ты — опытный эзотерический консультант.
Отвечай уверенно, мистично и заботливо.
Не упоминай ИИ, технологии или алгоритмы.
Говори так, будто информация получена через интуицию, символы и энергию.
Используй эмодзи, структуру и мягкий тон.
"""

# ================== SERVICES ==================

SERVICES = {
    "tarot_3": {
        "title": "🃏 Таро — 3 карты",
        "price": "500 ₽",
        "link": "https://t.me/tribute/app?startapp=pqgo",
        "prompt": BASE_PROMPT + "Сделай таро-расклад на 3 карты. Вопрос: "
    },
    "tarot_5": {
        "title": "🃏 Таро — 5 карт",
        "price": "700 ₽",
        "link": "https://t.me/tribute/app?startapp=pqgq",
        "prompt": BASE_PROMPT + "Сделай таро-расклад на 5 карт с анализом и советом. Вопрос: "
    },
    "tarot_8": {
        "title": "🃏 Таро — 8 карт",
        "price": "1000 ₽",
        "link": "https://t.me/tribute/app?startapp=pqgr",
        "prompt": BASE_PROMPT + "Сделай глубокий таро-расклад на 8 карт с выводами. Вопрос: "
    },
    "oracle_short": {
        "title": "🔮 Оракул — краткий ответ",
        "price": "500 ₽",
        "link": "https://t.me/tribute/app?startapp=pqgw",
        "prompt": BASE_PROMPT + "Дай краткое мистическое послание Оракула. Вопрос: "
    },
    "oracle_full": {
        "title": "🔮 Оракул — подробное послание",
        "price": "900 ₽",
        "link": "https://t.me/tribute/app?startapp=pqgx",
        "prompt": BASE_PROMPT + "Дай подробное послание Оракула с объяснением. Вопрос: "
    },
    "yes_no_simple": {
        "title": "❓ Да / Нет",
        "price": "300 ₽",
        "link": "https://t.me/tribute/app?startapp=pqgD",
        "prompt": BASE_PROMPT + "Ответь только Да или Нет. Вопрос: "
    },
    "yes_no_explain": {
        "title": "❓ Да / Нет с пояснением",
        "price": "600 ₽",
        "link": "https://t.me/tribute/app?startapp=pqgF",
        "prompt": BASE_PROMPT + "Ответь Да или Нет с пояснением. Вопрос: "
    }
}

# ================== /start ==================

@bot.message_handler(commands=["start"])
def start(message):
    keyboard = InlineKeyboardMarkup()
    keyboard.add(
        InlineKeyboardButton("🃏 ТАРО", callback_data="cat_tarot"),
        InlineKeyboardButton("🔮 ОРАКУЛ", callback_data="cat_oracle")
    )
    keyboard.add(
        InlineKeyboardButton("❓ ДА / НЕТ", callback_data="cat_yesno")
    )

    bot.send_message(
        message.chat.id,
        "🔮 Добро пожаловать.\nВыберите категорию:",
        reply_markup=keyboard
    )

# ================== CATEGORY ==================

@bot.callback_query_handler(func=lambda call: call.data.startswith("cat_"))
def category(call):
    cat = call.data.replace("cat_", "")
    keyboard = InlineKeyboardMarkup()

    if cat == "tarot":
        keyboard.add(
            InlineKeyboardButton("3 карты — 500 ₽", callback_data="service_tarot_3"),
            InlineKeyboardButton("5 карт — 700 ₽", callback_data="service_tarot_5"),
            InlineKeyboardButton("8 карт — 1000 ₽", callback_data="service_tarot_8")
        )

    if cat == "oracle":
        keyboard.add(
            InlineKeyboardButton("Краткий ответ — 500 ₽", callback_data="service_oracle_short"),
            InlineKeyboardButton("Подробно — 900 ₽", callback_data="service_oracle_full")
        )

    if cat == "yesno":
        keyboard.add(
            InlineKeyboardButton("Да / Нет — 300 ₽", callback_data="service_yes_no_simple"),
            InlineKeyboardButton("С пояснением — 600 ₽", callback_data="service_yes_no_explain")
        )

    keyboard.add(InlineKeyboardButton("⬅ Назад", callback_data="back"))

    bot.edit_message_text(
        "Выберите услугу:",
        call.message.chat.id,
        call.message.message_id,
        reply_markup=keyboard
    )

# ================== SERVICE ==================

@bot.callback_query_handler(func=lambda call: call.data.startswith("service_"))
def service(call):
    service_key = call.data.replace("service_", "")
    user_service[call.from_user.id] = service_key
    s = SERVICES[service_key]

    keyboard = InlineKeyboardMarkup()
    keyboard.add(InlineKeyboardButton("💳 Оплатить", url=s["link"]))

    bot.send_message(
        call.message.chat.id,
        f"✨ *{s['title']}*\n💰 Цена: {s['price']}\n\nПосле оплаты нажмите кнопку ниже:",
        reply_markup=keyboard,
        parse_mode="Markdown"
    )

# ================== PAYMENT ==================

@bot.message_handler(func=lambda m: m.text.startswith("/start "))
def payment(message):
    payment_id = message.text.split(" ")[1]

    if payment_id in used_payments:
        bot.send_message(message.chat.id, "❌ Эта оплата уже была использована.")
        return

    used_payments.add(payment_id)
    bot.send_message(message.chat.id, "✅ Оплата подтверждена.\nПожалуйста, напишите ваш вопрос.")

# ================== ANSWER ==================

@bot.message_handler(func=lambda m: m.from_user.id in user_service)
def answer(message):
    service_key = user_service.pop(message.from_user.id)
    prompt = SERVICES[service_key]["prompt"] + message.text

    response = openai.ChatCompletion.create(
        model="gpt-4",
        messages=[{"role": "user", "content": prompt}]
    )

    bot.send_message(
        message.chat.id,
        response.choices[0].message.content
    )

# ================== RUN ==================

bot.infinity_polling()
