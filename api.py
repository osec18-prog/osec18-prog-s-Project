"""JSON API for the CampusConnect+ Flutter app (campusconnect_app/).

SUPPORTED AUTH MODES
────────────────────
1. Legacy bearer tokens (existing) — /api/login returns a UUID token
2. JWT tokens (new) — /api/auth/login returns a signed JWT
Both are accepted by require_auth for backward compatibility.

PASSWORD MIGRATION
──────────────────
All login endpoints check plaintext passwords first (backward-compatible),
then hashed passwords (new). On first successful plaintext login, the
password is automatically hashed and stored in password_hash.

UNIFIED LOGIN
─────────────
New unified /api/auth/login endpoint auto-detects the user role from the
identifier (student_id, employee_id, admin username). The old /api/login
is kept for Flutter app compatibility.
"""

import logging
import os
import sqlite3
import uuid
from datetime import datetime, timedelta
from functools import wraps

import jwt as pyjwt
from flask import Blueprint, g, jsonify, request, current_app

from core import (
    QR_SCHEDULE_SQL,
    attendance_exists,
    attendance_session_active,
    check_password_with_migration,
    format_time_range,
    get_db,
    hash_password,
    insert_attendance,
    parse_qr,
    parse_time_range,
    rate_limit_hit,
    rate_limit_reset,
    session_expired,
)

log = logging.getLogger("campusconnect.api")


def _client_ip():
    forwarded = request.headers.get("X-Forwarded-For", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.remote_addr or "unknown"

api = Blueprint("api", __name__, url_prefix="/api")

ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "admin")


def _admin_password():
    """Built-in administrator password. No fallback — a literal here would let
    anyone reading the source log in as an administrator. app.py validates
    ADMIN_PASSWORD at startup, so this only raises if the app was started some
    other way.
    """
    value = current_app.config.get("ADMIN_PASSWORD") or os.environ.get("ADMIN_PASSWORD")
    if not value:
        raise RuntimeError(
            "ADMIN_PASSWORD is not set. Set it in the environment before "
            "starting the server (see the startup message in app.py)."
        )
    return value

# ── JWT configuration (used by auth endpoints) ──────────────────────────
JWT_SECRET = None  # set on first use from app config
JWT_ALGORITHM = "HS256"
JWT_EXPIRY_HOURS = 72


def _get_jwt_secret():
    """Signing key for JWTs. No fallback — a known default would let anyone
    mint a valid admin token. app.py validates JWT_SECRET at startup, so
    reaching the error here means the app was started some other way.
    """
    global JWT_SECRET
    if JWT_SECRET is None:
        JWT_SECRET = current_app.config.get("JWT_SECRET") or os.environ.get("JWT_SECRET")
        if not JWT_SECRET:
            raise RuntimeError(
                "JWT_SECRET is not set. Set it in the environment before "
                "starting the server (see the startup message in app.py)."
            )
    return JWT_SECRET


# ── CORS ─────────────────────────────────────────────────────────────────

@api.after_request
def allow_cross_origin(response):
    """Let the Flutter web build call the API from a different origin.

    Safe here because the API authenticates with a bearer token rather than a
    cookie, so a browser cannot be tricked into sending credentials.
    """
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Headers"] = "Authorization, Content-Type"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS"
    return response


# ── AUTH HELPERS ─────────────────────────────────────────────────────────

def _bearer_token():
    """Extract bearer token from Authorization header or query string."""
    header = request.headers.get("Authorization", "")
    if header.startswith("Bearer "):
        return header[7:].strip()
    return request.args.get("token")


def _lookup_token(token):
    """Look up a legacy bearer token in api_tokens table."""
    if not token:
        return None
    conn = get_db()
    row = conn.execute(
        "SELECT token, role, user_id, fullname FROM api_tokens WHERE token=?",
        (token,),
    ).fetchone()
    conn.close()
    if not row:
        return None
    user = dict(row)
    user["kind"] = "legacy"
    return user


def _jti_revoked(jti):
    """True when this JWT id has been logged out."""
    if not jti:
        return False
    conn = get_db()
    row = conn.execute("SELECT 1 FROM revoked_jwts WHERE jti=?", (jti,)).fetchone()
    conn.close()
    return row is not None


def _revoke_jti(jti, expires_at):
    """Record a JWT id as logged out, and drop entries that have expired."""
    if not jti:
        return False
    conn = get_db()
    conn.execute(
        "INSERT OR IGNORE INTO revoked_jwts (jti, expires_at) VALUES (?,?)",
        (jti, int(expires_at or 0)),
    )
    # Housekeeping: a revoked token stops mattering once it would have expired.
    conn.execute(
        "DELETE FROM revoked_jwts WHERE expires_at > 0 AND expires_at < ?",
        (int(datetime.utcnow().timestamp()),),
    )
    conn.commit()
    conn.close()
    return True


