# Installation Guide

## Requirements

- Python 3.11 or newer (`runtime.txt` pins 3.11.0 for Render)
- Windows, macOS, or Linux
- Flutter SDK — only if you intend to rebuild the mobile client

## 1. Get the code

Place the project anywhere you like. If it is not already a Git repository,
initialise one before making changes:

```powershell
git init
git add .
git commit -m "CampusConnect+ baseline"
```

This is strongly recommended. The project has already survived two incidents
where a file was corrupted by pasted text and had to be reconstructed from
compiled bytecode.

## 2. Install dependencies

```powershell
python -m pip install -r requirements.txt
```

This installs Flask, Flask-WTF (CSRF), PyJWT, qrcode, Pillow and gunicorn.

## 3. Set the required environment variables

```powershell
setx SECRET_KEY     "<random 64-char hex>"
setx JWT_SECRET     "<a different random 64-char hex>"
setx ADMIN_PASSWORD "<your administrator password>"
```

Generate the random values with:

```powershell
python -c "import secrets; print(secrets.token_hex(32))"
```

**Open a new terminal afterwards** — `setx` does not affect the current one.

See [ENVIRONMENT_VARIABLES.md](ENVIRONMENT_VARIABLES.md) for the full list.

## 4. Create the database

```powershell
python init_db.py
```

This creates `campusconnect.db` with all tables and seeds:

- one administrator (`admin`), password taken from `ADMIN_PASSWORD`, stored hashed
- five sample professors (`T001`–`T005`), password `prof123` unless you set
  `SEED_PROFESSOR_PASSWORD`, stored hashed

It is safe to run again — every statement is `CREATE TABLE IF NOT EXISTS` or
`INSERT OR IGNORE`, so existing data is never overwritten.

## 5. Run

```powershell
python app.py
```

The server listens on `0.0.0.0:5000`, so other devices on the same Wi-Fi can
reach it at `http://<your-lan-ip>:5000` — necessary for scanning QR codes with
a phone.

Check it is alive:

```powershell
curl http://127.0.0.1:5000/test      # -> Server is working!
curl http://127.0.0.1:5000/api/ping  # -> {"service":"CampusConnect+","success":true}
```

## 6. Log in

| Role | Where | Credentials |
|---|---|---|
| Administrator | `/admin_login` | `admin` + your `ADMIN_PASSWORD` |
| Professor | `/professor_login` | seeded professor email + `prof123` |
| Student | `/login` | create one at `/signup` |

## Rebuilding the Flutter web client (optional)

```powershell
cd campusconnect_app
flutter build web
```

Copy the contents of `campusconnect_app/build/web` into
`static/flutter_app/`. Flask serves it at `/app/`.

## Troubleshooting

| Symptom | Cause |
|---|---|
| `CampusConnect+ cannot start: SECRET_KEY is not set` | Environment variable missing. If you used `setx`, open a new terminal. |
| `ModuleNotFoundError: No module named 'jwt'` | Run `pip install -r requirements.txt`. The package is `PyJWT`, the module is `jwt`. |
| `Address already in use` | A previous server is still running. Find it with `Get-NetTCPConnection -LocalPort 5000` and stop that process. |
| Phone cannot reach the server | Use the LAN IP, not `localhost`, and make sure both devices are on the same network. |
| `400 Bad Request` on a form | Missing CSRF token. Reload the page rather than resubmitting an old tab. |
