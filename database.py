import sqlite3
from datetime import datetime, timedelta

conn = sqlite3.connect('barber.db', check_same_thread=False)
cursor = conn.cursor()

def init_db():
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS bookings (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT,
        phone TEXT,
        service TEXT,
        barber TEXT,
        date TEXT,
        time TEXT,
        telegram_id INTEGER,
        reminded INTEGER DEFAULT 0
    )
    ''')
    # Jadval mavjud bo'lsa, status ustunini qo'shish
    try:
        cursor.execute("ALTER TABLE bookings ADD COLUMN status TEXT DEFAULT 'active'")
        conn.commit()
    except sqlite3.OperationalError:
        pass
    conn.commit()


def add_client(name, phone, service, barber, date, time, telegram_id=None):
    cursor.execute('''
        INSERT INTO bookings (name, phone, service, barber, date, time, telegram_id, status)
        VALUES (?, ?, ?, ?, ?, ?, ?, 'active')
    ''', (name, phone, service, barber, date, time, telegram_id))
    conn.commit()


def get_user_bookings(telegram_id, now):
    cursor.execute(
        "SELECT id, name, phone, service, barber, date, time FROM bookings WHERE telegram_id=? AND date>=? ORDER BY date, time",
        (telegram_id, now.date().isoformat())
    )
    return cursor.fetchall()
def get_pending_reminders():
    cursor.execute("""
        SELECT id, name, phone, service, barber, date, time, telegram_id
        FROM bookings
        WHERE reminded = 0 AND status='active'
    """)
    rows = cursor.fetchall()
    return [
        {
            "id": r[0],
            "name": r[1],
            "phone": r[2],
            "service": r[3],
            "barber": r[4],
            "date": r[5],
            "time": r[6],
            "telegram_id": r[7],
        }
        for r in rows
    ]


def mark_as_reminded(booking_id):
    cursor.execute("UPDATE bookings SET reminded=1 WHERE id=?", (booking_id,))
    conn.commit()


def cancel_booking(booking_id):
    cursor.execute("UPDATE bookings SET status='cancelled' WHERE id=?", (booking_id,))
    conn.commit()
