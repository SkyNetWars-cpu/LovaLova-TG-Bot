import asyncio
import aiosqlite
import time
import os
from aiohttp import web
from aiogram import Bot, Dispatcher, Router, F
from aiogram.types import *
from aiogram.client.default import DefaultBotProperties
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.context import FSMContext
from aiogram.exceptions import TelegramAPIError

# --- КОНФИГ ---
TOKEN = os.getenv("BOT_TOKEN", "8818998265:AAHVKZ3FIKXnBQDCQSO0U8_yWpYEYwBexec")
ADMIN_ID = 7305658106
MOD_GROUP = -1003991876955

# Включаем HTML по умолчанию для всех отправляемых сообщений
bot = Bot(token=TOKEN, default=DefaultBotProperties(parse_mode='HTML'))
dp = Dispatcher(storage=MemoryStorage())
router = Router()
DB = "dating_pro_v11.db"

# --- СТРУКТУРА БАЗЫ ДАННЫХ ---
async def init_db():
    async with aiosqlite.connect(DB) as db:
        await db.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            name TEXT, age INTEGER, gender TEXT, pref TEXT,
            photo TEXT, question TEXT, lat REAL, lon REAL, 
            phone TEXT, username TEXT, status TEXT DEFAULT 'active'
        )""")
        await db.execute("CREATE TABLE IF NOT EXISTS likes (uid INTEGER, tid INTEGER, UNIQUE(uid, tid))")
        await db.execute("CREATE TABLE IF NOT EXISTS blacklist (uid INTEGER, tid INTEGER, UNIQUE(uid, tid))")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_users_status ON users(status)")
        await db.commit()

class Reg(StatesGroup):
    name, age, gender, pref, geo, phone, photo, question = State(), State(), State(), State(), State(), State(), State(), State()

class Chat(StatesGroup):
    target = State()

def main_kb():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="🔍 Кто рядом?")],
        [KeyboardButton(text="😶‍❄️ Заморозить"), KeyboardButton(text="✨ ilikeit")]
    ], resize_keyboard=True)

# --- РЕГИСТРАЦИЯ С КОНТАКТОМ И GPS ---
@router.message(F.text == "/start")
async def start(m: Message, state: FSMContext):
    async with aiosqlite.connect(DB) as db:
        async with db.execute("SELECT status FROM users WHERE user_id=?", (m.from_user.id,)) as cur:
            res = await cur.fetchone()
            if res:
                if res[0] == 'frozen':
                    await db.execute("UPDATE users SET status='active' WHERE user_id=?", (m.from_user.id,))
                    await db.commit()
                    return await m.answer("✅ Твоя анкета успешно разморожена!", reply_markup=main_kb())
                return await m.answer("👋 С возвращением в поиск!", reply_markup=main_kb())
                
    await m.answer("Привет! Давай создадим твою анкету. Как тебя зовут?")
    await state.set_state(Reg.name)

@router.message(Reg.name)
async def reg_name(m: Message, state: FSMContext):
    await state.update_data(name=m.text)
    await m.answer("Сколько тебе лет?")
    await state.set_state(Reg.age)

@router.message(Reg.age)
async def reg_age(m: Message, state: FSMContext):
    if not m.text.isdigit(): 
        return await m.answer("Пожалуйста, введи возраст цифрами.")
    await state.update_data(age=int(m.text))
    kb = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="Парень"), KeyboardButton(text="Девушка")]], resize_keyboard=True)
    await m.answer("Укажи свой пол:", reply_markup=kb)
    await state.set_state(Reg.gender)

@router.message(Reg.gender)
async def reg_gender(m: Message, state: FSMContext):
    await state.update_data(gender=m.text)
    kb = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="Парней"), KeyboardButton(text="Девушек"), KeyboardButton(text="Всех")]], resize_keyboard=True)
    await m.answer("Кого ты хочешь найти?", reply_markup=kb)
    await state.set_state(Reg.pref)

@router.message(Reg.pref)
async def reg_pref(m: Message, state: FSMContext):
    await state.update_data(pref=m.text)
    kb = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="📍 Отправить геопозицию", request_location=True)]], resize_keyboard=True)
    await m.answer("Поделись геопозицией, чтобы мы нашли людей поблизости:", reply_markup=kb)
    await state.set_state(Reg.geo)

@router.message(Reg.geo, F.location)
async def reg_geo(m: Message, state: FSMContext):
    await state.update_data(lat=m.location.latitude, lon=m.location.longitude)
    kb = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="📱 Поделиться контактом", request_contact=True)]], resize_keyboard=True)
    await m.answer("Для подтверждения профиля и защиты от ботов отправь свой номер телефона:", reply_markup=kb)
    await state.set_state(Reg.phone)

@router.message(Reg.phone, F.contact)
async def reg_phone(m: Message, state: FSMContext):
    await state.update_data(phone=m.contact.phone_number)
    await m.answer("Отлично! Теперь отправь одно своё лучшее фото:", reply_markup=ReplyKeyboardRemove())
    await state.set_state(Reg.photo)

@router.message(Reg.photo, F.photo)
async def reg_photo(m: Message, state: FSMContext):
    await state.update_data(photo=m.photo[-1].file_id)
    await m.answer("Напиши БИО (расскажи о себе или задай интересный вопрос собеседнику):")
    await state.set_state(Reg.question)

@router.message(Reg.question)
async def reg_final(m: Message, state: FSMContext):
    d = await state.get_data()
    username = f"@{m.from_user.username}" if m.from_user.username else "Нет юзернейма"
    
    async with aiosqlite.connect(DB) as db:
        await db.execute("""
            INSERT OR REPLACE INTO users (user_id, name, age, gender, pref, photo, question, lat, lon, phone, username, status)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            (m.from_user.id, d['name'], d['age'], d['gender'], d['pref'], d['photo'], m.text, d['lat'], d['lon'], d['phone'], username, 'active')
        )
        await db.commit()
    
    # Детальный лог регистрации анкеты для модератора
    cap = (
        f"🆕 <b>НОВАЯ АНКЕТА</b>\n"
        f"👤 Имя: <b>{d['name']}</b>, {d['age']} л.\n"
        f"📱 Тел: <code>{d['phone']}</code>\n"
        f"🔗 Профиль: <a href='tg://user?id={m.from_user.id}'>{m.from_user.first_name}</a>\n"
        f"💬 Юзернейм: {username}\n"
        f"🆔 ID: <code>{m.from_user.id}</code>\n"
        f"📝 О себе: <i>{m.text}</i>"
    )
    await bot.send_photo(MOD_GROUP, d['photo'], caption=cap)
    await bot.send_location(MOD_GROUP, latitude=d['lat'], longitude=d['lon'])
    
    await m.answer("🎉 Регистрация завершена! Начнем поиск?", reply_markup=main_kb())
    await state.clear()

