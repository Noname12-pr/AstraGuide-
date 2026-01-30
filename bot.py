import os
import asyncio
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from openai import AsyncOpenAI

# Отримуємо токени зі змінних оточення Railway
TOKEN = os.getenv("TELEGRAM_TOKEN")
OPENAI_KEY = os.getenv("OPENAI_API_KEY")

client = AsyncOpenAI(api_key=OPENAI_KEY)
bot = Bot(token=TOKEN)
dp = Dispatcher()

class OrderFlow(StatesGroup):
    waiting_for_payment = State()
    waiting_for_question = State()

# Дані про всі ваші послуги
SERVICES = {
    "🃏 ТАРО": {
        "3 карти (швидке)": {"price": 500, "link": "https://t.me/tribute/app?startapp=pqgo", "prompt": "Розклад на 3 карти: минуле, теперішнє, майбутнє."},
        "5 карт (порада)": {"price": 700, "link": "https://t.me/tribute/app?startapp=pqgq", "prompt": "Розклад на 5 карт: ситуація та порада."},
        "8 карт (глибоко)": {"price": 1000, "link": "https://t.me/tribute/app?startapp=pqgr", "prompt": "Глибокий розбір на 8 карт."},
    },
    "🔮 ОРАКУЛ": {
        "Краткий ответ": {"price": 500, "link": "https://t.me/tribute/app?startapp=pqgw", "prompt": "Коротка містична відповідь Оракула."},
    },
    "❓ ДА / НЕТ": {
        "Відповідь (1 питання)": {"price": 300, "link": "https://t.me/tribute/app?startapp=pqgD", "prompt": "Чітка відповідь ТАК або НІ з коротким поясненням."},
    }
}

# --- Навігація ---

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    builder = InlineKeyboardBuilder()
    for cat in SERVICES.keys():
        builder.button(text=cat, callback_data=f"cat_{cat}")
    builder.adjust(1)
    await message.answer("🔮 Вітаю! Я ваш цифровий оракул. Оберіть категорію послуг:", reply_markup=builder.as_markup())

@dp.callback_query(F.data.startswith("cat_"))
async def choose_sub(callback: types.CallbackQuery):
    cat = callback.data.split("_")[1]
    builder = InlineKeyboardBuilder()
    for sub in SERVICES[cat]:
        builder.button(text=f"{sub} - {SERVICES[cat][sub]['price']}₽", callback_data=f"svc_{cat}_{sub}")
    builder.button(text="⬅️ Назад", callback_data="back_home")
    builder.adjust(1)
    await callback.message.edit_text(f"Оберіть розклад ({cat}):", reply_markup=builder.as_markup())

@dp.callback_query(F.data == "back_home")
async def back_home(callback: types.CallbackQuery):
    await cmd_start(callback.message)

@dp.callback_query(F.data.startswith("svc_"))
async def process_selection(callback: types.CallbackQuery, state: FSMContext):
    _, cat, svc = callback.data.split("_")
    data = SERVICES[cat][svc]
    
    await state.update_data(current_svc=svc, system_prompt=data['prompt'])
    
    builder = InlineKeyboardBuilder()
    builder.button(text="💰 Оплатити", url=data['link'])
    builder.button(text="✅ Я оплатив", callback_data="check_pay")
    builder.adjust(1)
    
    await callback.message.edit_text(
        f"Ви обрали: **{svc}**\nЦіна: **{data['price']}₽**\n\nБудь ласка, здійсніть оплату через Tribute і натисніть кнопку нижче.",
        reply_markup=builder.as_markup(),
        parse_mode="Markdown"
    )
    await state.set_state(OrderFlow.waiting_for_payment)

@dp.callback_query(F.data == "check_pay")
async def ask_question(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer("Чудово! Гроші отримано. Тепер напишіть ваше питання для розкладу:")
    await state.set_state(OrderFlow.waiting_for_question)

@dp.message(OrderFlow.waiting_for_question)
async def ai_reading(message: types.Message, state: FSMContext):
    user_data = await state.get_data()
    msg = await message.answer("🔮 Зв'язуюсь із всесвітом... Карти розкладаються...")
    
    try:
        response = await client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": f"Ти — професійний таролог. Твоє завдання: {user_data['system_prompt']}. Будь містичним, але давай точні відповіді."},
                {"role": "user", "content": message.text}
            ]
        )
        await msg.edit_text(response.choices[0].message.content)
    except Exception as e:
        await msg.edit_text("❌ Виникла помилка при генерації. Зверніться до підтримки.")
    
    await state.clear()

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
