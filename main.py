import asyncio
import logging
import os
import sqlite3
from datetime import datetime
import aiohttp
from aiohttp import web
from apscheduler.schedulers.asyncio import AsyncIOScheduler

# تنظیمات لاگ برای مشاهده در کنسول رندر
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- تنظیمات اصلی (Configuration) ---
# اگر TOKEN را در Environment Variables رندر ست کردید، از همان استفاده می‌کند، در غیر این صورت از مقدار پیش‌فرض
TOKEN = os.environ.get("BOT_TOKEN", "1770530298:qdkjoE0lmqmEyOFSLdorAbr5SU-bUXyCNiY").strip()
CARD_NUMBER = os.environ.get("CARD_NUMBER", "5859831081169756 (بانک تجارت)")
BALE_API_URL = f"https://tapi.bale.ai/bot{TOKEN}"
DB_PATH = "bot_database.db"
ADMIN_ID = 160513400
FINAL_LINK = "https://t.me/your_link_here"
PORT = int(os.environ.get("PORT", 10000))


# --- بخش مدیریت دیتابیس (Database) ---
class Database:
    def __init__(self, db_file):
        try:
            self.conn = sqlite3.connect(db_file, check_same_thread=False)
            self.cursor = self.conn.cursor()
            self.create_tables()
        except Exception as e:
            logger.error(f"Database Connection Error: {e}")

    def create_tables(self):
        self.cursor.execute(
            "CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, name TEXT, phone TEXT, city TEXT, experience TEXT, job TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)"
        )
        self.conn.commit()

    def add_user(self, user_id, name=""):
        try:
            self.cursor.execute("INSERT OR IGNORE INTO users (user_id, name) VALUES (?, ?)", (user_id, name))
            self.conn.commit()
        except Exception as e:
            logger.error(f"DB Add User Error: {e}")

    def save_user_details(self, user_id, name, phone, city, job, exp):
        try:
            self.cursor.execute(
                "UPDATE users SET name=?, phone=?, city=?, experience=?, job=? WHERE user_id=?",
                (name, phone, city, exp, job, user_id),
            )
            self.conn.commit()
        except Exception as e:
            logger.error(f"DB Save Error: {e}")

    def get_all_users(self):
        self.cursor.execute("SELECT user_id FROM users")
        return [row[0] for row in self.cursor.fetchall()]

    def get_total_users(self):
        self.cursor.execute("SELECT COUNT(*) FROM users")
        return self.cursor.fetchone()[0]

    def get_new_users_today(self):
        today = datetime.now().strftime('%Y-%m-%d')
        self.cursor.execute("SELECT COUNT(*) FROM users WHERE created_at LIKE ?", (f"{today}%",))
        return self.cursor.fetchone()[0]


db = Database(DB_PATH)
user_states = {}
user_data = {}
user_timers = {}


# --- توابع کمکی برای ارسال پیام به بله ---
async def send_message(session, chat_id, text, reply_markup=None):
    url = f"{BALE_API_URL}/sendMessage"
    payload = {"chat_id": chat_id, "text": text}
    if reply_markup:
        payload["reply_markup"] = reply_markup
    try:
        async with session.post(url, json=payload) as resp:
            return await resp.json()
    except Exception as e:
        logger.error(f"Request Error (sendMessage): {e}")


async def send_photo(session, chat_id, file_id, caption=""):
    url = f"{BALE_API_URL}/sendPhoto"
    payload = {"chat_id": chat_id, "photo": file_id, "caption": caption}
    try:
        async with session.post(url, json=payload) as resp:
            return await resp.json()
    except Exception as e:
        logger.error(f"Request Error (sendPhoto): {e}")


# --- تعریف کیبوردها ---
def get_main_menu():
    return {"keyboard": [[{"text": "📋 ثبت درخواست"}]], "resize_keyboard": True}


