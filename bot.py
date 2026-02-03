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

# --- НАЛАШТУВАННЯ (БЕРУТЬСЯ З RAILWAY) ---
TOKEN = os.getenv("TELEGRAM_TOKEN")
GEMINI_KEY = os.getenv("GEMINI_API_KEY")
TRIBUTE_SECRET = os.getenv("TRIBUTE_SECRET")
PORT = int(os.getenv("PORT", 8080))

# Налаштування Gemini
genai.configure(api_key=GEMINI_KEY)

# Вимикаємо фільтри безпеки для Оракула
safety_settings = [
    {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
    {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
    {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
    {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
]

# Створюємо модель (Flash 1.5 - найшвидша)
model = genai.GenerativeModel(
    model_name='gemini-1.5-flash',
    safety_settings=safety_settings
)

bot = Bot(token=TOKEN)
dp = Dispatcher(storage=MemoryStorage())

class OrderFlow(StatesGroup):
    waiting_for_payment = State()
    waiting_for_question = State()

# --- ОБРОБКА WEBHOOK ВІД TRIBUTE ---
async def handle_tribute_webhook(request):
    try:
        signature = request.headers.get("X-Tribute-Signature")
        body = await request.read()
        
        # Перевірка підпису (секретний ключ)
        hash_check = hmac.new(TRIBUTE_SECRET.encode(), body, hashlib.sha256).hexdigest()
        if hash_check != signature:
            print("⚠️ Попередження: Невірний підпис вебхука!")
            return web.Response(status=403)

        data = await request.json()
        # Для товарів Tribute статус 'completed'
        if data.get("status") == "completed":
            custom_data = data.get("custom_data", "")
            if ":" in custom_data:
                user_id_str, svc_code = custom_data.split(":")
                user_id = int(user_id_str)
                
                # Активуємо режим питання для юзера
                state = dp.fsm.resolve_context(bot, user_id, user_id)
                await state.update_data(current_svc="Оплаченный расклад")
                await state.set_state(OrderFlow.waiting_for_question)
                
                await bot.send_message(user_id, "✅ **Оплата принята!**\n\nЯ готов ответить на ваш вопрос. Опишите ситуацию:")
        return web.Response(text="ok")
    except Exception as e:
        print(f"❌ Ошибка в обработчике вебхука: {e}")
        return web.Response(status=500)

# --- ЛОГІКА ТЕЛЕГРАМ-БОТА ---

@dp.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
    await state.clear()
    builder = InlineKeyboardBuilder()
    builder.button(text="🎁 Бесплатный вопрос", callback_data="test_me")
    builder.button(text="🃏 Таро — 3 карты", callback_data="pay_pqoQ")
    builder.adjust(1)
    await message.answer("🔮 **Оракул приветствует вас.**\nЯ вижу будущее и прошлое. Хотите проверить бесплатно или сделать глубокий расклад?", reply_markup=builder.as_markup())

# Секретна команда для розблокування (для тестів)
@dp.message(Command("unlock"))
async def cmd_unlock(message: types.Message, state: FSMContext):
    await state.update_data(current_svc="Тестовый доступ")
    await state.set_state(OrderFlow.waiting_for_question)
    await message.answer("🔑 **Доступ открыт (режим теста).**\nЗадавай свой вопрос Оракулу:")

@dp.callback_query(F.data == "test_me")
async def test_me(callback: types.CallbackQuery, state: FSMContext):
    await state.update_data(current_svc="Бесплатный тест")
    await state.set_state(OrderFlow.waiting_for_question)
    await callback.message.edit_text("✨ **Я слушаю.** Задай свой вопрос прямо здесь:")

@dp.callback_query(F.data.startswith("pay_"))
async def process_pay(callback: types.CallbackQuery, state: FSMContext):
    svc_code = callback.data.split("_")[1]
    # Формуємо лінк з ID юзера для Tribute
    pay_url = f"https://t.me/tribute/app?startapp={svc_code}&custom_data={callback.from_user.id}:{svc_code}"
    
    builder = InlineKeyboardBuilder()
    builder.button(text="💳 Оплатить", url=pay_url)
    await callback.message.edit_text("🔮 Нажмите кнопку для оплаты. После завершения я сам напишу вам, чтобы вы задали вопрос.", reply_markup=builder.as_markup())

@dp.message(OrderFlow.waiting_for_question)
async def oracle_answer(message: types.Message, state: FSMContext):
    data = await state.get_data()
    status = await message.answer("🔮 *Оракул погружается в астрал...*")
    
    try:
        # Промпт для ШІ
        prompt = f"Ты — мудрый и загадочный Оракул. Твои ответы глубокие. Отвечай на русском. Тип услуги: {data.get('current_svc')}. Вопрос клиента: {message.text}"
        
        # Спроба отримати відповідь
        response = model.generate_content(prompt)
        
        if response and response.text:
            await status.edit_text(f"📜 **Послание Оракула:**\n\n{response.text}")
        else:
            await status.edit_text("🌑 Духи сегодня молчат. Попробуй позже.")
            
    except Exception as e:
        await status.edit_text(f"🌑 Произошла ошибка связи с миром духов: {str(e)[:100]}")
    
    await state.clear()

# --- ЗАПУСК ---
async def main():
    # Налаштування веб-сервера для вебхуків
    app = web.Application()
    app.router.add_post("/webhook", handle_tribute_webhook)
    runner = web.AppRunner(app)
    await runner.setup()
    await web.TCPSite(runner, "0.0.0.0", PORT).start()
    
    print(f"🚀 Сервер вебхуков запущен на порту {PORT}")
    
    # Запуск бота (Polling)
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
