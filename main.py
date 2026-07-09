import asyncio
import logging
import os
import sqlite3
import aiohttp
from aiohttp import web

# --- CONFIGURATION ---
TOKEN = os.environ.get(
    "BOT_TOKEN", "1770530298:qdkjoE0lmqmEyOFSLdorAbr5SU-bUXyCNiY"
).strip()
CARD_NUMBER = os.environ.get("CARD_NUMBER", "5859831081169756 (بانک تجارت)")
BALE_API_URL = f"https://tapi.bale.ai/bot{TOKEN}"
DB_PATH = "/data/bot_database.db" if os.path.exists("/data") else "bot_database.db"


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
            "INSERT OR REPLACE INTO settings (key, value) VALUES ('admin_id', ?)",
            (str(admin_id),),
        )
        self.conn.commit()

    def get_admin(self):
        self.cursor.execute("SELECT value FROM settings WHERE key = 'admin_id'")
        result = self.cursor.fetchone()
        return int(result[0]) if result else None

    def save_user(self, user_id, name, phone, city, exp, job):
        self.cursor.execute(
            "INSERT OR REPLACE INTO users VALUES (?, ?, ?, ?, ?, ?)",
            (user_id, name, phone, city, exp, job),
        )
        self.conn.commit()

    def get_all_users(self):
        self.cursor.execute("SELECT user_id FROM users")
        return [row[0] for row in self.cursor.fetchall()]


db = Database(DB_PATH)
user_states = {}
user_data = {}
user_timers = {}  # ذخیره تایمرها برای مدیریت لیدهای رها شده


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
async def send_abandoned_lead_alert(session, chat_id, delay=900):
    """اگر کاربر بعد از فرستادن شماره فرم را ادامه نداد، بعد از ۱۵ دقیقه (۹۰۰ ثانیه) به ادمین پیام می‌دهد"""
    try:
        await asyncio.sleep(delay)
        admin_id = db.get_admin()
        if admin_id and chat_id in user_data:
            data = user_data[chat_id]
            # اگر فرآیند پرداخت شروع نشده باشد یعنی کاربر فرم را رها کرده است
            if user_states.get(chat_id) not in ["W_RECEIPT", None]:
                abandoned_info = (
                    f"⚠️ **لید رها شده (ثبت‌نام نیمه‌کاره)!**\n\n"
                    f"👤 نام: {data.get('name', 'نامشخص')}\n"
                    f"📍 شهر و سن: {data.get('city', 'نامشخص')}\n"
                    f"📞 شماره: {data.get('phone', 'نامشخص')}\n"
                    f"🛑 کاربر فرآیند ثبت‌نام را در این مرحله رها کرد."
                )
                await send_message(session, admin_id, abandoned_info)
    except asyncio.CancelledError:
        pass  # اگر کاربر ادامه دهد، تایمر کنسل می‌شود و این تابع کاری انجام نمی‌دهد


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

        if db.get_admin() is None:
            db.set_admin(chat_id)

        is_admin = chat_id == db.get_admin()

        if text == "/start":
            # اگر کاربر از قبل تایمری داشت، لغو شود
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

            # 🌟 شروع تایمر پس‌زمینه برای لید رها شده (مثلاً ۱۵ دقیقه = ۹۰۰ ثانیه)
            if chat_id in user_timers:
                user_timers[chat_id].cancel()
            user_timers[chat_id] = asyncio.create_task(
                send_abandoned_lead_alert(session, chat_id, delay=900)
            )

            await send_message(
                session,
                chat_id,
                "ممنون. در حال حاضر مشغول چه کاری هستید؟ (شغل فعلی خود را بنویسید) 👇",
            )
            user_states[chat_id] = "W_JOB"

        elif state == "W_JOB":
            user_data.setdefault(chat_id, {})["job"] = text
            await send_message(
                session,
                chat_id,
                "میزان تجربه کاری شما چقدر است؟ (مثلاً ۲ سال) 👇",
            )
            user_states[chat_id] = "W_EXP"

        elif state == "W_EXP":
            exp = text
            user_data.setdefault(chat_id, {})["exp"] = exp

            # 🌟 کاربر فرم را تا انتها پر کرد؛ پس تایمر لید رها شده لغو می‌شود
            if chat_id in user_timers:
                user_timers[chat_id].cancel()
                del user_timers[chat_id]

            db.save_user(
                chat_id,
                user_data[chat_id].get("name"),
                user_data[chat_id].get("phone"),
                user_data[chat_id].get("city"),
                exp,
                user_data[chat_id].get("job"),
            )

            admin_id = db.get_admin()
            if admin_id:
                full_info = (
                    f"✅ **تکمیل مشخصات کاربر (لید کامل):**\n\n"
                    f"👤 نام: {user_data[chat_id].get('name')}\n"
                    f"📍 شهر و سن: {user_data[chat_id].get('city')}\n"
                    f"📞 شماره: {user_data[chat_id].get('phone')}\n"
                    f"💼 شغل: {user_data[chat_id].get('job')}\n"
                    f"⏳ تجربه: {exp}\n"
                    f"🆔 آیدی: `{chat_id}`"
                )
                await send_message(session, admin_id, full_info)

            payment_text = (
                f"ممنون {user_data[chat_id].get('name')} عزیز. مشخصات شما با موفقیت ثبت شد. ✅\n\n"
                f"برای فعال‌سازی حساب و ورود به دوره، مبلغ **۲ میلیون تومان** پیش‌پرداخت را به شماره کارت زیر واریز کنید:\n\n"
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
            admin_id = db.get_admin()
            if admin_id:
                admin_text = (
                    f"🔔 **رسید جدید دریافت شد!**\n\n"
                    f"👤 کاربر: {data.get('name')}\n"
                    f"📞 تلفن: {data.get('phone')}\n"
                    f"📍 شهر: {data.get('city')}\n"
                    f"💼 شغل: {data.get('job')}\n"
                    f"🆔 آیدی: `{chat_id}`"
                )
                await send_message(
                    session, admin_id, admin_text, get_inline_approval(chat_id)
                )
                if file_id:
                    await send_photo(session, admin_id, file_id)
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
    port = int(os.environ.get("PORT", 10000))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()

    async with aiohttp.ClientSession() as session:
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
