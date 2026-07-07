import os
import logging
import asyncio
import sqlite3
import aiohttp
from aiohttp import web

# --- CONFIGURATION ---
TOKEN = "296563931:ZIhjuPVuDCxzIalxOC6Bm6JWRqktZGQrpUA"
CARD_NUMBER = os.environ.get("CARD_NUMBER", "5859831081169756 (بانک تجارت)")
BALE_API_URL = f"https://api.bale.ai/bot{TOKEN}"
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
        self.cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('admin_id', ?)", (str(admin_id),))
        self.conn.commit()

    def get_admin(self):
        self.cursor.execute("SELECT value FROM settings WHERE key = 'admin_id'")
        result = self.cursor.fetchone()
        return int(result[0]) if result else None

    def save_user(self, user_id, name, phone, city, exp, job):
        self.cursor.execute("INSERT OR REPLACE INTO users VALUES (?, ?, ?, ?, ?, ?)", (user_id, name, phone, city, exp, job))
        self.conn.commit()

    def get_all_users(self):
        self.cursor.execute("SELECT user_id FROM users")
        return [row[0] for row in self.cursor.fetchall()]

db = Database(DB_PATH)
user_states = {}
user_data = {}

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

# --- KEYBOARDS ---
def get_main_menu():
    return {"keyboard": [[{"text": "📋 ثبت درخواست"}]], "resize_keyboard": True}

def get_admin_menu():
    return {"keyboard": [[{"text": "📢 ارسال پیام گروهی"}], [{"text": "👥 لیست کاربران"}]], "resize_keyboard": True}

