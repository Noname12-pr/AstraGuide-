# --- НАЛАШТУВАННЯ ---
TOKEN = os.getenv("TELEGRAM_TOKEN")
G_KEY = os.getenv("G_KEY") 
TRIBUTE_SECRET = os.getenv("TRIBUTE_SECRET")
PORT = int(os.getenv("PORT", 8080))

genai.configure(api_key=G_KEY)

# АВТОМАТИЧНИЙ ПІДБІР РОБОЧОЇ МОДЕЛІ
def find_working_model():
    try:
        # Отримуємо список усіх моделей, доступних для твого ключа
        for m in genai.list_models():
            if 'generateContent' in m.supported_generation_methods:
                # Пріоритет на flash, якщо ні — беремо будь-яку робочу
                if 'gemini-1.5-flash' in m.name:
                    print(f"✅ Знайдено оптимальну модель: {m.name}")
                    return genai.GenerativeModel(m.name)
        
        # Якщо flash не знайдено, беремо першу ліпшу робочу
        available_models = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
        if available_models:
            print(f"📡 Використовую альтернативу: {available_models[0]}")
            return genai.GenerativeModel(available_models[0])
    except Exception as e:
        print(f"❌ Помилка при пошуку моделей: {e}")
    
    # Резервний варіант, якщо список не завантажився
    return genai.GenerativeModel('gemini-1.5-flash')

model = find_working_model()
