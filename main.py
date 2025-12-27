import logging
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove, KeyboardButton, BotCommand
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, CallbackContext, ConversationHandler
from datetime import datetime, timedelta, time as dtime
from database import init_db, add_client, get_bookings_for, get_pending_reminders, mark_as_reminded, cancel_booking, conn
from config import BOT_TOKEN, ADMINS
import pytz

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# States
ASK_NAME, ASK_PHONE, ASK_SERVICE, ASK_BARBER, ASK_DATE, ASK_TIME, CONFIRM = range(7)

# Data
BARBERS = ["Jamshed"]
SERVICES = ["Klassik soch olish", "Fade", "Ukladka", "Soch + Soqol"]

WORK_START = dtime(hour=9, minute=0)
WORK_END = dtime(hour=21, minute=0)
SLOT_MINUTES = 30

TZ = pytz.timezone('Asia/Tashkent')

# -------------------- START --------------------
def start(update: Update, context: CallbackContext):
    update.message.reply_text(
        "Assalomu alaykum! Sartaroshxonamizga xush kelibsiz.\n"
        "joyingizni bron qilish uchun /book tugmasini bosing."
    )

# -------------------- BOOK --------------------
def book_start(update: Update, context: CallbackContext):
    update.message.reply_text("Ismingizni yozing:", reply_markup=ReplyKeyboardRemove())
    return ASK_NAME

def ask_name(update: Update, context: CallbackContext):
    context.user_data['name'] = update.message.text.strip()
    contact_btn = KeyboardButton("📱 Raqamni yuborish", request_contact=True)
    markup = ReplyKeyboardMarkup([[contact_btn]], resize_keyboard=True, one_time_keyboard=True)
    update.message.reply_text("Telefon raqamingizni yuboring (+998) yoki pastdagi tugmadan foydalaning:", reply_markup=markup)
    return ASK_PHONE

def ask_phone(update: Update, context: CallbackContext):
    if update.message.contact:
        phone = update.message.contact.phone_number
    else:
        phone = update.message.text.strip()
    context.user_data['phone'] = phone
    markup = ReplyKeyboardMarkup([[s] for s in SERVICES], one_time_keyboard=True, resize_keyboard=True)
    update.message.reply_text("Qaysi xizmatni xohlaysiz?", reply_markup=markup)
    return ASK_SERVICE

def ask_service(update: Update, context: CallbackContext):
    context.user_data['service'] = update.message.text.strip()
    markup = ReplyKeyboardMarkup([[b] for b in BARBERS], one_time_keyboard=True, resize_keyboard=True)
    update.message.reply_text("Barberni tanlang", reply_markup=markup)
    return ASK_BARBER

def ask_barber(update: Update, context: CallbackContext):
    context.user_data['barber'] = update.message.text.strip()
    today = datetime.now(TZ).date()
    now_time = datetime.now(TZ).time()
    buttons, date_map = [], {}
    for i in range(7):
        day = today + timedelta(days=i)
        if i == 0 and now_time >= WORK_END:
            continue
        label = day.strftime("%d %b (%a)")
        buttons.append([label])
        date_map[label] = day.isoformat()
    markup = ReplyKeyboardMarkup(buttons, one_time_keyboard=True, resize_keyboard=True)
    update.message.reply_text("Sana tanlang:", reply_markup=markup)
    context.user_data['date_map'] = date_map
    return ASK_DATE

