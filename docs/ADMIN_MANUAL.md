# Administrator Manual

## Signing in

Go to **`/admin_login`**. The username is `admin` (unless `ADMIN_USERNAME` was
changed) and the password is whatever was set in `ADMIN_PASSWORD`.

There is a second way in: if your account exists in the students table with
`role = 'admin'`, you can sign in at `/login` with that student ID. These are
two separate accounts with separate passwords — changing one does not change the
other.

After ten wrong attempts you are locked out for five minutes.

## The dashboard

`/admin_dashboard` shows totals for students, professors, subjects, classes,
active attendance sessions and announcements, plus the full student list.

## Managing students

**`/admin_students`**

- **Add** — `/add_student`. The password is hashed immediately; it is never
  stored in readable form, and you cannot look it up later. If a student forgets
  it, set a new one.
- **Edit** — pencil icon. Changes ID, name and email. Does not touch passwords.
- **Delete** — asks for confirmation. **This cannot be undone**, and the
  student's attendance records remain in the database without them.

Students can also register themselves at `/signup`.

## Managing professors

**`/admin_professors`** — add, edit and delete, same pattern.

A professor needs a password to sign in. Four of the seeded sample professors
have none and cannot log in until you set one by deleting and re-adding them.

The `employee_id` matters: it links a professor to their schedules and to the QR
codes they generate. Changing it on an existing professor will orphan their
existing sessions.

## Subjects and schedules

**`/admin_subjects`** — the catalogue. Subject codes are unique.

**`/admin_schedules`** — assigns a subject to a professor, day, time, room, year
level, semester and class type. Only scheduled classes can have attendance QR
codes generated for them.

Two things to know:

- The professor is matched **by name**. If the name on the schedule does not
  exactly match a professor record, the schedule saves but QR generation later
  fails with "Selected subject has no registered professor."
- The schedule list sorts by day and time as **text**, so the order reads
  Friday, Monday, Saturday… and 10:00 AM before 8:00 AM. This is a known issue.

## Announcements

**`/admin_announcements`** — create, edit and delete. Every student sees them at
`/student_announcements`, and they appear in the Flutter app. Both title and
body are required. Timestamps are recorded in local time.

## Attendance and reports

**`/admin_attendance`** — every raw attendance record.
**`/admin_reports`** — a readable summary: student, subject, professor, date,
time, status.

Neither is paginated. With a few thousand records the page will get slow.

## Generating QR codes as an administrator

Administrators may use **`/generate_qr`** directly, without the identity
verification step professors go through. The subject's professor must already be
registered, since their `employee_id` is embedded in the code.

## Your own account

**`/edit_admin`** changes the name, email and password of the seeded admin row.

The password box is blank when the page loads — that is correct. Passwords are
hashed and cannot be displayed. Leave it blank to change only the name and
email; type a new one to change the password.

## Things that cannot be undone

- Deleting a student, professor, subject or schedule
- Changing a professor's `employee_id` after sessions exist

There is no undo and no soft delete. Back up `campusconnect.db` before bulk
changes.

## If something goes wrong

| Symptom | Likely cause |
|---|---|
| "Too many login attempts" | Rate limit. Wait five minutes. |
| Form rejected with a 400 | The page sat open too long and the CSRF token went stale. Reload and retry. |
| "Selected subject has no registered professor" | The professor name on the schedule does not match a professor record. |
| Data disappeared after a deploy | Render's free tier wipes the database on restart. See MAINTENANCE.md. |