def get_exp_keyboard():
    return {"keyboard": [[{"text": "✅ بله، دارم"}, {"text": "❌ خیر، ندارم"}]], "resize_keyboard": True}


def get_admin_menu():
    return {"keyboard": [[{"text": "📢 ارسال پیام گروهی"}, {"text": "👥 لیست کاربران"}]], "resize_keyboard": True}


def get_inline_approval(user_id):
    return {"inline_keyboard": [[{"text": "✅ تایید", "callback_data": f"app_{user_id}"}, {"text": "❌ رد", "callback_data": f"rej_{user_id}"}]]}


# --- تسک‌های زمان‌بندی شده ---
async def send_abandoned_lead_alert(session, chat_id, delay=300):
    try:
        await asyncio.sleep(delay)
        if chat_id in user_data and user_states.get(chat_id) not in ["W_RECEIPT", None]:
            data = user_data[chat_id]
            msg = f"⚠️ **لید رها شده!**\n\n👤 نام: {data.get('name')}\n📞 شماره: {data.get('phone')}\n🆔 آیدی: `{chat_id}`"
            await send_message(session, ADMIN_ID, msg)
    except asyncio.CancelledError:
        pass


async def daily_report(session):
    total = db.get_total_users()
    new_today = db.get_new_users_today()
    await send_message(session, ADMIN_ID, f"📊 **گزارش شبانه مدیریت**\n\n👥 کل کاربران: {total}\n✨ کاربران جدید امروز: {new_today}")


async def keep_alive():
    while True:
        try:
            async with aiohttp.ClientSession() as session:
                await session.get(f"http://127.0.0.1:{PORT}/")
        except:
            pass
        await asyncio.sleep(240)


