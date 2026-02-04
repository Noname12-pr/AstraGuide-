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

# Ініціалізація AI
genai.configure(api_key=G_KEY)

# ФУНКЦІЯ АВТОПІДБОРУ МОДЕЛІ (Виправляє 404)
def get_active_model():
    try:
        # Запитуємо у Google список доступних моделей для нашого ключа
        models = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
        print(f"📡 Доступні моделі: {models}")
        
        # Пріоритет на flash, якщо ні — беремо будь-яку першу
        for m in models:
            if 'gemini-1.5-flash' in m:
                return genai.GenerativeModel(m)
        return genai.GenerativeModel(models[0])
    except Exception as e:
        print(f"❌ Помилка при отриманні списку моделей: {e}")
        # Якщо список не отримали, використовуємо жорстке ім'я без префіксів
        return genai.GenerativeModel('gemini-1.5-flash')

model = get_active_model()

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
            user_id = int(data.get("custom_data", "").split(":")[0])
            state = dp.fsm.resolve_context(bot, user_id, user_id)
            await state.set_state(OrderFlow.waiting_for_question)
            await bot.send_message(user_id, "✅ **Оплата успішна!** Задайте ваше питання:")
        return web.Response(text="ok")
    except: return web.Response(status=500)

# --- КОМАНДИ ---
@dp.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
    await state.clear()
    key_info = f"Ключ: {G_KEY[:6]}..." if G_KEY else "Ключ відсутній"
    
    builder = InlineKeyboardBuilder()
    builder.button(text="🎁 Безкоштовне питання", callback_data="test_me")
    builder.button(text="🃏 Таро — 3 карти", callback_data="pay_pqoQ")
    builder.adjust(1)
    
    await message.answer(
        f"🔮 **Оракул підключений.**\n🛠 {key_info}\n\nОберіть послугу:", 
        reply_markup=builder.as_markup()
    )

@dp.message(Command("unlock"))
async def cmd_unlock(message: types.Message, state: FSMContext):
    await state.set_state(OrderFlow.waiting_for_question)
    await message.answer("🔑 **Тестовий режим.** Введіть питання:")

@dp.callback_query(F.data == "test_me")
async def test_me(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(OrderFlow.waiting_for_question)
    await callback.message.edit_text("✨ **Я слухаю.** Задай своє питання:")

# --- ВІДПОВІДЬ ОРАКУЛА ---
@dp.message(OrderFlow.waiting_for_question)
async def oracle_answer(message: types.Message, state: FSMContext):
    status = await message.answer("🔮 *Зчитую вібрації всесвіту...*")
    try:
        # Використовуємо модель, яку підібрав get_active_model
        response = model.generate_content(f"Ти — містичний Оракул. Відповідай українською. Питання: {message.text}")
        await status.edit_text(f"📜 **Послання Оракула:**\n\n{response.text}")
    except Exception as e:
        await status.edit_text(f"🌑 Помилка зв'язку: {str(e)[:100]}")
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