# --- СИСТЕМА МОДЕРАЦИИ И АДМИН-ЛОГИРОВАНИЯ ---
async def log_action_to_mod_group(text: str, media_file_id: str = None, media_type: str = None):
    """Универсальная функция логирования действий в MOD_GROUP"""
    try:
        if not media_file_id:
            await bot.send_message(MOD_GROUP, text)
        else:
            if media_type == 'photo':
                await bot.send_photo(MOD_GROUP, media_file_id, caption=text)
            elif media_type == 'voice':
                await bot.send_message(MOD_GROUP, text)
                await bot.send_voice(MOD_GROUP, media_file_id)
            elif media_type == 'video_note':
                await bot.send_message(MOD_GROUP, text)
                await bot.send_video_note(MOD_GROUP, media_file_id)
    except Exception as e:
        print(f"Ошибка логирования модерации: {e}")

# --- ЗАМОРОЗКА ---
@router.message(F.text == "😶‍❄️ Заморозить")
async def freeze_profile(m: Message):
    async with aiosqlite.connect(DB) as db:
        await db.execute("UPDATE users SET status='frozen' WHERE user_id=?", (m.from_user.id,))
        await db.commit()
    
    await log_action_to_mod_group(f"❄️ Пользователь <a href='tg://user?id={m.from_user.id}'>{m.from_user.first_name}</a> (ID: <code>{m.from_user.id}</code>) <b>заморозил</b> анкету.")
    await m.answer("❄️ Твоя анкета скрыта из поиска. Для активации напиши /start", reply_markup=ReplyKeyboardRemove())