def get_inline_approval(user_id):
    return {
        "inline_keyboard": [
            [{"text": "✅ تایید", "callback_data": f"app_{user_id}"}],
            [{"text": "❌ رد", "callback_data": f"rej_{user_id}"}]
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
            
        is_admin = (chat_id == db.get_admin())
        current_menu = get_admin_menu() if is_admin else get_main_menu()

        # Command /start
        if text == "/start":
            user_states[chat_id] = None
            welcome = (
                f"سلام {message['from'].get('first_name', 'عزیز')} عزیز! 🌟\n"
                f"به تیم آموزش و جذب 'سهراب بهادر' خوش آمدید.\n\n"
                f"ما اینجا هستیم تا شما را در مسیر موفقیت در دنیای بروکرینگ راهنمایی کنیم.\n\n"
                f"🎁 **وبینار رایگان:** برای آشنایی با متد ما و شنیدن پیش‌گفتار آموزش، می‌توانید در وبینار رایگان ما شرکت کنید. (لینک پس از ثبت اولیه ارسال می‌شود).\n\n"
                f"برای شروع مراحل پذیرش، روی دکمه زیر کلیک کنید 👇"
            )
            await send_message(session, chat_id, welcome, current_menu)
            return

        state = user_states.get(chat_id)

        # Main Menu Clicks
        if text == "📋 ثبت درخواست":
            await send_message(session, chat_id, "لطفاً نام و نام خانوادگی خود را وارد کنید: 👇")
            user_states[chat_id] = "W_NAME"
            user_data[chat_id] = {}
            return
            
        elif text == "📢 ارسال پیام گروهی" and is_admin:
            await send_message(session, chat_id, "پیام خود (مثلاً لینک وبینار) را بفرستید تا برای همه ارسال شود: 👇")
            user_states[chat_id] = "W_BROADCAST"
            return
            
        elif text == "👥 لیست کاربران" and is_admin:
            users = db.get_all_users()
            await send_message(session, chat_id, f"تعداد کاربران ثبت شده: {len(users)} نفر")
            return

        # FSM Steps
        if state == "W_NAME":
            user_data[chat_id]["name"] = text
            await send_message(session, chat_id, "لطفاً سن و شهر محل سکونت خود را بنویسید: 👇")
            user_states[chat_id] = "W_CITY"
        elif state == "W_CITY":
            user_data[chat_id]["city"] = text
            await send_message(session, chat_id, "سابقه فعالیت شما در زمینه بروکرینگ یا املاک چقدر است؟ 👇")
            user_states[chat_id] = "W_EXP"
        elif state == "W_EXP":
            user_data[chat_id]["exp"] = text
            await send_message(session, chat_id, "لطفاً شماره تماس خود را وارد کنید: 👇")
            user_states[chat_id] = "W_PHONE"
        elif state == "W_PHONE":
            user_data[chat_id]["phone"] = text
            await send_message(session, chat_id, "در حال حاضر مشغول چه کاری هستید؟ (شغل فعلی) 👇")
            user_states[chat_id] = "W_JOB"
        elif state == "W_JOB":
            user_data[chat_id]["job"] = text
            payment_text = (
                f"ممنون {user_data[chat_id].get('name')} عزیز. مشخصات شما ثبت شد. ✅\n\n"
                f"برای فعال‌سازی حساب و دریافت دسترسی به وبینار رایگان، مبلغ **۲ میلیون تومان** پیش‌پرداخت را به شماره کارت زیر واریز کنید:\n\n"
                f"💳 `{CARD_NUMBER}`\n\n"
                f"پس از واریز، لطفاً **عکس رسید** را همین‌جا ارسال کنید تا توسط مدیریت تایید شود."
            )
            await send_message(session, chat_id, payment_text)
            user_states[chat_id] = "W_RECEIPT"
        elif state == "W_RECEIPT":
            file_id = None
            if "photo" in message:
                file_id = message["photo"][-1]["file_id"]
            
            data = user_data.get(chat_id, {})
            db.save_user(chat_id, data.get("name"), data.get("phone"), data.get("city"), data.get("exp"), data.get("job"))
            
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
                await send_message(session, admin_id, admin_text, get_inline_approval(chat_id))
                if file_id:
                    await send_photo(session, admin_id, file_id)
                await send_message(session, chat_id, "رسید شما ارسال شد. منتظر تایید مدیریت باشید... ⏳")
                user_states[chat_id] = None
            else:
                await send_message(session, chat_id, "خطا: ادمین مشخص نیست.")
                
        elif state == "W_BROADCAST" and is_admin:
            users = db.get_all_users()
            count = 0
            for uid in users:
                res = await send_message(session, uid, text)
                if res and res.get("ok"): count += 1
                await asyncio.sleep(0.05)
            await send_message(session, chat_id, f"پیام شما برای {count} کاربر ارسال شد. ✅")
            user_states[chat_id] = None

    elif "callback_query" in update:
        cb = update["callback_query"]
        from_id = cb["from"]["id"]
        data = cb["data"]
        
        if data.startswith("app_"):
            target_user = int(data.split("_")[1])
            msg = ("جناب آقای/سرکار خانم عزیز،\nپیش‌پرداخت شما با موفقیت تایید شد. 🌟\n\n"
                   "مشخصات شما در دست بررسی کارشناسان است. به زودی نتیجه پذیرش و لینک وبینار رایگان برای شما ارسال خواهد شد.\n\n"
                   "سپاس از اعتماد شما.")
            await send_message(session, target_user, msg)
            await send_message(session, from_id, f"✅ کاربر {target_user} تایید شد.")
        elif data.startswith("rej_"):
            target_user = int(data.split("_")[1])
            await send_message(session, target_user, "متأسفیم، پرداخت شما تایید نشد. لطفاً مجدداً رسید را ارسال کنید.")
            await send_message(session, from_id, f"❌ رسید کاربر {target_user} رد شد.")

# --- RENDER WEB SERVER ---
async def handle(request):
    return web.Response(text="Bot is running completely fine!")

# --- MAIN POLLING LOOP ---
async def main():
    logging.basicConfig(level=logging.INFO)
    
    # راه اندازی وب سرور رندر برای هماهنگی با پورت سرور
    app = web.Application()
    app.router.add_get('/', handle)
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.environ.get("PORT", 10000))
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()
    print(f"Render Web Server active on port {port}")

    # دریافت مستقیم پیام‌ها از سرور بله بدون ارسال دستورات ناسازگار
    async with aiohttp.ClientSession() as session:
        offset = 0
        print("Direct polling started on Bale Server...")
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
                print(f"Polling warning: {e}")
            await asyncio.sleep(1)

if __name__ == "__main__":
    asyncio.run(main())
