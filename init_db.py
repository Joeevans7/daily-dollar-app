
# init_db.py - Run this once to initialize your local SQLite database

import sqlite3

conn = sqlite3.connect("daily_dollar.db")
cursor = conn.cursor()

# Users Table
cursor.execute('''
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    phone TEXT,
    password_hash TEXT NOT NULL,
    sms_opt_in BOOLEAN DEFAULT 0,
    auto_entry BOOLEAN DEFAULT 0,
    streak INTEGER DEFAULT 0,
    last_entry_date TEXT
)
''')

# Entries Table
cursor.execute('''
CREATE TABLE IF NOT EXISTS entries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    date TEXT NOT NULL,
    entry_type TEXT CHECK(entry_type IN ('main', 'free')),
    FOREIGN KEY(user_id) REFERENCES users(id)
)
''')

# Winners Table
cursor.execute('''
CREATE TABLE IF NOT EXISTS winners (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT NOT NULL,
    user_id INTEGER NOT NULL,
    entry_type TEXT CHECK(entry_type IN ('main', 'free')),
    prize_amount REAL,
    FOREIGN KEY(user_id) REFERENCES users(id)
)
''')

conn.commit()
conn.close()

print("Database initialized successfully.")
