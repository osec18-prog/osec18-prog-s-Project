# CampusConnect+ Deployment Guide (Render — Free Tier)

## Overview

Your project has **two parts**:
1. **Flask Backend** — Python server that handles all data, API, and admin web panel
2. **Flutter App** — Client that connects to the Flask backend

**Deployment strategy:** We'll deploy the Flask backend on Render (free tier). The Flask server will also **serve the Flutter web build** so everything lives under one URL.

---

## Step 1: Check Flutter Installation

Open **Command Prompt** or **PowerShell** and run:

```powershell
flutter --version
```

You should see output like `Flutter 3.x.x`. If not, install Flutter first.

Check that web is enabled:

```powershell
flutter config --enable-web
```

Verify:

```powershell
flutter devices
```

You should see `Chrome` or `Web Server` listed.

---

## Step 2: Build Flutter Web

```powershell
cd campusconnect_app

# Clean previous builds
flutter clean

# Get dependencies
flutter pub get

# Build for web with base-href /app/
flutter build web --base-href=/app/
```

> **Note about `mobile_scanner`:** The QR camera scanner only works on Android/iOS. For web, we've created a placeholder screen that tells users to use the mobile app. The conditional import system (`scan_screen.dart`) automatically picks the correct version based on the platform.

If the build succeeds, you'll see output in `campusconnect_app/build/web/`.

---

## Step 3: Copy Flutter Web Build into Flask's Static Folder

Create the target directory and copy the build output:

```powershell
# From the MyCode directory:
mkdir static\flutter_app

# Copy everything from the Flutter web build
xcopy /E /I campusconnect_app\build\web\* static\flutter_app\
```

Verify the files exist:

```powershell
dir static\flutter_app
```

You should see `index.html`, `flutter_bootstrap.js`, `main.dart.js`, etc.

---

## Step 4: Initialize the Database (Local Test)

Run the database init script to create tables and seed default data:

```powershell
python init_db.py
```

Expected output:
```
Database initialized successfully!
Database path: C:\Users\secoc\OneDrive\Desktop\MyCode\campusconnect.db
```

---

## Step 5: Test Locally

Start the Flask server:

```powershell
python app.py
```

Open your browser and go to:

- **Admin panel:** `http://127.0.0.1:5000/` (login with admin/admin123)
- **Flutter web app:** `http://127.0.0.1:5000/app/`

Verify:
- The admin login page loads
- You can log in as admin (username: `admin`, password: `admin123`)
- The Flutter app at `/app/` loads and connects to the server

Press **Ctrl+C** to stop the server.

---

## Step 6: Prepare for GitHub (Required by Render)

Create a `.gitignore` at the project root:

```powershell
# Create .gitignore
echo venv/ > .gitignore
echo __pycache__/ >> .gitignore
echo *.pyc >> .gitignore
echo .DS_Store >> .gitignore
echo *.db >> .gitignore
echo static/flutter_app/ >> .gitignore
```

> **Note:** We ignore `static/flutter_app/` because the Flutter web build is large. You'll need to rebuild and copy it after deployment (Step 8).

Initialize Git and push to GitHub:

```powershell
# Initialize git
git init
git add .
git commit -m "Initial commit - CampusConnect+"

# Create a repository on GitHub first (https://github.com/new)
# Then connect and push:
git remote add origin https://github.com/YOUR_USERNAME/campusconnect-plus.git
git branch -M main
git push -u origin main
```

---

## Step 7: Create and Configure the PostgreSQL Database on Render

### Why use PostgreSQL instead of SQLite?

SQLite is file-based and works great for local development, but on Render's free tier, file storage is **ephemeral** — meaning your data can be lost when the service restarts. 

> **⚠️ IMPORTANT:** For a **fully free** deployment without any paid add-ons, you can still use SQLite. Just be aware that your data (student registrations, attendance records, etc.) may be lost on service restarts. The Render free web service does restart periodically (~once a week).

**Option A: Use SQLite (Simpler, but data may be lost on restart)**

If you're okay with this limitation, skip to Step 8.

**Option B: Add Render PostgreSQL (Free tier, 1 GB storage)**

