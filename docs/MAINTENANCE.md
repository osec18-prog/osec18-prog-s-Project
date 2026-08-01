# Maintenance Guide

## Backups

The entire application state is one file: `campusconnect.db`.

```powershell
Copy-Item campusconnect.db "campusconnect.db.backup_$(Get-Date -Format yyyyMMdd_HHmmss)"
```

Do this before every upgrade, every schema change, and on a schedule you can
live with. Losing this file loses every student, professor, schedule and
attendance record.

To restore, stop the server, replace the file, start it again. `ensure_schema()`
will bring an older file up to date automatically.

## ⚠️ Data persistence on Render

**On Render's free tier the filesystem is ephemeral.** The database is recreated
on every deploy and on the periodic restarts Render performs (roughly weekly).
All data entered since the last deploy is lost.

Three options:

1. **Accept it** — fine for a demo or capstone defence. Re-seed with
   `init_db.py` and re-enter demo data before each showing.
2. **Attach a persistent disk** (paid plan). Add to `render.yaml`:
   ```yaml
   disk:
     name: campusconnect-data
     mountPath: /var/data
     sizeGB: 1
   ```
   and point the database at it by setting `DB_PATH` accordingly in `core.py`.
   Note that a persistent disk prevents zero-downtime deploys.
3. **Migrate to PostgreSQL** — the durable answer, and a substantial change.
   See below.

## PostgreSQL migration — scope, if you ever need it

Not done, and not recommended for a capstone. What it would involve:

- Replace roughly 50 `sqlite3.connect()` call sites with a `psycopg2` pool
- Change every `?` placeholder to `%s`
- `INTEGER PRIMARY KEY AUTOINCREMENT` → `SERIAL PRIMARY KEY`
- `INSERT OR IGNORE` → `INSERT ... ON CONFLICT DO NOTHING`
- Remove `PRAGMA` calls; rewrite `ensure_schema()` against `information_schema`
- Export and reload existing data with type coercion

That is a large change touching every data path, with real regression risk, for
no benefit at this scale. Do it only if the system goes into genuine multi-user
production.

## Routine checks

### Is the password migration finished?

```sql
SELECT COUNT(*) FROM students   WHERE password <> '';
SELECT COUNT(*) FROM professors WHERE password <> '';
```

Both zero means every account has logged in since the hash migration and the
legacy plaintext column holds nothing.

### Removing the legacy `password` column

Only once both counts are zero, and only deliberately:

1. Back up the database.
2. Remove `password` from the four INSERT statements in `app.py` and the one in
   `api.py`.
3. Delete the legacy branch in `core.check_password_with_migration()` so only
   the hash is checked.
4. `ALTER TABLE students DROP COLUMN password;` and the same for `professors`
   (SQLite 3.35+; older versions need a table rebuild).
5. **Fix `templates/edit_admin.html` line 46** — it uses `admin[4]`, a
   positional index that shifts when the column disappears.

Step 5 is the one that bites. Do not skip it.

### Clearing generated QR images

`static/qr/` accumulates a PNG per generated code and is never pruned.

```powershell
Get-ChildItem static\qr -Filter *.png |
  Where-Object { $_.LastWriteTime -lt (Get-Date).AddDays(-30) } |
  Remove-Item
```

Safe at any time — the images are regenerated on demand and the authoritative
data is in `attendance_sessions`.

### Expired attendance sessions

Sessions are never auto-closed, so the professor dashboard's "active sessions"
count includes long-expired ones. Scanning an expired code is still correctly
rejected, so this is cosmetic. To tidy up:

```sql
UPDATE attendance_sessions SET active = 0
WHERE active = 1 AND date < date('now', '-1 day');
```

### Revoked JWT table

Self-maintaining — expired entries are purged on each new revocation. No action
needed.

## Rotating secrets

See [ENVIRONMENT_VARIABLES.md](ENVIRONMENT_VARIABLES.md). Rotating
`SECRET_KEY` or `JWT_SECRET` simply logs everyone out; nothing is lost.

## Upgrading dependencies

```powershell
python -m pip install -r requirements.txt --upgrade
python -m py_compile app.py api.py core.py init_db.py
python app.py    # confirm it starts, then check a few pages
```

Flask-WTF and PyJWT are the two whose major versions could change behaviour —
CSRF token format and JWT decoding respectively. Read their changelogs before a
major bump.

## Log review

Failed logins and rate-limit triggers are logged at WARNING:

```
2026-08-01 13:03:07 WARNING campusconnect: login failed: student_id='230208' from 127.0.0.1
2026-08-01 13:05:22 WARNING campusconnect: rate limit: student login from 203.0.113.9
```

Repeated rate-limit warnings from one address indicate a brute-force attempt.
Block it at the network or hosting layer — the in-app limiter only slows it.

## Adding a professor or student

Prefer the admin UI (`/admin_professors`, `/admin_students`), which hashes the
password correctly. Direct SQL inserts must set `password_hash` and leave
`password` empty:

```python
from core import hash_password
cursor.execute(
    "INSERT INTO professors (employee_id, fullname, email, password, password_hash, department)"
    " VALUES (?,?,?,?,?,?)",
    ("T009", "Name", "email@aics.edu.ph", "", hash_password("their-password"), "BSCOMSCIE"),
)
```

An account with neither a password nor a hash cannot log in. Four seeded
professors are currently in that state.