def ask_date(update: Update, context: CallbackContext):
    sel = update.message.text.strip()
    date_map = context.user_data.get('date_map', {})
    date_iso = date_map.get(sel)
    if not date_iso:
        update.message.reply_text("Iltimos, tugmalardan birini tanlang.")
        return ASK_DATE
    context.user_data['date'] = date_iso
    barber = context.user_data['barber']
    booked = get_bookings_for(barber, date_iso)
    slots, now_dt = [], datetime.now(TZ)
    cur_dt = TZ.localize(datetime.combine(datetime.fromisoformat(date_iso), WORK_START))
    end_dt = TZ.localize(datetime.combine(datetime.fromisoformat(date_iso), WORK_END))
    while cur_dt <= end_dt:
        slot_str = cur_dt.strftime("%H:%M")
        if cur_dt > now_dt + timedelta(minutes=29) and slot_str not in booked:
            slots.append([slot_str])
        cur_dt += timedelta(minutes=SLOT_MINUTES)
    if not slots:
        update.message.reply_text("Kechirasiz, tanlangan kunda bo‘sh vaqtlar yo‘q. Boshqa kunni tanlab ko‘ring.", reply_markup=ReplyKeyboardRemove())
        return ASK_DATE
    markup = ReplyKeyboardMarkup(slots, one_time_keyboard=True, resize_keyboard=True)
    update.message.reply_text("Vaqtni tanlang:", reply_markup=markup)
    return ASK_TIME

def ask_time(update: Update, context: CallbackContext):
    context.user_data['time'] = update.message.text.strip()
    data = context.user_data
    msg = (f"Joyingiz band qilindi:\n\n"
           f"👤 Ism: {data['name']}\n"
           f"📞 Tel: {data['phone']}\n"
           f"🛠 Xizmat: {data['service']}\n"
           f"💈 Barber: {data['barber']}\n"
           f"📅 Sana: {data['date']}\n"
           f"⏰ Vaqt: {data['time']}\n\n"
           "Tasdiqlaysizmi? (yo'q/ha)")
    update.message.reply_text(msg, reply_markup=ReplyKeyboardMarkup([["yo'q", "ha"]], one_time_keyboard=True, resize_keyboard=True))
    return CONFIRM

def finish(update: Update, context: CallbackContext):
    text = update.message.text.strip().lower()
    data = context.user_data
    user_id = update.message.from_user.id
    if text == 'ha':
        booked = get_bookings_for(data['barber'], data['date'])
        if data['time'] in booked:
            update.message.reply_text("Afsuski, bu vaqt band. Iltimos boshqa vaqtni tanlang /start.", reply_markup=ReplyKeyboardRemove())
            return ASK_DATE
        add_client(data['name'], data['phone'], data['service'], data['barber'], data['date'], data['time'], user_id)
        # Admin notify
        admin_msg = (f"📥 *Yangi Mijoz!*\n\n"
                     f"👤 Ism: *{data['name']}*\n"
                     f"📞 Tel: *{data['phone']}*\n"
                     f"🛠 Xizmat: *{data['service']}*\n"
                     f"💈 Sartarosh: *{data['barber']}*\n"
                     f"📅 Sana: *{data['date']}*\n"
                     f"⏰ Vaqt: *{data['time']}*")
        for admin in ADMINS:
            try:
                context.bot.send_message(chat_id=admin, text=admin_msg, parse_mode="Markdown")
            except Exception:
                logger.exception("Admin notify failed")
        update.message.reply_text("Rahmat! Sizning joyingiz band qilindi. Vaqtingizni eslab qo‘ying 😊", reply_markup=ReplyKeyboardRemove())
        return ConversationHandler.END
    else:
        update.message.reply_text("Buyurtma bekor qilindi.", reply_markup=ReplyKeyboardRemove())
        return ConversationHandler.END

