"""Shared database + QR helpers used by both the web routes (app.py) and the
JSON API consumed by the Flutter app (api.py).

Enhanced with password hashing and schema migration for the redesigned
CampusConnect+ system.
"""

import os
import socket
import sqlite3
import threading
import time
from datetime import datetime

# Database compatibility layer — PostgreSQL when DATABASE_URL is set, the
# original SQLite file when it is not. All dialect translation lives in db.py.
import db

# ── Password hashing (werkzeug is already a Flask dependency) ────────────
from werkzeug.security import generate_password_hash as _generate_hash, \
    check_password_hash as _check_hash


# Always talk to the database that sits next to this file, no matter which
# folder the server was started from.
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "campusconnect.db")


def get_db():
    conn = db.connect()
    conn.row_factory = sqlite3.Row
    return conn


# --------------------------------------------------------------------------
# PASSWORD HELPERS (new)
# --------------------------------------------------------------------------

def hash_password(password: str) -> str:
    """Return a Werkzeug-hashed version of *password* (uses pbkdf2:sha256)."""
    return _generate_hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    """Return True if *password* matches the stored *password_hash*."""
    try:
        return _check_hash(password_hash, password)
    except (ValueError, TypeError):
        return False


# --------------------------------------------------------------------------
# LOGIN RATE LIMITING
# --------------------------------------------------------------------------

_RATE_BUCKETS = {}
_RATE_LOCK = threading.Lock()


def rate_limit_hit(key, limit=10, window_seconds=300):
    """Record an attempt for *key*; return True when it is over the limit.

    A deliberately small in-memory sliding window — enough to blunt password
    guessing without adding a dependency or a Redis server. State is per
    process, so it resets on restart; that is an accepted trade-off for a
    single-instance deployment.
    """
    now = time.time()
    cutoff = now - window_seconds

    with _RATE_LOCK:
        hits = [t for t in _RATE_BUCKETS.get(key, []) if t > cutoff]
        hits.append(now)
        _RATE_BUCKETS[key] = hits

        # Opportunistic cleanup so the dict cannot grow without bound.
        if len(_RATE_BUCKETS) > 2048:
            for k in [k for k, v in _RATE_BUCKETS.items() if not v or v[-1] <= cutoff]:
                _RATE_BUCKETS.pop(k, None)

        return len(hits) > limit


def rate_limit_reset(key):
    """Clear a key's history — called after a successful login."""
    with _RATE_LOCK:
        _RATE_BUCKETS.pop(key, None)


def check_password_with_migration(conn, table, id_column, row, password):
    """Authenticate *row* against *password*, upgrading legacy rows in place.

    This is the single place the password policy lives; the web login, the
    professor login and both mobile login endpoints all call it.

    Policy:
      * password_hash set   -> that is the ONLY thing checked. The legacy
                               plaintext column is ignored completely.
      * password_hash empty -> the legacy plaintext column is compared, and on
                               success the row is upgraded to a hash and the
                               plaintext is cleared.

    *row* may be a sqlite3.Row, a dict, or None. Returns True when the
    credentials are valid.
    """
    if row is None or not password:
        return False

    data = dict(row)
    stored_hash = data.get("password_hash")

    if stored_hash:
        return verify_password(password, stored_hash)

    legacy = data.get("password")
    if not legacy or legacy != password:
        return False

    # Legacy plaintext matched — upgrade this account now.
    new_hash = hash_password(password)

    # Belt and braces: never drop the plaintext unless the freshly created
    # hash actually validates the same password.
    if not verify_password(password, new_hash):
        return True  # still a valid login; just leave the row alone

    try:
        conn.execute(
            "UPDATE %s SET password_hash=?, password='' WHERE %s=?"
            % (table, id_column),
            (new_hash, data[id_column]),
        )
        conn.commit()
    except sqlite3.OperationalError:
        # password_hash column missing (ensure_schema not yet run). The login
        # itself already succeeded, so do not fail it.
        pass

    return True


# --------------------------------------------------------------------------
# SCHEMA MIGRATION (new — adds tables without dropping anything)
# --------------------------------------------------------------------------

