import sqlite3

conn = sqlite3.connect("campusconnect.db")
cursor = conn.cursor()

# Check all tables
cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
tables = cursor.fetchall()
print("Tables:", tables)

# Check schedules columns
cursor.execute("PRAGMA table_info(schedules)")
print("\nSchedules columns:")
for col in cursor.fetchall():
    print(f"  {col[1]} ({col[2]})")

# Check professors columns
cursor.execute("PRAGMA table_info(professors)")
print("\nProfessors columns:")
for col in cursor.fetchall():
    print(f"  {col[1]} ({col[2]})")

# Check if professor_id exists in schedules
cursor.execute("PRAGMA table_info(schedules)")
sched_cols = [col[1] for col in cursor.fetchall()]
print("\nDoes schedules have professor_id?", "professor_id" in sched_cols)
print("Does schedules have password column?", "password" in sched_cols)

# Check professors password column
cursor.execute("PRAGMA table_info(professors)")
prof_cols = [col[1] for col in cursor.fetchall()]
print("Does professors have password?", "password" in prof_cols)

# Try the queries from app.py get_qr_schedules()
try:
    cursor.execute("""
        SELECT s.id,
               s.subject_code,
               s.subject_name,
               s.professor,
               s.day,
               s.time,
               COALESCE(p.employee_id, '') AS professor_id
        FROM schedules s
        LEFT JOIN professors p
            ON TRIM(s.professor)=TRIM(p.fullname)
        ORDER BY s.subject_code
    """)
    print("\n✅ get_qr_schedules() query works!")
except Exception as e:
    print(f"\n❌ get_qr_schedules() query failed: {e}")

# Try the create_qr query
try:
    cursor.execute("""
        SELECT
            s.subject_code,
            s.subject_name,
            s.professor,
            s.day,
            s.time,
            COALESCE(p.employee_id, '') AS professor_id
        FROM schedules s
        LEFT JOIN professors p
            ON s.professor_id=p.employee_id
        WHERE s.id=1
    """)
    print("✅ create_qr() query works!")
except Exception as e:
    print(f"❌ create_qr() query failed: {e}")

conn.close()