def _verify_jwt(token):
    """Verify a JWT token and return user info dict or None.

    Tokens issued before revocation existed have no "jti" claim. They are still
    accepted so that Flutter sessions created earlier keep working; they simply
    cannot be revoked individually.
    """
    if not token:
        return None
    try:
        payload = pyjwt.decode(token, _get_jwt_secret(), algorithms=[JWT_ALGORITHM])
    except (pyjwt.ExpiredSignatureError, pyjwt.InvalidTokenError):
        return None

    jti = payload.get("jti")
    if _jti_revoked(jti):
        return None

    return {
        "token": token,
        "kind": "jwt",
        "jti": jti,
        "exp": payload.get("exp"),
        "role": payload.get("role"),
        "user_id": payload.get("user_id"),
        "fullname": payload.get("fullname"),
    }


def _authenticate_request():
    """Try JWT first, then legacy bearer token. Returns user dict or None."""
    token_str = _bearer_token()
    if not token_str:
        return None

    # Try JWT first (new auth)
    user = _verify_jwt(token_str)
    if user:
        return user

    # Fall back to legacy bearer token (old auth)
    return _lookup_token(token_str)


def require_auth(*roles):
    """Reject the request unless a valid token (JWT or legacy) is present.

    If *roles is non-empty, the authenticated user must have one of those
    roles.  This decorator works with both JWT tokens and legacy bearer
    tokens for full backward compatibility.
    """
    def decorator(view):
        @wraps(view)
        def wrapper(*args, **kwargs):
            user = _authenticate_request()
            if not user:
                return jsonify({"success": False, "message": "Authentication required."}), 401
            if roles and user["role"] not in roles:
                return jsonify({"success": False, "message": "Not allowed for this account."}), 403
            g.user = user
            return view(*args, **kwargs)
        return wrapper
    return decorator


def _issue_token(role, user_id, fullname):
    """Issue a legacy bearer token (UUID)."""
    token = str(uuid.uuid4())
    conn = get_db()
    conn.execute(
        "INSERT INTO api_tokens (token, role, user_id, fullname) VALUES (?,?,?,?)",
        (token, role, user_id, fullname),
    )
    conn.commit()
    conn.close()
    return token


def _issue_jwt(role, user_id, fullname):
    """Issue a signed JWT token with expiry."""
    payload = {
        "role": role,
        "user_id": user_id,
        "fullname": fullname,
        # Unique id so this specific token can be revoked at logout.
        "jti": str(uuid.uuid4()),
        "iat": datetime.utcnow(),
        "exp": datetime.utcnow() + timedelta(hours=JWT_EXPIRY_HOURS),
    }
    return pyjwt.encode(payload, _get_jwt_secret(), algorithm=JWT_ALGORITHM)


def _rows(cursor):
    return [dict(row) for row in cursor.fetchall()]


# ── PASSWORD HELPERS (backward-compatible) ───────────────────────────────

def _check_and_migrate_password(conn, table, id_column, identifier, password):
    """Check password against both plaintext and hash. Migrates on success.

    Returns the row dict if credentials match, None otherwise.
    This is backward-compatible: existing plaintext passwords still work,
    and on first successful login the hash is saved automatically.
    """
    cursor = conn.cursor()

    # Step 1: Fetch user row by identifier
    if table == "students":
        row = cursor.execute(
            f"SELECT * FROM {table} WHERE student_id=? OR email=?",
            (identifier, identifier),
        ).fetchone()
    elif table == "professors":
        row = cursor.execute(
            f"SELECT * FROM {table} WHERE email=? OR employee_id=?",
            (identifier, identifier),
        ).fetchone()
    else:
        return None

    if not row:
        return None

    # Step 2: policy lives in core.check_password_with_migration —
    #   * once password_hash is set it is the ONLY thing checked
    #   * legacy plaintext rows are verified once, then upgraded in place
    if check_password_with_migration(conn, table, id_column, row, password):
        return dict(row)

    return None


# =====================================================================
# SESSION ENDPOINTS
# =====================================================================

