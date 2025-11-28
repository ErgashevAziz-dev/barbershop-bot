# database.py
import sqlite3
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from config import SERVICE_ACCOUNT_FILE, SHEET_NAME

# Google auth
SCOPE = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.file",
    "https://www.googleapis.com/auth/drive"
]

def init_db():
    conn = sqlite3.connect("barber_clients.db")
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS clients (
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
    """)
    conn.commit()
    conn.close()

def add_client_sql(name, phone, service, barber, date_str, time_str):
    conn = sqlite3.connect("barber_clients.db")
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO clients (name, phone, service, barber, date, time)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (name, phone, service, barber, date_str, time_str))
    conn.commit()
    conn.close()

def append_to_sheet(name, phone, service, barber, date_str, time_str):
    creds = ServiceAccountCredentials.from_json_keyfile_name(SERVICE_ACCOUNT_FILE, SCOPE)
    gc = gspread.authorize(creds)
    try:
        sheet = gc.open(SHEET_NAME).sheet1
    except Exception as e:
        raise e
    # Append row: Date, Time, Barber, Service, Name, Phone
    sheet.append_row([date_str, time_str, barber, service, name, phone])

def add_client(name, phone, service, barber, date_str, time_str):
    # save to sqlite
    add_client_sql(name, phone, service, barber, date_str, time_str)
    # append to google sheets
    append_to_sheet(name, phone, service, barber, date_str, time_str)

def get_bookings_for(barber, date_str):
    """Return list of time strings already booked for this barber on date_str from SQLite (fast)."""
    conn = sqlite3.connect("barber_clients.db")
    cur = conn.cursor()
    cur.execute("SELECT time FROM clients WHERE barber=? AND date=?", (barber, date_str))
    rows = cur.fetchall()
    conn.close()
    return [r[0] for r in rows]

def get_pending_reminders():
    conn = sqlite3.connect("barber_clients.db")
    cur = conn.cursor()

    cur.execute("""
        SELECT id, name, phone, service, barber, date, time, telegram_id 
        FROM clients 
        WHERE reminded = 0
    """)

    rows = cur.fetchall()
    conn.close()

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

def mark_as_reminded(booking_id: int):
    conn = sqlite3.connect("barber_clients.db")
    cur = conn.cursor()
    cur.execute("UPDATE clients SET reminded = 1 WHERE id = ?", (booking_id,))
    conn.commit()
    conn.close()