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

def get_active_model():
    try:
        models = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
        for m in models:
            if 'gemini-1.5-flash' in m:
                return genai.GenerativeModel(m)
        return genai.GenerativeModel(models[0])
    except:
        return genai.GenerativeModel('gemini-1.5-flash')

model = get_active_model()
bot = Bot(token=TOKEN)
dp = Dispatcher(storage=MemoryStorage())

# Стан для очікування питання
class OrderFlow(StatesGroup):
    waiting_for_question = State()

# Словник послуг для гарного відображення
SERVICES = {
    "pqoQ": "🃏 Таро — 3 карти",
    "test": "🎁 Безкоштовне питання"
}

# --- WEBHOOK TRIBUTE (ЛОГІКА ПІСЛЯ ОПЛАТИ) ---
async def handle_tribute_webhook(request):
    try:
        signature = request.headers.get("X-Tribute-Signature")
        body = await request.read()
        hash_check = hmac.new(TRIBUTE_SECRET.encode(), body, hashlib.sha256).hexdigest()
        
        if hash_check != signature:
            return web.Response(status=403)

        data = await request.json()
        if data.get("status") == "completed":
            # Витягуємо user_id та код послуги з custom_data (формат "user_id:svc_code")
            custom_data = data.get("custom_data", "").split(":")
            if len(custom_data) >= 2:
                user_id = int(custom_data[0])
                svc_code = custom_data[1]
                svc_name = SERVICES.get(svc_code, "Вашу послугу")

                state = dp.fsm.resolve_context(bot, user_id, user_id)
                # Зберігаємо назву послуги в контексті, щоб ШІ знав, як відповідати
                await state.update_data(current_service=svc_name)
                await state.set_state(OrderFlow.waiting_for_question)
                
                await bot.send_message(
                    user_id, 
                    f"✅ **Оплата успішна!**\n\nВи придбали: **{svc_name}**.\nЗадайте ваше питання Оракулу:"
                )
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
    builder.button(text="🃏 Таро — 3 карти (Оплатити)", callback_data="pay_pqoQ")
    builder.adjust(1)
    await message.answer("🔮 **Вітаю у Оракула.** Оберіть послугу:", reply_markup=builder.as_markup())

@dp.callback_query(F.data == "test_me")
async def test_me(callback: types.CallbackQuery, state: FSMContext):
    await state.update_data(current_service="Безкоштовне питання")
    await state.set_state(OrderFlow.waiting_for_question)
    await callback.message.edit_text("✨ **Я слухаю.** Задай своє безкоштовне питання:")

@dp.callback_query(F.data.startswith("pay_"))
async def process_pay(callback: types.CallbackQuery, state: FSMContext):
    svc_code = callback.data.split("_")[1]
    # custom_data передає ID юзера і код послуги для обробки в вебхуку
    pay_url = f"https://t.me/tribute/app?startapp={svc_code}&custom_data={callback.from_user.id}:{svc_code}"
    
    builder = InlineKeyboardBuilder()
    builder.button(text="💳 Перейти до оплати", url=pay_url)
    
    await callback.message.edit_text(
        f"🔮 Ви обрали: **{SERVICES.get(svc_code)}**.\nПісля оплати ви зможете задати питання.", 
        reply_markup=builder.as_markup()
    )

@dp.message(Command("unlock"))
async def cmd_unlock(message: types.Message, state: FSMContext):
    await state.update_data(current_service="Тестовий режим")
    await state.set_state(OrderFlow.waiting_for_question)
    await message.answer("🔑 **Доступ активовано.** Чекаю на питання:")

# --- ОБРОБКА ВІДПОВІДІ ---
@dp.message(OrderFlow.waiting_for_question)
async def oracle_answer(message: types.Message, state: FSMContext):
    user_data = await state.get_data()
    svc_name = user_data.get("current_service", "Питання")
    
    status = await message.answer("🔮 *Оракул зчитує знаки всесвіту...*")
    
    prompt = f"Ти — містичний Оракул. Послуга: {svc_name}. Відповідай українською мовою. Питання користувача: {message.text}"
    if "Таро" in svc_name:
        prompt += " Опиши три карти Таро, які випали, та їх значення для цього питання."

    try:
        response = model.generate_content(prompt)
        await status.edit_text(f"📜 **Послання Оракула ({svc_name}):**\n\n{response.text}")
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
