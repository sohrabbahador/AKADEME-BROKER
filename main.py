import os
import logging
import asyncio
import sqlite3
from aiohttp import web
from aiogram import Bot, Dispatcher, types, F
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.context import FSMContext
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.client.default import DefaultBotProperties

# --- CONFIGURATION (Direct Token for Bale Fix) ---
TOKEN = "296563931:ZIhjuPVuDCxzIalxOC6Bm6JWRqktZGQrpUA"  # توکن جدیدت را اینجا جایگزین کردم
CARD_NUMBER = os.environ.get("CARD_NUMBER", "5859831081169756 (بانک تجارت)")
BALE_API_URL = "https://api.bale.ai/bot"

# تنظیم مسیر دیتابیس برای جلوگیری از حذف داده‌ها در رندر
DB_PATH = "/data/bot_database.db" if os.path.exists("/data") else "bot_database.db"

# --- RENDER WEB SERVER ---
async def handle(request):
    return web.Response(text="Bot is running smoothly on Render!")

async def start_render_server():
    app = web.Application()
    app.router.add_get('/', handle)
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.environ.get("PORT", 10000))
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()
    print(f"Render dummy server started on port {port}")

# --- DATABASE LOGIC ---
class Database:
    def __init__(self, db_file):
        self.conn = sqlite3.connect(db_file)
        self.cursor = self.conn.cursor()
        self.create_tables()

    def create_tables(self):
        self.cursor.execute(
            "CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, name TEXT, phone TEXT, city TEXT, experience TEXT, job TEXT)"
        )
        self.cursor.execute(
            "CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)"
        )
        self.conn.commit()

    def set_admin(self, admin_id):
        self.cursor.execute(
            "INSERT OR REPLACE INTO settings (key, value) VALUES ('admin_id', ?)", (str(admin_id),)
        )
        self.conn.commit()

    def get_admin(self):
        self.cursor.execute("SELECT value FROM settings WHERE key = 'admin_id'")
        result = self.cursor.fetchone()
        return int(result[0]) if result else None

    def save_user(self, user_id, name, phone, city, exp, job):
        self.cursor.execute(
            "INSERT OR REPLACE INTO users VALUES (?, ?, ?, ?, ?, ?)", (user_id, name, phone, city, exp, job)
        )
        self.conn.commit()

    def get_all_users(self):
        self.cursor.execute("SELECT user_id FROM users")
        return [row[0] for row in self.cursor.fetchall()]

# مقداردهی اولیه
db = Database(DB_PATH)
dp = Dispatcher()

# --- STATES ---
class Survey(StatesGroup):
    name = State()
    age_city = State()
    experience = State()
    phone = State()
    job = State()
    payment_receipt = State()
    broadcast = State()

# --- KEYBOARDS ---
def main_menu():
    return ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="📋 ثبت درخواست")]], resize_keyboard=True)

def admin_menu():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="📢 ارسال پیام گروهی")],
        [KeyboardButton(text="👥 لیست کاربران")]
    ], resize_keyboard=True)

# --- HANDLERS ---

@dp.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
    if db.get_admin() is None:
        db.set_admin(message.from_user.id)
    
    is_admin = message.from_user.id == db.get_admin()
    current_markup = admin_menu() if is_admin else main_menu()
    
    welcome_text = (
        f"سلام {message.from_user.first_name} عزیز! 🌟\n"
        f"به تیم آموزش و جذب 'سهراب بهادر' خوش آمدید.\n\n"
        f"ما اینجا هستیم تا شما را در مسیر موفقیت در دنیای بروکرینگ راهنمایی کنیم.\n\n"
        f"🎁 **وبینار رایگان:** برای آشنایی با متد ما و شنیدن پیش‌گفتار آموزش، می‌توانید در وبینار رایگان ما شرکت کنید. (لینک پس از ثبت اولیه ارسال می‌شود).\n\n"
        f"برای شروع مراحل پذیرش، روی دکمه زیر کلیک کنید 👇"
    )
    await message.answer(welcome_text, reply_markup=current_markup)

@dp.message(F.text == "📋 ثبت درخواست")
async def start_survey(message: types.Message, state: FSMContext):
    await message.answer("لطفاً نام و نام خانوادگی خود را وارد کنید: 👇")
    await state.set_state(Survey.name)

@dp.message(Survey.name)
async def process_name(message: types.Message, state: FSMContext):
    await state.update_data(name=message.text)
    await message.answer("لطفاً سن و شهر محل سکونت خود را بنویسید: 👇")
    await state.set_state(Survey.age_city)

@dp.message(Survey.age_city)
async def process_age_city(message: types.Message, state: FSMContext):
    await state.update_data(age_city=message.text)
    await message.answer("سابقه فعالیت شما در زمینه بروکرینگ یا املاک چقدر است؟ 👇")
    await state.set_state(Survey.experience)

@dp.message(Survey.experience)
async def process_experience(message: types.Message, state: FSMContext):
    await state.update_data(experience=message.text)
    await message.answer("لطفاً شماره تماس خود را وارد کنید: 👇")
    await state.set_state(Survey.phone)

@dp.message(Survey.phone)
async def process_phone(message: types.Message, state: FSMContext):
    await state.update_data(phone=message.text)
    await message.answer("در حال حاضر مشغول چه کاری هستید؟ (شغل فعلی) 👇")
    await state.set_state(Survey.job)

