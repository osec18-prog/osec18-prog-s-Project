# Architecture

## Overview

```
                    ┌──────────────────────────────┐
   Browser ────────▶│  app.py                      │
   (session cookie) │  • web routes                │
                    │  • CSRF, security headers    │
                    │  • session auth              │
                    └──────────┬───────────────────┘
                               │
   Flutter  ───────▶┌──────────▼───────────────────┐
   (bearer token)   │  api.py  (/api blueprint)    │
                    │  • JSON endpoints            │
                    │  • bearer + JWT auth         │
                    │  • CSRF-exempt               │
                    └──────────┬───────────────────┘
                               │
                    ┌──────────▼───────────────────┐
                    │  core.py                     │
                    │  • DB access + schema        │
                    │  • password policy           │
                    │  • QR parse / attendance     │
                    │  • rate limiting             │
                    └──────────┬───────────────────┘
                               │
                    ┌──────────▼───────────────────┐
                    │  campusconnect.db  (SQLite)  │
                    └──────────────────────────────┘
```

## The three modules

**`core.py`** — everything both front doors need. No Flask imports beyond
Werkzeug's password helpers. If a rule exists in only one place, it lives here:

- `ensure_schema()` — idempotent migrations, run at every start
- `get_db()` — connection with `sqlite3.Row` factory
- `check_password_with_migration()` — the single definition of "is this password correct"
- `parse_qr()` / `parse_professor_qr()` — QR payload formats
- `attendance_session_active()` / `insert_attendance()` — shared by all four scan paths
- `rate_limit_hit()` / `rate_limit_reset()` — in-memory sliding window

**`app.py`** — the browser-facing app. Owns the Flask instance, session config,
CSRF protection, security headers and logging. Registers the API blueprint.

**`api.py`** — a Flask blueprint mounted at `/api`. Authenticates with bearer
tokens rather than cookies, which is why it is CSRF-exempt.

## Two authentication systems, on purpose

They are genuinely different and must not be merged:

| | Browser | Flutter |
|---|---|---|
| Credential | Signed session cookie | `Authorization: Bearer …` |
| Set by | `session[...]` in `app.py` | `api_tokens` row + JWT |
| CSRF risk | Yes — cookies ride along automatically | No — headers do not |
| Logout | `session.clear()` | Delete token row, revoke `jti` |

Because the mobile client cannot obtain a CSRF token, `csrf.exempt(api)` is
required. Removing that line breaks every Flutter write.

## Request flow: taking attendance

1. Professor authenticates their identity by scanning their own QR at
   `/verify_professor_qr`, which sets `session["verified_professor_id"]`.
2. Professor opens `/generate_qr` and submits `/create_qr`. The server checks
   `verified_professor_id` matches `professor_id` before doing anything.
3. A row is written to `attendance_sessions` with a random `token` and an
   `expires_at`, and a QR image is rendered from the nine-field payload.
4. A student scans it. Three routes can accept the scan:
   - `/mark_attendance` — browser redirect flow
   - `/api/attendance/record` — the in-page scanner (`scan_qr.html`), session auth
   - `/api/attendance/scan` — the Flutter client, bearer auth
5. All three call the same `core` helpers: parse, check expiry, check the
   session is still `active=1`, check for a duplicate, then insert.
6. `/api/attendance/sync` replays records queued offline, returning a
   per-record `synced` / `skipped` / `failed` verdict.

## Why the duplication was removed

Those four scan paths each used to contain their own copy of the validation and
both INSERT variants — roughly 170 lines of copy-paste. A bug fixed in one was
not fixed in the others. They now share `attendance_session_active()` and
`insert_attendance()`.

## Schema evolution

`ensure_schema()` runs on every start and only ever adds. Each statement is
`CREATE TABLE IF NOT EXISTS` or an `ALTER TABLE` inside a try/except for
`OperationalError`. Nothing is ever dropped or rewritten, so starting an older
database against newer code upgrades it in place.

`core.migrate_schema()` also exists and creates thirteen further tables
(departments, courses, events, notifications, …). **It is never called.** Those
tables do not exist in the live database and the `api.py` endpoints that query
them return 500. They are an unfinished feature, not a broken one.

## Known architectural debt

- **Route organisation.** `app.py` is around 2,000 lines with roughly 55 routes.
  Splitting it into blueprints (auth, admin, professor, student, attendance,
  announcement, schedule, reports) is the obvious next refactor. Only three
  `url_for()` calls reference route endpoints, all in `announcements.html`, so
  the split is low-risk — but it is still a refactor and should be done with a
  regression suite in place.
- **Positional row access.** Several views use `SELECT *` with tuple indexing
  (`professor[1]`). Adding a column in the middle of a table would break them
  silently. New code uses named access.
- **No connection pooling.** Every query opens a new SQLite connection. Fine at
  this scale; it would not be at ten thousand users.
