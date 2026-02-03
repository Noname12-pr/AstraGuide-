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

# Спроба налаштувати AI з прямим вказанням версії
genai.configure(api_key=GEMINI_KEY)

# Створюємо модель максимально безпечно
# Ми використовуємо назву 'gemini-1.5-flash', яку Google розуміє найкраще
model = genai.GenerativeModel(model_name='gemini-1.5-flash')

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
            await state.set_state(OrderFlow.waiting_for_question)
            await bot.send_message(user_id, "✅ **Оплата прошла!**\n\nЗадавайте ваш вопрос Оракулу:")
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
    await message.answer("🔮 **Оракул приветствует вас.**", reply_markup=builder.as_markup())

@dp.message(Command("unlock"))
async def cmd_unlock(message: types.Message, state: FSMContext):
    await state.set_state(OrderFlow.waiting_for_question)
    await message.answer("🔑 **Режим теста активен.** Введите вопрос:")

@dp.callback_query(F.data == "test_me")
async def test_me(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(OrderFlow.waiting_for_question)
    await callback.message.edit_text("✨ **Слушаю тебя.** Задай свой вопрос:")

# --- ГЕНЕРАЦІЯ ВІДПОВІДІ (ТУТ ВИПРАВЛЕННЯ) ---
@dp.message(OrderFlow.waiting_for_question)
async def oracle_answer(message: types.Message, state: FSMContext):
    status = await message.answer("🔮 *Оракул соединяется с космосом...*")
    try:
        # Прямий виклик без додаткових налаштувань, щоб уникнути 404/400
        response = model.generate_content(f"Ты — древний Оракул. Отвечай кратко и загадочно на русском. Вопрос: {message.text}")
        
        if response.text:
            await status.edit_text(f"📜 **Ответ:**\n\n{response.text}")
        else:
            await status.edit_text("🌑 Духи молчат. Попробуй еще раз.")
            
    except Exception as e:
        # Виводимо частину помилки для діагностики
        error_msg = str(e)
        if "API_KEY_INVALID" in error_msg:
            await status.edit_text("🌑 Ошибка: Проблема с ключом API. Проверьте переменные в Railway.")
        elif "404" in error_msg:
            await status.edit_text("🌑 Ошибка: Модель не найдена. Попробуем перезагрузить систему.")
        else:
            await status.edit_text(f"🌑 Духи встревожены: {error_msg[:100]}")
    
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
