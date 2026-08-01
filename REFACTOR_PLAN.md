\i99999\
999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999990000000000000000000000000000000000000#




















 CampusConnect+ Redesign Plan

## Current State Assessment
- Flask backend with SQLite, HTML templates (Jinja2), and JSON API
- Flutter frontend with conditional web/mobile support
- Separate login pages (login.html, admin_login.html, professor_login.html)
- Basic RBAC via session roles and api_tokens table
- No password hashing (plaintext)
- ~30 HTML template files, ~20 Flutter Dart files

---

## Phase 1: Backend Security & Database (5 files)

### File 1: `core.py` — Password Hashing + Helpers
- Add `generate_password_hash(password)` and `check_password_hash(password, hash)` using `werkzeug.security`
- Add database migration helpers for new tables
- Keep all existing functionality

### File 2: `database.py` — Normalized Schema
- Add tables: `departments`, `courses`, `sections`
- Add `grades` table (future-ready)
- Add `events`, `calendar` tables
- Add `notifications` table
- Add `system_logs` table
- Add foreign key relationships
- Add `password_hash` column to students and professors
- Migration script to preserve existing data

### File 3: `api.py` — JWT Auth + New Endpoints
- Replace bearer tokens with proper JWT (PyJWT)
- Add password hashing on login/register
- Add new API endpoints: profile, grades, calendar, events, notifications
- Add department/course/section CRUD
- Add system logs

### File 4: `app.py` — Unified Login + Route Protection
- **Unified login page** at `/` that handles all 3 roles
- Remove separate `/admin_login` and `/professor_login` routes
- Add `@require_role` decorators on all dashboard routes
- Redirect to appropriate dashboard after login
- Add new routes for departments, courses, sections, settings, logs
- Add grades route (placeholder)

### File 5: `init_db.py` — Updated Seed Data
- Seed departments, courses, sections
- Seed hashed passwords
- Preserve all existing seed data

---

## Phase 2: HTML Templates Consolidation (select files)

### File 6: `templates/login.html` — Unified Login (replaces 3 login templates)
- Single login form with role dropdown OR auto-detect from identifier
- Clean modern UI

### File 7: `templates/admin_dashboard.html` — Expanded Admin
- Add tabs/sections for: Analytics, Departments, Courses, Sections, System Logs, Settings
- Keep all existing management features

### File 8: `templates/professor_dashboard.html` — Expanded Professor
- Add tabs for: Profile, Students list, Messages, Settings
- Keep all existing features

### File 9: `templates/dashboard.html` — Expanded Student
- Add tabs for: Profile, Grades, Calendar, Events, Lost & Found, etc.
- Keep all existing features

---

## Phase 3: Flutter Data Layer (2 files)

### File 10: `lib/api/models.dart` — New Models
- Add `Department`, `Course`, `Section`, `Grade`, `CalendarEvent`, `Notification`, `SystemLog`, `EmergencyContact`, `LostFoundItem`
- Enhance existing models with new fields

### File 11: `lib/api/api_client.dart` — New API Calls
- Add methods for all new endpoints
- Add profile update, grade fetching, calendar, events, notifications

---

## Phase 4: Flutter State & Auth (1 file)

### File 12: `lib/state/app_state.dart` — Enhanced State
- Add notification badge state
- Add profile cache
- Enhanced error handling

---

## Phase 5: Flutter Screens (many files)

### File 13: `lib/screens/login_screen.dart` — Unified Login (refined)
- Already supports 3 roles, just needs polishing
- Add "forgot password" placeholder

### File 14: `lib/screens/student/student_shell.dart` — Expanded Student Navigation
- Add all new sections: Profile, Grades, Calendar, Events, Lost & Found, Office Directory, Campus Map, Emergency Contacts, Downloads, Settings
- Use drawer + bottom nav combination for这么多 items

### File 15-N: Individual Student Screens
- `profile_screen.dart`
- `grades_screen.dart`
- `calendar_screen.dart`
- `events_screen.dart`
- `lost_found_screen.dart`
- `office_directory_screen.dart`
- `campus_map_screen.dart`
- `emergency_contacts_screen.dart`
- `downloads_screen.dart`
- `settings_screen.dart`

### File 16: Professor Shell + new screens
- `professor_shell.dart` — Add Students, Profile, Messages, Settings tabs
- `professor_students_screen.dart`
- `professor_messages_screen.dart`

### File 17: Admin Shell + new screens
- `admin_shell.dart` — Add Departments, Courses, Sections, Logs, Settings
- `admin_departments_screen.dart`
- `admin_courses_screen.dart`
- `admin_sections_screen.dart`
- `admin_logs_screen.dart`
- `admin_settings_screen.dart`

---

## Implementation Order (One File at a Time)

I will implement in this exact order, waiting for your approval after EACH file:

1. **`core.py`** — Password hashing, DB migration helpers
2. **`database.py`** — Normalized schema (new tables)
3. **`api.py`** — JWT auth, password hashing, new endpoints
4. **`app.py`** — Unified login, route protection, new routes
5. **`init_db.py`** — Updated seed data
6. **`templates/login.html`** — Unified login page
7. **Flutter `models.dart`** — New data models
8. **Flutter `api_client.dart`** — New API calls
9. **Flutter `app_state.dart`** — Enhanced state
10. **Student shell + new screens** (multiple Flutter files)
11. **Professor shell + new screens** (multiple Flutter files)
12. **Admin shell + new screens** (multiple Flutter files)

---

## Key Design Decisions

1. **Password Hashing**: Use `werkzeug.security.generate_password_hash` — industry standard, already a Flask dependency
2. **JWT**: Use `PyJWT` library with HS256, tokens expire in 24h
3. **Unified Login**: Auto-detect role from identifier format (@ = professor, admin prefix, else student)
4. **Route Protection**: Flask `@login_required` decorator that checks session role
5. **Database**: Add new normalized tables WITHOUT breaking existing ones — use ALTER TABLE / migration pattern
6. **Flutter Navigation**: Use NavigationDrawer for secondary features (profile, settings) + BottomNavigationBar for primary tabs

