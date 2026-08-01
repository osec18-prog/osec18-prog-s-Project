import sqlite3

import os
print("DATABASE:", os.path.abspath("campusconnect.db"))

conn = sqlite3.connect("campusconnect.db")
cursor = conn.cursor()

cursor.execute("SELECT id, subject_code, subject_name, professor FROM schedules")

rows = cursor.fetchall()

print("TOTAL:", len(rows))

for row in rows:
    print(row)

conn.close()