1. In your [Render Dashboard](https://dashboard.render.com), click **New +** → **PostgreSQL**
2. Fill in:
   - **Name:** `campusconnect-db`
   - **Database:** `campusconnect`
   - **User:** `campusconnect_user`
   - **Region:** Choose the closest one
   - **Plan:** **Free**
3. Click **Create Database**
4. Wait for it to provision (2-3 minutes)
5. Copy the **Internal Database URL** (starts with `postgres://...`)

The free PostgreSQL database on Render persists data even when your web service restarts.

---

## Step 8: Deploy to Render

### 8.1: Update app.py for PostgreSQL (Optional)

If you chose to use PostgreSQL (Option B above), you need to update `core.py`, `app.py`, and `api.py` to use PostgreSQL instead of SQLite. Since your project currently uses SQLite throughout, **for this deployment guide we'll stick with SQLite** since it's simpler and the free PostgreSQL on Render requires code changes to switch from sqlite3 to psycopg2.

> **Future improvement:** If you need persistent data, consider migrating to PostgreSQL.

### 8.2: Set Up Web Service on Render

1. Log in to [Render Dashboard](https://dashboard.render.com)
2. Click **New +** → **Web Service**
3. Connect your GitHub repository (`campusconnect-plus`)
4. Fill in the details:

| Field | Value |
|-------|-------|
| **Name** | `campusconnect-plus` |
| **Region** | Choose closest (e.g., Singapore/Oregon) |
| **Branch** | `main` |
| **Runtime** | `Python 3` |
| **Build Command** | `pip install -r requirements.txt && python init_db.py` |
| **Start Command** | `gunicorn app:app --worker-class=gthread --threads=4 --bind=0.0.0.0:$PORT --timeout=120` |
| **Plan** | **Free** |

5. Click **Advanced** and add these environment variables:

| Key | Value |
|-----|-------|
| `SECRET_KEY` | Click **Generate** — **required**, the app will not start without it |
| `JWT_SECRET` | Click **Generate** — **required**, signs the mobile app's JWTs |
| `ADMIN_PASSWORD` | **Required** — type your own. This is the password for the built-in `admin` account. Do **not** click Generate; you need to be able to read it back. |
| `ADMIN_USERNAME` | Optional, defaults to `admin` |
| `FLASK_ENV` | `production` — also turns on `SESSION_COOKIE_SECURE` |
| `PYTHON_VERSION` | `3.11.0` |
| `QR_HOST_URL` | Leave empty (will auto-detect) |

> `SECRET_KEY`, `JWT_SECRET` and `ADMIN_PASSWORD` have no fallback values. If
> any is missing the server exits at startup with a message naming the
> variable. Use two **different** random values for the secrets, at least 32
> bytes each. The administrator password used to be the literal `admin123` in
> the source code — pick something else.

6. Click **Create Web Service**

### 8.3: First Deploy

Render will:
1. Clone your repository
2. Install Python dependencies
3. Run `init_db.py` to create the database
4. Start the server

Wait for the deploy to finish (5-10 minutes). Look for:
```
--> Deploying...
--> Starting service with gunicorn...
--> Server is UP
```

Your app will be available at: `https://campusconnect-plus.onrender.com`

---

## Step 9: Build and Upload Flutter Web

Since we ignored `static/flutter_app/` in Git, you need to build and add the Flutter web files after each deploy.

### Option A: Manual Upload (Recommended for beginners)

1. Build Flutter web locally:
```powershell
cd campusconnect_app
flutter build web --base-href=/app/
cd ..
```

2. Copy to static folder:
```powershell
xcopy /E /I campusconnect_app\build\web\* static\flutter_app\
```

3. Deploy the static folder separately using Render's **Static Site** feature:
   - In Render Dashboard, click **New +** → **Static Site**
   - Connect the same GitHub repo
   - **Root Directory:** `static/flutter_app`
   - **Build Command:** Leave empty
   - **Publish Directory:** `.`
   - **Plan:** **Free**

   - Under **Redirect/Rewrite Rules**, add:
     - **Source:** `/app/*`
     - **Destination:** `/index.html`
     - **Action:** **Rewrite**

   This gives you a separate URL like `https://campusconnect-plus-app.onrender.com`.

### Option B: Include in Git (Simpler but larger repo)

1. Build and copy:
```powershell
cd campusconnect_app
flutter build web --base-href=/app/
cd ..
xcopy /E /I campusconnect_app\build\web\* static\flutter_app\
```

2. Remove `static/flutter_app/` from `.gitignore`
3. Commit and push to GitHub:
```powershell
git add -A
git commit -m "Add Flutter web build"
git push
```

4. Render will automatically redeploy

---

## Step 10: Verify Everything

After deployment, test these URLs:

### Web Admin Panel
```
https://campusconnect-plus.onrender.com/
```
- Login as **admin** / **admin123**
- Manage students, professors, subjects, schedules, announcements
- Generate QR codes and view attendance reports

### Flutter Web App (if using Static Site)
```
https://campusconnect-plus-app.onrender.com/app/
```
- Login as student, professor, or admin
- View dashboard, announcements, schedule, attendance history
- QR scanning placeholder (use mobile app for actual scanning)

### API Health Check
```
https://campusconnect-plus.onrender.com/test
```
Should show: `Server is working!`

### API Ping
```
https://campusconnect-plus.onrender.com/api/ping
```
Should return JSON with `"service": "CampusConnect+"`

---

## Step 11: Build the Android APK (for QR Scanning)

The QR scanner only works on Android. Build the APK:

```powershell
cd campusconnect_app
flutter build apk --release
```

The APK will be at:
```
campusconnect_app\build\app\outputs\flutter-apk\app-release.apk
```

Install this on students' phones. They'll enter the server URL (`https://campusconnect-plus.onrender.com`) on first launch.

---

## Default Accounts

| Role | Username/ID | Password |
|------|-------------|----------|
| **Admin** | `admin` | `admin123` |
| **Professor** | `T001` (Annalisa Magnaye) | `prof123` |
| **Professor** | `T002` (Yasmin) | `prof123` |
| **Professor** | `T003` (Roshell Salvador) | `prof123` |
| **Professor** | `T004` (Ogie Cutmora) | `prof123` |
| **Professor** | `T005` (Jobert Cruz) | `prof123` |
| **Student** | (self-register or admin creates) | (set during registration) |

---

## Important Notes

### Data Persistence
**SQLite on Render Free Tier:** Data is stored in a file (`campusconnect.db`) on the server's disk. Render's free web services use **ephemeral storage**, meaning:
- Data survives service restarts (Render does NOT restart free services frequently)
- Data will be **lost** if you delete and recreate the service
- For permanent data storage, consider Render's **PostgreSQL Free Tier** ($0/month, 1 GB storage)

### Flutter Web Limitations
- **QR Camera Scanning:** Not available on web. The web app shows an information screen directing users to the Android app.
- **Offline Support:** Not available on web. Requires a stable internet connection.

### Updating the App
When you make changes:
1. Update the Flask backend → push to GitHub → Render auto-deploys
2. Update Flutter app → rebuild web → rebuild APK → redeploy static site or re-upload

### Monitoring
- Render Dashboard shows logs, CPU, and memory usage
- Free tier includes **90 hours/month** of server runtime (more than enough for development)
- Service auto-sleeps after 15 minutes of inactivity
- Wakes up on first request (may take 30 seconds)

---

## Troubleshooting

### "Application Error" on Render
Check logs in Render Dashboard. Common issues:
- Missing `requirements.txt` → verify file exists
- Port conflict → ensure `$PORT` is used (we already handle this)
- Database not initialized → run `init_db.py`

### "flutter build web" Fails
- Run `flutter clean` first
- Run `flutter pub get` 
- If `mobile_scanner` causes issues, ensure conditional imports are correct
- Try `flutter build web --no-tree-shake-icons` if icons are missing

### Flutter App Can't Connect to Server
- On Android emulator: use `http://10.0.2.2:5000`
- On web: should auto-detect from the URL
- On physical device: use the full Render URL
- Ensure the server is running and accessible

### CORS Errors
The API already has CORS headers configured. If you see CORS errors:
- Verify `api.py` has the `@api.after_request` CORS handler
- Check that the Flutter web app is using the correct URL

---

## Files Created/Modified for Deployment

| File | Purpose |
|------|---------|
| `requirements.txt` | Python dependencies for Render |
| `runtime.txt` | Python version |
| `Procfile` | Gunicorn start command |
| `render.yaml` | Render infrastructure config |
| `init_db.py` | Database initialization script |
| `app.py` | (modified) Production config + Flutter web serving |
| `scan_screen.dart` | Conditional import (web vs mobile) |
| `scan_screen_web.dart` | Web placeholder for QR scanner |
| `scan_screen_mobile.dart` | Mobile camera scanner (same as original) |
| `main.dart` | (modified) Auto-detect server URL on web |
| `DEPLOYMENT_GUIDE.md` | This document |

---

**Congratulations!** Your CampusConnect+ app is now live on the internet for anyone to access through their web browser. Students can use the web app for checking announcements, schedules, and attendance history. For QR scanning, they'll need the Android APK.