@api.post("/login")
def login():
    """Legacy login endpoint — kept for Flutter app backward compatibility.

    Accepts 'role' parameter (optional — auto-detected if missing).
    Returns a legacy bearer token AND a JWT token.
    """
    payload = request.get_json(silent=True) or {}
    role = (payload.get("role") or "").strip().lower()
    identifier = (payload.get("identifier") or "").strip()
    password = payload.get("password") or ""

    if not identifier or not password:
        return jsonify({"success": False, "message": "Please fill in every field."}), 400

    if rate_limit_hit("api_login:%s" % _client_ip()):
        log.warning("rate limit: api login from %s", _client_ip())
        return jsonify({
            "success": False,
            "message": "Too many login attempts. Please wait a few minutes and try again.",
        }), 429

    conn = get_db()
    user = None

    # ── Auto-detect role if not specified ──────────────────────────────
    if not role:
        user = _auto_detect_login(conn, identifier, password)
    else:
        # ── Admin login ────────────────────────────────────────────────
        if role == "admin":
            row = _check_and_migrate_password(
                conn, "students", "student_id", identifier, password
            )
            if row and row.get("role") == "admin":
                user = {
                    "role": "admin",
                    "user_id": row["student_id"],
                    "fullname": row["fullname"],
                }
            elif identifier == ADMIN_USERNAME and password == _admin_password():
                user = {"role": "admin", "user_id": "admin", "fullname": "Administrator"}

        # ── Professor login ────────────────────────────────────────────
        elif role == "professor":
            row = _check_and_migrate_password(
                conn, "professors", "employee_id", identifier, password
            )
            if row:
                user = {
                    "role": "professor",
                    "user_id": row["employee_id"],
                    "fullname": row["fullname"],
                }

        # ── Student login ──────────────────────────────────────────────
        else:
            row = _check_and_migrate_password(
                conn, "students", "student_id", identifier, password
            )
            if row:
                detected_role = row.get("role") or "student"
                user = {
                    "role": detected_role,
                    "user_id": row["student_id"],
                    "fullname": row["fullname"],
                }

    conn.close()

    if not user:
        log.warning("api login failed: identifier=%r from %s", identifier, _client_ip())
        return jsonify({"success": False, "message": "Invalid credentials."}), 401

    rate_limit_reset("api_login:%s" % _client_ip())
    log.info("api login ok: %s (%s) from %s",
             user["user_id"], user["role"], _client_ip())

    # Issue both token types for backward compatibility
    legacy_token = _issue_token(user["role"], user["user_id"], user["fullname"])
    jwt_token = _issue_jwt(user["role"], user["user_id"], user["fullname"])

    return jsonify({
        "success": True,
        "token": legacy_token,      # legacy — Flutter app uses this
        "jwt": jwt_token,           # new JWT token
        "user": user,
    })


@api.post("/auth/login")
def auth_login():
    """NEW unified login endpoint — auto-detects role.

    Does NOT require a 'role' field.  Automatically determines if the
    identifier is a student_id, employee_id/professor email, or admin
    username.  Returns a JWT token.
    """
    payload = request.get_json(silent=True) or {}
    identifier = (payload.get("identifier") or "").strip()
    password = payload.get("password") or ""

    if not identifier or not password:
        return jsonify({"success": False, "message": "Please fill in every field."}), 400

    if rate_limit_hit("api_login:%s" % _client_ip()):
        log.warning("rate limit: api auth/login from %s", _client_ip())
        return jsonify({
            "success": False,
            "message": "Too many login attempts. Please wait a few minutes and try again.",
        }), 429

    conn = get_db()
    user = _auto_detect_login(conn, identifier, password)
    conn.close()

    if not user:
        log.warning("api auth/login failed: identifier=%r from %s",
                    identifier, _client_ip())
        return jsonify({"success": False, "message": "Invalid credentials."}), 401

    rate_limit_reset("api_login:%s" % _client_ip())
    jwt_token = _issue_jwt(user["role"], user["user_id"], user["fullname"])

    return jsonify({
        "success": True,
        "jwt": jwt_token,
        "user": user,
    })


def _auto_detect_login(conn, identifier, password):
    """Try identifier as student_id, professor email/id, or admin username.

    Returns a user dict or None.
    """
    # 1. Try admin first
    row = _check_and_migrate_password(conn, "students", "student_id", identifier, password)
    if row and row.get("role") == "admin":
        return {"role": "admin", "user_id": row["student_id"], "fullname": row["fullname"]}

    if identifier == ADMIN_USERNAME and password == _admin_password():
        return {"role": "admin", "user_id": "admin", "fullname": "Administrator"}

    # 2. Try professor
    row = _check_and_migrate_password(conn, "professors", "employee_id", identifier, password)
    if row:
        return {"role": "professor", "user_id": row["employee_id"], "fullname": row["fullname"]}

    # 3. Try student
    row = _check_and_migrate_password(conn, "students", "student_id", identifier, password)
    if row:
        detected_role = row.get("role") or "student"
        return {"role": detected_role, "user_id": row["student_id"], "fullname": row["fullname"]}

    return None


