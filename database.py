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
    conn.commit()

def add_client(name, phone, service, barber, date, time, telegram_id=None):
    cursor.execute('''
        INSERT INTO bookings (name, phone, service, barber, date, time, telegram_id)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', (name, phone, service, barber, date, time, telegram_id))
    conn.commit()

def get_bookings_for(barber, date):
    cursor.execute("SELECT time FROM bookings WHERE barber=? AND date=?", (barber, date))
    return [r[0] for r in cursor.fetchall()]

def get_pending_reminders():
    cursor.execute("SELECT id, name, time, date, telegram_id FROM bookings WHERE reminded=0")
    rows = cursor.fetchall()
    return [{"id": r[0], "name": r[1], "time": r[2], "date": r[3], "telegram_id": r[4]} for r in rows]

def mark_as_reminded(booking_id):
    cursor.execute("UPDATE bookings SET reminded=1 WHERE id=?", (booking_id,))
    conn.commit()
