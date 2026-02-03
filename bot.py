import os
import asyncio
import hmac
import hashlib
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiohttp import web
import google.generativeai as genai

# --- НАЛАШТУВАННЯ ---
TOKEN = os.getenv("TELEGRAM_TOKEN")
GEMINI_KEY = os.getenv("GEMINI_API_KEY")
TRIBUTE_SECRET = os.getenv("TRIBUTE_SECRET")
PORT = int(os.getenv("PORT", 8080))

# Конфігурація Google AI
genai.configure(api_key=GEMINI_KEY)

# Використовуємо 8b модель - вона легша і часто має вільніші ліміти
model = genai.GenerativeModel(
    model_name='gemini-1.5-flash-8b',
    safety_settings=[
        {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
        {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
        {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
        {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
    ]
)

bot = Bot(token=TOKEN)
dp = Dispatcher(storage=MemoryStorage())

class OrderFlow(StatesGroup):
    waiting_for_payment = State()
    waiting_for_question = State()

# --- WEBHOOK TRIBUTE ---
async def handle_tribute_webhook(request):
    try:
        signature = request.headers.get("X-Tribute-Signature")
        body = await request.read()
        hash_check = hmac.new(TRIBUTE_SECRET.encode(), body, hashlib.sha256).hexdigest()
        if hash_check != signature: return web.Response(status=403)
        data = await request.json()
        if data.get("status") == "completed":
            custom_data = data.get("custom_data", "").split(":")
            user_id = int(custom_data[0])
            state = dp.fsm.resolve_context(bot, user_id, user_id)
            await state.update_data(current_svc="Расклад")
            await state.set_state(OrderFlow.waiting_for_question)
            await bot.send_message(user_id, "✅ **Оплата принята!**\n\nВведите ваш вопрос:")
        return web.Response(text="ok")
    except: return web.Response(status=500)

# --- КОМАНДИ ---
@dp.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
    await state.clear()
    builder = InlineKeyboardBuilder()
    builder.button(text="🎁 Бесплатный вопрос", callback_data="test_me")
    builder.button(text="🃏 Таро — 3 карты", callback_data="pay_pqoQ")
    builder.adjust(1)
    await message.answer("🔮 **Оракул готов.** Выберите путь:", reply_markup=builder.as_markup())

@dp.message(Command("unlock"))
async def cmd_unlock(message: types.Message, state: FSMContext):
    await state.update_data(current_svc="Тест")
    await state.set_state(OrderFlow.waiting_for_question)
    await message.answer("🔑 **Доступ открыт.** Жду твой вопрос:")

@dp.callback_query(F.data == "test_me")
async def test_me(callback: types.CallbackQuery, state: FSMContext):
    await state.update_data(current_svc="Тест")
    await state.set_state(OrderFlow.waiting_for_question)
    await callback.message.edit_text("✨ **Я слушаю.** Задай вопрос:")

@dp.callback_query(F.data.startswith("pay_"))
async def process_pay(callback: types.CallbackQuery, state: FSMContext):
    svc_code = callback.data.split("_")[1]
    pay_url = f"https://t.me/tribute/app?startapp={svc_code}&custom_data={callback.from_user.id}:{svc_code}"
    builder = InlineKeyboardBuilder()
    builder.button(text="💳 Оплатить", url=pay_url)
    await callback.message.edit_text("🔮 Оплатите, и я сразу отвечу.", reply_markup=builder.as_markup())

# --- ВІДПОВІДЬ ---
@dp.message(OrderFlow.waiting_for_question)
async def oracle_answer(message: types.Message, state: FSMContext):
    status = await message.answer("🔮 *Оракул входит в транс...*")
    try:
        # Прямий виклик генерації
        response = model.generate_content(f"Ты мистический Оракул. Отвечай на русском. Вопрос: {message.text}")
        await status.edit_text(f"📜 **Ответ:**\n\n{response.text}")
    except Exception as e:
        await status.edit_text(f"🌑 Ошибка: {str(e)}")
    await state.clear()

async def main():
    app = web.Application(); app.router.add_post("/webhook", handle_tribute_webhook)
    runner = web.AppRunner(app); await runner.setup()
    await web.TCPSite(runner, "0.0.0.0", PORT).start()
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