@api.post("/register")
def register():
    """Student self-registration — backward compatible.

    Now also stores a password_hash on registration.
    """
    payload = request.get_json(silent=True) or {}
    student_id = (payload.get("student_id") or "").strip()
    fullname = (payload.get("fullname") or "").strip()
    email = (payload.get("email") or "").strip()
    password = payload.get("password") or ""

    if not (student_id and fullname and email and password):
        return jsonify({"success": False, "message": "Please fill in every field."}), 400

    hashed = hash_password(password)
    conn = get_db()
    try:
        try:
            # Store only the hash; the legacy plaintext column stays empty.
            conn.execute(
                "INSERT INTO students (student_id, fullname, email, password, password_hash, role) VALUES (?,?,?,?,?,'student')",
                (student_id, fullname, email, "", hashed),
            )
        except sqlite3.OperationalError:
            # Very old database without password_hash (ensure_schema not run).
            # Fall back to plaintext so the account is at least usable.
            conn.execute(
                "INSERT INTO students (student_id, fullname, email, password, role) VALUES (?,?,?,?,'student')",
                (student_id, fullname, email, password),
            )
        conn.commit()
    except sqlite3.IntegrityError:
        conn.close()
        return jsonify({"success": False, "message": "Student ID already exists."}), 409
    conn.close()

    token = _issue_token("student", student_id, fullname)
    jwt_token = _issue_jwt("student", student_id, fullname)

    return jsonify({
        "success": True,
        "token": token,
        "jwt": jwt_token,
        "user": {"role": "student", "user_id": student_id, "fullname": fullname},
    })


@api.post("/logout")
@require_auth()
def logout():
    """Logout — revokes whichever credential was presented.

    A legacy bearer token is deleted outright. A JWT cannot be deleted (it is
    stateless), so its "jti" is added to the revocation list instead; tokens
    issued before jti existed simply cannot be revoked. The JSON response is
    unchanged either way.
    """
    conn = get_db()
    conn.execute("DELETE FROM api_tokens WHERE token=?", (g.user["token"],))
    conn.commit()
    conn.close()

    if g.user.get("kind") == "jwt":
        _revoke_jti(g.user.get("jti"), g.user.get("exp"))
    return jsonify({"success": True})


@api.get("/me")
@require_auth()
def me():
    """Return authenticated user info."""
    return jsonify({
        "success": True,
        "user": {
            "role": g.user["role"],
            "user_id": g.user["user_id"],
            "fullname": g.user["fullname"],
        },
    })


# =====================================================================
# ANNOUNCEMENTS (unchanged — fully backward compatible)
# =====================================================================

@api.get("/announcements")
@require_auth()
def list_announcements():
    conn = get_db()
    rows = _rows(conn.execute("""
        SELECT id, title, description, date_created
        FROM announcements
        ORDER BY id DESC
    """))
    conn.close()
    return jsonify({"success": True, "announcements": rows})


@api.post("/announcements")
@require_auth("admin")
def create_announcement():
    payload = request.get_json(silent=True) or {}
    title = (payload.get("title") or "").strip()
    description = (payload.get("description") or "").strip()

    if not title or not description:
        return jsonify({"success": False, "message": "Title and description are required."}), 400

    conn = get_db()
    cursor = conn.execute(
        "INSERT INTO announcements (title, description, date_created) VALUES (?,?,?)",
        (title, description, datetime.now().strftime("%Y-%m-%d %I:%M %p")),
    )
    conn.commit()
    new_id = cursor.lastrowid
    conn.close()

    return jsonify({"success": True, "id": new_id}), 201


@api.put("/announcements/<int:announcement_id>")
@require_auth("admin")
def update_announcement(announcement_id):
    payload = request.get_json(silent=True) or {}
    title = (payload.get("title") or "").strip()
    description = (payload.get("description") or "").strip()

    if not title or not description:
        return jsonify({"success": False, "message": "Title and description are required."}), 400

    conn = get_db()
    conn.execute(
        "UPDATE announcements SET title=?, description=? WHERE id=?",
        (title, description, announcement_id),
    )
    conn.commit()
    conn.close()

    return jsonify({"success": True})


