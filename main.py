import logging
from datetime import datetime, timedelta, time as dtime
import pytz

from telegram import (
    Update, ReplyKeyboardMarkup, ReplyKeyboardRemove,
    KeyboardButton, BotCommand
)
from telegram.ext import (
    Updater, CommandHandler, MessageHandler,
    Filters, CallbackContext, ConversationHandler
)

from database import (
    init_db, add_booking, get_booked_times,
    get_future_user_bookings, cancel_booking,
    get_pending_reminders, mark_as_reminded
)
from config import BOT_TOKEN, ADMINS

# -------------------- CONFIG --------------------
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TZ = pytz.timezone("Asia/Tashkent")

BARBERS = ["Jamshed"]
SERVICES = ["Klassik soch olish", "Fade", "Ukladka", "Soch + Soqol"]

WORK_START = dtime(9, 0)
WORK_END = dtime(21, 0)
SLOT_MINUTES = 30

ASK_NAME, ASK_PHONE, ASK_SERVICE, ASK_BARBER, ASK_DATE, ASK_TIME, CONFIRM = range(7)
CANCEL_ID = range(1)

# -------------------- START --------------------
def start(update: Update, context: CallbackContext):
    update.message.reply_text(
        "Assalomu alaykum!\n"
        "Bron qilish uchun /book\n"
        "Bronlaringizni ko‘rish uchun /mybookings"
    )

# -------------------- BOOK FLOW --------------------
def book_start(update: Update, context: CallbackContext):
    update.message.reply_text("Ismingizni kiriting:")
    return ASK_NAME


def ask_name(update: Update, context: CallbackContext):
    context.user_data["name"] = update.message.text
    btn = KeyboardButton("📱 Raqamni yuborish", request_contact=True)
    update.message.reply_text(
        "Telefon raqamingiz:",
        reply_markup=ReplyKeyboardMarkup([[btn]], resize_keyboard=True)
    )
    return ASK_PHONE


def ask_phone(update: Update, context: CallbackContext):
    phone = update.message.contact.phone_number if update.message.contact else update.message.text
    context.user_data["phone"] = phone
    update.message.reply_text(
        "Xizmatni tanlang:",
        reply_markup=ReplyKeyboardMarkup([[s] for s in SERVICES], resize_keyboard=True)
    )
    return ASK_SERVICE


def ask_service(update: Update, context: CallbackContext):
    context.user_data["service"] = update.message.text
    update.message.reply_text(
        "Barberni tanlang:",
        reply_markup=ReplyKeyboardMarkup([[b] for b in BARBERS], resize_keyboard=True)
    )
    return ASK_BARBER


def ask_barber(update: Update, context: CallbackContext):
    context.user_data["barber"] = update.message.text

    today = datetime.now(TZ).date()
    buttons, date_map = [], {}

    for i in range(7):
        day = today + timedelta(days=i)
        label = day.strftime("%d %b (%a)")
        buttons.append([label])
        date_map[label] = day.isoformat()

    context.user_data["date_map"] = date_map
    update.message.reply_text(
        "Sanani tanlang:",
        reply_markup=ReplyKeyboardMarkup(buttons, resize_keyboard=True)
    )
    return ASK_DATE


def ask_date(update: Update, context: CallbackContext):
    date_iso = context.user_data["date_map"].get(update.message.text)
    if not date_iso:
        update.message.reply_text("Iltimos tugmadan tanlang.")
        return ASK_DATE

    context.user_data["date"] = date_iso
    barber = context.user_data["barber"]
    booked = get_booked_times(barber, date_iso)

    now = datetime.now(TZ)
    cur = TZ.localize(datetime.combine(datetime.fromisoformat(date_iso), WORK_START))
    end = TZ.localize(datetime.combine(datetime.fromisoformat(date_iso), WORK_END))

    slots = []
    while cur <= end:
        t = cur.strftime("%H:%M")
        if cur > now + timedelta(minutes=30) and t not in booked:
            slots.append([t])
        cur += timedelta(minutes=SLOT_MINUTES)

    if not slots:
        update.message.reply_text("Bo‘sh vaqt yo‘q.")
        return ASK_DATE

    update.message.reply_text(
        "Vaqtni tanlang:",
        reply_markup=ReplyKeyboardMarkup(slots, resize_keyboard=True)
    )
    return ASK_TIME


def ask_time(update: Update, context: CallbackContext):
    context.user_data["time"] = update.message.text
    d = context.user_data
    update.message.reply_text(
        f"Joyingiz band qilindi:\n\n"
        f"👤 Ism:  {d['name']}\n"
        f"📞 Tel: {d['phone']}\n"
        f"🛠 Xizmat: {d['service']}\n"
        f"💈 Barber: {d['barber']}\n"
        f"📅 Sana: {d['date']}\n"
        f"⏰ Vaqt: {d['time']}\n\n"
        "Tasdiqlaysizmi? (yo'q/ha)",
        reply_markup=ReplyKeyboardMarkup([["yo'q", "ha"]], resize_keyboard=True)
    )
    return CONFIRM


