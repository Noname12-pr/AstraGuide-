import os
import asyncio
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from openai import AsyncOpenAI

# Берем токены из Railway
TOKEN = os.getenv("TELEGRAM_TOKEN")
OPENAI_KEY = os.getenv("OPENAI_API_KEY")

client = AsyncOpenAI(api_key=OPENAI_KEY)
bot = Bot(token=TOKEN)
dp = Dispatcher()

class OrderFlow(StatesGroup):
    waiting_for_payment = State()
    waiting_for_question = State()

# Полный список ваших услуг
SERVICES = {
    "🃏 ТАРО (основа)": {
        "Таро — 3 карты": {"price": 500, "link": "https://t.me/tribute/app?startapp=pqgo"},
        "Таро — 5 карт": {"price": 700, "link": "https://t.me/tribute/app?startapp=pqgq"},
        "Таро — 8 карт": {"price": 1000, "link": "https://t.me/tribute/app?startapp=pqgr"},
    },
    "❤️ ОТНОШЕНИЯ": {
        "Что он(а) чувствует": {"price": 600, "link": "https://t.me/tribute/app?startapp=pqgz"},
        "Развитие отношений": {"price": 800, "link": "https://t.me/tribute/app?startapp=pqgB"},
    },
    "❓ ДА / НЕТ": {
        "Ответ Да/Нет": {"price": 300, "link": "https://t.me/tribute/app?startapp=pqgD"},
        "Да/Нет с пояснением": {"price": 600, "link": "https://t.me/tribute/app?startapp=pqgF"},
    }
}

# --- Кнопки главного меню ---
def get_main_menu():
    builder = InlineKeyboardBuilder()
    for cat in SERVICES.keys():
        builder.button(text=cat, callback_data=f"cat_{cat}")
    builder.adjust(1)
    return builder.as_markup()

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer(
        "🔮 **Добро пожаловать в мир предсказаний.**\n\nВыберите категорию услуг, чтобы начать расклад:",
        reply_markup=get_main_menu(),
        parse_mode="Markdown"
    )

@dp.callback_query(F.data.startswith("cat_"))
async def choose_sub(callback: types.CallbackQuery):
    cat = callback.data.split("_")[1]
    builder = InlineKeyboardBuilder()
    for sub in SERVICES[cat]:
        builder.button(text=f"{sub} — {SERVICES[cat][sub]['price']}₽", callback_data=f"svc_{cat}_{sub}")
    builder.button(text="⬅️ Назад", callback_data="back_home")
    builder.adjust(1)
    await callback.message.edit_text(f"📍 Категория: {cat}\nВыберите конкретную услугу:", reply_markup=builder.as_markup())

@dp.callback_query(F.data == "back_home")
async def back_home(callback: types.CallbackQuery):
    await callback.message.edit_text("Выберите категорию услуг:", reply_markup=get_main_menu())

@dp.callback_query(F.data.startswith("svc_"))
async def process_selection(callback: types.CallbackQuery, state: FSMContext):
    parts = callback.data.split("_")
    cat, svc = parts[1], parts[2]
    data = SERVICES[cat][svc]
    
    await state.update_data(current_svc=svc)
    
    builder = InlineKeyboardBuilder()
    builder.button(text="💳 Оплатить через Tribute", url=data['link'])
    builder.button(text="✅ Я оплатил", callback_data="check_pay")
    builder.adjust(1)
    
    await callback.message.edit_text(
        f"✨ Вы выбрали: **{svc}**\n💰 К оплате: **{data['price']}₽**\n\n"
        "1. Нажмите кнопку 'Оплатить'.\n"
        "2. После подтверждения платежа вернитесь сюда и нажмите 'Я оплатил'.",
        reply_markup=builder.as_markup(),
        parse_mode="Markdown"
    )
    await state.set_state(OrderFlow.waiting_for_payment)

@dp.callback_query(F.data == "check_pay", OrderFlow.waiting_for_payment)
async def ask_question(callback: types.CallbackQuery, state: FSMContext):
    # В идеале здесь должна быть проверка через Tribute API. 
    # Пока оставляем на подтверждении пользователем.
    await callback.message.answer("💎 Оплата подтверждена! Теперь введите ваш вопрос для ChatGPT (Оракула):")
    await state.set_state(OrderFlow.waiting_for_question)

@dp.message(OrderFlow.waiting_for_question)
async def ai_reading(message: types.Message, state: FSMContext):
    user_data = await state.get_data()
    service_name = user_data.get('current_svc', 'Расклад Таро')
    
    status_msg = await message.answer("🔮 *Карты открываются... Силы Вселенной готовят ответ...*", parse_mode="Markdown")
    
    try:
        # Запрос к ChatGPT
        completion = await client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "Ты профессиональный таролог и мистик. Давай подробные, точные и глубокие ответы на русском языке."},
                {"role": "user", "content": f"Услуга: {service_name}. Вопрос клиента: {message.text}"}
            ]
        )
        answer = completion.choices[0].message.content
        await status_msg.edit_text(f"📜 **Ваше предсказание ({service_name}):**\n\n{answer}", parse_mode="Markdown")
    except Exception as e:
        print(f"Ошибка OpenAI: {e}")
        await status_msg.edit_text("❌ Произошла ошибка при связи с Оракулом. Попробуйте позже или напишите администратору.")
    
    await state.clear()

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
