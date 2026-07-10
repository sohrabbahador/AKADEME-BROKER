import asyncio
import logging
import os
import sqlite3
from datetime import datetime
import aiohttp
from aiohttp import web

# --- CONFIGURATION ---
TOKEN = os.environ.get(
    "BOT_TOKEN", "1770530298:qdkjoE0lmqmEyOFSLdorAbr5SU-bUXyCNiY"
).strip()
CARD_NUMBER = os.environ.get("CARD_NUMBER", "5859831081169756 (بانک تجارت)")
BALE_API_URL = f"https://tapi.bale.ai/bot{TOKEN}"
DB_PATH = "/data/bot_database.db" if os.path.exists("/data") else "bot_database.db"
ADMIN_ID = 160513400  # شناسه ثابت مدیریت
PORT = int(os.environ.get("PORT", 10000))


# --- DATABASE LOGIC ---
class Database:
    def __init__(self, db_file):
        self.conn = sqlite3.connect(db_file)
        self.cursor = self.conn.cursor()
        self.create_tables()

    def create_tables(self):
        self.cursor.execute(
            "CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, name TEXT, phone TEXT, city TEXT, experience TEXT, job TEXT, created_at DATE)"
        )
        self.conn.commit()

    def save_user(self, user_id, name, phone, city, job, exp):
        today = datetime.now().strftime('%Y-%m-%d')
        self.cursor.execute(
            "INSERT OR REPLACE INTO users (user_id, name, phone, city, experience, job, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (user_id, name, phone, city, exp, job, today),
        )
        self.conn.commit()

    def register_initial_user(self, user_id):
        """ثبت کاربر به محض استارت زدن در دیتابیس"""
        today = datetime.now().strftime('%Y-%m-%d')
        self.cursor.execute(
            "INSERT OR IGNORE INTO users (user_id, created_at) VALUES (?, ?)",
            (user_id, today),
        )
        self.conn.commit()

    def get_all_users(self):
        self.cursor.execute("SELECT user_id FROM users")
        return [row[0] for row in self.cursor.fetchall()]

    def get_daily_stats(self):
        today = datetime.now().strftime('%Y-%m-%d')
        self.cursor.execute("SELECT COUNT(*) FROM users")
        total = self.cursor.fetchone()[0]
        self.cursor.execute("SELECT COUNT(*) FROM users WHERE created_at = ?", (today,))
        daily = self.cursor.fetchone()[0]
        return total, daily


db = Database(DB_PATH)
user_states = {}
user_data = {}
user_timers = {}


# --- BALE API HELPERS ---
async def send_message(session, chat_id, text, reply_markup=None):
    url = f"{BALE_API_URL}/sendMessage"
    payload = {"chat_id": chat_id, "text": text}
    if reply_markup:
        payload["reply_markup"] = reply_markup
    try:
        async with session.post(url, json=payload) as resp:
            return await resp.json()
    except Exception as e:
        print(f"Error sending message: {e}")


async def send_photo(session, chat_id, file_id):
    url = f"{BALE_API_URL}/sendPhoto"
    payload = {"chat_id": chat_id, "photo": file_id}
    try:
        async with session.post(url, json=payload) as resp:
            return await resp.json()
    except Exception as e:
        print(f"Error sending photo: {e}")


# --- TIMED LEAD DELAY FUNCTION ---
async def send_abandoned_lead_alert(session, chat_id, delay=300):
    try:
        await asyncio.sleep(delay)
        if chat_id in user_data:
            # بررسی اینکه آیا کاربر هنوز در حالت انتظار برای رسید است یا نه
            if user_states.get(chat_id) != "W_RECEIPT":
                data = user_data[chat_id]
                abandoned_info = (
                    f"⚠️ **لید رها شده (ثبت‌نام نیمه‌کاره)!**\n\n"
                    f"👤 نام: {data.get('name', 'نامشخص')}\n"
                    f"📍 شهر و سن: {data.get('city', 'نامشخص')}\n"
                    f"🏢 سابقه املاک: {data.get('exp_pre', 'نامشخص')}\n"
                    f"📞 شماره: {data.get('phone', 'نامشخص')}\n"
                    f"💼 شغل فعلی: {data.get('job', 'نامشخص')}\n\n"
                    f"🛑 کاربر فرآیند ثبت‌نام را رها کرد."
                )
                await send_message(session, ADMIN_ID, abandoned_info)
    except asyncio.CancelledError:
        pass


# --- DAILY REPORT FUNCTION ---
async def send_daily_report(session):
    while True:
        # محاسبه زمان تا ساعت ۱۲ شب
        now = datetime.now()
        tomorrow = now.replace(hour=0, minute=0, second=0, microsecond=0)
        # اگر امروز ساعت ۱۲ گذشته باشد، برای فردا تنظیم می‌شود
        # در اینجا ساده‌ترین حالت: هر ۲۴ ساعت یکبار چک می‌کند یا در ساعت خاص
        # برای دقت بیشتر، هر ساعت چک می‌کنیم اگر ساعت 00:00 بود گزارش بفرستد
        if now.hour == 0 and now.minute == 0:
            total, daily = db.get_daily_stats()
            report = (
                f"📊 **گزارش روزانه ربات**\n\n"
                f"👥 کل کاربران عضو: {total} نفر\n"
                f"🆕 ثبت‌نام‌های امروز: {daily} نفر"
            )
            await send_message(session, ADMIN_ID, report)
        await asyncio.sleep(60)


