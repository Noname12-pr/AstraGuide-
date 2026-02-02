import os
import asyncio
import hmac
import hashlib
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage # Використовуємо пам'ять для станів
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiohttp import web
import google.generativeai as genai

# --- НАЛАШТУВАННЯ ---
TOKEN = os.getenv("TELEGRAM_TOKEN")
GEMINI_KEY = os.getenv("GEMINI_API_KEY")
TRIBUTE_SECRET = os.getenv("TRIBUTE_SECRET")
PORT = int(os.getenv("PORT", 8080))

# Налаштування Gemini
genai.configure(api_key=GEMINI_KEY)

# Вимикаємо фільтри безпеки (максимальна свобода відповідей)
safety_settings = [
    {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
    {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
    {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
    {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
]

def find_working_model():
    try:
        for m in genai.list_models():
            if 'generateContent' in m.supported_generation_methods:
                return m.name
    except: pass
    return 'models/gemini-1.5-flash'

WORKING_MODEL_NAME = find_working_model()
model = genai.GenerativeModel(model_name=WORKING_MODEL_NAME, safety_settings=safety_settings)

# Ініціалізація бота з пам'яттю для станів
bot = Bot(token=TOKEN)
dp = Dispatcher(storage=MemoryStorage())

class OrderFlow(StatesGroup):
    waiting_for_payment = State()
    waiting_for_question = State()

# Оновлена карта послуг (додано pqoQ)
SERVICES_MAP = {
    "pqoQ": "Таро — 3 карты",
    "free_test": "Бесплатная проверка"
}

# --- WEBHOOK ДЛЯ TRIBUTE ---
async def handle_tribute_webhook(request):
    try:
        signature = request.headers.get("X-Tribute-Signature")
        body = await request.read()
        hash_check = hmac.new(TRIBUTE_SECRET.encode(), body, hashlib.sha256).hexdigest()
        if hash_check != signature: return web.Response(status=403)
        
        data = await request.json()
        if data.get("status") == "completed":
            payload = data.get("custom_data", "").split(":")
            user_id = int(payload[0])
            svc_code = payload[1]
            
            user_state = dp.fsm.resolve_context(bot, user_id, user_id)
            await user_state.update_data(current_svc=SERVICES_MAP.get(svc_code, "Расклад"))
            await user_state.set_state(OrderFlow.waiting_for_question)
            await bot.send_message(user_id, "✅ **Оплата принята!**\n\nЯ никуда не спешу. Можете детально описать вашу ситуацию или вопрос, а когда будете готовы — отправляйте сообщение:")
        return web.Response(text="ok")
    except: return web.Response(status=500)

# --- ЛОГІКА БОТА ---
@dp.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
    await state.clear()
    builder = InlineKeyboardBuilder()
    builder.button(text="🎁 Бесплатный вопрос", callback_data="test_me")
    builder.button(text="🃏 Платные расклады", callback_data="cat_taro")
    builder.adjust(1)
    await message.answer("🔮 **Оракул пробудился.**\nВыберите путь:", reply_markup=builder.as_markup())

@dp.callback_query(F.data == "test_me")
async def test_me(callback: types.CallbackQuery, state: FSMContext):
    await state.update_data(current_svc="Бесплатный тест")
    await state.set_state(OrderFlow.waiting_for_question)
    await callback.message.edit_text("✨ **Я слушаю ваш вопрос.**\nНе торопитесь, опишите всё детально. Я жду.")

@dp.callback_query(F.data == "cat_taro")
async def cat_taro(callback: types.CallbackQuery):
    builder = InlineKeyboardBuilder()
    # ВИКОРИСТОВУЄМО ВАШЕ НОВЕ ПОСИЛАННЯ (код pqoQ)
    builder.button(text="3 карты (500 ₽)", callback_data="pay_pqoQ")
    builder.button(text="⬅️ Назад", callback_data="back")
    builder.adjust(1)
    await callback.message.edit_text("🔮 **Выберите глубину расклада:**", reply_markup=builder.as_markup())

@dp.callback_query(F.data == "back")
async def back(callback: types.CallbackQuery, state: FSMContext):
    await cmd_start(callback.message, state)

@dp.callback_query(F.data.startswith("pay_"))
async def process_buy(callback: types.CallbackQuery, state: FSMContext):
    svc_code = callback.data.split("_")[1]
    # Посилання генерується автоматично з правильним кодом
    pay_url = f"https://t.me/tribute/app?startapp={svc_code}&custom_data={callback.from_user.id}:{svc_code}"
    builder = InlineKeyboardBuilder()
    builder.button(text="💳 Оплатить", url=pay_url)
    await callback.message.edit_text("✨ После оплаты я буду ждать ваш вопрос столько, сколько потребуется.", reply_markup=builder.as_markup())
    await state.set_state(OrderFlow.waiting_for_payment)

# --- ВІДПОВІДЬ ОРАКУЛА З ПОВТОРОМ ---
@dp.message(OrderFlow.waiting_for_question)
async def oracle_answer(message: types.Message, state: FSMContext):
    data = await state.get_data()
    svc = data.get("current_svc", "Расклад")
    
    # Видаляємо стан очікування ТІЛЬКИ ПІСЛЯ ТОГО, як отримали повідомлення
    status_msg = await message.answer("🔮 *Оракул погружается в ваши слова...*")
    
    for attempt in range(2):
        try:
            prompt = f"Ты — мудрый Оракул. Отвечай глубоко на русском. Услуга: {svc}. Вопрос клиента: {message.text}"
            response = model.generate_content(prompt)
            if response and response.text:
                await status_msg.edit_text(f"📜 **Послание Оракула:**\n\n{response.text}")
                await state.clear()
                return
        except Exception:
            if attempt == 0: await asyncio.sleep(3)
            else: await status_msg.edit_text("🌑 Эфир затуманен. Попробуйте отправить вопрос снова через минуту.")
    await state.clear()

async def main():
    asyncio.create_task(dp.start_polling(bot))
    app = web.Application(); app.router.add_post("/webhook", handle_tribute_webhook)
    runner = web.AppRunner(app); await runner.setup()
    await web.TCPSite(runner, "0.0.0.0", PORT).start()
    await asyncio.Event().wait()

if __name__ == "__main__":
    asyncio.run(main())
