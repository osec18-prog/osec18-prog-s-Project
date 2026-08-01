# CampusConnect+ (Flutter app)

Mobile client for the existing CampusConnect+ Flask system. The phone app does
not carry its own database — it talks to the same `campusconnect.db` through the
JSON API in `../api.py`, so the web admin panel and the app always agree.

```
Phone (Flutter)  ──HTTP/JSON──▶  Flask (app.py + api.py)  ──▶  campusconnect.db
                                            ▲
Browser (admin) ────────────────────────────┘
```

## 1. Start the server

On the PC that holds the database:

```powershell
cd ..            # the folder with app.py
python app.py    # listens on 0.0.0.0:5000
```

Find that PC's address with `ipconfig` and note the IPv4 address, e.g.
`192.168.1.5`. The phone must be on the same Wi-Fi network.

> If port 5000 seems to serve old code, close every stale `python app.py`
> window first — several servers can bind the same port on Windows and the
> oldest one answers.

## 2. Run the app

```powershell
flutter pub get
flutter run                 # phone or emulator
flutter build apk --release # installable APK -> build/app/outputs/flutter-apk/
```

Building for Android needs the Android SDK (install Android Studio, then
`flutter doctor` should show a green Android toolchain).

On first launch the app asks for the server address:

| Where the app runs | Address to enter |
| --- | --- |
| Physical phone on campus Wi-Fi | `http://192.168.1.5:5000` (your PC's IP) |
| Android emulator | `http://10.0.2.2:5000` |
| Same PC / Chrome | `http://127.0.0.1:5000` |

The address and login are remembered; change them later from the avatar menu in
the top-right.

## 3. Signing in

| Role | Identifier | Notes |
| --- | --- | --- |
| Student | Student ID | Same account as the website; can also self-register |
| Professor | Email or Employee ID | Needs a password set in the professors table |
| Admin | `admin` | Default password `admin123` |

## What each role gets

**Student** — dashboard with today's classes, announcements feed, class
schedule, attendance history, and a camera QR scanner that records attendance
straight to the server (duplicates, expired codes and closed sessions are all
rejected server-side).

**Professor** — class list, generate an attendance QR for a class (the code is
shown full-screen for students to scan), and a live attendance view that polls
every 10 seconds while students scan in.

**Admin** — counts dashboard, announcement posting/editing/deleting, subject and
schedule management, student and professor directories, QR generation, and the
live attendance view for every professor.

## Layout

```
lib/
  api/            api_client.dart (HTTP calls), models.dart (JSON -> Dart)
  state/          app_state.dart — server address + session, persisted
  screens/
    server_setup_screen.dart, login_screen.dart, register_screen.dart
    student/      student_shell.dart, scan_screen.dart
    professor/    professor_shell.dart
    admin/        admin_shell.dart, admin_manage_screen.dart
    shared/       announcements, generate_qr, active_sessions, account sheet
  widgets/        common.dart — AsyncList, StatTile, SectionCard, Pill…
  theme.dart      colours matched to the web dashboard
```

## Tests

```powershell
flutter analyze
flutter test
```

## API endpoints used

All under `/api`, authenticated with `Authorization: Bearer <token>` from
`POST /api/login`.

| Method | Path | Role |
| --- | --- | --- |
| POST | `/login`, `/register`, `/logout` | any |
| GET | `/me`, `/ping` | any |
| GET | `/announcements` | any |
| POST/PUT/DELETE | `/announcements[/id]` | admin |
| GET | `/subjects`, `/schedules` | any |
| POST/DELETE | `/subjects[/id]`, `/schedules[/id]` | admin |
| GET | `/students`, `/professors`, `/stats` | admin |
| POST | `/qr/create` | professor, admin |
| GET | `/attendance/sessions` | professor, admin |
| POST | `/attendance/sessions/<id>/close` | professor, admin |
| POST | `/attendance/scan` | student |
| GET | `/attendance/mine` | student |
| GET | `/attendance` | professor, admin |
