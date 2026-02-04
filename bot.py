# --- НАЛАШТУВАННЯ ---
TOKEN = os.getenv("TELEGRAM_TOKEN")
G_KEY = os.getenv("G_KEY") 

# Очищуємо ключ від можливих пробілів прямо в коді
if G_KEY:
    G_KEY = G_KEY.strip()

genai.configure(api_key=G_KEY)
model = genai.GenerativeModel('gemini-1.5-flash')

@dp.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
    await state.clear()
    
    # Визначаємо, що саме бачить бот
    if not G_KEY:
        status_info = "❌ Ключ не знайдено в налаштуваннях Railway!"
    else:
        status_info = f"📡 Ключ підключено (починається на: {G_KEY[:6]}...)"

    builder = InlineKeyboardBuilder()
    builder.button(text="🎁 Безкоштовне питання", callback_data="test_me")
    builder.button(text="🃏 Таро — 3 карти", callback_data="pay_pqoQ")
    builder.adjust(1)
    
    await message.answer(
        f"🔮 **Оракул вітає вас.**\n\n"
        f"🛠 **Статус системи:**\n{status_info}\n\n"
        f"Оберіть послугу:", 
        reply_markup=builder.as_markup()
    )