def migrate_schema():
    """Add new normalised tables alongside existing ones.

    This is safe to call repeatedly — every statement uses IF NOT EXISTS
    or graceful ALTER TABLE fallback.  Existing data is never touched.
    """
    conn = db.connect()
    cursor = conn.cursor()

    # 1.  Departments
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS departments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT UNIQUE NOT NULL,
            name TEXT NOT NULL,
            description TEXT DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # 2.  Courses (belongs to a department)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS courses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT UNIQUE NOT NULL,
            name TEXT NOT NULL,
            department_id INTEGER REFERENCES departments(id),
            description TEXT DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # 3.  Sections (belongs to a course)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS sections (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT UNIQUE NOT NULL,
            name TEXT NOT NULL,
            course_id INTEGER REFERENCES courses(id),
            year_level TEXT DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # 4.  Grades (future-ready — write-only for now, no UI yet)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS grades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id TEXT NOT NULL REFERENCES students(student_id),
            subject_code TEXT NOT NULL,
            semester TEXT NOT NULL,
            school_year TEXT NOT NULL,
            grade TEXT DEFAULT 'IN PROGRESS',
            remarks TEXT DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # 5.  Events (campus events / school calendar)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            description TEXT DEFAULT '',
            event_date TEXT NOT NULL,
            event_time TEXT DEFAULT '',
            location TEXT DEFAULT '',
            category TEXT DEFAULT 'general',   -- general, academic, sports, holiday
            created_by TEXT DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # 6.  Notifications
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS notifications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            recipient_role TEXT NOT NULL,       -- 'student', 'professor', 'admin', 'all'
            recipient_id TEXT DEFAULT '',       -- empty = all users of that role
            title TEXT NOT NULL,
            message TEXT DEFAULT '',
            is_read INTEGER DEFAULT 0,
            link TEXT DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # 7.  System Logs
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS system_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT DEFAULT '',
            user_role TEXT DEFAULT '',
            action TEXT NOT NULL,
            details TEXT DEFAULT '',
            ip_address TEXT DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # 8.  Lost & Found items
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS lost_found (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            item_name TEXT NOT NULL,
            description TEXT DEFAULT '',
            location TEXT DEFAULT '',
            status TEXT DEFAULT 'lost',          -- 'lost' or 'found'
            reporter_name TEXT DEFAULT '',
            reporter_contact TEXT DEFAULT '',
            image_path TEXT DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            resolved_at TIMESTAMP
        )
    """)

    # 9.  Office Directory
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS office_directory (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            office_name TEXT NOT NULL,
            description TEXT DEFAULT '',
            location TEXT DEFAULT '',
            phone TEXT DEFAULT '',
            email TEXT DEFAULT '',
            office_hours TEXT DEFAULT '',
            head_officer TEXT DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # 10. Emergency Contacts
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS emergency_contacts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            phone TEXT NOT NULL,
            description TEXT DEFAULT '',
            priority INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # 11. Campus Map locations
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS campus_map_locations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            building_name TEXT NOT NULL,
            latitude REAL DEFAULT 0,
            longitude REAL DEFAULT 0,
            description TEXT DEFAULT '',
            category TEXT DEFAULT 'building',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # 12. Downloads (shared files / forms)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS downloads (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            description TEXT DEFAULT '',
            file_path TEXT DEFAULT '',
            file_type TEXT DEFAULT '',
            category TEXT DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # 13. Password hash column migration for existing tables
    for table, col in [("students", "password_hash"), ("professors", "password_hash")]:
        try:
            cursor.execute(f"ALTER TABLE {table} ADD COLUMN {col} TEXT")
        except sqlite3.OperationalError:
            pass  # already exists

    # 14. Add department_id / course_id / section_id to existing subjects
    for col in ["department_id", "course_id", "section_id"]:
        try:
            cursor.execute(f"ALTER TABLE subjects ADD COLUMN {col} INTEGER DEFAULT 0")
        except sqlite3.OperationalError:
            pass

    conn.commit()
    conn.close()


# --------------------------------------------------------------------------
# LEGACY SCHEMA (unchanged)
# --------------------------------------------------------------------------

def ensure_schema():
    """Bring an older campusconnect.db up to the columns/tables the app needs."""

    conn = db.connect()
    cursor = conn.cursor()

    for stmt in [
        "ALTER TABLE attendance ADD COLUMN uuid TEXT",
        "ALTER TABLE attendance ADD COLUMN professor_id TEXT",
        "ALTER TABLE attendance ADD COLUMN professor_name TEXT",
        "ALTER TABLE attendance ADD COLUMN day TEXT",
        "ALTER TABLE attendance ADD COLUMN schedule TEXT",
        "ALTER TABLE attendance ADD COLUMN token TEXT",
        # schedules.class_type is written by the admin schedule form but was
        # missing from older databases, which made every INSERT fail.
        "ALTER TABLE schedules ADD COLUMN class_type TEXT",
        "ALTER TABLE schedules ADD COLUMN professor_id TEXT",
        # Password hashing. The legacy plaintext `password` column is kept so
        # that accounts which have not logged in since the migration can still
        # be verified once, and upgraded at that moment.
        "ALTER TABLE students ADD COLUMN password_hash TEXT",
        "ALTER TABLE professors ADD COLUMN password_hash TEXT",
    ]:
        try:
            cursor.execute(stmt)
        except sqlite3.OperationalError:
            pass

    try:
        cursor.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_attendance_uuid ON attendance(uuid)")
    except sqlite3.OperationalError:
        pass

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

    # JWTs are stateless, so logging out cannot simply delete them. Every JWT
    # issued from now on carries a unique "jti" claim; logging out records that
    # jti here and _verify_jwt refuses any token listed. Rows are purged once
    # the token would have expired anyway, so this stays small.
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS revoked_jwts(
            jti TEXT PRIMARY KEY,
            expires_at INTEGER,
            revoked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Bearer tokens handed out to the Flutter app; the browser keeps using
    # Flask's cookie session instead.
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS api_tokens(
            token TEXT PRIMARY KEY,
            role TEXT,
            user_id TEXT,
            fullname TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    conn.commit()
    conn.close()


# --------------------------------------------------------------------------
# QR PAYLOADS (unchanged)
# --------------------------------------------------------------------------

def parse_qr(qr_text):
    """Attendance QR. v1 is the old 5-field payload, v2 the tokenised one."""

    if not qr_text:
        return None

    data = qr_text.split("|")

    if len(data) == 5:
        return {
            "version": 1,
            "subject_code": data[0].strip(),
            "subject_name": data[1].strip(),
            "professor": data[2].strip(),
            "day": data[3].strip(),
            "schedule": data[4].strip()
        }

    if len(data) == 9:
        return {
            "version": 2,
            "subject_code": data[0].strip(),
            "subject_name": data[1].strip(),
            "professor_id": data[2].strip(),
            "professor_name": data[3].strip(),
            "day": data[4].strip(),
            "schedule": data[5].strip(),
            "date": data[6].strip(),
            "expires_at": data[7].strip(),
            "token": data[8].strip()
        }

    return None


def parse_professor_qr(qr_text):
    if not qr_text:
        return None

    data = qr_text.split("|")

    if len(data) != 4 or data[0] != "PROF":
        return None

    return {
        "professor_id": data[1].strip(),
        "professor_name": data[2].strip(),
        "token": data[3].strip()
    }


def attendance_exists(cursor, student_id, subject_code, date, token=None):
    if token:
        cursor.execute(
            "SELECT id FROM attendance WHERE student_id=? AND token=?",
            (student_id, token)
        )
    else:
        cursor.execute(
            "SELECT id FROM attendance WHERE student_id=? AND subject_code=? AND date=?",
            (student_id, subject_code, date)
        )

    return cursor.fetchone() is not None


def attendance_session_active(cursor, parsed):
    """True when the v2 attendance session named by *parsed* is still open.

    Shared by the web scanner, the offline sync endpoint and the mobile
    scan endpoint so the "is this session accepting scans?" rule lives in
    exactly one place.
    """
    cursor.execute(
        "SELECT active FROM attendance_sessions WHERE token=? AND professor_id=?",
        (parsed["token"], parsed["professor_id"])
    )
    row = cursor.fetchone()

    if not row:
        return False

    # Works for both plain tuple rows and sqlite3.Row.
    return row[0] == 1


def insert_attendance(cursor, student_id, fullname, parsed, date, time_label, record_id):
    """Insert one attendance row, picking the v1 or v2 column set.

    v2 payloads carry the professor id/name, day, schedule and token, and
    record the date that was baked into the QR. v1 payloads only know the
    professor name, and use the caller-supplied *date*.
    """
    if parsed["version"] == 2:
        cursor.execute("""
            INSERT INTO attendance
            (
                student_id,
                fullname,
                subject_code,
                subject_name,
                professor_id,
                professor_name,
                day,
                schedule,
                date,
                time,
                status,
                uuid,
                token
            )
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            student_id,
            fullname,
            parsed["subject_code"],
            parsed["subject_name"],
            parsed["professor_id"],
            parsed["professor_name"],
            parsed["day"],
            parsed["schedule"],
            parsed["date"],
            time_label,
            "Present",
            record_id,
            parsed["token"]
        ))
    else:
        cursor.execute("""
            INSERT INTO attendance
            (
                student_id,
                fullname,
                subject_code,
                subject_name,
                professor,
                date,
                time,
                status,
                uuid
            )
            VALUES (?,?,?,?,?,?,?,?,?)
        """, (
            student_id,
            fullname,
            parsed["subject_code"],
            parsed["subject_name"],
            parsed["professor"],
            date,
            time_label,
            "Present",
            record_id
        ))


