# Environment Variables

## Required — the app refuses to start without these

| Variable | Purpose | How to choose a value |
|---|---|---|
| `SECRET_KEY` | Signs the browser session cookie. Anyone who knows it can forge a logged-in session, including an admin one. | `python -c "import secrets; print(secrets.token_hex(32))"` |
| `JWT_SECRET` | Signs the mobile app's JWTs. Must be **different** from `SECRET_KEY`. | Same command, run again |
| `ADMIN_PASSWORD` | Password for the built-in `admin` account. Used by `/admin_login` and `/api/login`. | Pick your own. It used to be a literal string in the source code — do not reuse that value. |

If any is missing, the server exits at startup and prints a message naming the
variable and the exact command to set it.

## Optional

| Variable | Default | Effect |
|---|---|---|
| `ADMIN_USERNAME` | `admin` | Username for the built-in administrator. Not a secret. |
| `FLASK_ENV` | *(unset)* | Set to `production` to enable `SESSION_COOKIE_SECURE` and HSTS, and to raise the log level from DEBUG to INFO. |
| `SEED_PROFESSOR_PASSWORD` | `prof123` | Password given to the five sample professors that `init_db.py` seeds. Only affects a **fresh** database. |
| `QR_HOST_URL` | *(empty)* | Currently has **no effect** — see known issue 4 in the README. |

## Setting them

### Windows, current terminal only

```powershell
$env:SECRET_KEY     = "..."
$env:JWT_SECRET     = "..."
$env:ADMIN_PASSWORD = "..."
python app.py
```

### Windows, permanently

```powershell
setx SECRET_KEY     "..."
setx JWT_SECRET     "..."
setx ADMIN_PASSWORD "..."
```

`setx` does **not** affect the terminal you run it in. Open a new one.

### Render

Set them under **Environment** in the service dashboard. `render.yaml` already
declares all three:

- `SECRET_KEY` and `JWT_SECRET` use `generateValue: true`, so Render creates
  strong values for you.
- `ADMIN_PASSWORD` uses `sync: false`, meaning you type it in the dashboard.
  `generateValue` would produce a password you cannot read back, which is
  useless for an account you need to log in to.

## Rotating a secret

| Variable | What breaks when you change it |
|---|---|
| `SECRET_KEY` | Every browser session is invalidated. Users log in again. Harmless. |
| `JWT_SECRET` | Every outstanding JWT stops validating. Mobile users log in again. Legacy bearer tokens in `api_tokens` are unaffected. |
| `ADMIN_PASSWORD` | Only the built-in admin login changes. Note this does **not** change the seeded `admin` row in the `students` table — that has its own hashed password. |

Rotate `SECRET_KEY` and `JWT_SECRET` if you ever committed them, pasted them
into a chat, or shared a screenshot of them.
