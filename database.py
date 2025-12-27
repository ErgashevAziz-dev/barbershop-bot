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
        reminded INTEGER DEFAULT 0,
        status TEXT DEFAULT 'active'
    )
    ''')
    conn.commit()

def add_client(name, phone, service, barber, date, time, telegram_id=None):
    cursor.execute('''
        INSERT INTO bookings (name, phone, service, barber, date, time, telegram_id)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', (name, phone, service, barber, date, time, telegram_id))
    conn.commit()

def get_bookings_for(barber, date):
    cursor.execute("SELECT time FROM bookings WHERE barber=? AND date=? AND status='active'", (barber, date))
    return [r[0] for r in cursor.fetchall()]

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

# =========================
# MIJOZNING FAOL BRONLARI
# =========================

def get_user_bookings(user_id):
    cursor.execute("""
        SELECT id, date, time, barber
        FROM bookings
        WHERE telegram_id=? AND status='active'
        ORDER BY date, time
    """, (user_id,))
    rows = cursor.fetchall()
    return [
        {"id": r[0], "date": r[1], "time": r[2], "barber": r[3]}
        for r in rows
    ]

def get_booking_for_cancel(booking_id, user_id):
    cursor.execute("""
        SELECT id, date, time
        FROM bookings
        WHERE id=? AND telegram_id=? AND status='active'
    """, (booking_id, user_id))
    row = cursor.fetchone()
    if not row:
        return None
    return {
        "id": row[0],
        "date": row[1],
        "time": row[2]
    }

def cancel_user_booking(booking_id):
    cursor.execute("""
        UPDATE bookings
        SET status='cancelled'
        WHERE id=?
    """, (booking_id,))
    conn.commit()