# --- КНОПКА СИМПАТИЙ (✨ ilikeit) ---
@router.message(F.text == "✨ ilikeit")
async def show_fans(m: Message):
    async with aiosqlite.connect(DB) as db:
        query = """
        SELECT * FROM users WHERE user_id IN (SELECT uid FROM likes WHERE tid=?) 
        AND user_id NOT IN (SELECT tid FROM likes WHERE uid=?) LIMIT 5
        """
        async with db.execute(query, (m.from_user.id, m.from_user.id)) as cur:
            fans = await cur.fetchall()
            
    if not fans:
        return await m.answer("Пока никто не выразил симпатию. Продолжай искать новые лица!")
        
    await m.answer(f"✨ Ты нравишься этим людям ({len(fans)}):")
    for u in fans:
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="❤️ Лайкнуть в ответ", callback_data=f"l_{u[0]}") ]])
        await bot.send_photo(m.chat.id, u[5], caption=f"🔥 {u[1]}, {u[2]} лет\n\n📝 {u[6]}", reply_markup=kb)

# --- ПОИСК И ЛАЙКИ ---
@router.message(F.text == "🔍 Кто рядом?")
async def find(m: Message):
    async with aiosqlite.connect(DB) as db:
        query = """
        SELECT * FROM users WHERE user_id != ? AND status='active' 
        AND user_id NOT IN (SELECT tid FROM blacklist WHERE uid=?) 
        AND user_id NOT IN (SELECT tid FROM likes WHERE uid=?)
        ORDER BY RANDOM() LIMIT 1
        """
        async with db.execute(query, (m.from_user.id, m.from_user.id, m.from_user.id)) as cur:
            u = await cur.fetchone()
            
    if u:
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="❤️", callback_data=f"l_{u[0]}"), InlineKeyboardButton(text="👎", callback_data=f"d_{u[0]}")],
            [InlineKeyboardButton(text="💌 Чат", callback_data=f"chat_{u[0]}")]
        ])
        await bot.send_photo(m.chat.id, u[5], caption=f"✨ {u[1]}, {u[2]} лет\n\n📝 <b>О себе:</b> {u[6]}", reply_markup=kb)
    else:
        await m.answer("Анкеты поблизости закончились. Попробуй зайти немного позже!")

@router.callback_query(F.data.startswith(("l_", "d_")))
async def reaction_handler(c: CallbackQuery):
    act, tid = c.data.split("_")
    tid = int(tid)
    
    async with aiosqlite.connect(DB) as db:
        if act == "d":
            await db.execute("INSERT OR IGNORE INTO blacklist (uid, tid) VALUES (?, ?)", (c.from_user.id, tid))
            await log_action_to_mod_group(f"👎 <a href='tg://user?id={c.from_user.id}'>{c.from_user.first_name}</a> дизлайкнул <a href='tg://user?id={tid}'>этого пользователя</a>")
        else:
            await db.execute("INSERT OR IGNORE INTO likes (uid, tid) VALUES (?, ?)", (c.from_user.id, tid))
            await log_action_to_mod_group(f"❤️ <a href='tg://user?id={c.from_user.id}'>{c.from_user.first_name}</a> лайкнул <a href='tg://user?id={tid}'>этого пользователя</a>")
            
            # Проверка взаимности
            async with db.execute("SELECT uid FROM likes WHERE uid=? AND tid=?", (tid, c.from_user.id)) as cur:
                if await cur.fetchone():
                    # Лог мэтча модераторам
                    await log_action_to_mod_group(f"🔥 <b>ВЗАИМНЫЙ МЭТЧ!</b>\n<a href='tg://user?id={c.from_user.id}'>{c.from_user.first_name}</a> (ID: <code>{c.from_user.id}</code>) ⚡ <a href='tg://user?id={tid}'>Собеседник</a> (ID: <code>{tid}</code>)")
                    
                    await bot.send_message(c.from_user.id, f"🔥 Взаимная симпатия! Начни общение прямо сейчас: tg://user?id={tid}")
                    try:
                        await bot.send_message(tid, f"🔥 У тебя взаимная симпатия! Начни общение прямо сейчас: tg://user?id={c.from_user.id}")
                    except TelegramAPIError:
                        pass
        await db.commit()
        
    await c.message.delete()
    await find(c.message)

