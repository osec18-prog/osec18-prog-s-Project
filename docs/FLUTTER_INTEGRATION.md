# Flutter Integration Guide

The Flutter client lives in `campusconnect_app/`. It talks to the backend
exclusively through the `/api` blueprint.

## Client structure

| File | Role |
|---|---|
| `lib/api/api_client.dart` | Every HTTP call. The single source of truth for what the backend must provide. |
| `lib/api/models.dart` | `fromJson` factories. These define the exact JSON keys the backend must return. |
| `lib/state/app_state.dart` | Token storage, current user |
| `lib/screens/…` | UI |

If you change a backend response shape, check `models.dart` first — the field
names there are the contract.

## Pointing the app at a server

`server_setup_screen.dart` calls `GET /api/ping` to confirm an address is a
CampusConnect+ server. The endpoint is deliberately unauthenticated, since it
runs before login, and must return:

```json
{ "success": true, "service": "CampusConnect+" }
```

The client rejects any response where `service` is not exactly
`CampusConnect+`.

For a phone on the same Wi-Fi, use the machine's LAN address
(`http://192.168.x.x:5000`), not `localhost`.

## Authentication

```dart
final json = await _send('POST', '/api/login', body: {
  'role': roleToString(role),   // 'student' | 'professor' | 'admin'
  'identifier': identifier,     // student_id, employee_id, email, or 'admin'
  'password': password,
});
```

Response:

```json
{
  "success": true,
  "token": "<uuid bearer token>",
  "jwt":   "<signed JWT, 72h>",
  "user":  { "role": "student", "user_id": "230208", "fullname": "..." }
}
```

The client stores `token` and sends `Authorization: Bearer <token>`. The server
accepts either credential — it tries the JWT first, then falls back to the
bearer token table.

`POST /api/logout` invalidates whichever one was presented.

After ten failed attempts from one IP within five minutes, login returns **429**
with the usual `{"success": false, "message": "..."}` shape. Surface `message`
to the user; it explains the wait.

## Endpoints the client uses

| Method | Route | Model |
|---|---|---|
| GET | `/api/ping` | — |
| POST | `/api/login`, `/api/register`, `/api/logout` | `AppUser` |
| GET | `/api/me` | `AppUser` |
| GET | `/api/announcements` | `Announcement` |
| POST/PUT/DELETE | `/api/announcements[/<id>]` | — |
| GET | `/api/subjects` | `Subject` |
| POST/DELETE | `/api/subjects[/<id>]` | — |
| GET | `/api/schedules` | `ClassSchedule` |
| POST/DELETE | `/api/schedules[/<id>]` | — |
| GET | `/api/professors` | `Professor` |
| GET | `/api/students` | — |
| GET | `/api/stats` | — |
| POST | `/api/qr/create` | `AttendanceSession` |
| GET | `/api/attendance/sessions` | `AttendanceSession` |
| POST | `/api/attendance/sessions/<id>/close` | — |
| POST | `/api/attendance/scan` | — |
| GET | `/api/attendance/mine` | `AttendanceRecord` |
| GET | `/api/attendance` | `AttendanceRecord` |

## Role scoping

The backend filters by the authenticated role, so the client does not have to:

- `/api/schedules` — a professor sees only their own classes unless `?all=1`
- `/api/attendance` — admin sees everything, a professor sees only records from
  their own sessions
- `/api/attendance/sessions` — same scoping
- `/api/attendance/mine` — students only

Calling an endpoint your role is not allowed to use returns **403**, not an
empty list. Distinguish the two in the UI.

## The QR flow

1. Professor: `POST /api/qr/create` with `{"schedule_id": 1, "expires_at": "23:59"}`
2. Response contains `session.payload` — render **that string** as the QR image.
   Do not construct the payload client-side; the `token` inside it comes from
   the server.
3. Student: scan, then `POST /api/attendance/scan` with `{"qr": "<payload>"}`

Responses to expect:

| Status | Message | Meaning |
|---|---|---|
| 200 | `Attendance Recorded Successfully.` | Done |
| 409 | `Duplicate attendance detected.` | Already marked for this session |
| 400 | `QR code expired.` | Past `expires_at` |
| 400 | `Attendance session is not active.` | Professor closed it |
| 400 | `Invalid QR code.` | Not a CampusConnect+ payload |

All five are normal outcomes. Show `message` directly.

## CSRF

Do **not** send a CSRF token to `/api/*`. The blueprint is exempt because it
uses bearer authentication. Sending one is harmless but pointless.

`/api/attendance/record` and `/api/attendance/sync` are **not** part of the
blueprint — they live in `app.py`, authenticate by session cookie, and *do*
require a CSRF token. They exist for the in-browser scanner
(`templates/scan_qr.html`), not for Flutter. The Flutter equivalent is
`/api/attendance/scan`.

## Rebuilding the web build

```powershell
cd campusconnect_app
flutter build web
```

Copy `build/web/*` into `static/flutter_app/`. Flask serves it at `/app/` and
falls back to `index.html` so Flutter's own router handles deep links.