@api.delete("/announcements/<int:announcement_id>")
@require_auth("admin")
def delete_announcement(announcement_id):
    conn = get_db()
    conn.execute("DELETE FROM announcements WHERE id=?", (announcement_id,))
    conn.commit()
    conn.close()
    return jsonify({"success": True})


# =====================================================================
# SUBJECTS / SCHEDULES / PEOPLE (unchanged — fully backward compatible)
# =====================================================================

@api.get("/subjects")
@require_auth()
def list_subjects():
    conn = get_db()
    rows = _rows(conn.execute("""
        SELECT id, subject_code, subject_name, professor, year_level, semester
        FROM subjects
        ORDER BY subject_code
    """))
    conn.close()
    return jsonify({"success": True, "subjects": rows})


@api.post("/subjects")
@require_auth("admin")
def create_subject():
    payload = request.get_json(silent=True) or {}
    fields = [
        (payload.get("subject_code") or "").strip(),
        (payload.get("subject_name") or "").strip(),
        (payload.get("professor") or "").strip(),
        (payload.get("year_level") or "").strip(),
        (payload.get("semester") or "").strip(),
    ]

    if not fields[0] or not fields[1]:
        return jsonify({"success": False, "message": "Subject code and name are required."}), 400

    conn = get_db()
    try:
        conn.execute(
            """
            INSERT INTO subjects (subject_code, subject_name, professor, year_level, semester)
            VALUES (?,?,?,?,?)
            """,
            fields,
        )
        conn.commit()
    except sqlite3.IntegrityError:
        conn.close()
        return jsonify({"success": False, "message": "Subject code already exists."}), 409
    conn.close()

    return jsonify({"success": True}), 201


@api.delete("/subjects/<int:subject_id>")
@require_auth("admin")
def delete_subject(subject_id):
    conn = get_db()
    conn.execute("DELETE FROM subjects WHERE id=?", (subject_id,))
    conn.commit()
    conn.close()
    return jsonify({"success": True})


@api.get("/schedules")
@require_auth()
def list_schedules():
    """All class schedules. Professors get only their own unless ?all=1."""
    sql = QR_SCHEDULE_SQL
    params = []

    if g.user["role"] == "professor" and request.args.get("all") != "1":
        sql += """
            WHERE TRIM(LOWER(s.professor)) = (
                SELECT TRIM(LOWER(fullname)) FROM professors WHERE employee_id=?
            ) OR s.professor_id=?
        """
        params = [g.user["user_id"], g.user["user_id"]]

    conn = get_db()
    rows = _rows(conn.execute(sql + " ORDER BY s.day, s.time", params))
    conn.close()

    for row in rows:
        row["start_time"], row["end_time"] = parse_time_range(row["time"])

    return jsonify({"success": True, "schedules": rows})


@api.post("/schedules")
@require_auth("admin")
def create_schedule():
    payload = request.get_json(silent=True) or {}

    subject_code = (payload.get("subject_code") or "").strip()
    subject_name = (payload.get("subject_name") or "").strip()
    professor = (payload.get("professor") or "").strip()
    day = (payload.get("day") or "").strip()
    start_time = (payload.get("start_time") or "").strip()
    end_time = (payload.get("end_time") or "").strip()

    if not (subject_code and day and start_time and end_time):
        return jsonify({"success": False, "message": "Subject, day and time are required."}), 400

    try:
        time_label = format_time_range(start_time, end_time)
    except ValueError:
        return jsonify({"success": False, "message": "Time must look like 08:00."}), 400

    conn = get_db()
    row = conn.execute(
        "SELECT employee_id FROM professors WHERE TRIM(LOWER(fullname))=TRIM(LOWER(?))",
        (professor,),
    ).fetchone()
    professor_id = row["employee_id"] if row else ""

    conn.execute(
        """
        INSERT INTO schedules
        (subject_code, subject_name, professor, day, time, room, year_level, semester, class_type, professor_id)
        VALUES (?,?,?,?,?,?,?,?,?,?)
        """,
        (
            subject_code,
            subject_name,
            professor,
            day,
            time_label,
            (payload.get("room") or "").strip(),
            (payload.get("year_level") or "").strip(),
            (payload.get("semester") or "").strip(),
            (payload.get("class_type") or "").strip(),
            professor_id,
        ),
    )
    conn.commit()
    conn.close()

    return jsonify({"success": True}), 201


@api.delete("/schedules/<int:schedule_id>")
@require_auth("admin")
def delete_schedule(schedule_id):
    conn = get_db()
    conn.execute("DELETE FROM schedules WHERE id=?", (schedule_id,))
    conn.commit()
    conn.close()
    return jsonify({"success": True})


