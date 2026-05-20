import sqlite3
import os
import json
from datetime import datetime
from werkzeug.security import generate_password_hash

DB_NAME = 'RITB.db'
if os.environ.get('VERCEL') == '1' or os.environ.get('VERCEL'):
    DB_PATH = os.path.join('/tmp', DB_NAME)
    original_path = os.path.join(os.path.dirname(__file__), DB_NAME)
    if not os.path.exists(DB_PATH) and os.path.exists(original_path):
        with open(original_path, 'rb') as sf:
            with open(DB_PATH, 'wb') as df:
                df.write(sf.read())
    if os.path.exists(DB_PATH):
        try:
            os.chmod(DB_PATH, 0o666)
        except Exception:
            pass
else:
    DB_PATH = os.path.join(os.path.dirname(__file__), DB_NAME)

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

def init_db():
    conn = get_db()
    c = conn.cursor()

    # Users table
    c.execute('''CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        email TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        role TEXT NOT NULL DEFAULT 'student',
        name TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'active',
        avatar_url TEXT,
        student_id TEXT,
        program TEXT,
        year TEXT,
        created_at TEXT NOT NULL
    )''')

    # News table
    c.execute('''CREATE TABLE IF NOT EXISTS news (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        category TEXT NOT NULL DEFAULT 'General',
        content TEXT NOT NULL,
        excerpt TEXT,
        image_url TEXT,
        author_id INTEGER,
        published_at TEXT NOT NULL,
        FOREIGN KEY(author_id) REFERENCES users(id)
    )''')

    # Events table
    c.execute('''CREATE TABLE IF NOT EXISTS events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        category TEXT NOT NULL DEFAULT 'General',
        event_date TEXT NOT NULL,
        time_start TEXT,
        time_end TEXT,
        location TEXT,
        description TEXT,
        image_url TEXT,
        organizer_id INTEGER,
        registered_students TEXT,
        created_at TEXT NOT NULL,
        FOREIGN KEY(organizer_id) REFERENCES users(id)
    )''')

    # Faculty table
    c.execute('''CREATE TABLE IF NOT EXISTS faculty (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER UNIQUE,
        name TEXT NOT NULL,
        title TEXT,
        department TEXT,
        bio TEXT,
        photo_url TEXT,
        email TEXT,
        research_areas TEXT,
        publications TEXT DEFAULT '[]',
        courses TEXT DEFAULT '[]',
        FOREIGN KEY(user_id) REFERENCES users(id)
    )''')

    # Attendance table
    c.execute('''CREATE TABLE IF NOT EXISTS attendance (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        event_id INTEGER NOT NULL,
        user_id  INTEGER,
        student_name TEXT NOT NULL,
        student_branch TEXT,
        status   TEXT NOT NULL DEFAULT 'absent',
        marked_at TEXT,
        UNIQUE(event_id, student_name),
        FOREIGN KEY(event_id) REFERENCES events(id) ON DELETE CASCADE,
        FOREIGN KEY(user_id)  REFERENCES users(id)  ON DELETE SET NULL
    )''')

    conn.commit()

    # -- Migrations: safely add columns that may not exist in older DBs --
    for col, defn in [
        ('registered_students', 'TEXT DEFAULT NULL'),
        ('extra_images', 'TEXT DEFAULT "[]"'),
        ('attendance_enabled', 'INTEGER DEFAULT 0'),
    ]:
        try:
            c.execute(f'ALTER TABLE events ADD COLUMN {col} {defn}')
            conn.commit()
        except Exception:
            pass  # column already exists

    for col, defn in [
        ('extra_images', 'TEXT DEFAULT "[]"'),
    ]:
        try:
            c.execute(f'ALTER TABLE news ADD COLUMN {col} {defn}')
            conn.commit()
        except Exception:
            pass  # column already exists

    for col, defn in [
        ('student_year', 'TEXT DEFAULT NULL'),
        ('rank',         'TEXT DEFAULT NULL'),
    ]:
        try:
            c.execute(f'ALTER TABLE attendance ADD COLUMN {col} {defn}')
            conn.commit()
        except Exception:
            pass  # column already exists

    # Faculty new columns migration
    for col, defn in [
        ('total_publications', 'INTEGER DEFAULT 0'),
        ('experience',         'INTEGER DEFAULT 0'),
    ]:
        try:
            c.execute(f'ALTER TABLE faculty ADD COLUMN {col} {defn}')
            conn.commit()
        except Exception:
            pass  # column already exists

    # Seed default data if empty
    try:
        _seed_data(c)
        conn.commit()
    except Exception:
        conn.rollback()
    
    conn.close()

def _seed_data(c):
    # Admin user
    c.execute("SELECT COUNT(*) FROM users WHERE role='admin'")
    if c.fetchone()[0] == 0:
        now = datetime.now().isoformat()
        c.execute('''INSERT INTO users (email, password_hash, role, name, status, created_at)
                     VALUES (?, ?, ?, ?, ?, ?)''',
                  ('admin@ritb.edu', generate_password_hash('admin123'), 'admin', 'Administrator', 'active', now))


if __name__ == '__main__':
    init_db()
    print("Database initialized successfully.")
