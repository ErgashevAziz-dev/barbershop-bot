import logging
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove, KeyboardButton, BotCommand
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, CallbackContext, ConversationHandler
from datetime import datetime, timedelta, time as dtime
from database import init_db, add_client, get_bookings_for, get_pending_reminders, mark_as_reminded
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
BARBERS = ["Jamshed", "Zarshed"]
SERVICES = ["Klassik soch olish", "Fade", "Ukladka", "Soch + Soqol"]

WORK_START = dtime(hour=9, minute=0)
WORK_END = dtime(hour=21, minute=0)
SLOT_MINUTES = 30

# Timezone
TZ = pytz.timezone('Asia/Tashkent')


# START
def start(update: Update, context: CallbackContext):
    update.message.reply_text(
        "Assalomu alaykum! Sartaroshxonamizga xush kelibsiz.\n"
        "Buyurtma berish uchun /book tugmasini bosing."
    )


# BOOK START
def book_start(update: Update, context: CallbackContext):
    update.message.reply_text(
        "Ismingizni yozing:", reply_markup=ReplyKeyboardRemove()
    )
    return ASK_NAME


# ASK NAME
def ask_name(update: Update, context: CallbackContext):
    context.user_data['name'] = update.message.text.strip()

    # Telefonni so'raymiz
    contact_btn = KeyboardButton("📱 Raqamni yuborish", request_contact=True)
    markup = ReplyKeyboardMarkup([[contact_btn]], resize_keyboard=True, one_time_keyboard=True)
    update.message.reply_text(
        "Telefon raqamingizni yuboring (+998) yoki pastdagi tugmadan foydalaning:",
        reply_markup=markup
    )
    return ASK_PHONE


# ASK PHONE

def ask_phone(update: Update, context: CallbackContext):
    # Foydalanuvchi matn yozsa, uni telefon sifatida qabul qilamiz
    phone = update.message.text.strip()
    context.user_data['phone'] = phone

    # Xizmatni tanlash tugmalari
    markup = ReplyKeyboardMarkup([[s] for s in SERVICES], one_time_keyboard=True, resize_keyboard=True)
    update.message.reply_text("Qaysi xizmatni xohlaysiz?", reply_markup=markup)
    return ASK_SERVICE


def phone_from_contact(update: Update, context: CallbackContext):
    contact = update.message.contact
    phone = contact.phone_number
    context.user_data['phone'] = phone

    markup = ReplyKeyboardMarkup([[s] for s in SERVICES], one_time_keyboard=True, resize_keyboard=True)
    update.message.reply_text("Qaysi xizmatni xohlaysiz?", reply_markup=markup)
    return ASK_SERVICE


# ASK SERVICE
def ask_service(update: Update, context: CallbackContext):
    context.user_data['service'] = update.message.text.strip()
    markup = ReplyKeyboardMarkup([[b] for b in BARBERS], one_time_keyboard=True, resize_keyboard=True)
    update.message.reply_text("Qaysi Sartaroshga yozilmoqchisiz?", reply_markup=markup)
    return ASK_BARBER


# ASK BARBER
def ask_barber(update: Update, context: CallbackContext):
    context.user_data['barber'] = update.message.text.strip()

    today = datetime.now(TZ).date()
    now_time = datetime.now(TZ).time()
    buttons = []
    date_map = {}

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


# ASK DATE
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

    slots = []
    today = datetime.now(TZ).date()
    now_time = datetime.now(TZ).time()
    cur_dt = TZ.localize(datetime.combine(datetime.fromisoformat(date_iso), WORK_START))
    end_dt = TZ.localize(datetime.combine(datetime.fromisoformat(date_iso), WORK_END))

    while cur_dt.time() <= end_dt.time():
        slot_str = cur_dt.strftime("%H:%M")
        if datetime.fromisoformat(date_iso).date() == today:
            if cur_dt.time() > now_time and slot_str not in booked:
                slots.append([slot_str])
        else:
            if slot_str not in booked:
                slots.append([slot_str])
        cur_dt += timedelta(minutes=SLOT_MINUTES)

    if not slots:
        update.message.reply_text(
            "Kechirasiz, tanlangan kunda bo‘sh vaqtlar yo‘q. Boshqa kunni tanlab ko‘ring.",
            reply_markup=ReplyKeyboardRemove()
        )
        return ASK_DATE

    markup = ReplyKeyboardMarkup(slots, one_time_keyboard=True, resize_keyboard=True)
    update.message.reply_text("Vaqtni tanlang:", reply_markup=markup)
    return ASK_TIME


# ASK TIME
def ask_time(update: Update, context: CallbackContext):
    context.user_data['time'] = update.message.text.strip()
    name = context.user_data.get('name')
    phone = context.user_data.get('phone')
    service = context.user_data.get('service')
    barber = context.user_data.get('barber')
    date_iso = context.user_data.get('date')
    time_str = context.user_data.get('time')

    msg = (
        f"Joyingiz band qilindi:\n\n"
        f"👤 Ism: {name}\n"
        f"📞 Tel: {phone}\n"
        f"🛠 Xizmat: {service}\n"
        f"💈 Sartarosh: {barber}\n"
        f"📅 Sana: {date_iso}\n"
        f"⏰ Vaqt: {time_str}\n\n"
        "Tasdiqlaysizmi? (ha/yo'q)"
    )
    update.message.reply_text(
        msg, reply_markup=ReplyKeyboardMarkup([['ha', "yo'q"]], one_time_keyboard=True, resize_keyboard=True)
    )
    return CONFIRM