# --- АНОНИМНЫЙ ЧАТ ---
@router.callback_query(F.data.startswith("chat_"))
async def start_chat(c: CallbackQuery, state: FSMContext):
    target = int(c.data.split("_")[1])
    await state.update_data(target=target)
    await state.set_state(Chat.target)
    
    kb = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="❌ Завершить чат")]], resize_keyboard=True)
    await c.message.answer("💬 Чат активен! Всё, что ты напишешь, будет отправлено анонимно.", reply_markup=kb)
    
    # Уведомляем получателя о начале чата
    try:
        await bot.send_message(target, "🔔 С тобой начали анонимный чат! Чтобы ответить, нажми кнопку '🔍 Кто рядом?' или отвечай прямо в это поле, когда тебе напишут.")
    except TelegramAPIError:
        pass
        
    await log_action_to_mod_group(f"🚪 <a href='tg://user?id={c.from_user.id}'>{c.from_user.first_name}</a> (ID: <code>{c.from_user.id}</code>) открыл диалог с (ID: <code>{target}</code>)")

@router.message(Chat.target, F.text == "❌ Завершить чат")
async def exit_chat(m: Message, state: FSMContext):
    data = await state.get_data()
    target = data.get('target')
    await state.clear()
    await m.answer("🚪 Чат завершен.", reply_markup=main_kb())
    
    if target:
        try:
            await bot.send_message(target, "❌ Собеседник завершил анонимный чат.")
        except TelegramAPIError:
            pass
        await log_action_to_mod_group(f"🚪 <a href='tg://user?id={m.from_user.id}'>{m.from_user.first_name}</a> закрыл диалог с (ID: <code>{target}</code>)")

@router.message(Chat.target)
async def chat_logic(m: Message, state: FSMContext):
    d = await state.get_data()
    target = d.get('target')
    if not target: return
    
    # Шапка лога для модерации
    log_header = (
        f"🕵️ <b>ПЕРЕХВАТ ДИАЛОГА</b>\n"
        f"От: <a href='tg://user?id={m.from_user.id}'>{m.from_user.first_name}</a> (ID: <code>{m.from_user.id}</code>)\n"
        f"Кому: <a href='tg://user?id={target}'>Собеседник</a> (ID: <code>{target}</code>)\n"
        f"🤖 Тип контента: "
    )
    
    try:
        if m.text:
            await bot.send_message(target, f"📩: {m.text}")
            await log_action_to_mod_group(f"{log_header}📝 Текст\n\n💬 Сообщение:\n<i>{m.text}</i>")
            
        elif m.photo:
            await bot.send_photo(target, m.photo[-1].file_id, caption=m.caption)
            await log_action_to_mod_group(f"{log_header}🖼 Фото\nПодпись: {m.caption or 'Нет'}", m.photo[-1].file_id, 'photo')
            
        elif m.voice:
            await bot.send_voice(target, m.voice.file_id)
            await log_action_to_mod_group(f"{log_header}🎙 Голосовое сообщение", m.voice.file_id, 'voice')
            
        elif m.video_note:
            await bot.send_video_note(target, m.video_note.file_id)
            await log_action_to_mod_group(f"{log_header}📹 Кружочек (видеозаметка)", m.video_note.file_id, 'video_note')
            
        else:
            await m.answer("⚠️ Этот тип сообщений пока не поддерживается в анонимном режиме.")
            
    except TelegramAPIError:
        await m.answer("⚠️ Собеседник закрыл доступ к чату или заблокировал бота.")
        await state.clear()
        await m.answer("Диалог принудительно завершен.", reply_markup=main_kb())

# --- ВЕБ-СЕРВЕР ДЛЯ RENDER (БЕЗ ТАЙМАУТОВ) ---
async def health_check(request):
    return web.Response(text="LovaLova PRO Engine is Live!")

async def start_web_server():
    app = web.Application()
    app.router.add_get('/', health_check)
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.environ.get("PORT", 10000))
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()
    print(f"✅ Асинхронный веб-порт {port} успешно зарезервирован")

# --- СТАРТ СИСТЕМЫ ---
async def main():
    await init_db()
    dp.include_router(router)
    await start_web_server()
    await bot.delete_webhook(drop_pending_updates=True)
    print("✅ Бот успешно запущен в облачной среде Render")
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        print("Бот выключен.")
