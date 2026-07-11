import asyncio
# ایمپورت متغیرها و توابع مورد نیاز از فایل اصلی
import main


async def start_payment_process(session, chat_id, data):
    """این تابع بلافاصله پس از ذخیره لید در دیتابیس، از فایل اصلی صدا زده می‌شود"""
    payment_text = (
        f"ممنون {data.get('name')} عزیز. مشخصات شما با موفقیت ثبت شد. ✅\n\n"
        f"برای فعال‌سازی حساب و ورود به دوره، مبلغ ۲ میلیون تومان پیش‌پذیرش را به شماره کارت زیر واریز کنید:\n\n"
        f"💳 {main.CARD_NUMBER}\n\n"
        f"پس از واریز، لطفاً عکس رسید را همین‌جا ارسال کنید."
    )
    await main.send_message(session, chat_id, payment_text)
    main.user_states[chat_id] = "W_RECEIPT"


async def handle_receipt_submission(session, chat_id, message, data):
    """مدیریت دریافت عکس رسید از کاربر"""
    file_id = (
        message.get("photo", [{}])[0].get("file_id")
        if "photo" in message
        else None
    )
    if not file_id:
        await main.send_message(
            session,
            chat_id,
            "لطفاً حتماً عکس رسید را ارسال کنید تا مدیریت بتواند تایید کند. 👇",
        )
        return

    admin_text = (
        f"🔔 رسید جدید دریافت شد!\n\n"
        f"👤 کاربر: {data.get('name')}\n"
        f"📞 تلفن: {data.get('phone')}\n"
        f"📍 شهر: {data.get('city')}\n"
        f"🏢 سابقه املاک: {data.get('exp_pre')}\n"
        f"💼 شغل فعلی: {data.get('job')}\n"
        f"🆔 آیدی: {chat_id}"
    )
    await main.send_message(
        session, main.ADMIN_ID, admin_text, main.get_inline_approval(chat_id)
    )
    await main.send_photo(session, main.ADMIN_ID, file_id)
    await main.send_message(
        session,
        chat_id,
        "رسید شما با موفقیت ارسال شد. منتظر تایید مدیریت باشید... ⏳",
    )
    main.user_states[chat_id] = None


async def handle_admin_callback(session, from_id, data_callback):
    """مدیریت کلیک ادمین روی دکمه‌های تایید یا رد رسید"""
    if data_callback.startswith("app_"):
        target_user = int(data_callback.split("_")[1])
        msg = "جناب آقای/سرکار خانم عزیز،\nپیش‌پرداخت شما با موفقیت تایید شد. 🌟\n\nبه زودی لینک وبینار رایگان برای شما ارسال خواهد شد."
        await main.send_message(session, target_user, msg)
        await main.send_message(session, from_id, f"✅ کاربر {target_user} تایید شد.")

    elif data_callback.startswith("rej_"):
        target_user = int(data_callback.split("_")[1])
        await main.send_message(
            session,
            target_user,
            "متأسفیم، پرداخت شما تایید نشد. لطفاً مجدداً رسید را ارسال کنید.",
        )
        await main.send_message(session, from_id, f"❌ رسید کاربر {target_user} رد شد.")