# done
def finish(update: Update, context: CallbackContext):
    text = update.message.text.strip().lower()
    if text == 'ha':
        name = context.user_data.get('name')
        phone = context.user_data.get('phone')
        service = context.user_data.get('service')
        barber = context.user_data.get('barber')
        date_iso = context.user_data.get('date')
        time_str = context.user_data.get('time')
        user_id = update.message.from_user.id

        booked = get_bookings_for(barber, date_iso)
        if time_str in booked:
            update.message.reply_text(
                "Afsuski, bu vaqt band. Iltimos boshqa vaqtni tanlang /start.",
                reply_markup=ReplyKeyboardRemove()
            )
            return ASK_DATE

        add_client(name, phone, service, barber, date_iso, time_str, telegram_id=user_id)

        # Admin notify
        admin_msg = (
            f"📥 *Yangi Mijoz!*\n\n"
            f"👤 Ism: *{name}*\n"
            f"📞 Tel: *{phone}*\n"
            f"🛠 Xizmat: *{service}*\n"
            f"💈 Sartarosh: *{barber}*\n"
            f"📅 Sana: *{date_iso}*\n"
            f"⏰ Vaqt: *{time_str}*"
        )
        for admin in ADMINS:
            try:
                context.bot.send_message(chat_id=admin, text=admin_msg, parse_mode="Markdown")
            except Exception:
                logger.exception("Admin notify failed")

        update.message.reply_text(
            "Rahmat! Sizning joyingiz band qilindi. Vaqtingizni eslab qo‘ying 😊",
            reply_markup=ReplyKeyboardRemove()
        )
        return ConversationHandler.END
    else:
        update.message.reply_text("Buyurtma bekor qilindi.", reply_markup=ReplyKeyboardRemove())
        return ConversationHandler.END


# CANCEL
def cancel(update: Update, context: CallbackContext):
    update.message.reply_text("Bekor qilindi.", reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END


# REMINDERS
def check_reminders(context: CallbackContext):
    now = datetime.now(TZ)
    bookings = get_pending_reminders()

    for b in bookings:
        booking_datetime = TZ.localize(
            datetime.strptime(f"{b['date']} {b['time']}", "%Y-%m-%d %H:%M")
        )

        if timedelta(minutes=29) < (booking_datetime - now) <= timedelta(minutes=31):

            #1) CUSTOMER notify
            context.bot.send_message(
                chat_id=b["telegram_id"],
                text=(
                    f"📢 *Eslatma!* \n\n"
                    f"Siz bugun soat *{b['time']}* da "
                    f"bizning sartaroshxonamizga yozilgansiz.\n"
                    f"⏳ Sizni kutib qolamiz!"
                ),
                parse_mode="Markdown"
            )

            #2) ADMIN notify
            admin_text = (
                f"⚠️ *30 daqiqadan keyin mijoz keladi!*\n\n"
                f"👤 Ism: *{b['name']}*\n"
                f"📞 Tel: *{b['phone']}*\n"
                f"🛠 Xizmat: *{b['service']}*\n"
                f"💈 Sartarosh: *{b['barber']}*\n"
                f"📅 Sana: *{b['date']}*\n"
                f"⏰ Vaqt: *{b['time']}*\n"
            )

            for admin in ADMINS:
                try:
                    context.bot.send_message(
                        chat_id=admin,
                        text=admin_text,
                        parse_mode="Markdown"
                    )
                except Exception:
                    logger.exception("Admin reminder failed")

            mark_as_reminded(b["id"])


# OTHER COMMANDS
def numbers(update: Update, context: CallbackContext):
    update.message.reply_text("Admin bilan bog‘lanish: https://t.me/Death0201")


def developer(update: Update, context: CallbackContext):
    update.message.reply_text("Bot developer: https://t.me/ergashev_dev")


def main():
    init_db()
    updater = Updater(BOT_TOKEN)
    dp = updater.dispatcher

    conv = ConversationHandler(
        entry_points=[CommandHandler("book", book_start)],
        states={
            ASK_NAME: [MessageHandler(Filters.text & ~Filters.command, ask_name)],
            ASK_PHONE: [
                MessageHandler(Filters.contact, phone_from_contact),
                MessageHandler(Filters.text & ~Filters.command, ask_service)
            ],
            ASK_SERVICE: [MessageHandler(Filters.text & ~Filters.command, ask_service)],
            ASK_BARBER: [MessageHandler(Filters.text & ~Filters.command, ask_barber)],
            ASK_DATE: [MessageHandler(Filters.text & ~Filters.command, ask_date)],
            ASK_TIME: [MessageHandler(Filters.text & ~Filters.command, ask_time)],
            CONFIRM: [MessageHandler(Filters.text & ~Filters.command, finish)]
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        allow_reentry=True
    )
    #
    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(CommandHandler("numbers", numbers))
    dp.add_handler(CommandHandler("developer", developer))
    dp.add_handler(conv)

    updater.bot.set_my_commands([
        BotCommand("start", "Botni ishga tushiradi"),
        BotCommand("book", "Bron qilish"),
        BotCommand("numbers", "Kontaktlar"),
        BotCommand("developer", "Developer profili")
    ])

    updater.job_queue.run_repeating(check_reminders, interval=60, first=10)

    updater.start_polling()
    logger.info("Bot started")
    updater.idle()


if __name__ == "__main__":
    main()
