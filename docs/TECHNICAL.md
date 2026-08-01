# Technical Notes

## Password storage

`werkzeug.security` scrypt hashes (`scrypt:32768:8:1$...`).

The migration from plaintext is **lazy**. `core.check_password_with_migration()`
is the only place the rule lives:

```
password_hash set?
├── yes → verify_password() only. The plaintext column is ignored entirely.
└── no  → compare the legacy plaintext column
          ├── match → hash it, verify the hash round-trips, save it,
          │            blank the plaintext, allow the login
          └── no match → reject
```

The hash is verified against the same password *before* the plaintext is
cleared. If that check ever failed, the login still succeeds and the row is left
untouched — a user can never be locked out by the migration.

Accounts that have never logged in since the migration still hold plaintext.
Check the current state with:

```sql
SELECT COUNT(*) FROM students   WHERE password <> '';
SELECT COUNT(*) FROM professors WHERE password <> '';
```

The legacy `password` column must not be dropped until both are zero. See
[MAINTENANCE.md](MAINTENANCE.md) for the removal plan.

## The built-in administrator

There are two different admin identities and they are easy to confuse:

| | Built-in admin | Seeded admin row |
|---|---|---|
| Stored where | `ADMIN_PASSWORD` env var | `students` table, `role='admin'` |
| Logs in at | `/admin_login`, `/api/login` | `/login` |
| Password change | Edit the environment variable | `/edit_admin` |

Changing one does not change the other.

## Session cookies

```python
SESSION_COOKIE_HTTPONLY = True          # JavaScript cannot read it
SESSION_COOKIE_SAMESITE = "Lax"         # not sent on cross-site POSTs
SESSION_COOKIE_SECURE   = IS_PRODUCTION # HTTPS-only when FLASK_ENV=production
```

`SECURE` is deliberately off in development. The LAN server runs over plain
HTTP, and switching it on there would stop the cookie being sent at all.

## CSRF

Flask-WTF `CSRFProtect` covers every browser route. Forms carry:

```html
<input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
```

`fetch()` calls in `scan_qr.html` send `X-CSRFToken` instead, read from a meta
tag in the page head.

`csrf.exempt(api)` exempts the whole `/api` blueprint. This is correct, not a
shortcut: that blueprint authenticates with a bearer token, so a cross-site form
post cannot carry credentials, and the Flutter client has no way to obtain a
token.

Six routes that changed data over GET were converted to POST:
`delete_student`, `delete_professor`, `delete_subject`, `delete_schedule`,
`delete_announcement`, `close_attendance_session`. Previously an
`<img src="/delete_student/5">` on any page would delete a record while an
admin was logged in.

`edit_*` routes remain GET — they only render a form.

## JWT and revocation

Issued with a 72-hour expiry and a random `jti`:

```json
{ "role": "...", "user_id": "...", "fullname": "...",
  "jti": "<uuid4>", "iat": ..., "exp": ... }
```

Logout inserts the `jti` into `revoked_jwts`; `_verify_jwt()` rejects anything
listed. Expired entries are purged opportunistically on each revocation, so the
table cannot grow without bound.

Tokens issued before revocation existed have no `jti`. They are still accepted —
deliberately, so nobody was logged out by the upgrade — but cannot be revoked
individually. They age out within 72 hours.

## Rate limiting

`core.rate_limit_hit(key, limit=10, window_seconds=300)` — an in-memory sliding
window keyed by client IP, applied to `/login`, `/admin_login`,
`/professor_login`, `/api/login` and `/api/auth/login`. Over the limit returns
HTTP 429. A successful login clears the counter.

Limitations, stated plainly: the state is per process and resets on restart, and
separate gunicorn workers do not share it. For a single instance this is
adequate. Scaling out requires Redis or similar.

`X-Forwarded-For` is honoured so the limit applies to the real client behind
Render's proxy, not to the proxy itself.

## Security headers

Set on every response by `security_headers()`:

| Header | Value |
|---|---|
| `X-Content-Type-Options` | `nosniff` |
| `X-Frame-Options` | `SAMEORIGIN` |
| `Referrer-Policy` | `same-origin` |
| `Permissions-Policy` | `geolocation=(), microphone=()` |
| `Strict-Transport-Security` | `max-age=31536000; includeSubDomains` (production only) |

### Content-Security-Policy — not set, and why

The templates load Bootstrap and the QR library from `cdn.jsdelivr.net`,
`cdnjs.cloudflare.com` and `unpkg.com`, and contain fifteen inline handlers and
script blocks. A policy permissive enough to allow all that would need
`'unsafe-inline'`, which removes most of the protection, while still risking
breakage that cannot be verified without a browser.

The correct sequence is: bundle those three libraries into `static/`, replace
the inline `onsubmit=` handlers with attached listeners, then adopt:

```
Content-Security-Policy:
  default-src 'self';
  script-src 'self';
  style-src 'self';
  img-src 'self' data:;
  frame-ancestors 'self';
  base-uri 'self';
  form-action 'self'
```

## QR payload format

Attendance QR codes carry pipe-delimited data, not a URL:

```
subject_code|subject_name|professor_id|professor_name|day|schedule|date|expires_at|token
```

Nine fields is v2. Five fields is the legacy v1 format
(`subject_code|subject_name|professor|day|schedule`) and is still accepted on
scan, so old printed codes keep working.

Professor identity codes use four: `PROF|employee_id|fullname|token`.

Validation order on scan, and it matters:

1. Parse — reject if the field count is neither 5 nor 9
2. Expiry — v2 only, compared against `date` + `expires_at`
3. Session active — the `attendance_sessions` row must have `active=1`
4. Duplicate — by `uuid`, then by student + token
5. Insert

Because expiry is checked before the session lookup, an expired code reports
"QR code expired" rather than "session is not active", which is the more useful
message.

## Logging

`logging.basicConfig` at DEBUG locally, INFO in production. Logger names:
`campusconnect` (web) and `campusconnect.api`.

Security-relevant events are logged: successful logins with role and IP, failed
logins with the attempted identifier, and every rate-limit trigger. Passwords
are never logged.

Under gunicorn the app logger inherits gunicorn's handlers, so records reach
Render's log stream without extra configuration.