def finish(update: Update, context: CallbackContext):
    if update.message.text.lower() != "ha":
        update.message.reply_text("Bekor qilindi.", reply_markup=ReplyKeyboardRemove())
        return ConversationHandler.END

    d = context.user_data
    user_id = update.message.from_user.id

    add_booking(
        d["name"], d["phone"], d["service"],
        d["barber"], d["date"], d["time"],
        user_id
    )

    # Adminga xabar
    admin_msg = (f"📥 *Yangi Mijoz!*\n\n"
                 f"👤 Ism: *{d['name']}*\n"
                 f"📞 Tel: *{d['phone']}*\n"
                 f"🛠 Xizmat: *{d['service']}*\n"
                 f"💈 Barber: *{d['barber']}*\n"
                 f"📅 Sana: *{d['date']}*\n"
                 f"⏰ Vaqt: *{d['time']}*")

    for admin in ADMINS:
        try:
            context.bot.send_message(chat_id=admin, text=admin_msg, parse_mode="Markdown")
        except Exception:
            logger.exception(f"Admin notify failed for {admin}")

    update.message.reply_text("✅ Joyingiz bron qilindi", reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END



# -------------------- MY BOOKINGS --------------------
def my_bookings(update: Update, context: CallbackContext):
    now = datetime.now(TZ)
    rows = get_future_user_bookings(update.message.from_user.id)

    text = ""
    for r in rows:
        dt = TZ.localize(datetime.strptime(f"{r[3]} {r[4]}", "%Y-%m-%d %H:%M"))
        if dt > now:
            text += f"🆔 {r[0]} | {r[1]} | {r[3]} | {r[4]}\n"

    update.message.reply_text(text or "sizda bronlar yo‘q.")


# -------------------- CANCEL --------------------
def cancel_start(update: Update, context: CallbackContext):
    now = datetime.now(TZ)
    rows = get_future_user_bookings(update.message.from_user.id)

    future = []
    for r in rows:
        dt = TZ.localize(datetime.strptime(f"{r[3]} {r[4]}", "%Y-%m-%d %H:%M"))
        if dt > now:
            future.append(r)

    if not future:
        update.message.reply_text("❌ Sizda bekor qilinadigan bron yo‘q.")
        return ConversationHandler.END

    text = "Bekor qilmoqchi bo‘lgan bron ID sini yuboring:\n\n"
    for r in future:
        text += f"🆔 {r[0]} | {r[1]} | {r[3]} {r[4]}\n"

    update.message.reply_text(text)
    return 0



def cancel_confirm(update: Update, context: CallbackContext):
    booking_id = update.message.text
    now = datetime.now(TZ)

    rows = get_future_user_bookings(update.message.from_user.id)
    for r in rows:
        if str(r[0]) == booking_id:
            dt = TZ.localize(datetime.strptime(f"{r[3]} {r[4]}", "%Y-%m-%d %H:%M"))
            if dt - now < timedelta(hours=1):
                update.message.reply_text("❌ 1 soatdan kam qoldi.")
                return ConversationHandler.END
            cancel_booking(booking_id)
            update.message.reply_text("✅ Bekor qilindi.")
            return ConversationHandler.END

    update.message.reply_text("Bron topilmadi.")
    return ConversationHandler.END


def check_reminders(context: CallbackContext):
    now = datetime.now(TZ)
    bookings = get_pending_reminders()
    for b in bookings:
        booking_dt = TZ.localize(datetime.strptime(f"{b['date']} {b['time']}", "%Y-%m-%d %H:%M"))
        diff = booking_dt - now
        if 0 < diff.total_seconds() <= 1800:  # 30 min ichida
            mark_as_reminded(b["id"])
            # Mijozga
            try:
                context.bot.send_message(chat_id=b["telegram_id"], text=f"📢 *Eslatma!*\n\nSiz bugun soat *{b['time']}* da sartaroshxonamizga yozilgansiz.", parse_mode="Markdown")
            except Exception:
                logger.exception("Customer reminder failed")
            # Adminga
            admin_text = (f"⚠️ *30 daqiqadan keyin mijoz keladi!*\n\n"
                          f"👤 Ism: *{b['name']}*\n"
                          f"📞 Tel: *{b['phone']}*\n"
                          f"🛠 Xizmat: *{b['service']}*\n"
                          f"💈 Sartarosh: *{b['barber']}*\n"
                          f"📅 Sana: *{b['date']}*\n"
                          f"⏰ Vaqt: *{b['time']}*")
            for admin in ADMINS:
                try:
                    context.bot.send_message(chat_id=admin, text=admin_text, parse_mode="Markdown")
                except Exception:
                    logger.exception(f"Admin reminder failed for {admin}")

def numbers(update: Update, context: CallbackContext):
    update.message.reply_text("Admin bilan bog‘lanish: https://t.me/Death0201") 
    
def developer(update: Update, context: CallbackContext):
    update.message.reply_text("Bot developer: https://t.me/ergashev_dev")
# -------------------- MAIN --------------------
def main():
    init_db()
    updater = Updater(BOT_TOKEN)
    dp = updater.dispatcher

    book_conv = ConversationHandler(
        entry_points=[CommandHandler("book", book_start)],
        states={
            ASK_NAME: [MessageHandler(Filters.text, ask_name)],
            ASK_PHONE: [MessageHandler(Filters.text | Filters.contact, ask_phone)],
            ASK_SERVICE: [MessageHandler(Filters.text, ask_service)],
            ASK_BARBER: [MessageHandler(Filters.text, ask_barber)],
            ASK_DATE: [MessageHandler(Filters.text, ask_date)],
            ASK_TIME: [MessageHandler(Filters.text, ask_time)],
            CONFIRM: [MessageHandler(Filters.text, finish)],
        },
        fallbacks=[]
    )

    cancel_conv = ConversationHandler(
        entry_points=[CommandHandler("cancelbooking", cancel_start)],
        states={0: [MessageHandler(Filters.text, cancel_confirm)]},
        fallbacks=[]
    )

    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(CommandHandler("mybookings", my_bookings))
    dp.add_handler(book_conv)
    dp.add_handler(cancel_conv)
    dp.add_handler(CommandHandler("numbers", numbers))
    dp.add_handler(CommandHandler("developer", developer))

    updater.job_queue.run_repeating(check_reminders, 60, first=10)
    updater.start_polling()
    updater.idle()


if __name__ == "__main__":
    main()