def cancel(update: Update, context: CallbackContext):
    update.message.reply_text("Bekor qilindi.", reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END

# -------------------- REMINDERS --------------------
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

# -------------------- USER CANCEL COMMAND --------------------
def my_bookings(update: Update, context: CallbackContext):
    now = datetime.now(TZ)
    rows = get_future_user_bookings(update.message.from_user.id, now)

    if not rows:
        update.message.reply_text("Sizda kelajakdagi bronlar yo‘q.")
        return

    msg = "📋 *Sizning bronlaringiz:*\n\n"
    for r in rows:
        msg += (
            f"🆔 ID: {r[0]}\n"
            f"🛠 Xizmat: {r[1]}\n"
            f"💈 Barber: {r[2]}\n"
            f"📅 Sana: {r[3]}\n"
            f"⏰ Vaqt: {r[4]}\n\n"
        )

    update.message.reply_text(msg, parse_mode="Markdown")

def cancelbooking_start(update: Update, context: CallbackContext):
    update.message.reply_text("Bekor qilmoqchi bo‘lgan bron ID sini yuboring:")
    return 1


def cancelbooking_confirm(update: Update, context: CallbackContext):
    booking_id = update.message.text.strip()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT date, time FROM bookings
        WHERE id=? AND telegram_id=? AND status='active'
    """, (booking_id, update.message.from_user.id))

    row = cursor.fetchone()
    if not row:
        update.message.reply_text("Bunday aktiv bron topilmadi.")
        return ConversationHandler.END

    booking_dt = TZ.localize(datetime.strptime(f"{row[0]} {row[1]}", "%Y-%m-%d %H:%M"))
    now = datetime.now(TZ)

    if booking_dt - now < timedelta(hours=1):
        update.message.reply_text("❌ 1 soatdan kam vaqt qolgani uchun bekor qilib bo‘lmaydi.")
        return ConversationHandler.END

    cancel_booking(booking_id)
    update.message.reply_text("✅ Bron muvaffaqiyatli bekor qilindi.")
    return ConversationHandler.END


# -------------------- OTHER --------------------
def numbers(update: Update, context: CallbackContext):
    update.message.reply_text("Admin bilan bog‘lanish: https://t.me/Death0201")

def developer(update: Update, context: CallbackContext):
    update.message.reply_text("Bot developer: https://t.me/ergashev_dev")

# -------------------- MAIN --------------------
def main():
    # 1. DB init
    init_db()

    # 2. Botni ishga tushiramiz
    updater = Updater(BOT_TOKEN)
    dp = updater.dispatcher

    # 3. Conversation (BOOK)
    conv = ConversationHandler(
        entry_points=[CommandHandler("book", book_start)],
        states={
            ASK_NAME: [MessageHandler(Filters.text & ~Filters.command, ask_name)],
            ASK_PHONE: [MessageHandler(Filters.text | Filters.contact, ask_phone)],
            ASK_SERVICE: [MessageHandler(Filters.text & ~Filters.command, ask_service)],
            ASK_BARBER: [MessageHandler(Filters.text & ~Filters.command, ask_barber)],
            ASK_DATE: [MessageHandler(Filters.text & ~Filters.command, ask_date)],
            ASK_TIME: [MessageHandler(Filters.text & ~Filters.command, ask_time)],
            CONFIRM: [MessageHandler(Filters.text & ~Filters.command, finish)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        allow_reentry=True
    )

    # 4. ❗ ODDIY COMMAND HANDLERLAR (MUHIM QISM)
    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(CommandHandler("mybookings", my_bookings))
    dp.add_handler(CommandHandler("cancelbooking", cancel_my_booking))
    dp.add_handler(CommandHandler("numbers", numbers))
    dp.add_handler(CommandHandler("developer", developer))

    # 5. Conversation handler ENG OXIRIDA
    dp.add_handler(conv)

    # 6. Bot komandalarini menyuga chiqarish
    updater.bot.set_my_commands([
        BotCommand("start", "Botni ishga tushirish"),
        BotCommand("book", "Bron qilish"),
        BotCommand("mybookings", "Mening bronlarim"),
        BotCommand("cancelbooking", "Bronni bekor qilish"),
        BotCommand("numbers", "Kontaktlar"),
        BotCommand("developer", "Developer profili")
    ])

    # 7. Reminder job
    updater.job_queue.run_repeating(
        check_reminders,
        interval=60,
        first=10
    )

    # 8. Botni ishga tushiramiz
    updater.start_polling()
    logger.info("Bot started")
    updater.idle()


if __name__ == "__main__":
    main()
