# CampusConnect+ Database Schema

Generated from `campusconnect.db` on 2026-08-01. Engine: **SQLite**.

Schema changes are applied by `core.ensure_schema()`, which runs on every
start. Every statement is `CREATE TABLE IF NOT EXISTS` or an `ALTER TABLE`
wrapped in a try/except, so it is safe to run repeatedly and never destroys
data.

## Tables

### `announcements`  — 2 row(s)

| Column | Type | Not null | Default | PK |
|---|---|---|---|---|
| `id` | INTEGER |  |  | yes |
| `title` | TEXT |  |  |  |
| `description` | TEXT |  |  |  |
| `date_created` | TIMESTAMP |  | CURRENT_TIMESTAMP |  |

### `api_tokens`  — 1 row(s)

| Column | Type | Not null | Default | PK |
|---|---|---|---|---|
| `token` | TEXT |  |  | yes |
| `role` | TEXT |  |  |  |
| `user_id` | TEXT |  |  |  |
| `fullname` | TEXT |  |  |  |
| `created_at` | TIMESTAMP |  | CURRENT_TIMESTAMP |  |

### `attendance`  — 5 row(s)

| Column | Type | Not null | Default | PK |
|---|---|---|---|---|
| `id` | INTEGER |  |  | yes |
| `student_id` | TEXT |  |  |  |
| `fullname` | TEXT |  |  |  |
| `subject_code` | TEXT |  |  |  |
| `subject_name` | TEXT |  |  |  |
| `professor` | TEXT |  |  |  |
| `date` | TEXT |  |  |  |
| `time` | TEXT |  |  |  |
| `status` | TEXT |  |  |  |
| `uuid` | TEXT |  |  |  |
| `professor_id` | TEXT |  |  |  |
| `professor_name` | TEXT |  |  |  |
| `day` | TEXT |  |  |  |
| `schedule` | TEXT |  |  |  |
| `token` | TEXT |  |  |  |

### `attendance_sessions`  — 12 row(s)

| Column | Type | Not null | Default | PK |
|---|---|---|---|---|
| `id` | INTEGER |  |  | yes |
| `professor_id` | TEXT |  |  |  |
| `professor_name` | TEXT |  |  |  |
| `subject_code` | TEXT |  |  |  |
| `subject_name` | TEXT |  |  |  |
| `day` | TEXT |  |  |  |
| `schedule` | TEXT |  |  |  |
| `date` | TEXT |  |  |  |
| `expires_at` | TEXT |  |  |  |
| `token` | TEXT |  |  |  |
| `active` | INTEGER |  | 1 |  |
| `created_at` | TIMESTAMP |  | CURRENT_TIMESTAMP |  |

### `professors`  — 12 row(s)

| Column | Type | Not null | Default | PK |
|---|---|---|---|---|
| `id` | INTEGER |  |  | yes |
| `employee_id` | TEXT |  |  |  |
| `fullname` | TEXT |  |  |  |
| `email` | TEXT |  |  |  |
| `department` | TEXT |  |  |  |
| `password` | TEXT |  |  |  |
| `password_hash` | TEXT |  |  |  |

### `revoked_jwts`  — 0 row(s)

| Column | Type | Not null | Default | PK |
|---|---|---|---|---|
| `jti` | TEXT |  |  | yes |
| `expires_at` | INTEGER |  |  |  |
| `revoked_at` | TIMESTAMP |  | CURRENT_TIMESTAMP |  |

### `schedules`  — 5 row(s)

| Column | Type | Not null | Default | PK |
|---|---|---|---|---|
| `id` | INTEGER |  |  | yes |
| `subject_code` | TEXT |  |  |  |
| `subject_name` | TEXT |  |  |  |
| `professor` | TEXT |  |  |  |
| `day` | TEXT |  |  |  |
| `time` | TEXT |  |  |  |
| `room` | TEXT |  |  |  |
| `year_level` | TEXT |  |  |  |
| `semester` | TEXT |  |  |  |
| `professor_id` | TEXT |  |  |  |
| `class_type` | TEXT |  |  |  |

### `students`  — 10 row(s)

| Column | Type | Not null | Default | PK |
|---|---|---|---|---|
| `id` | INTEGER |  |  | yes |
| `student_id` | TEXT |  |  |  |
| `fullname` | TEXT |  |  |  |
| `email` | TEXT |  |  |  |
| `password` | TEXT |  |  |  |
| `role` | TEXT |  | 'student' |  |
| `password_hash` | TEXT |  |  |  |

### `subjects`  — 12 row(s)

| Column | Type | Not null | Default | PK |
|---|---|---|---|---|
| `id` | INTEGER |  |  | yes |
| `subject_code` | TEXT |  |  |  |
| `subject_name` | TEXT |  |  |  |
| `professor` | TEXT |  |  |  |
| `year_level` | TEXT |  |  |  |
| `semester` | TEXT |  |  |  |

## Indexes

| Index | Table | Definition |
|---|---|---|
| `idx_attendance_uuid` | `attendance` | `CREATE UNIQUE INDEX idx_attendance_uuid ON attendance(uuid)` |

## Notes on specific columns

- **`students.password` / `professors.password`** — legacy plaintext. Emptied
  the first time an account logs in after the hash migration. Kept only so
  accounts that have not logged in since can still be verified once.
- **`students.password_hash` / `professors.password_hash`** — scrypt hash
  produced by `werkzeug.security`. Once set, it is the only thing checked.
- **`attendance.professor`** — v1 records. **`attendance.professor_name`** —
  v2 records. The API returns whichever is populated.
- **`attendance.uuid`** — client-supplied id used to de-duplicate offline
  scans. Has a UNIQUE index.
- **`attendance.token`** — links a record to the `attendance_sessions` row
  whose QR was scanned.
- **`revoked_jwts.jti`** — JWT ids invalidated by logout. Rows are purged
  once the token would have expired anyway.
- **`schedules.time`** — a display string such as `8:00 AM - 10:00 AM`, not a
  sortable value. See the known issues in README.md.