def session_expired(parsed):
    """True when a v2 attendance QR is past its expiration time."""

    try:
        expires_dt = datetime.strptime(
            f"{parsed['date']} {parsed['expires_at']}",
            "%Y-%m-%d %I:%M %p"
        )
    except ValueError:
        return None

    return datetime.now() > expires_dt


# --------------------------------------------------------------------------
# TIME HELPERS (unchanged)
# --------------------------------------------------------------------------

def format_time_range(start_time, end_time):
    """'08:00', '10:00' -> '8:00 AM - 10:00 AM'"""

    start = datetime.strptime(start_time, "%H:%M").strftime("%I:%M %p").lstrip("0")
    end = datetime.strptime(end_time, "%H:%M").strftime("%I:%M %p").lstrip("0")
    return f"{start} - {end}"


def parse_time_range(time_range):
    """'8:00 AM - 10:00 AM' -> ('08:00', '10:00')"""

    if not time_range:
        return "", ""

    try:
        start, end = time_range.split(" - ")
        start_iso = datetime.strptime(start.strip(), "%I:%M %p").strftime("%H:%M")
        end_iso = datetime.strptime(end.strip(), "%I:%M %p").strftime("%H:%M")
        return start_iso, end_iso
    except ValueError:
        return "", ""


# --------------------------------------------------------------------------
# SCHEDULES (unchanged)
# --------------------------------------------------------------------------

QR_SCHEDULE_SQL = """
    SELECT
        s.id,
        s.subject_code,
        s.subject_name,
        s.professor,
        s.day,
        s.time,
        COALESCE(NULLIF(p.employee_id,''), NULLIF(s.professor_id,''), '') AS professor_id,
        COALESCE(s.room,'') AS room,
        COALESCE(s.class_type,'') AS class_type
    FROM schedules s
    LEFT JOIN professors p
        ON TRIM(LOWER(s.professor))=TRIM(LOWER(p.fullname))
"""


def get_local_ip():
    """Best-effort LAN address so QR links work from a phone."""

    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
    except OSError:
        pass

    try:
        host_name = socket.gethostname()
        for info in socket.getaddrinfo(host_name, None):
            family, _, _, _, sockaddr = info
            if family == socket.AF_INET:
                candidate = sockaddr[0]
                if candidate and not candidate.startswith("127."):
                    return candidate
    except OSError:
        pass

    try:
        host_name = socket.gethostname()
        candidate = socket.gethostbyname(host_name)
        if candidate and not candidate.startswith("127."):
            return candidate
    except OSError:
        pass

    return None