# --- ANTI SLEEP FUNCTION ---
async def keep_alive():
    await asyncio.sleep(10)
    async with aiohttp.ClientSession() as session:
        while True:
            try:
                async with session.get(f"http://127.0.0.1:{PORT}/") as resp:
                    pass
            except Exception:
                pass
            await asyncio.sleep(240)


# --- KEYBOARDS ---
def get_main_menu():
    return {"keyboard": [[{"text": "📋 ثبت درخواست"}]], "resize_keyboard": True}


def get_admin_menu():
    return {
        "keyboard": [
            [{"text": "📢 ارسال پیام گروهی"}],
            [{"text": "👥 لیست کاربران"}],
        ],
        "resize_keyboard": True,
    }


def get_contact_keyboard():
    return {
        "keyboard": [[{"text": "📱 ارسال شماره تماس", "request_contact": True}]],
        "resize_keyboard": True,
        "one_time_keyboard": True,
    }


def get_inline_approval(user_id):
    return {
        "inline_keyboard": [
            [{"text": "✅ تایید", "callback_data": f"app_{user_id}"}],
            [{"text": "❌ رد", "callback_data": f"rej_{user_id}"}],
        ]
    }


# --- MESSAGE HANDLER ---
async def handle_update(update, session):
    if "message" in update:
        message = update["message"]
        chat_id = message["chat"]["id"]
        text = message.get("text", "")
        is_admin = chat_id == ADMIN_ID

        if text == "/start":
            # عضویت کاربر در دیتابیس به محض استارت
            db.register_initial_user(chat_id)
            if chat_id in user_timers:
                user_timers[chat_id].cancel()
            user_states[chat_id] = None
            welcome = (
                f"سلام {message['from'].get('first_name', 'عزیز')} عزیز! 🌟\n"
                f"به آکادمی املاک «حرفه‌ای شو» خوش آمدید.\n\n"
                f"برای شروع مراحل پذیرش و ثبت درخواست، روی دکمه زیر کلیک کنید 👇"
            )
            await send_message(session, chat_id, welcome, get_main_menu())
            return

        if text == "📋 ثبت درخواست":
            if chat_id in user_timers:
                user_timers[chat_id].cancel()
            await send_message(
                session,
                chat_id,
                "خوشحالیم که با ما همراه شدید. 🚀\nلطفاً نام و نام خانوادگی کامل خود را وارد کنید: 👇",
            )
            user_states[chat_id] = "W_NAME"
            user_data[chat_id] = {}
            return

        state = user_states.get(chat_id)

        if state == "W_NAME":
            user_data.setdefault(chat_id, {})["name"] = text
            await send_message(
                session,
                chat_id,
                "ممنون. لطفاً سن و شهر محل سکونت خود را بنویسید:\n(مانند: ۳۰ سال - تهران) 👇",
            )
            user_states[chat_id] = "W_CITY"

        elif state == "W_CITY":
            user_data.setdefault(chat_id, {})["city"] = text
            await send_message(
                session,
                chat_id,
                "سابقه فعالیت در املاک داشته‌اید؟:\n(خیر / بله) 👇",
            )
            user_states[chat_id] = "W_EXP_PRE"

        elif state == "W_EXP_PRE":
            user_data.setdefault(chat_id, {})["exp_pre"] = text
            await send_message(
                session,
                chat_id,
                "لطفاً شماره تماس خود را ارسال کنید: 👇",
                get_contact_keyboard(),
            )
            user_states[chat_id] = "W_PHONE"

        elif state == "W_PHONE":
            phone = (
                message["contact"].get("phone_number", "")
                if "contact" in message
                else text
            )
            user_data.setdefault(chat_id, {})["phone"] = phone

            if chat_id in user_timers:
                user_timers[chat_id].cancel()
            # فعال کردن تایمر هشدار لید رها شده
            user_timers[chat_id] = asyncio.create_task(
                send_abandoned_lead_alert(session, chat_id, delay=300)
            )

            await send_message(
                session,
                chat_id,
                "ممنون. در حال حاضر مشغول چه کاری هستید? (شغل فعلی خود را بنویسید) 👇",
            )
            user_states[chat_id] = "W_JOB"

        elif state == "W_JOB":
            user_data.setdefault(chat_id, {})["job"] = text
            data = user_data.get(chat_id, {})

            if chat_id in user_timers:
                user_timers[chat_id].cancel()
                del user_timers[chat_id]

            db.save_user(
                chat_id,
                data.get("name"),
                data.get("phone"),
                data.get("city"),
                text,
                data.get("exp_pre"),
            )

            full_info = (
                f"✅ **تکمیل مشخصات کاربر (لید کامل):**\n\n"
                f"👤 نام: {data.get('name')}\n"
                f"📍 شهر و سن: {data.get('city')}\n"
                f"🏢 سابقه املاک: {data.get('exp_pre')}\n"
                f"📞 شماره: {data.get('phone')}\n"
                f"💼 شغل فعلی: {text}\n"
                f"🆔 آیدی: `{chat_id}`"
            )
            await send_message(session, ADMIN_ID, full_info)

            payment_text = (
                f"ممنون {data.get('name')} عزیز. مشخصات شما با موفقیت ثبت شد. ✅\n\n"
                f"برای فعال‌سازی حساب و ورود به دوره، مبلغ **۲ میلیون تومان** پیش‌پذیرش را به شماره کارت زیر واریز کنید:\n\n"
                f"💳 `{CARD_NUMBER}`\n\n"
                f"پس از واریز، لطفاً **عکس رسید** را همین‌جا ارسال کنید."
            )
            await send_message(session, chat_id, payment_text)
            user_states[chat_id] = "W_RECEIPT"

        elif state == "W_RECEIPT":
            file_id = (
                message.get("photo", [{}])[0].get("file_id")
                if "photo" in message
                else None
            )

            if not file_id:
                await send_message(
                    session,
                    chat_id,
                    "لطفاً حتماً عکس رسید را ارسال کنید تا مدیریت بتواند تایید کند. 👇",
                )
                return

            data = user_data.get(chat_id, {})
            admin_text = (
                f"🔔 **رسید جدید دریافت شد!**\n\n"
                f"👤 کاربر: {data.get('name')}\n"
                f"📞 تلفن: {data.get('phone')}\n"
                f"📍 شهر: {data.get('city')}\n"
                f"🏢 سابقه املاک: {data.get('exp_pre')}\n"
                f"💼 شغل فعلی: {data.get('job')}\n"
                f"🆔 آیدی: `{chat_id}`"
            )
            await send_message(
                session, ADMIN_ID, admin_text, get_inline_approval(chat_id)
            )
            if file_id:
                await send_photo(session, ADMIN_ID, file_id)
            await send_message(
                session,
                chat_id,
                "رسید شما با موفقیت ارسال شد. منتظر تایید مدیریت باشید... ⏳",
            )
            user_states[chat_id] = None

        elif state == "W_BROADCAST" and is_admin:
            users = db.get_all_users()
            count = 0
            for uid in users:
                res = await send_message(session, uid, text)
                if res and res.get("ok"):
                    count += 1
                await asyncio.sleep(0.05)
            await send_message(
                session, chat_id, f"پیام شما برای {count} کاربر ارسال شد. ✅"
            )
            user_states[chat_id] = None

        if is_admin:
            if text == "📢 ارسال پیام گروهی":
                await send_message(
                    session,
                    chat_id,
                    "پیام خود را بفرستید تا برای همه کاربران ارسال شود: 👇",
                )
                user_states[chat_id] = "W_BROADCAST"
                return
            elif text == "👥 لیست کاربران":
                users = db.get_all_users()
                await send_message(
                    session, chat_id, f"تعداد کل کاربران ثبت شده: {len(users)} نفر"
                )
                return

    elif "callback_query" in update:
        cb = update["callback_query"]
        from_id = cb["from"]["id"]
        data = cb["data"]

        if data.startswith("app_"):
            target_user = int(data.split("_")[1])
            msg = "جناب آقای/سرکار خانم عزیز،\nپیش‌پرداخت شما با موفقیت تایید شد. 🌟\n\nبه زودی لینک وبینار رایگان برای شما ارسال خواهد شد."
            await send_message(session, target_user, msg)
            await send_message(session, from_id, f"✅ کاربر {target_user} تایید شد.")
        elif data.startswith("rej_"):
            target_user = int(data.split("_")[1])
            await send_message(
                session,
                target_user,
                "متأسفیم، پرداخت شما تایید نشد. لطفاً مجدداً رسید را ارسال کنید.",
            )
            await send_message(session, from_id, f"❌ رسید کاربر {target_user} رد شد.")


async def handle(request):
    return web.Response(text="Bot is perfectly connected via Proxy!")


async def main():
    logging.basicConfig(level=logging.INFO)
    app = web.Application()
    app.router.add_get("/", handle)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", PORT)
    await site.start()

    # فعال‌سازی تسک ضد خواب سرور
    asyncio.create_task(keep_alive())

    async with aiohttp.ClientSession() as session:
        # فعال‌سازی تسک گزارش روزانه
        asyncio.create_task(send_daily_report(session))

        offset = 0
        while True:
            try:
                url = f"{BALE_API_URL}/getUpdates?offset={offset}&timeout=20"
                async with session.get(url) as resp:
                    if resp.status == 200:
                        res_json = await resp.json()
                        if res_json.get("ok"):
                            for update in res_json.get("result", []):
                                await handle_update(update, session)
                                offset = update["update_id"] + 1
            except Exception as e:
                print(f"Polling error: {e}")
            await asyncio.sleep(1)


if __name__ == "__main__":
    asyncio.run(main())
