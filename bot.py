import os
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

# =======================
# ENV
# =======================
BOT_TOKEN = os.getenv("BOT_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

if not BOT_TOKEN or not OPENAI_API_KEY:
    raise ValueError("Не найдены переменные окружения BOT_TOKEN или OPENAI_API_KEY")

bot = telebot.TeleBot(BOT_TOKEN)

# =======================
# START
# =======================
@bot.message_handler(commands=["start"])
def start(message):
    keyboard = InlineKeyboardMarkup()
    keyboard.add(
        InlineKeyboardButton("🃏 Таро", callback_data="cat_tarot"),
        InlineKeyboardButton("🔮 Оракул", callback_data="cat_oracle"),
        InlineKeyboardButton("❓ Да / Нет", callback_data="cat_yesno")
    )

    bot.send_message(
        message.chat.id,
        "✨ Выберите категорию:",
        reply_markup=keyboard
    )

# =======================
# CATEGORIES
# =======================
@bot.callback_query_handler(func=lambda call: call.data.startswith("cat_"))
def category(call):
    cat = call.data.replace("cat_", "")
    keyboard = InlineKeyboardMarkup()

    if cat == "tarot":
        keyboard.add(
            InlineKeyboardButton("🃏 3 карты — 500 ₽", callback_data="service_tarot_3"),
            InlineKeyboardButton("🃏 5 карт — 700 ₽", callback_data="service_tarot_5"),
            InlineKeyboardButton("🃏 8 карт — 1000 ₽", callback_data="service_tarot_8")
        )

    elif cat == "oracle":
        keyboard.add(
            InlineKeyboardButton("🔮 Краткий ответ — 500 ₽", callback_data="service_oracle_short"),
            InlineKeyboardButton("🔮 Подробный ответ — 900 ₽", callback_data="service_oracle_full")
        )

    elif cat == "yesno":
        keyboard.add(
            InlineKeyboardButton("❓ Да / Нет — 300 ₽", callback_data="service_yesno_simple"),
            InlineKeyboardButton("❓ С пояснением — 600 ₽", callback_data="service_yesno_explain")
        )

    keyboard.add(
        InlineKeyboardButton("⬅️ Назад в меню", callback_data="back_to_menu")
    )

    bot.send_message(
        call.message.chat.id,
        "✨ Выберите услугу:",
        reply_markup=keyboard
    )

# =======================
# BACK TO MENU
# =======================
@bot.callback_query_handler(func=lambda call: call.data == "back_to_menu")
def back_to_menu(call):
    start(call.message)

# =======================
# SERVICES
# =======================
@bot.callback_query_handler(func=lambda call: call.data.startswith("service_"))
def service_selected(call):
    service = call.data

    SERVICE_TEXT = {
        "service_tarot_3": "🃏 Вы выбрали Таро — 3 карты\n\nОплата: 500 ₽",
        "service_tarot_5": "🃏 Вы выбрали Таро — 5 карт\n\nОплата: 700 ₽",
        "service_tarot_8": "🃏 Вы выбрали Таро — 8 карт\n\nОплата: 1000 ₽",
        "service_oracle_short": "🔮 Оракул — краткий ответ\n\nОплата: 500 ₽",
        "service_oracle_full": "🔮 Оракул — подробный ответ\n\nОплата: 900 ₽",
        "service_yesno_simple": "❓ Да / Нет\n\nОплата: 300 ₽",
        "service_yesno_explain": "❓ Да / Нет с пояснением\n\nОплата: 600 ₽",
    }

    text = SERVICE_TEXT.get(service, "Услуга не найдена")

    keyboard = InlineKeyboardMarkup()
    keyboard.add(
        InlineKeyboardButton("💳 Оплатить", url="https://t.me/tribute/app"),
        InlineKeyboardButton("⬅️ Назад", callback_data="back_to_menu")
    )

    bot.send_message(
        call.message.chat.id,
        text,
        reply_markup=keyboard
    )

# =======================
# RUN
# =======================
bot.infinity_polling()
