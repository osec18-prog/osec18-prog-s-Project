"""
CampusConnect+ — Complete database schema with migration support.

This script is IDEMPOTENT: it can be run any number of times without
destroying data.  Every CREATE uses IF NOT EXISTS; every ALTER is wrapped
in try/except.

Existing tables are NEVER dropped — only new columns are added when missing.
All seed data uses INSERT OR IGNORE to avoid duplicates.
"""

import sqlite3
from datetime import datetime

DB_PATH = "campusconnect.db"


def run_migration():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # =====================================================================
    # 1.  EXISTING TABLES  (preserved exactly — only add missing columns)
    # =====================================================================

    # ── students ─────────────────────────────────────────────────────────
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS students(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id TEXT UNIQUE,
            fullname TEXT,
            email TEXT,
            password TEXT
        )
    """)
    for col in ["role", "password_hash", "phone", "address", "profile_pic"]:
        try:
            cursor.execute(f"ALTER TABLE students ADD COLUMN {col} TEXT DEFAULT ''")
        except sqlite3.OperationalError:
            pass
    try:
        cursor.execute("ALTER TABLE students ADD COLUMN campus_id INTEGER DEFAULT 0")
    except sqlite3.OperationalError:
        pass
    try:
        cursor.execute("ALTER TABLE students ADD COLUMN section_id INTEGER DEFAULT 0")
    except sqlite3.OperationalError:
        pass
    try:
        cursor.execute("ALTER TABLE students ADD COLUMN enrolled INTEGER DEFAULT 1")
    except sqlite3.OperationalError:
        pass

    # ── professors ───────────────────────────────────────────────────────
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS professors(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            employee_id TEXT UNIQUE,
            fullname TEXT,
            email TEXT,
            department TEXT
        )
    """)
    for col in ["password", "password_hash", "phone", "profile_pic"]:
        try:
            cursor.execute(f"ALTER TABLE professors ADD COLUMN {col} TEXT DEFAULT ''")
        except sqlite3.OperationalError:
            pass
    try:
        cursor.execute("ALTER TABLE professors ADD COLUMN campus_id INTEGER DEFAULT 0")
    except sqlite3.OperationalError:
        pass

    # ── announcements ────────────────────────────────────────────────────
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS announcements(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT,
            description TEXT,
            date_created TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    try:
        cursor.execute("ALTER TABLE announcements ADD COLUMN category_id INTEGER DEFAULT 0")
    except sqlite3.OperationalError:
        pass
    try:
        cursor.execute("ALTER TABLE announcements ADD COLUMN created_by TEXT DEFAULT ''")
    except sqlite3.OperationalError:
        pass
    try:
        cursor.execute("ALTER TABLE announcements ADD COLUMN pinned INTEGER DEFAULT 0")
    except sqlite3.OperationalError:
        pass

    # ── subjects ─────────────────────────────────────────────────────────
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
    for col in ["department_id", "course_id", "section_id", "units", "description"]:
        try:
            cursor.execute(f"ALTER TABLE subjects ADD COLUMN {col} INTEGER DEFAULT 0")
        except sqlite3.OperationalError:
            # description is TEXT, not INTEGER
            if col == "description":
                try:
                    cursor.execute(f"ALTER TABLE subjects ADD COLUMN {col} TEXT DEFAULT ''")
                except sqlite3.OperationalError:
                    pass
            pass

    # ── schedules ────────────────────────────────────────────────────────
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
    for col in ["class_type", "professor_id"]:
        try:
            cursor.execute(f"ALTER TABLE schedules ADD COLUMN {col} TEXT DEFAULT ''")
        except sqlite3.OperationalError:
            pass
    for col in ["classroom_id", "section_id", "semester_id"]:
        try:
            cursor.execute(f"ALTER TABLE schedules ADD COLUMN {col} INTEGER DEFAULT 0")
        except sqlite3.OperationalError:
            pass

    # ── attendance (legacy — kept for backward compatibility) ────────────
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
    for col in ["uuid", "professor_id", "professor_name", "day", "schedule", "token"]:
        try:
            cursor.execute(f"ALTER TABLE attendance ADD COLUMN {col} TEXT DEFAULT ''")
        except sqlite3.OperationalError:
            pass
    try:
        cursor.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_attendance_uuid ON attendance(uuid)")
    except sqlite3.OperationalError:
        pass

    # ── attendance_sessions (legacy — kept for backward compatibility) ───
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

    # ── api_tokens (legacy bearer tokens) ────────────────────────────────
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS api_tokens(
            token TEXT PRIMARY KEY,
            role TEXT,
            user_id TEXT,
            fullname TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # =====================================================================
    # 2.  NEW NORMALIZED TABLES
    # =====================================================================

    # ── 2a.  Campuses (future multi-campus) ──────────────────────────────
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS campuses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT UNIQUE NOT NULL,
            name TEXT NOT NULL,
            address TEXT DEFAULT '',
            phone TEXT DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # ── 2b.  Buildings (belongs to a campus) ─────────────────────────────
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS buildings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT UNIQUE NOT NULL,
            name TEXT NOT NULL,
            campus_id INTEGER REFERENCES campuses(id),
            description TEXT DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # ── 2c.  Classrooms (belongs to a building) ──────────────────────────
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS classrooms (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT UNIQUE NOT NULL,
            name TEXT NOT NULL,
            building_id INTEGER REFERENCES buildings(id),
            capacity INTEGER DEFAULT 0,
            equipment TEXT DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # ── 2d.  Departments ─────────────────────────────────────────────────
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS departments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT UNIQUE NOT NULL,
            name TEXT NOT NULL,
            description TEXT DEFAULT '',
            campus_id INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # ── 2e.  Courses (belongs to a department) ───────────────────────────
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS courses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT UNIQUE NOT NULL,
            name TEXT NOT NULL,
            department_id INTEGER REFERENCES departments(id),
            description TEXT DEFAULT '',
            duration_years INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # ── 2f.  Sections (belongs to a course) ──────────────────────────────
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS sections (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT UNIQUE NOT NULL,
            name TEXT NOT NULL,
            course_id INTEGER REFERENCES courses(id),
            year_level TEXT DEFAULT '',
            campus_id INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # ── 2g.  Academic Years ──────────────────────────────────────────────
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS academic_years (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT UNIQUE NOT NULL,
            name TEXT NOT NULL,
            start_date TEXT DEFAULT '',
            end_date TEXT DEFAULT '',
            is_current INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # ── 2h.  Semesters ───────────────────────────────────────────────────
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS semesters (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT UNIQUE NOT NULL,
            name TEXT NOT NULL,
            academic_year_id INTEGER REFERENCES academic_years(id),
            start_date TEXT DEFAULT '',
            end_date TEXT DEFAULT '',
            is_current INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # ── 2i.  School Years (junction of academic_year + semester) ────────
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS school_years (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT UNIQUE NOT NULL,
            academic_year_id INTEGER REFERENCES academic_years(id),
            semester_id INTEGER REFERENCES semesters(id),
            name TEXT NOT NULL,
            is_current INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # ── 2j.  Student Sections (many-to-many: student ↔ section) ─────────
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS student_sections (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id TEXT NOT NULL REFERENCES students(student_id),
            section_id INTEGER NOT NULL REFERENCES sections(id),
            school_year_id INTEGER REFERENCES school_years(id),
            enrolled_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(student_id, section_id, school_year_id)
        )
    """)

    # ── 2k.  Professor Subjects (many-to-many: professor ↔ subject) ─────
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS professor_subjects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            professor_id TEXT NOT NULL REFERENCES professors(employee_id),
            subject_id INTEGER NOT NULL REFERENCES subjects(id),
            school_year_id INTEGER REFERENCES school_years(id),
            assigned_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(professor_id, subject_id, school_year_id)
        )
    """)

    # ── 2l.  Enrollments ─────────────────────────────────────────────────
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS enrollments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id TEXT NOT NULL REFERENCES students(student_id),
            course_id INTEGER REFERENCES courses(id),
            section_id INTEGER REFERENCES sections(id),
            school_year_id INTEGER REFERENCES school_years(id),
            enrollment_date TEXT DEFAULT (date('now')),
            status TEXT DEFAULT 'enrolled',
            remarks TEXT DEFAULT '',
            UNIQUE(student_id, school_year_id)
        )
    """)

    # ── 2m.  Grades (future-ready) ───────────────────────────────────────
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

    # ── 2n.  NEW Attendance Sessions (scalable redesign) ─────────────────
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS new_attendance_sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT UNIQUE NOT NULL,
            subject_id INTEGER REFERENCES subjects(id),
            professor_id TEXT REFERENCES professors(employee_id),
            section_id INTEGER REFERENCES sections(id),
            semester_id INTEGER REFERENCES semesters(id),
            academic_year_id INTEGER REFERENCES academic_years(id),
            qr_token TEXT UNIQUE NOT NULL,
            start_time TEXT NOT NULL,
            end_time TEXT DEFAULT '',
            expiration_time TEXT NOT NULL,
            status TEXT DEFAULT 'active',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # ── 2o.  NEW Attendance Records (scalable redesign) ──────────────────
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS attendance_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            record_id TEXT UNIQUE NOT NULL,
            session_id TEXT REFERENCES new_attendance_sessions(session_id),
            student_id TEXT REFERENCES students(student_id),
            time_in TEXT NOT NULL,
            device TEXT DEFAULT '',
            ip_address TEXT DEFAULT '',
            status TEXT DEFAULT 'present',
            remarks TEXT DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # ── 2p.  Announcement Categories ─────────────────────────────────────
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS announcement_categories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT UNIQUE NOT NULL,
            name TEXT NOT NULL,
            description TEXT DEFAULT '',
            color TEXT DEFAULT '#2F69FF',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # ── 2q.  Event Categories ────────────────────────────────────────────
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS event_categories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT UNIQUE NOT NULL,
            name TEXT NOT NULL,
            description TEXT DEFAULT '',
            color TEXT DEFAULT '#17C3A2',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # ── 2r.  Events ──────────────────────────────────────────────────────
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            description TEXT DEFAULT '',
            event_date TEXT NOT NULL,
            event_time TEXT DEFAULT '',
            end_date TEXT DEFAULT '',
            location TEXT DEFAULT '',
            category_id INTEGER DEFAULT 0,
            created_by TEXT DEFAULT '',
            is_all_day INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # ── 2s.  Notifications ───────────────────────────────────────────────
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS notifications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            recipient_role TEXT NOT NULL,
            recipient_id TEXT DEFAULT '',
            title TEXT NOT NULL,
            message TEXT DEFAULT '',
            is_read INTEGER DEFAULT 0,
            link TEXT DEFAULT '',
            priority TEXT DEFAULT 'normal',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # ── 2t.  System Logs ─────────────────────────────────────────────────
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

    # ── 2u.  Lost & Found ────────────────────────────────────────────────
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS lost_found (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            item_name TEXT NOT NULL,
            description TEXT DEFAULT '',
            location TEXT DEFAULT '',
            status TEXT DEFAULT 'lost',
            reporter_name TEXT DEFAULT '',
            reporter_contact TEXT DEFAULT '',
            image_path TEXT DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            resolved_at TIMESTAMP
        )
    """)

    # ── 2v.  Office Directory ────────────────────────────────────────────
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
            campus_id INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # ── 2w.  Emergency Contacts ──────────────────────────────────────────
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS emergency_contacts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            phone TEXT NOT NULL,
            description TEXT DEFAULT '',
            priority INTEGER DEFAULT 0,
            campus_id INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # ── 2x.  Campus Map Locations ────────────────────────────────────────
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS campus_map_locations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            building_name TEXT NOT NULL,
            latitude REAL DEFAULT 0,
            longitude REAL DEFAULT 0,
            description TEXT DEFAULT '',
            category TEXT DEFAULT 'building',
            campus_id INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # ── 2y.  Downloads ───────────────────────────────────────────────────
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS downloads (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            description TEXT DEFAULT '',
            file_path TEXT DEFAULT '',
            file_type TEXT DEFAULT '',
            category TEXT DEFAULT '',
            uploader TEXT DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # =====================================================================
    # 3.  PERFORMANCE INDEXES
    # =====================================================================
    indexes = [
        "CREATE INDEX IF NOT EXISTS idx_attendance_student ON attendance(student_id)",
        "CREATE INDEX IF NOT EXISTS idx_attendance_date ON attendance(date)",
        "CREATE INDEX IF NOT EXISTS idx_attendance_token ON attendance(token)",
        "CREATE INDEX IF NOT EXISTS idx_attendance_sessions_token ON attendance_sessions(token)",
        "CREATE INDEX IF NOT EXISTS idx_attendance_sessions_professor ON attendance_sessions(professor_id)",
        "CREATE INDEX IF NOT EXISTS idx_attendance_sessions_active ON attendance_sessions(active)",
        "CREATE INDEX IF NOT EXISTS idx_new_attendance_sessions_qr ON new_attendance_sessions(qr_token)",
        "CREATE INDEX IF NOT EXISTS idx_new_attendance_sessions_professor ON new_attendance_sessions(professor_id)",
        "CREATE INDEX IF NOT EXISTS idx_attendance_records_session ON attendance_records(session_id)",
        "CREATE INDEX IF NOT EXISTS idx_attendance_records_student ON attendance_records(student_id)",
        "CREATE INDEX IF NOT EXISTS idx_notifications_role ON notifications(recipient_role)",
        "CREATE INDEX IF NOT EXISTS idx_notifications_read ON notifications(is_read)",
        "CREATE INDEX IF NOT EXISTS idx_system_logs_action ON system_logs(action)",
        "CREATE INDEX IF NOT EXISTS idx_system_logs_created ON system_logs(created_at)",
        "CREATE INDEX IF NOT EXISTS idx_enrollments_student ON enrollments(student_id)",
        "CREATE INDEX IF NOT EXISTS idx_enrollments_school_year ON enrollments(school_year_id)",
        "CREATE INDEX IF NOT EXISTS idx_grades_student ON grades(student_id)",
        "CREATE INDEX IF NOT EXISTS idx_student_sections_student ON student_sections(student_id)",
        "CREATE INDEX IF NOT EXISTS idx_professor_subjects_professor ON professor_subjects(professor_id)",
        "CREATE INDEX IF NOT EXISTS idx_events_date ON events(event_date)",
    ]
    for index_sql in indexes:
        try:
            cursor.execute(index_sql)
        except sqlite3.OperationalError:
            pass

    # =====================================================================
    # 4.  SEED DATA  (INSERT OR IGNORE — safe to re-run)
    # =====================================================================

    # ── Default admin account ────────────────────────────────────────────
    cursor.execute("""
        INSERT OR IGNORE INTO students (student_id, fullname, email, password, role)
        VALUES ('admin', 'System Administrator', 'admin@aics.edu.ph', 'admin123', 'admin')
    """)
    cursor.execute("UPDATE students SET role='admin' WHERE student_id='admin' AND role=''")

    # ── Sample professors ────────────────────────────────────────────────
    sample_professors = [
        ("T001", "Annalisa Magnaye", "annalisa@aics.edu.ph", "prof123", "BSCOMSCIE"),
        ("T002", "Yasmin", "yasmin@aics.edu.ph", "prof123", "BSCOMSCIE"),
        ("T003", "Roshell Salvador", "roshell@aics.edu.ph", "prof123", "BSCOMSCIE"),
        ("T004", "Ogie Cutmora", "ogie@aics.edu.ph", "prof123", "BSCOMSCIE"),
        ("T005", "Jobert Cruz", "jobert@aics.edu.ph", "prof123", "BSCOMSCIE"),
    ]
    for emp_id, name, email, pwd, dept in sample_professors:
        cursor.execute("""
            INSERT OR IGNORE INTO professors (employee_id, fullname, email, password, department)
            VALUES (?, ?, ?, ?, ?)
        """, (emp_id, name, email, pwd, dept))

    # ── Sample campus ────────────────────────────────────────────────────
    cursor.execute("""
        INSERT OR IGNORE INTO campuses (id, code, name, address)
        VALUES (1, 'MAIN', 'AICS Main Campus', 'Manila, Philippines')
    """)

    # ── Sample departments ───────────────────────────────────────────────
    departments = [
        ("BSCOMSCIE", "Bachelor of Science in Computer Science", 1),
        ("BSIT", "Bachelor of Science in Information Technology", 1),
        ("BSBA", "Bachelor of Science in Business Administration", 1),
        ("BSED", "Bachelor of Science in Education", 1),
    ]
    for code, name, campus_id in departments:
        cursor.execute("""
            INSERT OR IGNORE INTO departments (code, name, campus_id)
            VALUES (?, ?, ?)
        """, (code, name, campus_id))

    # ── Sample courses ───────────────────────────────────────────────────
    courses = [
        ("BSCS", "Bachelor of Science in Computer Science", 1),
        ("BSIT", "Bachelor of Science in Information Technology", 2),
        ("BSBA-MGT", "BSBA Major in Management", 3),
    ]
    for code, name, dept_id in courses:
        cursor.execute("""
            INSERT OR IGNORE INTO courses (code, name, department_id)
            VALUES (?, ?, ?)
        """, (code, name, dept_id))

    # ── Sample sections ──────────────────────────────────────────────────
    sections = [
        ("BSCS-1A", "BSCS Year 1 Section A", 1, "1st Year"),
        ("BSCS-1B", "BSCS Year 1 Section B", 1, "1st Year"),
        ("BSCS-2A", "BSCS Year 2 Section A", 1, "2nd Year"),
        ("BSCS-3A", "BSCS Year 3 Section A", 1, "3rd Year"),
        ("BSCS-4A", "BSCS Year 4 Section A", 1, "4th Year"),
        ("BSIT-1A", "BSIT Year 1 Section A", 2, "1st Year"),
    ]
    for code, name, course_id, year_level in sections:
        cursor.execute("""
            INSERT OR IGNORE INTO sections (code, name, course_id, year_level)
            VALUES (?, ?, ?, ?)
        """, (code, name, course_id, year_level))

    # ── Academic Year ────────────────────────────────────────────────────
    cursor.execute("""
        INSERT OR IGNORE INTO academic_years (id, code, name, start_date, end_date, is_current)
        VALUES (1, 'AY2024-2025', 'Academic Year 2024-2025', '2024-08-01', '2025-05-31', 1)
    """)

    # ── Semesters ────────────────────────────────────────────────────────
    semesters_data = [
        (1, "SEM1", "1st Semester", 1, "2024-08-01", "2024-12-20", 1),
        (2, "SEM2", "2nd Semester", 1, "2025-01-06", "2025-05-31", 0),
    ]
    for sid, code, name, ay_id, start, end, current in semesters_data:
        cursor.execute("""
            INSERT OR IGNORE INTO semesters (id, code, name, academic_year_id, start_date, end_date, is_current)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (sid, code, name, ay_id, start, end, current))

    # ── School Year (junction) ───────────────────────────────────────────
    cursor.execute("""
        INSERT OR IGNORE INTO school_years (id, code, academic_year_id, semester_id, name, is_current)
        VALUES (1, 'AY2024-2025-SEM1', 1, 1, 'AY 2024-2025 — 1st Semester', 1)
    """)
    cursor.execute("""
        INSERT OR IGNORE INTO school_years (id, code, academic_year_id, semester_id, name, is_current)
        VALUES (2, 'AY2024-2025-SEM2', 1, 2, 'AY 2024-2025 — 2nd Semester', 0)
    """)

    # ── Sample buildings ─────────────────────────────────────────────────
    buildings_data = [
        ("MB", "Main Building", 1),
        ("SB", "Science Building", 1),
        ("LB", "Library", 1),
    ]
    for code, name, campus_id in buildings_data:
        cursor.execute("""
            INSERT OR IGNORE INTO buildings (code, name, campus_id)
            VALUES (?, ?, ?)
        """, (code, name, campus_id))

    # ── Sample classrooms ────────────────────────────────────────────────
    classrooms_data = [
        ("MB101", "Room 101", 1, 40),
        ("MB102", "Room 102", 1, 35),
        ("MB201", "Room 201", 1, 30),
        ("SB101", "Science Lab 101", 2, 25),
    ]
    for code, name, bldg_id, cap in classrooms_data:
        cursor.execute("""
            INSERT OR IGNORE INTO classrooms (code, name, building_id, capacity)
            VALUES (?, ?, ?, ?)
        """, (code, name, bldg_id, cap))

    # ── Announcement Categories ──────────────────────────────────────────
    ann_cats = [
        ("GENERAL", "General", "General announcements", "#2F69FF"),
        ("ACADEMIC", "Academic", "Academic-related announcements", "#17C3A2"),
        ("EVENT", "Events", "Upcoming events", "#F59E0B"),
        ("URGENT", "Urgent", "Urgent notices", "#E11D48"),
    ]
    for code, name, desc, color in ann_cats:
        cursor.execute("""
            INSERT OR IGNORE INTO announcement_categories (code, name, description, color)
            VALUES (?, ?, ?, ?)
        """, (code, name, desc, color))

    # ── Event Categories ─────────────────────────────────────────────────
    evt_cats = [
        ("ACADEMIC", "Academic", "Academic events", "#2F69FF"),
        ("SPORTS", "Sports", "Sports events", "#17C3A2"),
        ("CULTURAL", "Cultural", "Cultural events", "#F59E0B"),
        ("HOLIDAY", "Holiday", "Holidays and breaks", "#E11D48"),
        ("MEETING", "Meeting", "Meetings and conferences", "#8B5CF6"),
    ]
    for code, name, desc, color in evt_cats:
        cursor.execute("""
            INSERT OR IGNORE INTO event_categories (code, name, description, color)
            VALUES (?, ?, ?, ?)
        """, (code, name, desc, color))

    # ── Emergency Contacts ───────────────────────────────────────────────
    emergency_contacts_data = [
        ("Campus Security", "0917-123-4567", "24/7 Campus Security Hotline", 1, 1),
        ("Emergency Hotline", "911", "National Emergency Hotline", 0, 1),
        ("Medical Clinic", "0917-123-4568", "Campus Medical Clinic", 2, 1),
        ("IT Support", "0917-123-4569", "IT Help Desk", 3, 1),
    ]
    for name, phone, desc, priority, campus_id in emergency_contacts_data:
        cursor.execute("""
            INSERT OR IGNORE INTO emergency_contacts (name, phone, description, priority, campus_id)
            VALUES (?, ?, ?, ?, ?)
        """, (name, phone, desc, priority, campus_id))

    # ── Office Directory ──────────────────────────────────────────────────
    offices = [
        ("Registrar's Office", "Student records, enrollment, and registration", "Ground Floor, Main Building", "02-1234-5678", "registrar@aics.edu.ph", "8:00 AM - 5:00 PM", "Registrar", 1),
        ("Accounting Office", "Tuition and financial concerns", "Ground Floor, Main Building", "02-1234-5679", "accounting@aics.edu.ph", "8:00 AM - 5:00 PM", "Accountant", 1),
        ("Student Affairs", "Student services and activities", "2nd Floor, Main Building", "02-1234-5680", "osa@aics.edu.ph", "8:00 AM - 5:00 PM", "OSA Director", 1),
        ("Library", "School library and learning resources", "3rd Floor, Main Building", "02-1234-5681", "library@aics.edu.ph", "7:00 AM - 7:00 PM", "Librarian", 1),
        ("IT Office", "Technical support and computer labs", "2nd Floor, Science Building", "02-1234-5682", "it@aics.edu.ph", "8:00 AM - 5:00 PM", "IT Head", 1),
    ]
    for name, desc, loc, phone, email, hours, head, campus_id in offices:
        cursor.execute("""
            INSERT OR IGNORE INTO office_directory (office_name, description, location, phone, email, office_hours, head_officer, campus_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (name, desc, loc, phone, email, hours, head, campus_id))

    conn.commit()
    conn.close()
    print("✅ Database migration completed successfully!")
    print(f"   Database: {DB_PATH}")
    print(f"   Existing tables preserved: students, professors, announcements, subjects, schedules, attendance, attendance_sessions, api_tokens")
    print(f"   New tables added: campuses, buildings, classrooms, departments, courses, sections, academic_years, semesters, school_years, student_sections, professor_subjects, enrollments, grades, new_attendance_sessions, attendance_records, announcement_categories, event_categories, events, notifications, system_logs, lost_found, office_directory, emergency_contacts, campus_map_locations, downloads")


if __name__ == "__main__":
    run_migration()

