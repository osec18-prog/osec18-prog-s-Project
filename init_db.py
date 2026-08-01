"""
Initialize / migrate CampusConnect+ database.
Run ONCE after deploying to create tables and seed default data.
"""
import sqlite3
import os

import db
from core import hash_password

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "campusconnect.db")

# Seeded accounts are created hashed. Existing rows are never touched, because
# every seed statement is INSERT OR IGNORE.
DEFAULT_PROFESSOR_PASSWORD = os.environ.get("SEED_PROFESSOR_PASSWORD", "prof123")


def _admin_seed_password():
    """Password for the seeded administrator row.

    Read from ADMIN_PASSWORD so a fresh deployment does not come up with a
    publicly known credential. This script runs during the Render build, where
    the variable is available.
    """
    value = os.environ.get("ADMIN_PASSWORD")
    if not value:
        raise SystemExit(
            "ADMIN_PASSWORD is not set.\n"
            "init_db.py seeds the administrator account and refuses to fall back "
            "to a default password.\n"
            "  PowerShell:  $env:ADMIN_PASSWORD = \"<password>\"; python init_db.py"
        )
    return value


def init_database():
    conn = db.connect()
    cursor = conn.cursor()

    # -----------------------------
    # STUDENTS TABLE
    # -----------------------------
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS students(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        student_id TEXT UNIQUE,
        fullname TEXT,
        email TEXT,
        password TEXT
    )
    """)

    try:
        cursor.execute("ALTER TABLE students ADD COLUMN role TEXT DEFAULT 'student'")
    except sqlite3.OperationalError:
        pass

    # -----------------------------
    # ANNOUNCEMENTS TABLE
    # -----------------------------
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS announcements(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT,
        description TEXT,
        date_created TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

    # -----------------------------
    # PROFESSORS TABLE
    # -----------------------------
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS professors(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        employee_id TEXT UNIQUE,
        fullname TEXT,
        email TEXT UNIQUE,
        password TEXT,
        department TEXT
    )
    """)

    try:
        cursor.execute("ALTER TABLE professors ADD COLUMN password TEXT")
    except sqlite3.OperationalError:
        pass

    # -----------------------------
    # SUBJECTS TABLE
    # -----------------------------
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS subjects(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        subject_code TEXT UNIQUE,
        subject_name TEXT,
        professor TEXT,
        year_level TEXT,
        semester TEXT
    )
    """)

    # -----------------------------
    # SCHEDULES TABLE
    # -----------------------------
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS schedules(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        subject_code TEXT,
        subject_name TEXT,
        professor TEXT,
        day TEXT,
        time TEXT,
        room TEXT,
        year_level TEXT,
        semester TEXT,
        class_type TEXT,
        professor_id TEXT
    )
    """)

    try:
        cursor.execute("ALTER TABLE schedules ADD COLUMN class_type TEXT")
    except sqlite3.OperationalError:
        pass
    try:
        cursor.execute("ALTER TABLE schedules ADD COLUMN professor_id TEXT")
    except sqlite3.OperationalError:
        pass

    # -----------------------------
    # ATTENDANCE TABLE
    # -----------------------------
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS attendance(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        student_id TEXT,
        fullname TEXT,
        subject_code TEXT,
        subject_name TEXT,
        professor TEXT,
        professor_id TEXT,
        professor_name TEXT,
        day TEXT,
        schedule TEXT,
        date TEXT,
        time TEXT,
        status TEXT,
        uuid TEXT,
        token TEXT
    )
    """)

    try:
        cursor.execute("ALTER TABLE attendance ADD COLUMN uuid TEXT")
    except sqlite3.OperationalError:
        pass
    try:
        cursor.execute("ALTER TABLE attendance ADD COLUMN professor_id TEXT")
    except sqlite3.OperationalError:
        pass
    try:
        cursor.execute("ALTER TABLE attendance ADD COLUMN professor_name TEXT")
    except sqlite3.OperationalError:
        pass
    try:
        cursor.execute("ALTER TABLE attendance ADD COLUMN day TEXT")
    except sqlite3.OperationalError:
        pass
    try:
        cursor.execute("ALTER TABLE attendance ADD COLUMN schedule TEXT")
    except sqlite3.OperationalError:
        pass
    try:
        cursor.execute("ALTER TABLE attendance ADD COLUMN token TEXT")
    except sqlite3.OperationalError:
        pass

    try:
        cursor.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_attendance_uuid ON attendance(uuid)")
    except sqlite3.OperationalError:
        pass

    # -----------------------------
    # ATTENDANCE SESSIONS TABLE
    # -----------------------------
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS attendance_sessions(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        professor_id TEXT,
        professor_name TEXT,
        subject_code TEXT,
        subject_name TEXT,
        day TEXT,
        schedule TEXT,
        date TEXT,
        expires_at TEXT,
        token TEXT UNIQUE,
        active INTEGER DEFAULT 1,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

    # -----------------------------
    # API TOKENS TABLE
    # -----------------------------
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS api_tokens(
        token TEXT PRIMARY KEY,
        role TEXT,
        user_id TEXT,
        fullname TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

    # -----------------------------
    # REVOKED JWTS TABLE
    # -----------------------------
    # Logging out cannot delete a stateless JWT, so the token's "jti" claim is
    # recorded here and api._verify_jwt refuses any token listed. Kept
    # byte-identical to core.ensure_schema's definition: that one runs at app
    # start on an existing database, this one builds a database from nothing,
    # and the two must not drift.
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS revoked_jwts(
        jti TEXT PRIMARY KEY,
        expires_at INTEGER,
        revoked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

    # -----------------------------
    # DEFAULT ADMIN ACCOUNT
    # -----------------------------
    # The password column stays empty; only the hash is stored.
    try:
        cursor.execute("ALTER TABLE students ADD COLUMN password_hash TEXT")
    except sqlite3.OperationalError:
        pass

    cursor.execute("""
    INSERT OR IGNORE INTO students
    (student_id, fullname, email, password, password_hash)
    VALUES
    ('admin', 'System Administrator', 'admin@aics.edu.ph', '', ?)
    """, (hash_password(_admin_seed_password()),))

    cursor.execute("""
    UPDATE students SET role='admin' WHERE student_id='admin'
    """)

    # -----------------------------
    # SAMPLE PROFESSORS
    # -----------------------------
    sample_professors = [
        ("T001", "Annalisa Magnaye", "annalisa@aics.edu.ph", "BSCOMSCIE"),
        ("T002", "Yasmin", "yasmin@aics.edu.ph", "BSCOMSCIE"),
        ("T003", "Roshell Salvador", "roshell@aics.edu.ph", "BSCOMSCIE"),
        ("T004", "Ogie Cutmora", "ogie@aics.edu.ph", "BSCOMSCIE"),
        ("T005", "Jobert Cruz", "jobert@aics.edu.ph", "BSCOMSCIE"),
    ]

    try:
        cursor.execute("ALTER TABLE professors ADD COLUMN password_hash TEXT")
    except sqlite3.OperationalError:
        pass

    # Seeded hashed; the plaintext column stays empty.
    seeded_professor_hash = hash_password(DEFAULT_PROFESSOR_PASSWORD)
    for emp_id, name, email, dept in sample_professors:
        cursor.execute("""
            INSERT OR IGNORE INTO professors
            (employee_id, fullname, email, password, password_hash, department)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (emp_id, name, email, "", seeded_professor_hash, dept))

    conn.commit()
    conn.close()
    print("Database initialized successfully!")
    if db.is_postgres():
        print("Backend: PostgreSQL (Supabase)")
    else:
        print(f"Backend: SQLite — {DB_PATH}")


if __name__ == "__main__":
    init_database()