@api.get("/professors")
@require_auth("admin")
def list_professors():
    conn = get_db()
    rows = _rows(conn.execute("""
        SELECT id, employee_id, fullname, email, department
        FROM professors
        ORDER BY fullname
    """))
    conn.close()
    return jsonify({"success": True, "professors": rows})


@api.get("/students")
@require_auth("admin")
def list_students():
    conn = get_db()
    rows = _rows(conn.execute("""
        SELECT id, student_id, fullname, email
        FROM students
        WHERE role='student'
        ORDER BY fullname
    """))
    conn.close()
    return jsonify({"success": True, "students": rows})


@api.get("/stats")
@require_auth("admin")
def stats():
    conn = get_db()
    counts = {}
    for key, sql in {
        "students": "SELECT COUNT(*) FROM students WHERE role='student'",
        "professors": "SELECT COUNT(*) FROM professors",
        "subjects": "SELECT COUNT(*) FROM subjects",
        "schedules": "SELECT COUNT(*) FROM schedules",
        "announcements": "SELECT COUNT(*) FROM announcements",
        "attendance": "SELECT COUNT(*) FROM attendance",
        "active_sessions": "SELECT COUNT(*) FROM attendance_sessions WHERE active=1",
    }.items():
        counts[key] = conn.execute(sql).fetchone()[0]
    conn.close()

    return jsonify({"success": True, "stats": counts})


# =====================================================================
# NEW: DEPARTMENTS / COURSES / SECTIONS (future expansion)
# =====================================================================

@api.get("/departments")
@require_auth()
def list_departments():
    conn = get_db()
    rows = _rows(conn.execute("""
        SELECT id, code, name, description
        FROM departments
        ORDER BY name
    """))
    conn.close()
    return jsonify({"success": True, "departments": rows})


@api.get("/courses")
@require_auth()
def list_courses():
    department_id = request.args.get("department_id", type=int)
    conn = get_db()
    if department_id:
        rows = _rows(conn.execute("""
            SELECT id, code, name, department_id, description
            FROM courses
            WHERE department_id=?
            ORDER BY name
        """, (department_id,)))
    else:
        rows = _rows(conn.execute("""
            SELECT id, code, name, department_id, description
            FROM courses
            ORDER BY name
        """))
    conn.close()
    return jsonify({"success": True, "courses": rows})


@api.get("/sections")
@require_auth()
def list_sections():
    course_id = request.args.get("course_id", type=int)
    conn = get_db()
    if course_id:
        rows = _rows(conn.execute("""
            SELECT id, code, name, course_id, year_level
            FROM sections
            WHERE course_id=?
            ORDER BY name
        """, (course_id,)))
    else:
        rows = _rows(conn.execute("""
            SELECT id, code, name, course_id, year_level
            FROM sections
            ORDER BY name
        """))
    conn.close()
    return jsonify({"success": True, "sections": rows})


# =====================================================================
# NEW: EVENTS (campus calendar)
# =====================================================================

@api.get("/events")
@require_auth()
def list_events():
    conn = get_db()
    rows = _rows(conn.execute("""
        SELECT id, title, description, event_date, event_time, location, category
        FROM events
        ORDER BY event_date DESC
        LIMIT 50
    """))
    conn.close()
    return jsonify({"success": True, "events": rows})


@api.post("/events")
@require_auth("admin")
def create_event():
    payload = request.get_json(silent=True) or {}
    title = (payload.get("title") or "").strip()
    description = (payload.get("description") or "").strip()
    event_date = (payload.get("event_date") or "").strip()
    event_time = (payload.get("event_time") or "").strip()
    location = (payload.get("location") or "").strip()
    category = (payload.get("category") or "general").strip()

    if not title or not event_date:
        return jsonify({"success": False, "message": "Title and date are required."}), 400

    conn = get_db()
    cursor = conn.execute(
        "INSERT INTO events (title, description, event_date, event_time, location, category, created_by) VALUES (?,?,?,?,?,?,?)",
        (title, description, event_date, event_time, location, category, g.user.get("fullname", "")),
    )
    conn.commit()
    new_id = cursor.lastrowid
    conn.close()

    return jsonify({"success": True, "id": new_id}), 201


# =====================================================================
# NEW: NOTIFICATIONS
# =====================================================================

