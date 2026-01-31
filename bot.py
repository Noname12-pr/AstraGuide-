import os
import asyncio
import hmac
import hashlib
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
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

# ФУНКЦІЯ АВТОМАТИЧНОГО ВИБОРУ МОДЕЛІ
def find_working_model():
    print("🔍 Пошук доступних моделей...")
    try:
        for m in genai.list_models():
            if 'generateContent' in m.supported_generation_methods:
                print(f"✅ Знайдено робочу модель: {m.name}")
                return m.name
    except Exception as e:
        print(f"❌ Не вдалося отримати список моделей: {e}")
    return 'models/gemini-1.5-flash' # Запасний варіант

WORKING_MODEL_NAME = find_working_model()
model = genai.GenerativeModel(WORKING_MODEL_NAME)

bot = Bot(token=TOKEN)
dp = Dispatcher()

class OrderFlow(StatesGroup):
    waiting_for_payment = State()
    waiting_for_question = State()

SERVICES_MAP = {
    "pqgo": "Таро — 3 карты",
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
            user_id, svc_code = data.get("custom_data", "").split(":")
            user_id = int(user_id)
            user_state = dp.fsm.resolve_context(bot, user_id, user_id)
            await user_state.update_data(current_svc=SERVICES_MAP.get(svc_code, "Расклад"))
            await user_state.set_state(OrderFlow.waiting_for_question)
            await bot.send_message(user_id, "✅ Оплата принята! Оракул слушает вопрос:")
        return web.Response(text="ok")
    except: return web.Response(status=500)

# --- ЛОГІКА БОТА ---
@dp.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
    builder = InlineKeyboardBuilder()
    builder.button(text="🎁 Проверить бесплатно", callback_data="test_me")
    builder.button(text="🃏 Платные расклады", callback_data="cat_taro")
    builder.adjust(1)
    await message.answer("🔮 Оракул на связи. Модель активирована.", reply_markup=builder.as_markup())

@dp.callback_query(F.data == "test_me")
async def test_me(callback: types.CallbackQuery, state: FSMContext):
    await state.update_data(current_svc="Бесплатный тест")
    await state.set_state(OrderFlow.waiting_for_question)
    await callback.message.edit_text("✨ Задайте свой вопрос Оракулу:")

@dp.callback_query(F.data == "cat_taro")
async def cat_taro(callback: types.CallbackQuery):
    builder = InlineKeyboardBuilder()
    builder.button(text="3 карты (500 ₽)", callback_data="pay_pqgo")
    builder.button(text="⬅️ Назад", callback_data="back")
    builder.adjust(1)
    await callback.message.edit_text("🔮 Выберите расклад:", reply_markup=builder.as_markup())

@dp.callback_query(F.data.startswith("pay_"))
async def process_buy(callback: types.CallbackQuery, state: FSMContext):
    svc_code = callback.data.split("_")[1]
    pay_url = f"https://t.me/tribute/app?startapp={svc_code}&custom_data={callback.from_user.id}:{svc_code}"
    builder = InlineKeyboardBuilder()
    builder.button(text="💳 Оплатить", url=pay_url)
    await callback.message.edit_text("✨ Оплатите, и я сразу отвечу.", reply_markup=builder.as_markup())
    await state.set_state(OrderFlow.waiting_for_payment)

@dp.message(OrderFlow.waiting_for_question)
async def oracle_answer(message: types.Message, state: FSMContext):
    data = await state.get_data()
    status = await message.answer("🔮 *Оракул входит в транс...*")
    try:
        prompt = f"Ты — мистический Оракул. Отвечай на русском. Услуга: {data.get('current_svc')}. Вопрос: {message.text}"
        response = model.generate_content(prompt)
        await status.edit_text(f"📜 **Ответ:**\n\n{response.text}")
    except Exception as e:
        await status.edit_text(f"🌑 Ошибка: {str(e)}")
    await state.clear()

async def main():
    asyncio.create_task(dp.start_polling(bot))
    app = web.Application(); app.router.add_post("/webhook", handle_tribute_webhook)
    runner = web.AppRunner(app); await runner.setup()
    await web.TCPSite(runner, "0.0.0.0", PORT).start()
    await asyncio.Event().wait()

if __name__ == "__main__":
    asyncio.run(main())
