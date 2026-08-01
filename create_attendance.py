import sqlite3

conn = sqlite3.connect("campusconnect.db")
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS attendance (

    id INTEGER PRIMARY KEY AUTOINCREMENT,

    student_id TEXT,

    fullname TEXT,

    subject_code TEXT,

    subject_name TEXT,

    professor TEXT,

    date TEXT,

    time TEXT,

    status TEXT

)
""")

conn.commit()
conn.close()

print("Attendance table created successfully!")