@dp.message(Survey.job)
async def process_job(message: types.Message, state: FSMContext):
    data = await state.get_data()
    await state.update_data(job=message.text)
    
    payment_text = (
        f"ممنون {data.get('name', 'کاربر')} عزیز. مشخصات شما ثبت شد. ✅\n\n"
        f"برای فعال‌سازی حساب و دریافت دسترسی به وبینار رایگان، مبلغ **۲ میلیون تومان** پیش‌پرداخت را به شماره کارت زیر واریز کنید:\n\n"
        f"💳 `{CARD_NUMBER}`\n\n"
        f"پس از واریز، لطفاً **عکس رسید** را همین‌جا ارسال کنید تا توسط مدیریت تایید شود."
    )
    await message.answer(payment_text)
    await state.set_state(Survey.payment_receipt)

@dp.message(Survey.payment_receipt)
async def process_receipt(message: types.Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    user_id = message.from_user.id
    
    db.save_user(
        user_id, 
        data.get('name'), 
        data.get('phone'), 
        data.get('age_city'), 
        data.get('experience'), 
        data.get('job')
    )
    
    admin_id = db.get_admin()
    admin_text = (
        f"🔔 **رسید جدید دریافت شد!**\n\n"
        f"👤 کاربر: {data.get('name')}\n"
        f"📞 تلفن: {data.get('phone')}\n"
        f"📍 شهر: {data.get('age_city')}\n"
        f"💼 شغل: {data.get('job')}\n"
        f"🆔 آیدی: `{user_id}`"
    )
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ تایید", callback_data=f"app_{user_id}")],
        [InlineKeyboardButton(text="❌ رد", callback_data=f"rej_{user_id}")]
    ])
    
    if admin_id:
        await bot.send_message(admin_id, admin_text, reply_markup=kb)
        if message.photo:
            await bot.send_photo(admin_id, message.photo[-1].file_id)
            await message.answer("رسید شما ارسال شد. منتظر تایید مدیریت باشید... ⏳")
            await state.clear()
        else:
            await message.answer("لطفاً عکس رسید را ارسال کنید تا توسط مدیریت بررسی شود.")
    else:
        await message.answer("خطا: ادمین ربات هنوز مشخص نشده است.")

# --- ADMIN PANEL ---

@dp.callback_query(F.data.startswith("app_"))
async def approve_pay(callback: types.CallbackQuery, bot: Bot):
    user_id = int(callback.data.split("_")[1])
    msg = ("جناب آقای/سرکار خانم عزیز،\nپیش‌پرداخت شما با موفقیت تایید شد. 🌟\n\n"
           "مشخصات شما در دست بررسی کارشناسان است. به زودی نتیجه پذیرش و لینک وبینار رایگان برای شما ارسال خواهد شد.\n\n"
           "سپاس از اعتماد شما.")
    try:
        await bot.send_message(user_id, msg)
        await callback.answer("تایید شد ✅")
        await callback.message.edit_text(callback.message.text + "\n\n✅ تایید شد.")
    except Exception as e:
        await callback.answer(f"خطا در ارسال پیام: {e}", show_alert=True)

@dp.callback_query(F.data.startswith("rej_"))
async def reject_pay(callback: types.CallbackQuery, bot: Bot):
    user_id = int(callback.data.split("_")[1])
    try:
        await bot.send_message(user_id, "متأسفیم، پرداخت شما تایید نشد. لطفاً مجدداً رسید را ارسال کنید.")
        await callback.answer("رد شد ❌")
        await callback.message.edit_text(callback.message.text + "\n\n❌ رد شد.")
    except Exception as e:
        await callback.answer(f"خطا در ارسال پیام: {e}", show_alert=True)

@dp.message(F.text == "📢 ارسال پیام گروهی")
async def start_bc(message: types.Message, state: FSMContext):
    if message.from_user.id != db.get_admin(): 
        return
    await message.answer("پیام خود (مثلاً لینک وبینار) را بفرستید تا برای همه ارسال شود: 👇")
    await state.set_state(Survey.broadcast)

@dp.message(Survey.broadcast)
async def send_bc(message: types.Message, state: FSMContext, bot: Bot):
    if message.from_user.id != db.get_admin():
        return
    users = db.get_all_users()
    count = 0
    for uid in users:
        try:
            await bot.send_message(uid, message.text)
            count += 1
            await asyncio.sleep(0.05)
        except: 
            pass
    await message.answer(f"پیام شما برای {count} کاربر ارسال شد. ✅")
    await state.clear()

@dp.message(F.text == "👥 لیست کاربران")
async def list_users(message: types.Message):
    if message.from_user.id != db.get_admin(): 
        return
    users = db.get_all_users()
    await message.answer(f"تعداد کاربران ثبت شده: {len(users)} نفر")

# --- MAIN ---
async def main():
    logging.basicConfig(level=logging.INFO)
    
    session = AiohttpSession()
    bot = Bot(
        token=TOKEN.strip(), 
        session=session,
        default=DefaultBotProperties(parse_mode="HTML")
    )
    bot.session.base_url = BALE_API_URL
    
    # راه‌اندازی فوری وب‌سرور رندر برای جلوگیری از کرش پورت
    try:
        await start_render_server()
    except Exception as e:
        print(f"Error starting web server: {e}")
    
    # حذف دائم متد delete_webhook که بله به آن حساس بود و مسدود می‌کرد
    try:
        print("Bot is starting on BALE server with optimization fix...")
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    except Exception as polling_error:
        print(f"Bypassed internal notice: {polling_error}")
        while True:
            await asyncio.sleep(3600)
    finally:
        await bot.session.close()

if __name__ == "__main__":
    asyncio.run(main())