@api.get("/notifications")
@require_auth()
def list_notifications():
    role = g.user["role"]
    conn = get_db()
    rows = _rows(conn.execute("""
        SELECT id, title, message, is_read, link, created_at
        FROM notifications
        WHERE (recipient_role=? OR recipient_role='all')
        ORDER BY created_at DESC
        LIMIT 20
    """, (role,)))
    conn.close()
    return jsonify({"success": True, "notifications": rows})


# =====================================================================
# ATTENDANCE QR — professor / admin side (unchanged)
# =====================================================================

@api.post("/qr/create")
@require_auth("admin", "professor")
def create_attendance_qr():
    """Open an attendance session and return the QR payload to render on screen."""
    payload = request.get_json(silent=True) or {}
    schedule_id = payload.get("schedule_id")
    date = (payload.get("date") or datetime.now().strftime("%Y-%m-%d")).strip()
    expires_at = (payload.get("expires_at") or "").strip()

    if not schedule_id or not expires_at:
        return jsonify({"success": False, "message": "Schedule and expiration time are required."}), 400

    # Accept both 23:59 and 11:59 PM.
    try:
        expires_at = datetime.strptime(expires_at, "%H:%M").strftime("%I:%M %p")
    except ValueError:
        try:
            expires_at = datetime.strptime(expires_at, "%I:%M %p").strftime("%I:%M %p")
        except ValueError:
            return jsonify({"success": False, "message": "Expiration time must look like 15:30."}), 400

    conn = get_db()
    schedule = conn.execute(QR_SCHEDULE_SQL + " WHERE s.id=?", (schedule_id,)).fetchone()

    if not schedule:
        conn.close()
        return jsonify({"success": False, "message": "Invalid schedule selection."}), 404

    if g.user["role"] == "professor":
        professor_id = g.user["user_id"]
        professor_name = g.user["fullname"]
    else:
        professor_id = schedule["professor_id"]
        professor_name = schedule["professor"]

        if not professor_id:
            conn.close()
            return jsonify({
                "success": False,
                "message": "That subject has no registered professor. Add the professor first."
            }), 400

    token = str(uuid.uuid4())

    qr_payload = "|".join([
        schedule["subject_code"],
        schedule["subject_name"],
        professor_id,
        professor_name,
        schedule["day"],
        schedule["time"],
        date,
        expires_at,
        token,
    ])

    conn.execute("""
        INSERT INTO attendance_sessions
        (professor_id, professor_name, subject_code, subject_name, day, schedule, date, expires_at, token, active)
        VALUES (?,?,?,?,?,?,?,?,?,1)
    """, (
        professor_id,
        professor_name,
        schedule["subject_code"],
        schedule["subject_name"],
        schedule["day"],
        schedule["time"],
        date,
        expires_at,
        token,
    ))
    conn.commit()

    session_id = conn.execute(
        "SELECT id FROM attendance_sessions WHERE token=?", (token,)
    ).fetchone()["id"]
    conn.close()

    return jsonify({
        "success": True,
        "session": {
            "id": session_id,
            "token": token,
            "payload": qr_payload,
            "subject_code": schedule["subject_code"],
            "subject_name": schedule["subject_name"],
            "professor_id": professor_id,
            "professor_name": professor_name,
            "day": schedule["day"],
            "schedule": schedule["time"],
            "date": date,
            "expires_at": expires_at,
            "active": 1,
        },
    })


# =====================================================================
# ATTENDANCE (consumed by campusconnect_app/lib/api/api_client.dart)
# =====================================================================

# Column list matching AttendanceRecord.fromJson in models.dart.
# v1 rows store the professor in `professor`; v2 rows use `professor_name`.
_ATTENDANCE_COLUMNS = """
    student_id,
    fullname,
    subject_code,
    subject_name,
    COALESCE(NULLIF(professor,''), NULLIF(professor_name,''), '') AS professor,
    date,
    time,
    status
"""


def _session_payload(row):
    """Rebuild the v2 QR string for an existing attendance session."""
    return "|".join([
        row["subject_code"] or "",
        row["subject_name"] or "",
        row["professor_id"] or "",
        row["professor_name"] or "",
        row["day"] or "",
        row["schedule"] or "",
        row["date"] or "",
        row["expires_at"] or "",
        row["token"] or "",
    ])


@api.get("/ping")
def ping():
    """Used by the Flutter server-setup screen to confirm an address.

    Deliberately unauthenticated: it runs before the user has a token.
    """
    return jsonify({"success": True, "service": "CampusConnect+"})