# --- هندلر اصلی پیام‌ها ---
async def handle_update(update, session):
    if not update:
        return

    if "callback_query" in update:
        cb = update["callback_query"]
        q_data = cb["data"]
        user_id = cb["from"]["id"]
        try:
            target_user = int(q_data.split("_")[1])
            if q_data.startswith("app_"):
                await send_message(session, target_user, f"🎉 پرداخت تایید شد! خوش آمدید.\n\nلینک دسترسی شما: {FINAL_LINK}")
                await send_message(session, user_id, f"✅ کاربر {target_user} تایید شد و لینک ارسال شد.")
            elif q_data.startswith("rej_"):
                await send_message(session, target_user, "متأسفیم، پرداخت تایید نشد. لطفا مجدد رسید را بفرستید.")
                await send_message(session, user_id, f"❌ کاربر {target_user} رد شد.")
        except:
            pass
        return

    if "message" not in update:
        return

    message = update["message"]
    chat_id = message["chat"]["id"]
    user_id = message.get("from", {}).get("id")
    text = message.get("text", "")

    if not user_id:
        return

    db.add_user(user_id, message.get("from", {}).get("first_name"))

    if text == "/start":
        if chat_id in user_timers:
            user_timers[chat_id].cancel()
        user_states[chat_id] = None
        welcome_text = "سلام و خوش آمدید! 🌟\nبه آکادمی املاک «حرفه‌ای شو» خوش آمدید."
        await send_message(session, chat_id, welcome_text, get_admin_menu() if chat_id == ADMIN_ID else get_main_menu())
        return

    if text == "📋 ثبت درخواست":
        if chat_id in user_timers:
            user_timers[chat_id].cancel()
        user_states[chat_id] = "W_NAME"
        user_data[chat_id] = {}
        await send_message(session, chat_id, "👤 لطفا نام و نام خانوادگی خود را وارد کنید:")
        return

    state = user_states.get(chat_id)
    if state == "W_NAME":
        user_data.setdefault(chat_id, {})['name'] = text
        user_states[chat_id] = "W_CITY"
        await send_message(session, chat_id, "📍 شهر محل سکونت شما کجاست؟")
        return

    if state == "W_CITY":
        user_data[chat_id]['city'] = text
        user_states[chat_id] = "W_EXP"
        await send_message(session, chat_id, "💼 آیا سابقه فعالیت در املاک را دارید؟", get_exp_keyboard())
        return

    if state == "W_EXP":
        user_data[chat_id]['exp'] = text
        user_states[chat_id] = "W_JOB"
        await send_message(session, chat_id, "🛠️ شغل فعلی شما چیست؟")
        return

    if state == "W_JOB":
        user_data[chat_id]['job'] = text
        user_states[chat_id] = "W_PHONE"
        await send_message(session, chat_id, "📱 لطفا شماره تماس خود را ارسال کنید:")
        return

    if state == "W_PHONE":
        phone = message.get("contact", {}).get("phone_number", text) if "contact" in message else text
        user_data[user_id] = user_data.get(user_id, {})
        user_data[user_id]['phone'] = phone
        db.save_user_details(user_id, user_data[user_id].get('name', ''), phone, user_data[user_id].get('city', ''), user_data[user_id].get('job', ''), user_data[user_id].get('exp', ''))
        user_states[user_id] = "W_RECEIPT"
        msg_pay = f"ممنون عزیز. مشخصات ثبت شد. ✅\n\nبرای فعال‌سازی، مبلغ **۲ میلیون تومان** را به کارت زیر واریز کنید:\n\n💳 `{CARD_NUMBER}`\n\nسپس عکس رسید را ارسال کنید."
        await send_message(session, user_id, msg_pay)
        user_timers[user_id] = asyncio.create_task(send_abandoned_lead_alert(session, user_id))
        return

    if state == "W_RECEIPT" and "photo" in message:
        file_id = message["photo"][0]["file_id"]
        data = user_data.get(user_id, {})
        admin_text = f"🔔 **رسید جدید!**\n👤 {data.get('name')}\n📞 {data.get('phone')}\n🆔 `{user_id}`"
        await send_photo(session, ADMIN_ID, file_id, caption=admin_text)
        await send_message(session, ADMIN_ID, "تایید یا رد رسید:", get_inline_approval(user_id))
        await send_message(session, user_id, "رسید شما دریافت شد. منتظر تایید مدیریت باشید... ⏳")
        user_states[user_id] = None
        return

    if user_id == ADMIN_ID:
        if text == "👥 لیست کاربران":
            await send_message(session, user_id, f"تعداد کل کاربران: {db.get_total_users()}")
        elif text == "📢 ارسال پیام گروهی":
            user_states[user_id] = "W_BROADCAST"
            await send_message(session, user_id, "پیام خود را برای ارسال به همه کاربران بفرستید:")
        elif state == "W_BROADCAST":
            users = db.get_all_users()
            for uid in users:
                await send_message(session, uid, text)
                await asyncio.sleep(0.05)
            await send_message(session, user_id, "✅ پیام با موفقیت به تمام کاربران ارسال شد.")
            user_states[user_id] = None


# --- وب‌سرور برای جلوگیری از خاموش شدن در Render ---
async def handle_web(request):
    return web.Response(text="Bot is running!")


async def main():
    app = web.Application()
    app.router.add_get("/", handle_web)
    runner = web.AppRunner(app)
    await runner.setup()
    await web.TCPSite(runner, "0.0.0.0", PORT).start()

    asyncio.create_task(keep_alive())

    scheduler = AsyncIOScheduler()
    async with aiohttp.ClientSession() as session:
        # گزارش روزانه ساعت 00:00
        scheduler.add_job(lambda: daily_report(session), 'cron', hour=0, minute=0)
        scheduler.start()

        offset = 0
        while True:
            try:
                async with session.get(f"{BALE_API_URL}/getUpdates?offset={offset}&timeout=20") as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        for update in data.get("result", []):
                            await handle_update(update, session)
                            offset = update["update_id"] + 1
            except Exception as e:
                logger.error(f"Poll Error: {e}")
            await asyncio.sleep(1)


if __name__ == "__main__":
    asyncio.run(main())
