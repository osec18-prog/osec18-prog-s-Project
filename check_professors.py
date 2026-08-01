import sqlite3

conn = sqlite3.connect("campusconnect.db")
cursor = conn.cursor()

print("=== TABLE STRUCTURE ===")
cursor.execute("PRAGMA table_info(professors)")
for row in cursor.fetchall():
    print(row)

print("\n=== PROFESSORS DATA ===")
cursor.execute("SELECT * FROM professors")
for row in cursor.fetchall():
    print(row)

conn.close()