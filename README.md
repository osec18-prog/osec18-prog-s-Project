# CampusConnect+

A campus attendance and announcements system for AICS. A Flask backend serves
both a server-rendered web app (students, professors, administrators) and a JSON
API consumed by a Flutter mobile/web client. Attendance is taken by scanning a
QR code that a professor generates for a specific class session.

---

## Quick start

```powershell
# 1. Install dependencies
python -m pip install -r requirements.txt

# 2. Set the three required secrets (once, then open a NEW terminal)
setx SECRET_KEY     "<random 64-char hex>"
setx JWT_SECRET     "<a different random 64-char hex>"
setx ADMIN_PASSWORD "<your administrator password>"

# Generate a good random value with:
#   python -c "import secrets; print(secrets.token_hex(32))"

# 3. Create the database (first run only)
python init_db.py

# 4. Run
python app.py
```

Then open <http://127.0.0.1:5000>. `GET /test` returns `Server is working!` if
the server is up.

The app **will not start** without the three variables above — this is
deliberate. Earlier versions fell back to hard-coded defaults, which meant
anyone with a copy of the source could forge a login session.

---

## Documentation

| Document | What it covers |
|---|---|
| [docs/INSTALLATION.md](docs/INSTALLATION.md) | Local setup, step by step |
| [docs/ENVIRONMENT_VARIABLES.md](docs/ENVIRONMENT_VARIABLES.md) | Every variable, required and optional |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | How the pieces fit together |
| [docs/API.md](docs/API.md) | Every endpoint, generated from the running app |
| [docs/DATABASE_SCHEMA.md](docs/DATABASE_SCHEMA.md) | Every table and column |
| [docs/FLUTTER_INTEGRATION.md](docs/FLUTTER_INTEGRATION.md) | How the mobile client talks to the backend |
| [docs/TECHNICAL.md](docs/TECHNICAL.md) | Security model, QR format, design decisions |
| [docs/MAINTENANCE.md](docs/MAINTENANCE.md) | Backups, upgrades, routine tasks |
| [docs/ADMIN_MANUAL.md](docs/ADMIN_MANUAL.md) | For administrators |
| [docs/PROFESSOR_MANUAL.md](docs/PROFESSOR_MANUAL.md) | For professors |
| [docs/STUDENT_MANUAL.md](docs/STUDENT_MANUAL.md) | For students |
| [DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md) | Deploying to Render |

---

## Project layout

```
app.py                  Web routes, session auth, CSRF, security headers
api.py                  /api blueprint — JSON API for the Flutter client
core.py                 Shared: DB access, password policy, QR parsing, rate limiting
init_db.py              Creates and seeds a fresh database
templates/              Jinja2 templates for the web app
static/                 CSS, generated QR images, Flutter web build
campusconnect_app/      Flutter client source
docs/                   Documentation
```

`app.py` and `api.py` never duplicate business logic — anything both need lives
in `core.py`.

---

## Security model at a glance

| Concern | How it is handled |
|---|---|
| Passwords | scrypt hashes via `werkzeug.security`. Legacy plaintext is verified once, then upgraded and cleared. |
| Browser sessions | Signed cookie, `HttpOnly`, `SameSite=Lax`, `Secure` in production. |
| Mobile auth | Bearer token in `api_tokens`, plus a JWT with a `jti` that logout revokes. |
| CSRF | Flask-WTF on every browser form. The `/api` blueprint is exempt (bearer auth). |
| Brute force | 10 login attempts per IP per 5 minutes, then HTTP 429. |
| Headers | `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`, `Permissions-Policy`, HSTS in production. |

Full detail in [docs/TECHNICAL.md](docs/TECHNICAL.md).

---

## Known issues and limitations

These are real and unresolved. None of them block normal use.

1. **SQLite on Render's free tier is ephemeral.** The database file is recreated
   on every deploy and periodic restart, so attendance records and
   registrations are lost. Fix: attach a persistent disk (paid plan) or migrate
   to PostgreSQL. See [docs/MAINTENANCE.md](docs/MAINTENANCE.md).
2. **No Content-Security-Policy.** The templates load Bootstrap and the QR
   library from three CDNs and use inline event handlers, so a policy strict
   enough to be worth having would break the UI. Bundle those assets locally
   first, then adopt the policy in [docs/TECHNICAL.md](docs/TECHNICAL.md).
3. **`schedules.time` is a display string** (`8:00 AM - 10:00 AM`), so
   `ORDER BY day, time` sorts alphabetically rather than chronologically.
   Fixing it properly needs `start_time` / `end_time` columns and a migration.
4. **`QR_HOST_URL` has no effect.** Its only consumer, `build_host_url()`, is
   never called — QR payloads are pipe-delimited data, not URLs. The variable
   is still documented because removing it would be a config change.
5. **Rate limiting is per process and in memory.** It resets on restart and is
   not shared between workers. Adequate for a single instance; use Redis if you
   scale out.
6. **JWTs issued before revocation existed have no `jti`** and cannot be
   revoked individually. They expire on their own within 72 hours.
7. **The project is not under version control.** `git init` is strongly
   recommended before any further work.

---

## Running the tests

There is no automated test suite committed to the repository. Verification
during development was done with throwaway harnesses that ran against a **copy**
of the database. If you add tests, mirror that approach — never let a test write
to `campusconnect.db`.
