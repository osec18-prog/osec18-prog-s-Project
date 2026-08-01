# CampusConnect+ API Reference

Generated from the running application on 2026-08-01.

Base URL: `http://<host>:5000` locally, or your Render URL in production.

## Authentication

`POST /api/login` returns **two** credentials:

| Field | What it is | Used by |
|---|---|---|
| `token` | Opaque bearer token stored in `api_tokens` | The Flutter app |
| `jwt` | Signed JWT, expires in 72 hours, carries a `jti` | Newer clients |

Send either as `Authorization: Bearer <value>`. The server accepts both.

`POST /api/logout` deletes the bearer token and, if a JWT was presented,
adds its `jti` to the `revoked_jwts` table so it stops working immediately.

### Standard response shape

```json
{ "success": true,  "<payload key>": ... }
{ "success": false, "message": "Human readable reason" }
```

| Status | Meaning |
|---|---|
| 200 / 201 | Success |
| 400 | Validation failed |
| 401 | Missing or invalid credentials |
| 403 | Authenticated, but wrong role |
| 404 | Not found |
| 409 | Conflict (duplicate attendance, duplicate code) |
| 429 | Too many login attempts |

> The `/api` blueprint is exempt from CSRF because it authenticates with a
> bearer token rather than the session cookie. Do **not** send a CSRF token.

## JSON API endpoints

| Method | Route | Auth required |
|---|---|---|
| GET | `/api/announcements` | any logged-in user |
| POST | `/api/announcements` | admin |
| DELETE | `/api/announcements/<int:announcement_id>` | admin |
| PUT | `/api/announcements/<int:announcement_id>` | admin |
| GET | `/api/attendance` | admin, professor |
| GET | `/api/attendance/mine` | student |
| POST | `/api/attendance/record` | none |
| POST | `/api/attendance/scan` | student |
| GET | `/api/attendance/sessions` | admin, professor |
| POST | `/api/attendance/sessions/<int:session_id>/close` | admin, professor |
| POST | `/api/attendance/sync` | none |
| POST | `/api/auth/login` | none |
| GET | `/api/courses` | any logged-in user |
| GET | `/api/departments` | any logged-in user |
| GET | `/api/events` | any logged-in user |
| POST | `/api/events` | admin |
| POST | `/api/login` | none |
| POST | `/api/logout` | any logged-in user |
| GET | `/api/me` | any logged-in user |
| GET | `/api/notifications` | any logged-in user |
| GET | `/api/ping` | none |
| GET | `/api/professors` | admin |
| POST | `/api/qr/create` | admin, professor |
| POST | `/api/register` | none |
| GET | `/api/schedules` | any logged-in user |
| POST | `/api/schedules` | admin |
| DELETE | `/api/schedules/<int:schedule_id>` | admin |
| GET | `/api/sections` | any logged-in user |
| GET | `/api/stats` | admin |
| GET | `/api/students` | admin |
| GET | `/api/subjects` | any logged-in user |
| POST | `/api/subjects` | admin |
| DELETE | `/api/subjects/<int:subject_id>` | admin |

## Browser routes (session cookie + CSRF token)

| Method | Route |
|---|---|
| GET | `/` |
| GET | `/active_attendance` |
| POST | `/add_announcement` |
| GET/POST | `/add_professor` |
| POST | `/add_schedule` |
| GET/POST | `/add_student` |
| POST | `/add_subject` |
| GET | `/admin_announcements` |
| GET | `/admin_attendance` |
| GET | `/admin_dashboard` |
| GET/POST | `/admin_login` |
| GET | `/admin_professors` |
| GET | `/admin_reports` |
| GET | `/admin_schedules` |
| GET | `/admin_students` |
| GET | `/admin_subjects` |
| GET | `/app/` |
| GET | `/app/<path:filename>` |
| POST | `/close_attendance_session/<int:session_id>` |
| POST | `/create_qr` |
| GET | `/dashboard` |
| POST | `/delete_announcement/<int:id>` |
| POST | `/delete_professor/<int:id>` |
| POST | `/delete_schedule/<int:id>` |
| POST | `/delete_student/<int:id>` |
| POST | `/delete_subject/<int:id>` |
| GET | `/edit_admin` |
| GET | `/edit_announcement/<int:id>` |
| GET | `/edit_professor/<int:id>` |
| GET | `/edit_schedule/<int:id>` |
| GET | `/edit_student/<int:id>` |
| GET | `/edit_subject/<int:id>` |
| GET | `/generate_qr` |
| GET/POST | `/login` |
| GET | `/logout` |
| GET | `/mark_attendance` |
| GET | `/professor_dashboard` |
| GET/POST | `/professor_login` |
| GET | `/professor_logout` |
| GET | `/professor_qr` |
| GET/POST | `/professor_signup` |
| POST | `/register` |
| GET | `/scan_qr` |
| GET | `/signup` |
| GET | `/student_announcements` |
| GET | `/student_attendance` |
| GET | `/student_schedule` |
| GET | `/test` |
| POST | `/update_admin` |
| POST | `/update_announcement` |
| POST | `/update_professor` |
| POST | `/update_schedule` |
| POST | `/update_student` |
| POST | `/update_subject` |
| GET/POST | `/verify_professor_qr` |

Every browser form that changes data must include:

```html
<input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
```

`fetch()` calls may send the token as an `X-CSRFToken` header instead.

## QR payload format

Attendance QR codes are pipe-delimited, not URLs.

```
subject_code|subject_name|professor_id|professor_name|day|schedule|date|expires_at|token
```

Nine fields is the current (v2) format. A five-field payload is the legacy
v1 format and is still accepted on scan:

```
subject_code|subject_name|professor|day|schedule
```

Professor identity QR codes use four fields: `PROF|employee_id|fullname|token`.
