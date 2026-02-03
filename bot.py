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

# --- НАЛАШТУВАННЯ (НОВА НАЗВА ЗМІННОЇ) ---
TOKEN = os.getenv("TELEGRAM_TOKEN")
G_KEY = os.getenv("G_KEY")  # Змінено з GEMINI_API_KEY на G_KEY
TRIBUTE_SECRET = os.getenv("TRIBUTE_SECRET")
PORT = int(os.getenv("PORT", 8080))

# Перевірка ключа в логах Railway (розділ Logs)
if G_KEY:
    print(f"📡 Бот ініціалізований. Ключ починається на: {G_KEY[:5]}")
else:
    print("⚠️ КРИТИЧНО: Змінна G_KEY не знайдена!")

# Ініціалізація AI
genai.configure(api_key=G_KEY)
model = genai.GenerativeModel('gemini-1.5-flash')

bot = Bot(token=TOKEN)
dp = Dispatcher(storage=MemoryStorage())

class OrderFlow(StatesGroup):
    waiting_for_question = State()

# --- WEBHOOK ДЛЯ TRIBUTE ---
async def handle_tribute_webhook(request):
    try:
        signature = request.headers.get("X-Tribute-Signature")
        body = await request.read()
        hash_check = hmac.new(TRIBUTE_SECRET.encode(), body, hashlib.sha256).hexdigest()
        
        if hash_check != signature:
            return web.Response(status=403)

        data = await request.json()
        if data.get("status") == "completed":
            custom_data = data.get("custom_data", "").split(":")
            user_id = int(custom_data[0])
            state = dp.fsm.resolve_context(bot, user_id, user_id)
            await state.set_state(OrderFlow.waiting_for_question)
            await bot.send_message(user_id, "✅ **Оплата підтверджена!**\n\nТепер напишіть ваше запитання Оракулу:")
        return web.Response(text="ok")
    except Exception as e:
        print(f"Webhook error: {e}")
        return web.Response(status=500)

# --- КОМАНДИ ---
@dp.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
    await state.clear()
    builder = InlineKeyboardBuilder()
    builder.button(text="🎁 Безкоштовне питання", callback_data="test_me")
    builder.button(text="🃏 Таро — 3 карти", callback_data="pay_pqoQ")
    builder.adjust(1)
    await message.answer("🔮 **Оракул вітає вас.** Оберіть послугу:", reply_markup=builder.as_markup())

@dp.message(Command("unlock"))
async def cmd_unlock(message: types.Message, state: FSMContext):
    await state.set_state(OrderFlow.waiting_for_question)
    await message.answer("🔑 **Тестовий доступ активовано.** Чекаю на твоє питання:")

@dp.callback_query(F.data == "test_me")
async def test_me(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(OrderFlow.waiting_for_question)
    await callback.message.edit_text("✨ **Я слухаю.** Задай своє питання:")

@dp.callback_query(F.data.startswith("pay_"))
async def process_pay(callback: types.CallbackQuery, state: FSMContext):
    svc_code = callback.data.split("_")[1]
    pay_url = f"https://t.me/tribute/app?startapp={svc_code}&custom_data={callback.from_user.id}:{svc_code}"
    builder = InlineKeyboardBuilder()
    builder.button(text="💳 Оплатити", url=pay_url)
    await callback.message.edit_text("🔮 Натисніть кнопку для оплати. Після цього ви зможете задати питання.", reply_markup=builder.as_markup())

# --- ОБРОБКА ВІДПОВІДІ ШІ ---
@dp.message(OrderFlow.waiting_for_question)
async def oracle_answer(message: types.Message, state: FSMContext):
    status = await message.answer("🔮 *Оракул звертається до зірок...*")
    try:
        # Прямий виклик без зайвих налаштувань версій
        response = model.generate_content(f"Ти містичний Оракул. Відповідай українською мовою. Питання: {message.text}")
        
        if response.text:
            await status.edit_text(f"📜 **Послання Оракула:**\n\n{response.text}")
        else:
            await status.edit_text("🌑 Зірки сьогодні мовчать. Спробуйте пізніше.")
            
    except Exception as e:
        error_msg = str(e)
        if "400" in error_msg or "API_KEY_INVALID" in error_msg:
            await status.edit_text("🌑 Помилка: Ключ API все ще не приймається. Спробуйте створити новий на іншому Google-акаунті.")
        else:
            await status.edit_text(f"🌑 Помилка зв'язку: {error_msg[:100]}")
    
    await state.clear()

async def main():
    # Запуск веб-сервера (для Tribute)
    app = web.Application()
    app.router.add_post("/webhook", handle_tribute_webhook)
    runner = web.AppRunner(app)
    await runner.setup()
    await web.TCPSite(runner, "0.0.0.0", PORT).start()
    
    # Запуск бота
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