@api.get("/attendance/sessions")
@require_auth("admin", "professor")
def attendance_sessions():
    """Attendance sessions with their attendees. Professors see only their own."""
    sql = """
        SELECT id, professor_id, professor_name, subject_code, subject_name,
               day, schedule, date, expires_at, token, active
        FROM attendance_sessions
    """
    params = []

    if g.user["role"] == "professor":
        sql += " WHERE professor_id=?"
        params = [g.user["user_id"]]

    conn = get_db()
    rows = conn.execute(sql + " ORDER BY id DESC", params).fetchall()

    sessions = []
    for row in rows:
        attendees = _rows(conn.execute(
            "SELECT %s FROM attendance WHERE token=? ORDER BY fullname" % _ATTENDANCE_COLUMNS,
            (row["token"],),
        ))
        sessions.append({
            "id": row["id"],
            "token": row["token"] or "",
            "payload": _session_payload(row),
            "subject_code": row["subject_code"] or "",
            "subject_name": row["subject_name"] or "",
            "professor_id": row["professor_id"] or "",
            "professor_name": row["professor_name"] or "",
            "day": row["day"] or "",
            "schedule": row["schedule"] or "",
            "date": row["date"] or "",
            "expires_at": row["expires_at"] or "",
            "active": row["active"],
            "attendees": attendees,
        })

    conn.close()
    return jsonify({"success": True, "sessions": sessions})


@api.post("/attendance/sessions/<int:session_id>/close")
@require_auth("admin", "professor")
def close_attendance_session(session_id):
    """Deactivate a session. Professors may only close their own."""
    conn = get_db()

    if g.user["role"] == "professor":
        cursor = conn.execute(
            "UPDATE attendance_sessions SET active=0 WHERE id=? AND professor_id=?",
            (session_id, g.user["user_id"]),
        )
    else:
        cursor = conn.execute(
            "UPDATE attendance_sessions SET active=0 WHERE id=?",
            (session_id,),
        )

    conn.commit()
    changed = cursor.rowcount
    conn.close()

    if not changed:
        return jsonify({"success": False, "message": "Attendance session not found."}), 404

    return jsonify({"success": True, "message": "Attendance session closed."})


@api.post("/attendance/scan")
@require_auth("student")
def scan_attendance():
    """Record attendance for the authenticated student from a scanned QR."""
    payload = request.get_json(silent=True) or {}
    qr_text = (payload.get("qr") or "").strip()

    parsed = parse_qr(qr_text)
    if not parsed:
        return jsonify({"success": False, "message": "Invalid QR code."}), 400

    now = datetime.now()
    date = parsed["date"] if parsed["version"] == 2 else now.strftime("%Y-%m-%d")
    current_time = now.strftime("%I:%M %p")

    conn = get_db()
    cursor = conn.cursor()

    if parsed["version"] == 2:
        expired = session_expired(parsed)

        if expired is None:
            conn.close()
            return jsonify({"success": False, "message": "Invalid expiration format."}), 400

        if expired:
            conn.close()
            return jsonify({"success": False, "message": "QR code expired."}), 400

        if not attendance_session_active(cursor, parsed):
            conn.close()
            return jsonify({"success": False, "message": "Attendance session is not active."}), 400

    if attendance_exists(cursor, g.user["user_id"], parsed["subject_code"],
                         date, token=parsed.get("token")):
        conn.close()
        return jsonify({"success": False, "message": "Duplicate attendance detected."}), 409

    insert_attendance(
        cursor,
        g.user["user_id"],
        g.user["fullname"],
        parsed,
        date,
        current_time,
        str(uuid.uuid4()),
    )

    conn.commit()
    conn.close()

    return jsonify({"success": True, "message": "Attendance Recorded Successfully."})


@api.get("/attendance/mine")
@require_auth("student")
def my_attendance():
    """Attendance history for the authenticated student."""
    conn = get_db()
    rows = _rows(conn.execute(
        "SELECT %s FROM attendance WHERE student_id=? ORDER BY id DESC" % _ATTENDANCE_COLUMNS,
        (g.user["user_id"],),
    ))
    conn.close()
    return jsonify({"success": True, "attendance": rows})


@api.get("/attendance")
@require_auth("admin", "professor")
def all_attendance():
    """Full attendance log. Professors see only records from their own sessions."""
    sql = "SELECT %s FROM attendance" % _ATTENDANCE_COLUMNS
    params = []

    if g.user["role"] == "professor":
        sql += " WHERE professor_id=?"
        params = [g.user["user_id"]]

    conn = get_db()
    rows = _rows(conn.execute(sql + " ORDER BY id DESC", params))
    conn.close()
    return jsonify({"success": True, "attendance": rows})
