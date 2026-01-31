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

# Читання налаштувань з Railway
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

# Словник послуг (Код з Tribute : Назва для Оракула)
SERVICES_MAP = {
    "pqgo": "Таро — 3 карты",
    "pqgq": "Таро — 5 карт",
    "pqgr": "Таро — 8 карт",
    "pqgu": "Таро — отношения",
    "pqgw": "Оракул — ответ",
    "pqgD": "Ответ Да / Нет"
}

# --- ОБРОБНИК ВЕБХУКА (АВТОМАТИЧНА ОПЛАТА) ---
async def handle_tribute_webhook(request):
    try:
        signature = request.headers.get("X-Tribute-Signature")
        body = await request.read()
        
        # Перевірка безпеки
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
                
                await bot.send_message(
                    user_id, 
                    "✅ **Оплата подтверждена!**\n\nОракул готов. Пожалуйста, введите ваш вопрос:"
                )
        return web.Response(text="ok")
    except Exception:
        return web.Response(status=500)

# --- ЛОГІКА БОТА ---

@dp.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
    # Перевірка, чи не повернувся юзер після оплати
    current_state = await state.get_state()
    if current_state == OrderFlow.waiting_for_question:
        await message.answer("🔮 С возвращением! Оплата получена. Напишите ваш вопрос:")
        return

    builder = InlineKeyboardBuilder()
    builder.button(text="🃏 ТАРО", callback_data="cat_taro")
    builder.button(text="🔮 ОРАКУЛ", callback_data="cat_ora")
    builder.adjust(1)
    await message.answer("🔮 **Добро пожаловать к Оракулу.**\nВыберите категорию:", reply_markup=builder.as_markup())

@dp.callback_query(F.data == "cat_taro")
async def cat_taro(callback: types.CallbackQuery):
    builder = InlineKeyboardBuilder()
    # Приклад кнопок (заміни коди на свої)
    builder.button(text="3 карты (500 ₽)", callback_data="buy_pqgo")
    builder.button(text="8 карт (1000 ₽)", callback_data="buy_pqgr")
    builder.button(text="⬅️ Назад", callback_data="back")
    builder.adjust(1)
    await callback.message.edit_text("✨ **Расклады Таро:**", reply_markup=builder.as_markup())

@dp.callback_query(F.data == "back")
async def back(callback: types.CallbackQuery, state: FSMContext):
    await cmd_start(callback.message, state)

@dp.callback_query(F.data.startswith("buy_"))
async def process_buy(callback: types.CallbackQuery, state: FSMContext):
    svc_code = callback.data.split("_")[1]
    user_id = callback.from_user.id
    
    # Посилання з даними для вебхука
    pay_url = f"https://t.me/tribute/app?startapp={svc_code}&custom_data={user_id}:{svc_code}"
    
    builder = InlineKeyboardBuilder()
    builder.button(text="💳 Оплатить", url=pay_url)
    
    await callback.message.edit_text(
        "🔮 После оплаты доступ к Оракулу откроется автоматически в этом чате.",
        reply_markup=builder.as_markup()
    )
    await state.set_state(OrderFlow.waiting_for_payment)

@dp.message(OrderFlow.waiting_for_question)
async def oracle_answer(message: types.Message, state: FSMContext):
    data = await state.get_data()
    svc = data.get("current_svc", "Расклад")
    
    status = await message.answer("🔮 *Оракул входит в транс...*")
    
    try:
        response = await client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "Ты — древний мудрый Оракул. Твои ответы глубокие и мистические. Отвечай на русском. Не упоминай ИИ."},
                {"role": "user", "content": f"Услуга: {svc}. Вопрос: {message.text}"}
            ]
        )
        await status.edit_text(f"📜 **Ответ Оракула:**\n\n{response.choices[0].message.content}")
    except:
        await status.edit_text("🌑 Связь прервана. Попробуйте еще раз.")
    
    await state.clear()

# --- СТАРТ ---
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
