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
from openai import AsyncOpenAI

# Налаштування з Railway
TOKEN = os.getenv("TELEGRAM_TOKEN")
OPENAI_KEY = os.getenv("OPENAI_API_KEY")
TRIBUTE_SECRET = os.getenv("TRIBUTE_SECRET")
PORT = int(os.getenv("PORT", 8080))

bot = Bot(token=TOKEN)
dp = Dispatcher()
client = AsyncOpenAI(api_key=OPENAI_KEY)

class OrderFlow(StatesGroup):
    waiting_for_payment = State()
    waiting_for_question = State()

# Словник усіх послуг
SERVICES_MAP = {
    "pqgo": "Таро — 3 карты",
    "pqgq": "Таро — 5 карт",
    "pqgr": "Таро — 8 карт",
    "pqgu": "Таро — расклад на отношения",
    "pqgw": "Оракул — краткий ответ",
    "pqgD": "Ответ Да / Нет",
    "free_test": "Бесплатная проверка"
}

# --- ВЕБХУК ДЛЯ АВТО-ОПЛАТИ ---
async def handle_tribute_webhook(request):
    try:
        signature = request.headers.get("X-Tribute-Signature")
        body = await request.read()
        hash_check = hmac.new(TRIBUTE_SECRET.encode(), body, hashlib.sha256).hexdigest()
        
        if hash_check != signature:
            return web.Response(status=403)

        data = await request.json()
        if data.get("status") == "completed":
            payload = data.get("custom_data", "")
            if ":" in payload:
                user_id, svc_code = payload.split(":")
                user_id = int(user_id)
                
                user_state = dp.fsm.resolve_context(bot, user_id, user_id)
                await user_state.update_data(current_svc=SERVICES_MAP.get(svc_code, "Расклад"))
                await user_state.set_state(OrderFlow.waiting_for_question)
                
                await bot.send_message(user_id, "✅ **Оплата подтверждена!**\nОракул готов. Введите ваш вопрос:")
        return web.Response(text="ok")
    except:
        return web.Response(status=500)

# --- ЛОГІКА БОТА ---

@dp.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
    current_state = await state.get_state()
    if current_state == OrderFlow.waiting_for_question:
        await message.answer("🔮 Оракул на связи. Жду ваш вопрос:")
        return

    builder = InlineKeyboardBuilder()
    # БЕЗКОШТОВНА КНОПКА ДЛЯ ПЕРЕВІРКИ
    builder.button(text="🎁 Проверить Оракула (Бесплатно)", callback_data="free_test")
    builder.button(text="🃏 ТАРО (Платные расклады)", callback_data="cat_taro")
    builder.adjust(1)
    await message.answer("🔮 **Добро пожаловать к Оракулу.**\n\nВы можете проверить мои силы бесплатно или выбрать глубокий расклад:", reply_markup=builder.as_markup())

# Обробка безкоштовної перевірки
@dp.callback_query(F.data == "free_test")
async def free_test(callback: types.CallbackQuery, state: FSMContext):
    await state.update_data(current_svc="Бесплатная проверка (Таро 3 карты)")
    await state.set_state(OrderFlow.waiting_for_question)
    await callback.message.edit_text("✨ **Тестовый режим активирован.**\n\nЗадайте свой вопрос Оракулу (бесплатно):")

# Обробка вибору платної категорії Таро
@dp.callback_query(F.data == "cat_taro")
async def cat_taro(callback: types.CallbackQuery):
    builder = InlineKeyboardBuilder()
    builder.button(text="3 карты (500 ₽)", callback_data="buy_pqgo")
    builder.button(text="8 карт (1000 ₽)", callback_data="buy_pqgr")
    builder.button(text="⬅️ Назад", callback_data="back")
    builder.adjust(1)
    await callback.message.edit_text("🔮 **Выберите платный расклад:**", reply_markup=builder.as_markup())

@dp.callback_query(F.data == "back")
async def back(callback: types.CallbackQuery, state: FSMContext):
    await cmd_start(callback.message, state)

@dp.callback_query(F.data.startswith("buy_"))
async def process_buy(callback: types.CallbackQuery, state: FSMContext):
    svc_code = callback.data.split("_")[1]
    user_id = callback.from_user.id
    pay_url = f"https://t.me/tribute/app?startapp={svc_code}&custom_data={user_id}:{svc_code}"
    
    builder = InlineKeyboardBuilder()
    builder.button(text="💳 Оплатить", url=pay_url)
    await callback.message.edit_text("✨ После оплаты Оракул сразу примет ваш вопрос.", reply_markup=builder.as_markup())
    await state.set_state(OrderFlow.waiting_for_payment)

# ВІДПОВІДЬ CHATGPT (ОРАКУЛА)
@dp.message(OrderFlow.waiting_for_question)
async def oracle_answer(message: types.Message, state: FSMContext):
    data = await state.get_data()
    svc = data.get("current_svc", "Расклад")
    
    status = await message.answer("🔮 *Оракул входит в транс...*")
    
    try:
        response = await client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "Ты — древний мудрый Оракул. Твои ответы глубокие, мистические и загадочные. Не упоминай, что ты ИИ. Отвечай на русском."},
                {"role": "user", "content": f"Услуга: {svc}. Вопрос клиента: {message.text}"}
            ]
        )
        await status.edit_text(f"📜 **Послание Оракула:**\n\n{response.choices[0].message.content}")
    except Exception as e:
        await status.edit_text("🌑 Связь с миром духов прервана. Попробуйте еще раз.")
    
    await state.clear()

# ЗАПУСК
async def main():
    asyncio.create_task(dp.start_polling(bot))
    app = web.Application()
    app.router.add_post("/webhook", handle_tribute_webhook)
    runner = web.AppRunner(app)
    await runner.setup()
    await web.TCPSite(runner, "0.0.0.0", PORT).start()
    await asyncio.Event().wait()

if __name__ == "__main__":
    asyncio.run(main())
