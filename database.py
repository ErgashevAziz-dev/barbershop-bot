import sqlite3

conn = sqlite3.connect("barber.db", check_same_thread=False)
cursor = conn.cursor()


def init_db():
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS bookings (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT,
        phone TEXT,
        service TEXT,
        barber TEXT,
        date TEXT,
        time TEXT,
        telegram_id INTEGER,
        status TEXT DEFAULT 'active',
        reminded INTEGER DEFAULT 0
    )
    """)
    conn.commit()


def add_booking(name, phone, service, barber, date, time, telegram_id):
    cursor.execute("""
        INSERT INTO bookings (name, phone, service, barber, date, time, telegram_id)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (name, phone, service, barber, date, time, telegram_id))
    conn.commit()


def get_booked_times(barber, date):
    cursor.execute("""
        SELECT time FROM bookings
        WHERE barber=? AND date=? AND status='active'
    """, (barber, date))
    return {r[0] for r in cursor.fetchall()}


def get_future_user_bookings(telegram_id):
    cursor.execute("""
        SELECT id, service, barber, date, time
        FROM bookings
        WHERE telegram_id=? AND status='active'
        ORDER BY date, time
    """, (telegram_id,))
    return cursor.fetchall()


def cancel_booking(booking_id):
    cursor.execute("""
        UPDATE bookings SET status='cancelled'
        WHERE id=?
    """, (booking_id,))
    conn.commit()


def get_pending_reminders():
    cursor.execute("""
        SELECT id, name, phone, service, barber, date, time, telegram_id
        FROM bookings
        WHERE reminded=0 AND status='active'
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
