import os
import asyncio
import hmac
import hashlib
import json
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiohttp import web
from openai import AsyncOpenAI

# Налаштування зі змінних оточення Railway
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

# Список послуг (назви та посилання)
SERVICES = {
    "🃏 ТАРО (основа)": {
        "Таро — 3 карты": "https://t.me/tribute/app?startapp=pqoQ",
        "Таро — 5 карт": "https://t.me/tribute/app?startapp=pqgq",
        "Таро — 8 карт": "https://t.me/tribute/app?startapp=pqgr",
    },
    "❤️ ОТНОШЕНИЯ": {
        "Что он(а) чувствует": "https://t.me/tribute/app?startapp=pqgz",
        "Развитие отношений": "https://t.me/tribute/app?startapp=pqgB",
    },
    "🔮 ОРАКУЛ": {
        "Оракул — ответ": "https://t.me/tribute/app?startapp=pqgw",
    }
}

# --- ОБРОБНИК ВЕБХУКА (АВТОМАТИЧНА ОПЛАТА) ---
async def handle_tribute_webhook(request):
    try:
        signature = request.headers.get("X-Tribute-Signature")
        body = await request.read()
        
        # Перевірка безпеки (підпису)
        hash_check = hmac.new(TRIBUTE_SECRET.encode(), body, hashlib.sha256).hexdigest()
        if hash_check != signature:
            return web.Response(status=403)

        data = await request.json()
        # Перевіряємо, чи оплата успішна
        if data.get("status") == "completed":
            # Отримуємо ID користувача з custom_data
            user_id = int(data.get("custom_data"))
            
            # Змінюємо стан користувача на очікування питання
            user_state = dp.fsm.resolve_context(bot, user_id, user_id)
            await user_state.set_state(OrderFlow.waiting_for_question)
            
            await bot.send_message(
                user_id, 
                "✅ **Оплата получена!**\n\nОракул готов ответить на ваш запрос. Пожалуйста, напишите ваш вопрос прямо здесь:"
            )
        return web.Response(text="ok")
    except Exception as e:
        print(f"Webhook error: {e}")
        return web.Response(status=500)

# --- ЛОГІКА ТЕЛЕГРАМ БОТА ---

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    builder = InlineKeyboardBuilder()
    for cat in SERVICES.keys():
        builder.button(text=cat, callback_data=f"cat_{cat}")
    builder.adjust(1)
    await message.answer("🔮 **Добро пожаловать к Оракулу.**\nВыберите категорию для расклада:", reply_markup=builder.as_markup())

@dp.callback_query(F.data.startswith("cat_"))
async def choose_sub(callback: types.CallbackQuery):
    cat = callback.data.split("_")[1]
    builder = InlineKeyboardBuilder()
    for sub, link in SERVICES[cat].items():
        builder.button(text=sub, callback_data=f"svc_{cat}_{sub}")
    builder.button(text="⬅️ Назад", callback_data="back")
    builder.adjust(1)
    await callback.message.edit_text(f"Выберите услугу ({cat}):", reply_markup=builder.as_markup())

@dp.callback_query(F.data == "back")
async def back(callback: types.CallbackQuery):
    await cmd_start(callback.message)

@dp.callback_query(F.data.startswith("svc_"))
async def process_selection(callback: types.CallbackQuery, state: FSMContext):
    _, cat, svc = callback.data.split("_")
    base_link = SERVICES[cat][svc]
    user_id = callback.from_user.id
    
    # Додаємо ID користувача в посилання, щоб дізнатися його при оплаті
    final_pay_url = f"{base_link}&custom_data={user_id}"
    
    await state.update_data(current_svc=svc)
    
    builder = InlineKeyboardBuilder()
    builder.button(text="💳 Оплатить", url=final_pay_url)
    
    await callback.message.edit_text(
        f"✨ **Вы выбрали:** {svc}\n\nОплатите услугу по кнопке ниже. Доступ к вопросу откроется автоматически сразу после оплаты.",
        reply_markup=builder.as_markup()
    )
    await state.set_state(OrderFlow.waiting_for_payment)

@dp.message(OrderFlow.waiting_for_question)
async def ai_oracle_answer(message: types.Message, state: FSMContext):
    user_data = await state.get_data()
    svc = user_data.get('current_svc', 'Расклад')
    
    status_msg = await message.answer("🔮 *Оракул входит в транс... Собираю энергию для ответа...*")
    
    try:
        response = await client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "Ты — мудрый и загадочный Оракул. Твои ответы глубокие, с метафорами, на русском языке. Никогда не говори, что ты робот или ChatGPT."},
                {"role": "user", "content": f"Услуга: {svc}. Вопрос клиента: {message.text}"}
            ]
        )
        await status_msg.edit_text(f"📜 **Послание Оракула:**\n\n{response.choices[0].message.content}")
    except Exception:
        await status_msg.edit_text("🌒 Сейчас связь с миром духов нестабильна. Попробуйте еще раз через минуту.")
    
    await state.clear()

# --- ЗАПУСК ---
async def main():
    # Запускаємо бота
    asyncio.create_task(dp.start_polling(bot))
    
    # Створюємо веб-сервер для вебхуків Tribute
    app = web.Application()
    app.router.add_post("/webhook", handle_tribute_webhook)
    runner = web.AppRunner(app)
    await runner.setup()
    await web.TCPSite(runner, "0.0.0.0", PORT).start()
    
    print(f"Server started on port {PORT}")
    await asyncio.Event().wait()

if __name__ == "__main__":
    asyncio.run(main())

