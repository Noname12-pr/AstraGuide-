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
G_KEY = os.getenv("G_KEY") 
TRIBUTE_SECRET = os.getenv("TRIBUTE_SECRET")
PORT = int(os.getenv("PORT", 8080))

# НАЛАШТУВАННЯ AI (ВИПРАВЛЕННЯ 404)
genai.configure(api_key=G_KEY)

# Спроба ініціалізувати модель через різні імена (одне з них точно спрацює)
def get_model():
    models_to_try = ['gemini-1.5-flash', 'models/gemini-1.5-flash', 'gemini-pro']
    for m_name in models_to_try:
        try:
            print(f"📡 Пробую модель: {m_name}")
            m = genai.GenerativeModel(model_name=m_name)
            # Перевірочний виклик не робимо тут, щоб не витрачати квоту
            return m
        except:
            continue
    return genai.GenerativeModel('gemini-pro') # Резерв

model = get_model()

bot = Bot(token=TOKEN)
dp = Dispatcher(storage=MemoryStorage())

class OrderFlow(StatesGroup):
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
            await state.set_state(OrderFlow.waiting_for_question)
            await bot.send_message(user_id, "✅ **Оплата прийнята!** Напишіть ваше питання:")
        return web.Response(text="ok")
    except: return web.Response(status=500)

# --- КОМАНДИ ---
@dp.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
    await state.clear()
    builder = InlineKeyboardBuilder()
    builder.button(text="🎁 Безкоштовне питання", callback_data="test_me")
    builder.button(text="🃏 Таро — 3 карти", callback_data="pay_pqoQ")
    builder.adjust(1)
    await message.answer("🔮 **Оракул готовий.** Оберіть послугу:", reply_markup=builder.as_markup())

@dp.message(Command("unlock"))
async def cmd_unlock(message: types.Message, state: FSMContext):
    await state.set_state(OrderFlow.waiting_for_question)
    await message.answer("🔑 **Тест активовано.** Чекаю на питання:")

@dp.callback_query(F.data == "test_me")
async def test_me(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(OrderFlow.waiting_for_question)
    await callback.message.edit_text("✨ **Я слухаю.** Задай питання:")

# --- ГЕНЕРАЦІЯ ВІДПОВІДІ ---
@dp.message(OrderFlow.waiting_for_question)
async def oracle_answer(message: types.Message, state: FSMContext):
    status = await message.answer("🔮 *З'єднуюсь з інформаційним полем...*")
    try:
        # Використовуємо спрощений виклик
        response = model.generate_content(f"Ти містичний Оракул. Відповідай українською. Питання: {message.text}")
        await status.edit_text(f"📜 **Послання:**\n\n{response.text}")
    except Exception as e:
        # Якщо знову 404, пробуємо резервний метод прямо тут
        try:
            fallback_model = genai.GenerativeModel('gemini-pro')
            response = fallback_model.generate_content(message.text)
            await status.edit_text(f"📜 **Послання (резервний канал):**\n\n{response.text}")
        except Exception as e2:
            await status.edit_text(f"🌑 Помилка: {str(e2)[:100]}")
    await state.clear()

async def main():
    app = web.Application()
    app.router.add_post("/webhook", handle_tribute_webhook)
    runner = web.AppRunner(app); await runner.setup()
    await web.TCPSite(runner, "0.0.0.0", PORT).start()
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
