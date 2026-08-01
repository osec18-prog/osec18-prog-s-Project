from flask import Flask, render_template, request, redirect, session, jsonify, send_from_directory, flash
from flask_wtf.csrf import CSRFProtect
import sqlite3
from datetime import datetime
from urllib.parse import quote, urlparse
import logging
import os
import qrcode
import uuid

# Database compatibility layer. Talks to Supabase PostgreSQL when DATABASE_URL
# is set, and to the original SQLite file when it is not. Every dialect
# difference is handled inside db.py; nothing here needs to know which.
import db

from core import (
    QR_SCHEDULE_SQL,
    attendance_exists,
    attendance_session_active,
    check_password_with_migration,
    ensure_schema,
    format_time_range,
    get_local_ip,
    hash_password,
    insert_attendance,
    parse_professor_qr,
    parse_qr,
    parse_time_range,
    rate_limit_hit,
    rate_limit_reset,
)
from api import api

def _require_env(name):
    """Read a required secret from the environment, or refuse to start.

    These used to fall back to hard-coded literals, which meant anyone with a
    copy of the source could forge a session cookie or a JWT.
    """
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(
            "\n"
            "=====================================================================\n"
            " CampusConnect+ cannot start: %s is not set.\n"
            "=====================================================================\n"
            " This secret no longer has a default, because a hard-coded default\n"
            " lets anyone forge a login session.\n"
            "\n"
            " Three variables are required:\n"
            "     SECRET_KEY      signs the browser session cookie\n"
            "     JWT_SECRET      signs the mobile app's tokens\n"
            "     ADMIN_PASSWORD  password for the built-in 'admin' account\n"
            "\n"
            " Set them for the current PowerShell window:\n"
            "     $env:SECRET_KEY     = \"<random string>\"\n"
            "     $env:JWT_SECRET     = \"<a different random string>\"\n"
            "     $env:ADMIN_PASSWORD = \"<your admin password>\"\n"
            "     python app.py\n"
            "\n"
            " To set them permanently for your user account:\n"
            "     setx SECRET_KEY     \"<random string>\"\n"
            "     setx JWT_SECRET     \"<a different random string>\"\n"
            "     setx ADMIN_PASSWORD \"<your admin password>\"\n"
            "   (then open a NEW terminal — setx does not affect the current one)\n"
            "\n"
            " Generate a good random value with:\n"
            "     python -c \"import secrets; print(secrets.token_hex(32))\"\n"
            "=====================================================================\n"
            % name
        )
    return value


IS_PRODUCTION = os.environ.get("FLASK_ENV", "").strip().lower() == "production"

app = Flask(__name__)
app.secret_key = _require_env("SECRET_KEY")

# Validated at startup so a missing JWT secret fails here rather than on the
# first mobile login. api.py reads the same variable.
_require_env("JWT_SECRET")

# The built-in administrator account. The password used to be a literal string
# in both app.py and api.py, so anyone reading the source could log in as an
# administrator. The username stays configurable but is not a secret.
ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = _require_env("ADMIN_PASSWORD")

# ── Session cookie hardening ────────────────────────────────────────────
# HTTPONLY keeps JavaScript away from the session cookie; SAMESITE=Lax stops
# the cookie riding along on cross-site POSTs. SECURE is only switched on in
# production because the LAN/dev server runs over plain HTTP — turning it on
# there would stop the cookie being sent at all.
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=IS_PRODUCTION,
)

# ── Logging ─────────────────────────────────────────────────────────────
# Under gunicorn the app logger inherits gunicorn's handlers; running
# `python app.py` directly needs its own. Either way, security-relevant
# events (failed logins, rate limiting) end up in the server log.
logging.basicConfig(
    level=logging.INFO if IS_PRODUCTION else logging.DEBUG,
    format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
)
log = logging.getLogger("campusconnect")


@app.after_request
def security_headers(response):
    """Headers that cost nothing and close off common attacks.

    No Content-Security-Policy is set here on purpose: the templates load
    Bootstrap/qr libraries from three CDNs and use inline handlers, so a
    policy strict enough to be worth having would break the UI. See the
    security notes in README.md for the policy to adopt once those are
    bundled locally.
    """
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "SAMEORIGIN"
    response.headers["Referrer-Policy"] = "same-origin"
    response.headers["Permissions-Policy"] = "geolocation=(), microphone=()"
    if IS_PRODUCTION:
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return response


def client_ip():
    """Caller's address, honouring Render's proxy header."""
    forwarded = request.headers.get("X-Forwarded-For", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.remote_addr or "unknown"

# ── CSRF protection for the browser-facing forms ────────────────────────
# Every HTML form that changes data now carries a token tied to the session,
# so another site cannot make the browser submit it.
csrf = CSRFProtect(app)

# JSON API used by the Flutter mobile app (see campusconnect_app/).
app.register_blueprint(api)

# The /api blueprint authenticates with a bearer token rather than the session
# cookie, so it is not reachable by a cross-site form post in the first place —
# and the mobile client has no way to obtain a CSRF token. Exempt it, or every
# Flutter write would start failing with 400.
csrf.exempt(api)

ensure_schema()


# ---------------------------------------------------------------------------
# Serve the Flutter web build (built with `flutter build web`)
# ---------------------------------------------------------------------------
FLUTTER_WEB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static", "flutter_app")


@app.route("/app/")
@app.route("/app/<path:filename>")
def serve_flutter_app(filename=None):
    """Serve the Flutter web build at /app/ so it lives alongside the admin panel."""
    if filename is None:
        filename = "index.html"

    file_path = os.path.join(FLUTTER_WEB_DIR, filename)

    # If the file doesn't exist, serve index.html so Flutter's router handles it
    if not os.path.isfile(file_path):
        file_path = os.path.join(FLUTTER_WEB_DIR, "index.html")

    return send_from_directory(FLUTTER_WEB_DIR, os.path.relpath(file_path, FLUTTER_WEB_DIR))


@app.after_request
def no_cache_html(response):
    # Announcements/attendance pages must never be served from the browser
    # cache, otherwise new posts look like they never appeared.
    if response.mimetype == "text/html":
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
    return response


def build_host_url():
    configured = os.environ.get("QR_HOST_URL")
    if configured:
        return configured.rstrip("/")

    host_url = request.host_url.rstrip("/")
    parsed = urlparse(host_url)
    if parsed.hostname in ("localhost", "127.0.0.1", "0.0.0.0"):
        local_ip = get_local_ip()
        if local_ip:
            netloc = local_ip
            if parsed.port:
                netloc = f"{local_ip}:{parsed.port}"
            return f"{parsed.scheme}://{netloc}"
    return host_url


def get_qr_schedules():
    """Every class schedule that can be turned into an attendance QR."""
    conn = db.connect()
    cursor = conn.cursor()
    cursor.execute(QR_SCHEDULE_SQL + " ORDER BY s.subject_code")
    schedules = cursor.fetchall()
    conn.close()
    return schedules


@app.route("/")
def home():
    return render_template("login.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "GET":
        return render_template("login.html")

    student_id = request.form["student_id"]
    password = request.form["password"]

    if rate_limit_hit("login:%s" % client_ip()):
        log.warning("rate limit: student login from %s", client_ip())
        return render_template(
            "login.html",
            error="Too many login attempts. Please wait a few minutes and try again."
        ), 429

    conn = db.connect()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # Look the account up by id only; the password is checked in Python so a
    # hashed password can be verified. Legacy plaintext rows are upgraded on
    # the way through.
    cursor.execute("SELECT * FROM students WHERE student_id=?", (student_id,))
    row = cursor.fetchone()

    user = None
    if check_password_with_migration(conn, "students", "student_id", row, password):
        user = (row["fullname"], row["student_id"], row["role"])

    conn.close()

    if user:
        rate_limit_reset("login:%s" % client_ip())
        log.info("login ok: student_id=%s role=%s from %s", user[1], user[2], client_ip())

        # Save pending QR if mayroon
        pending_qr = session.get("pending_qr")

        # Clear old session
        session.clear()

        # Restore pending QR
        if pending_qr:
            session["pending_qr"] = pending_qr

        # Login session
        session["fullname"] = user[0]
        session["student_id"] = user[1]
        session["role"] = user[2]

        # Kung galing sa QR scan, automatic bumalik sa attendance
        if "pending_qr" in session:
            qr = session.pop("pending_qr")
            return redirect("/mark_attendance?qr=" + quote(qr))

        # Normal login
        if session["role"] == "admin":
            return redirect("/admin_dashboard")
        else:
            return redirect("/dashboard")

    log.warning("login failed: student_id=%r from %s", student_id, client_ip())
    return render_template("login.html", error="Invalid Student ID or Password")


@app.route("/signup")
def signup():
    return render_template("register.html")


@app.route("/register", methods=["POST"])
def register():
    student_id = request.form["student_id"]
    fullname = request.form["fullname"]
    email = request.form["email"]
    password = request.form["password"]

    conn = db.connect()
    cursor = conn.cursor()

    try:
        cursor.execute(
            "INSERT INTO students(student_id, fullname, email, password, password_hash, role) VALUES (?, ?, ?, ?, ?, ?)",
            (student_id, fullname, email, "", hash_password(password), "student")
        )
        conn.commit()
    except sqlite3.IntegrityError:
        return render_template("register.html", error="Student ID already exists!")
    finally:
        conn.close()

    return redirect("/")


@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")


@app.route("/dashboard")
def dashboard():
    if "role" not in session or session["role"] != "student":
        return redirect("/")
    return render_template("dashboard.html", fullname=session["fullname"], student_id=session["student_id"])


# --------------------------
# ADMIN LOGIN
# --------------------------


@app.route("/admin_login", methods=["GET", "POST"])
def admin_login():
    if request.method == "GET":
        return render_template("admin_login.html")

    username = request.form["username"]
    password = request.form["password"]

    if rate_limit_hit("admin_login:%s" % client_ip()):
        log.warning("rate limit: admin login from %s", client_ip())
        return render_template(
            "admin_login.html",
            error="Too many login attempts. Please wait a few minutes and try again."
        ), 429

    if username == ADMIN_USERNAME and password == ADMIN_PASSWORD:
        rate_limit_reset("admin_login:%s" % client_ip())
        log.info("login ok: admin from %s", client_ip())
        session.clear()
        session["fullname"] = "Administrator"
        session["student_id"] = "admin"
        session["role"] = "admin"
        return redirect("/admin_dashboard")

    log.warning("login failed: admin username=%r from %s", username, client_ip())
    return render_template("admin_login.html", error="Invalid Admin Username or Password")


@app.route("/admin_dashboard")
def admin_dashboard():
    if "role" not in session or session["role"] != "admin":
        return redirect("/")

    conn = db.connect()
    cursor = conn.cursor()

    cursor.execute("""SELECT id, student_id, fullname, email FROM students ORDER BY fullname""")
    students = cursor.fetchall()

    cursor.execute("SELECT COUNT(*) FROM students WHERE role='student'")
    total_students = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM students WHERE role='admin'")
    total_admins = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM professors")
    total_professors = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM subjects")
    total_subjects = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM schedules")
    total_classes = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM attendance_sessions WHERE active=1")
    active_sessions = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM announcements")
    total_announcements = cursor.fetchone()[0]

    conn.close()

    return render_template(
        "admin_dashboard.html",
        fullname=session["fullname"],
        students=students,
        total_students=total_students,
        total_professors=total_professors,
        total_admins=total_admins,
        total_subjects=total_subjects,
        total_classes=total_classes,
        active_sessions=active_sessions,
        total_announcements=total_announcements
    )


@app.route("/edit_admin")
def edit_admin():
    # Previously unguarded: any anonymous visitor could read the admin row
    # (including the password) and POST a new one to /update_admin.
    if "role" not in session:
        return redirect("/")
    if session["role"] != "admin":
        return redirect("/dashboard")

    conn = db.connect()
    cursor = conn.cursor()
    # ORDER BY is required, not cosmetic: SQLite returns the lowest rowid for
    # an unordered LIMIT 1, PostgreSQL may return any matching row. Without
    # this, a second admin account would make this page edit an arbitrary one.
    cursor.execute("""SELECT * FROM students WHERE role='admin' ORDER BY id LIMIT 1""")
    admin = cursor.fetchone()
    conn.close()
    return render_template("edit_admin.html", admin=admin)


@app.route("/update_admin", methods=["POST"])
def update_admin():
    if "role" not in session:
        return redirect("/")
    if session["role"] != "admin":
        return redirect("/dashboard")

    id = request.form["id"]
    fullname = request.form["fullname"]
    email = request.form["email"]
    password = request.form.get("password") or ""

    conn = db.connect()
    cursor = conn.cursor()

    if password:
        # Store the new password hashed. Writing only the old plaintext column
        # here would silently do nothing, because login reads password_hash.
        cursor.execute("""
            UPDATE students
            SET fullname=?, email=?, password='', password_hash=?
            WHERE id=?
        """, (fullname, email, hash_password(password), id))
    else:
        # The form can no longer pre-fill the password (it is hashed), so an
        # empty box means "leave the password alone".
        cursor.execute("""
            UPDATE students
            SET fullname=?, email=?
            WHERE id=?
        """, (fullname, email, id))

    conn.commit()
    conn.close()
    return redirect("/admin_dashboard")


# ----------------------------
# DELETE STUDENT
# ----------------------------

@app.route("/delete_student/<int:id>", methods=["POST"])
def delete_student(id):
    if "role" not in session:
        return redirect("/")
    if session["role"] != "admin":
        return redirect("/dashboard")

    conn = db.connect()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM students WHERE id=?", (id,))
    conn.commit()
    conn.close()
    return redirect("/admin_dashboard")


# ----------------------------
# EDIT STUDENT
# ----------------------------

@app.route("/edit_student/<int:id>")
def edit_student(id):
    if "role" not in session:
        return redirect("/")
    if session["role"] != "admin":
        return redirect("/dashboard")

    conn = db.connect()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM students WHERE id=?", (id,))
    student = cursor.fetchone()
    conn.close()

    if student is None:
        return redirect("/admin_students")
    return render_template("edit_student.html", student=student)


@app.route("/update_student", methods=["POST"])
def update_student():
    if "role" not in session:
        return redirect("/")
    if session["role"] != "admin":
        return redirect("/dashboard")

    id = request.form["id"]
    student_id = request.form["student_id"]
    fullname = request.form["fullname"]
    email = request.form["email"]

    conn = db.connect()
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE students
        SET student_id=?, fullname=?, email=?
        WHERE id=?
    """, (student_id, fullname, email, id))
    conn.commit()
    conn.close()
    return redirect("/admin_students")


# ==========================
# ADMIN ANNOUNCEMENTS
# ==========================

@app.route("/admin_announcements")
def admin_announcements():
    if "role" not in session:
        return redirect("/")
    if session["role"] not in ["admin", "professor"]:
        return redirect("/dashboard")

    conn = db.connect()
    cursor = conn.cursor()
    cursor.execute("""SELECT id, title, description, date_created FROM announcements ORDER BY id DESC""")
    announcements = cursor.fetchall()
    conn.close()

    return render_template("announcements.html", announcements=announcements,
                           fullname=session.get("fullname", session.get("professor_name", "")))


@app.route("/add_announcement", methods=["POST"])
def add_announcement():
    if "role" not in session:
        return redirect("/")
    if session["role"] != "admin":
        return redirect("/dashboard")

    title = (request.form.get("title") or "").strip()
    description = (request.form.get("description") or "").strip()

    if not title or not description:
        return redirect("/admin_announcements")

    conn = db.connect()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO announcements (title, description, date_created)
        VALUES (?,?,?)
    """, (title, description, datetime.now().strftime("%Y-%m-%d %I:%M %p")))
    conn.commit()
    conn.close()

    return redirect("/admin_announcements")


@app.route("/delete_announcement/<int:id>", methods=["POST"])
def delete_announcement(id):
    if "role" not in session or session["role"] != "admin":
        return redirect("/")

    conn = db.connect()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM announcements WHERE id=?", (id,))
    conn.commit()
    conn.close()
    return redirect("/admin_announcements")


@app.route("/edit_announcement/<int:id>")
def edit_announcement(id):
    if "role" not in session or session["role"] != "admin":
        return redirect("/")

    conn = db.connect()
    cursor = conn.cursor()
    cursor.execute("SELECT id, title, description FROM announcements WHERE id=?", (id,))
    announcement = cursor.fetchone()
    conn.close()
    return render_template("edit_announcement.html", announcement=announcement)


# ==========================
# UPDATE ANNOUNCEMENT
# ==========================

@app.route("/update_announcement", methods=["POST"])
def update_announcement():

    if "role" not in session or session["role"] != "admin":
        return redirect("/")

    id = request.form["id"]
    title = request.form["title"]
    description = request.form["description"]

    conn = db.connect()
    cursor = conn.cursor()

    cursor.execute("""
        UPDATE announcements
        SET title=?,
            description=?
        WHERE id=?
    """, (
        title,
        description,
        id
    ))

    conn.commit()
    conn.close()

    return redirect("/admin_announcements")


# ==========================
# STUDENT ANNOUNCEMENTS
# ==========================

@app.route("/student_announcements")
def student_announcements():

    if "student_id" not in session:
        return redirect("/")

    conn = db.connect()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT title, description, date_created
        FROM announcements
        ORDER BY id DESC
    """)

    announcements = cursor.fetchall()

    conn.close()

    return render_template(
        "student_announcements.html",
        announcements=announcements,
        fullname=session["fullname"]
    )

@app.route("/admin_professors")
def admin_professors():

    if "role" not in session:
        return redirect("/")

    if session["role"] != "admin":
        return redirect("/dashboard")

    conn = db.connect()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT *
        FROM professors
        ORDER BY fullname
    """)

    professors = cursor.fetchall()

    conn.close()

    return render_template(
        "professors.html",
        professors=professors
    )


@app.route("/add_professor", methods=["GET", "POST"])
def add_professor():

    if "role" not in session:
        return redirect("/")

    if session["role"] != "admin":
        return redirect("/dashboard")

    if request.method == "POST":
        employee_id = request.form["employee_id"]
        fullname = request.form["fullname"]
        email = request.form["email"]
        password = request.form["password"]
        department = request.form["department"]

        conn = db.connect()
        cursor = conn.cursor()

        try:
            cursor.execute(
                "INSERT INTO professors(employee_id, fullname, email, password, password_hash, department) VALUES (?, ?, ?, ?, ?, ?)",
                (employee_id, fullname, email, "", hash_password(password), department)
            )
            conn.commit()
        except sqlite3.IntegrityError:
            conn.close()
            return render_template(
                "add_professor.html",
                error="Professor ID or Email already exists!"
            )
        finally:
            conn.close()

        return redirect("/admin_professors")

    return render_template(
        "add_professor.html"
    )


@app.route("/delete_professor/<int:id>", methods=["POST"])
def delete_professor(id):

    if "role" not in session:
        return redirect("/")

    if session["role"] != "admin":
        return redirect("/dashboard")

    conn = db.connect()
    cursor = conn.cursor()

    cursor.execute(
        "DELETE FROM professors WHERE id=?",
        (id,)
    )

    conn.commit()
    conn.close()

    return redirect("/admin_professors")

@app.route("/update_professor", methods=["POST"])
def update_professor():

    if "role" not in session:
        return redirect("/")

    if session["role"] != "admin":
        return redirect("/dashboard")

    id = request.form["id"]
    employee_id = request.form["employee_id"]
    fullname = request.form["fullname"]
    email = request.form["email"]
    department = request.form["department"]

    conn = db.connect()
    cursor = conn.cursor()

    cursor.execute("""
        UPDATE professors
        SET employee_id=?,
            fullname=?,
            email=?,
            department=?
        WHERE id=?
    """, (
        employee_id,
        fullname,
        email,
        department,
        id
    ))

    conn.commit()
    conn.close()

    return redirect("/admin_professors")

@app.route("/edit_professor/<int:id>")
def edit_professor(id):

    if "role" not in session:
        return redirect("/")

    if session["role"] != "admin":
        return redirect("/dashboard")

    conn = db.connect()
    cursor = conn.cursor()

    cursor.execute(
        "SELECT * FROM professors WHERE id=?",
        (id,)
    )

    professor = cursor.fetchone()

    conn.close()

    if professor is None:
        return redirect("/admin_professors")

    return render_template(
        "edit_professor.html",
        professor=professor
    )


@app.route("/edit_subject/<int:id>")
def edit_subject(id):

    if "role" not in session:
        return redirect("/")

    if session["role"] != "admin":
        return redirect("/dashboard")

    conn = db.connect()
    cursor = conn.cursor()

    cursor.execute(
        "SELECT * FROM subjects WHERE id=?",
        (id,)
    )

    subject = cursor.fetchone()

    conn.close()

    return render_template(
        "edit_subject.html",
        subject=subject
    )

@app.route("/admin_subjects")
def admin_subjects():

    if "role" not in session:
        return redirect("/")

    if session["role"] != "admin":
        return redirect("/dashboard")

    conn = db.connect()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT *
        FROM subjects
        ORDER BY subject_code
    """)

    subjects = cursor.fetchall()

    conn.close()

    return render_template(
        "subjects.html",
        subjects=subjects
    )

@app.route("/add_subject", methods=["POST"])
def add_subject():

    if "role" not in session:
        return redirect("/")

    if session["role"] != "admin":
        return redirect("/dashboard")

    subject_code = request.form["subject_code"]
    subject_name = request.form["subject_name"]
    professor = request.form["professor"]
    year_level = request.form["year_level"]
    semester = request.form["semester"]

    conn = db.connect()
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO subjects
        (subject_code, subject_name, professor, year_level, semester)
        VALUES (?,?,?,?,?)
    """, (
        subject_code,
        subject_name,
        professor,
        year_level,
        semester
    ))

    conn.commit()
    conn.close()

    return redirect("/admin_subjects")

@app.route("/delete_subject/<int:id>", methods=["POST"])
def delete_subject(id):

    if "role" not in session:
        return redirect("/")

    if session["role"] != "admin":
        return redirect("/dashboard")

    conn = db.connect()
    cursor = conn.cursor()

    cursor.execute(
        "DELETE FROM subjects WHERE id=?",
        (id,)
    )

    conn.commit()
    conn.close()

    return redirect("/admin_subjects")

@app.route("/update_subject", methods=["POST"])
def update_subject():

    if "role" not in session:
        return redirect("/")

    if session["role"] != "admin":
        return redirect("/dashboard")

    id = request.form["id"]
    subject_code = request.form["subject_code"]
    subject_name = request.form["subject_name"]
    professor = request.form["professor"]
    year_level = request.form["year_level"]
    semester = request.form["semester"]

    conn = db.connect()
    cursor = conn.cursor()

    # Check kung may kaparehong Subject Code
    cursor.execute("""
        SELECT id
        FROM subjects
        WHERE subject_code=? AND id!=?
    """, (subject_code, id))

    existing = cursor.fetchone()

    if existing:
        conn.close()
        return "Error: Subject Code already exists."

    cursor.execute("""
        UPDATE subjects
        SET
            subject_code=?,
            subject_name=?,
            professor=?,
            year_level=?,
            semester=?
        WHERE id=?
    """, (
        subject_code,
        subject_name,
        professor,
        year_level,
        semester,
        id
    ))

    conn.commit()
    conn.close()

    return redirect("/admin_subjects")



@app.route("/admin_schedules")
def admin_schedules():

    if "role" not in session:
        return redirect("/")

    if session["role"] != "admin":
        return redirect("/dashboard")

    conn = db.connect()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT id, subject_code, subject_name, professor, day, time,
               room, year_level, semester, class_type
        FROM schedules
        ORDER BY day,time
    """)

    schedules = cursor.fetchall()

    cursor.execute("""
        SELECT subject_code,
               subject_name,
               professor,
               year_level,
               semester
        FROM subjects
        ORDER BY subject_code
    """)

    subjects = cursor.fetchall()

    cursor.execute("""
        SELECT fullname
        FROM professors
        ORDER BY fullname
    """)

    professors = cursor.fetchall()

    conn.close()

    return render_template(
        "schedules.html",
        schedules=schedules,
        subjects=subjects,
        professors=professors
    )


# =============================================================================
# SCHEDULE MANAGEMENT — FIXED ROUTES
# =============================================================================
# Bugs fixed:
#   1. Silent redirect when "|" separator missing → now shows flash error
#   2. No try/except around format_time_range → now catches ValueError
#   3. No database error handling → now catches sqlite3.Error
#   4. No user feedback on success → now shows flash success message
#   5. No validation of required fields → now validates all fields
# =============================================================================

@app.route("/add_schedule", methods=["POST"])
def add_schedule():

    if "role" not in session:
        flash("Session expired. Please log in again.", "error")
        return redirect("/")

    if session["role"] != "admin":
        flash("Access denied. Admin only.", "error")
        return redirect("/dashboard")

    # ── Validate and extract subject ────────────────────────────────────────
    subject = request.form.get("subject", "").strip()
    if "|" not in subject:
        flash("Invalid subject selection. Please select a subject from the list.", "error")
        return redirect("/admin_schedules")

    subject_code, subject_name = subject.split("|", 1)
    subject_code = subject_code.strip()
    subject_name = subject_name.strip()

    if not subject_code or not subject_name:
        flash("Subject code and name cannot be empty.", "error")
        return redirect("/admin_schedules")

    # ── Extract other fields ────────────────────────────────────────────────
    professor = request.form.get("professor", "").strip()
    day = request.form.get("day", "").strip()
    start_time = request.form.get("start_time", "").strip()
    end_time = request.form.get("end_time", "").strip()
    room = request.form.get("room", "").strip()
    year_level = request.form.get("year_level", "").strip()
    semester = request.form.get("semester", "").strip()
    class_type = request.form.get("class_type", "").strip()

    # ── Validate required fields ────────────────────────────────────────────
    missing = []
    if not professor: missing.append("Professor")
    if not day: missing.append("Day")
    if not start_time: missing.append("Start Time")
    if not end_time: missing.append("End Time")
    if not room: missing.append("Room")
    if not year_level: missing.append("Year Level")
    if not semester: missing.append("Semester")
    if not class_type: missing.append("Class Type")

    if missing:
        flash(f"Missing required fields: {', '.join(missing)}", "error")
        return redirect("/admin_schedules")

    # ── Format time range (with error handling) ─────────────────────────────
    try:
        time_label = format_time_range(start_time, end_time)
    except ValueError:
        flash("Invalid time format. Use HH:MM (e.g., 08:00).", "error")
        return redirect("/admin_schedules")

    # ── Insert into database ────────────────────────────────────────────────
    try:
        conn = db.connect()
        cursor = conn.cursor()

        # Resolve professor_id
        cursor.execute(
            "SELECT employee_id FROM professors WHERE TRIM(fullname)=TRIM(?)",
            (professor,)
        )
        row = cursor.fetchone()
        professor_id = row[0] if row else ""

        cursor.execute("""
            INSERT INTO schedules
            (subject_code, subject_name, professor, day, time, room, year_level, semester, class_type, professor_id)
            VALUES (?,?,?,?,?,?,?,?,?,?)
        """, (
            subject_code,
            subject_name,
            professor,
            day,
            time_label,
            room,
            year_level,
            semester,
            class_type,
            professor_id
        ))

        conn.commit()
        conn.close()

        flash(f"Schedule '{subject_code} - {subject_name}' added successfully!", "success")

    except sqlite3.Error as e:
        flash(f"Database error: {str(e)}", "error")

    return redirect("/admin_schedules")


@app.route("/update_schedule", methods=["POST"])
def update_schedule():

    if "role" not in session:
        flash("Session expired. Please log in again.", "error")
        return redirect("/")

    if session["role"] != "admin":
        flash("Access denied. Admin only.", "error")
        return redirect("/dashboard")

    # ── Get schedule ID ─────────────────────────────────────────────────────
    try:
        schedule_id = int(request.form.get("id", 0))
    except (ValueError, TypeError):
        flash("Invalid schedule ID.", "error")
        return redirect("/admin_schedules")

    if schedule_id <= 0:
        flash("Invalid schedule ID.", "error")
        return redirect("/admin_schedules")

    # ── Validate and extract subject ────────────────────────────────────────
    subject = request.form.get("subject", "").strip()
    if "|" not in subject:
        flash("Invalid subject selection. Please select a subject from the list.", "error")
        return redirect("/admin_schedules")

    subject_code, subject_name = subject.split("|", 1)
    subject_code = subject_code.strip()
    subject_name = subject_name.strip()

    if not subject_code or not subject_name:
        flash("Subject code and name cannot be empty.", "error")
        return redirect("/admin_schedules")

    # ── Extract other fields ────────────────────────────────────────────────
    professor = request.form.get("professor", "").strip()
    day = request.form.get("day", "").strip()
    start_time = request.form.get("start_time", "").strip()
    end_time = request.form.get("end_time", "").strip()
    room = request.form.get("room", "").strip()
    year_level = request.form.get("year_level", "").strip()
    semester = request.form.get("semester", "").strip()
    class_type = request.form.get("class_type", "").strip()

    # ── Validate required fields ────────────────────────────────────────────
    missing = []
    if not professor: missing.append("Professor")
    if not day: missing.append("Day")
    if not start_time: missing.append("Start Time")
    if not end_time: missing.append("End Time")
    if not room: missing.append("Room")
    if not year_level: missing.append("Year Level")
    if not semester: missing.append("Semester")
    if not class_type: missing.append("Class Type")

    if missing:
        flash(f"Missing required fields: {', '.join(missing)}", "error")
        return redirect(f"/edit_schedule/{schedule_id}")

    # ── Format time range (with error handling) ─────────────────────────────
    try:
        time_label = format_time_range(start_time, end_time)
    except ValueError:
        flash("Invalid time format. Use HH:MM (e.g., 08:00).", "error")
        return redirect(f"/edit_schedule/{schedule_id}")

    # ── Update database ─────────────────────────────────────────────────────
    try:
        conn = db.connect()
        cursor = conn.cursor()

        cursor.execute(
            "SELECT employee_id FROM professors WHERE TRIM(fullname)=TRIM(?)",
            (professor,)
        )
        row = cursor.fetchone()
        professor_id = row[0] if row else ""

        cursor.execute("""
            UPDATE schedules
            SET
                subject_code=?,
                subject_name=?,
                professor=?,
                day=?,
                time=?,
                room=?,
                year_level=?,
                semester=?,
                class_type=?,
                professor_id=?
            WHERE id=?
        """, (
            subject_code,
            subject_name,
            professor,
            day,
            time_label,
            room,
            year_level,
            semester,
            class_type,
            professor_id,
            schedule_id
        ))

        conn.commit()
        conn.close()

        flash(f"Schedule '{subject_code} - {subject_name}' updated successfully!", "success")

    except sqlite3.Error as e:
        flash(f"Database error: {str(e)}", "error")

    return redirect("/admin_schedules")


# ==========================
# MOBILE / OFFLINE ATTENDANCE API
# ==========================
# Consumed by templates/scan_qr.html (browser scanner) and the Flutter app.

@app.route("/api/attendance/record", methods=["POST"])
def api_attendance_record():

    if "student_id" not in session:
        return jsonify({"success": False, "message": "Authentication required."}), 401

    payload = request.get_json() or {}
    qr_text = payload.get("qr")

    if not qr_text:
        return jsonify({"success": False, "message": "Invalid QR data."}), 400

    record_id = payload.get("uuid") or str(uuid.uuid4())
    scan_date = payload.get("scan_date") or datetime.now().strftime("%Y-%m-%d")
    scan_time = payload.get("scan_time") or datetime.now().strftime("%I:%M %p")

    parsed = parse_qr(qr_text)

    if not parsed:
        return jsonify({"success": False, "message": "Invalid QR format."}), 400

    conn = db.connect()
    cursor = conn.cursor()

    cursor.execute("SELECT id FROM attendance WHERE uuid=?", (record_id,))

    if cursor.fetchone():
        conn.close()
        return jsonify({"success": True, "message": "Attendance already recorded."})

    if parsed["version"] == 2:

        try:
            expires_dt = datetime.strptime(
                f"{parsed['date']} {parsed['expires_at']}",
                "%Y-%m-%d %I:%M %p"
            )
        except ValueError:
            conn.close()
            return jsonify({"success": False, "message": "Invalid expiration format."}), 400

        if datetime.now() > expires_dt:
            conn.close()
            return jsonify({"success": False, "message": "QR code expired."}), 400

        if not attendance_session_active(cursor, parsed):
            conn.close()
            return jsonify({"success": False, "message": "Attendance session is not active."}), 400

    if attendance_exists(cursor, session["student_id"], parsed["subject_code"],
                         scan_date, token=parsed.get("token")):
        conn.close()
        return jsonify({"success": False, "message": "Duplicate attendance detected."}), 409

    insert_attendance(
        cursor,
        session["student_id"],
        session["fullname"],
        parsed,
        scan_date,
        scan_time,
        record_id
    )

    conn.commit()
    conn.close()

    return jsonify({"success": True, "message": "Attendance Recorded Successfully."})


@app.route("/api/attendance/sync", methods=["POST"])
def api_attendance_sync():

    if "student_id" not in session:
        return jsonify({"success": False, "message": "Authentication required."}), 401

    payload = request.get_json() or {}
    records = payload.get("records", [])

    if not isinstance(records, list):
        return jsonify({"success": False, "message": "Invalid payload."}), 400

    results = []

    conn = db.connect()
    cursor = conn.cursor()

    for record in records:

        record_id = record.get("uuid")
        qr_text = record.get("qr")
        scan_date = record.get("scan_date") or datetime.now().strftime("%Y-%m-%d")
        scan_time = record.get("scan_time") or datetime.now().strftime("%I:%M %p")

        if not record_id or not qr_text:
            results.append({
                "uuid": record_id,
                "status": "failed",
                "message": "Invalid offline record."
            })
            continue

        cursor.execute("SELECT id FROM attendance WHERE uuid=?", (record_id,))

        if cursor.fetchone():
            results.append({
                "uuid": record_id,
                "status": "skipped",
                "message": "Already synced."
            })
            continue

        parsed = parse_qr(qr_text)

        if not parsed:
            results.append({
                "uuid": record_id,
                "status": "failed",
                "message": "Invalid QR format."
            })
            continue

        if parsed["version"] == 2:

            try:
                expires_dt = datetime.strptime(
                    f"{parsed['date']} {parsed['expires_at']}",
                    "%Y-%m-%d %I:%M %p"
                )
            except ValueError:
                results.append({
                    "uuid": record_id,
                    "status": "failed",
                    "message": "Invalid expiration format."
                })
                continue

            if datetime.now() > expires_dt:
                results.append({
                    "uuid": record_id,
                    "status": "failed",
                    "message": "QR code expired."
                })
                continue

            if not attendance_session_active(cursor, parsed):
                results.append({
                    "uuid": record_id,
                    "status": "failed",
                    "message": "Attendance session is not active."
                })
                continue

        if attendance_exists(cursor, session["student_id"], parsed["subject_code"],
                             scan_date, token=parsed.get("token")):
            results.append({
                "uuid": record_id,
                "status": "skipped",
                "message": "Duplicate attendance."
            })
            continue

        insert_attendance(
            cursor,
            session["student_id"],
            session["fullname"],
            parsed,
            scan_date,
            scan_time,
            record_id
        )

        results.append({
            "uuid": record_id,
            "status": "synced",
            "message": "Attendance synced."
        })

    conn.commit()
    conn.close()

    return jsonify({"success": True, "results": results})


@app.route("/delete_schedule/<int:id>", methods=["POST"])
def delete_schedule(id):

    if "role" not in session:
        flash("Session expired. Please log in again.", "error")
        return redirect("/")

    if session["role"] != "admin":
        flash("Access denied. Admin only.", "error")
        return redirect("/dashboard")

    try:
        conn = db.connect()
        cursor = conn.cursor()

        # Fetch schedule info for the flash message
        cursor.execute("SELECT subject_code, subject_name FROM schedules WHERE id=?", (id,))
        schedule = cursor.fetchone()

        if schedule:
            subject_code, subject_name = schedule
            cursor.execute("DELETE FROM schedules WHERE id=?", (id,))
            conn.commit()
            flash(f"Schedule '{subject_code} - {subject_name}' deleted.", "success")
        else:
            flash("Schedule not found.", "error")

        conn.close()

    except sqlite3.Error as e:
        flash(f"Database error: {str(e)}", "error")

    return redirect("/admin_schedules")


# ── End of fixed schedule management routes ─────────────────────────────


@app.route("/edit_schedule/<int:id>")
def edit_schedule(id):

    if "role" not in session:
        return redirect("/")

    if session["role"] != "admin":
        return redirect("/dashboard")

    conn = db.connect()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT id, subject_code, subject_name, professor, day, time,
               room, year_level, semester, class_type
        FROM schedules
        WHERE id=?
    """, (id,))
    schedule = cursor.fetchone()

    cursor.execute("""
        SELECT subject_code, subject_name, professor, year_level, semester
        FROM subjects
        ORDER BY subject_code
    """)
    subjects = cursor.fetchall()

    cursor.execute("""
        SELECT fullname
        FROM professors
        ORDER BY fullname
    """)
    professors = cursor.fetchall()

    conn.close()

    if schedule is None:
        flash("Schedule not found.", "error")
        return redirect("/admin_schedules")

    start_time, end_time = parse_time_range(schedule[5])

    return render_template(
        "edit_schedule.html",
        schedule=schedule,
        subjects=subjects,
        professors=professors,
        start_time=start_time,
        end_time=end_time
    )



@app.route("/generate_qr")
def generate_qr():

    if "role" not in session:
        return redirect("/")

    if session["role"] not in ["admin", "professor"]:
        return redirect("/dashboard")

    schedules = get_qr_schedules()

    return render_template(
        "generate_qr.html",
        schedules=schedules,
        verified_professor=session.get("verified_professor_id"),
        role=session["role"]
    )

@app.route("/create_qr", methods=["POST"])
def create_qr():

    if "role" not in session:
        return redirect("/")

    if session["role"] not in ["admin", "professor"]:
        return redirect("/dashboard")

    # A professor must scan their own identity QR first. The template already
    # reflected this, but the check was never enforced server-side, so the
    # step could be skipped by POSTing straight to /create_qr.
    if session["role"] == "professor":
        if session.get("verified_professor_id") != session.get("professor_id"):
            return redirect("/verify_professor_qr")


    schedule_id = request.form["schedule_id"]
    date = request.form.get("date")
    expires_at = request.form.get("expires_at")


    conn = db.connect()
    cursor = conn.cursor()


    cursor.execute("""
        SELECT
            s.subject_code,
            s.subject_name,
            s.professor,
            s.day,
            s.time,
            COALESCE(NULLIF(p.employee_id,''), NULLIF(s.professor_id,''), '') AS professor_id
        FROM schedules s
        LEFT JOIN professors p
            ON TRIM(LOWER(s.professor))=TRIM(LOWER(p.fullname))
        WHERE s.id=?
    """, (schedule_id,))


    schedule = cursor.fetchone()


    if not schedule:
        conn.close()
        return render_template(
            "generate_qr.html",
            error="Invalid schedule selection.",
            schedules=get_qr_schedules(),
            verified_professor=session.get("verified_professor_id"),
            role=session["role"]
        )


    subject_code, subject_name, schedule_professor, day, schedule_time, schedule_professor_id = schedule


    if session["role"] == "professor":

        professor_id = session["professor_id"]
        professor_name = session["professor_name"]

    else:

        professor_id = schedule_professor_id
        professor_name = schedule_professor

        if not professor_id:
            conn.close()
            return render_template(
                "generate_qr.html",
                error="Selected subject has no registered professor.",
                schedules=get_qr_schedules(),
                verified_professor=session.get("verified_professor_id"),
                role=session["role"]
            )


    if not date or not expires_at:

        conn.close()

        return render_template(
            "generate_qr.html",
            error="Date and expiration time are required.",
            schedules=get_qr_schedules(),
            verified_professor=session.get("verified_professor_id"),
            role=session["role"]
        )


    try:
        expires_dt = datetime.strptime(expires_at, "%H:%M")
        expires_at = expires_dt.strftime("%I:%M %p")

    except ValueError:
        pass



    # CREATE QR TOKEN
    token = str(uuid.uuid4())


    # QR DATA
    qr_payload = "|".join([
        subject_code,
        subject_name,
        professor_id,
        professor_name,
        day,
        schedule_time,
        date,
        expires_at,
        token
    ])



    # SAVE QR IMAGE

    os.makedirs("static/qr", exist_ok=True)


    qr_url = qr_payload


    img = qrcode.make(qr_url)


    img_path = f"qr/attendance_{token}.png"


    img.save(f"static/{img_path}")



    # SAVE ATTENDANCE SESSION

    cursor.execute("""
        INSERT INTO attendance_sessions
        (
            professor_id,
            professor_name,
            subject_code,
            subject_name,
            day,
            schedule,
            date,
            expires_at,
            token,
            active
        )
        VALUES (?,?,?,?,?,?,?,?,?,1)

    """, (
        professor_id,
        professor_name,
        subject_code,
        subject_name,
        day,
        schedule_time,
        date,
        expires_at,
        token
    ))


    conn.commit()
    conn.close()



    return render_template(
        "generate_qr.html",
        success=True,
        qr_url=qr_url,
        qr_image=img_path,
        verified_professor=session.get("verified_professor_id"),
        schedules=get_qr_schedules(),
        role=session["role"]
    )

@app.route("/professor_qr")
def professor_qr():
    if "role" not in session or session["role"] != "professor":
        return redirect("/professor_login")

    professor_id = session["professor_id"]
    professor_name = session["professor_name"]

    token = str(uuid.uuid4())
    qr_payload = "|".join(["PROF", professor_id, professor_name, token])

    os.makedirs("static/qr", exist_ok=True)
    img_path = f"qr/professor_{professor_id}.png"
    qrcode.make(qr_payload).save(f"static/{img_path}")

    # The verification step compares id + name only, so the token can be fresh
    # every time the page is opened.
    return render_template(
        "professor_qr.html",
        qr_image=img_path,
        qr_payload=qr_payload
    )


@app.route("/student_schedule")
def student_schedule():
    if "student_id" not in session:
        return redirect("/")

    conn = db.connect()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT subject_code, subject_name, professor, day, time, room
        FROM schedules
        ORDER BY day, time
    """)

    schedules = cursor.fetchall()
    conn.close()

    return render_template(
        "student_schedule.html",
        schedules=schedules,
        fullname=session["fullname"]
    )


@app.route("/verify_professor_qr", methods=["GET","POST"])
def verify_professor_qr():
    if "role" not in session or session["role"] != "professor":
        return redirect("/professor_login")

    if request.method == "GET":
        return render_template("verify_professor_qr.html")

    payload = request.get_json() if request.is_json else request.form
    qr_text = payload.get("qr")
    parsed = parse_professor_qr(qr_text)
    if not parsed:
        if request.is_json:
            return jsonify({"success": False, "message": "Invalid Professor QR."}), 400
        return render_template("verify_professor_qr.html", error="Invalid Professor QR.")

    if parsed["professor_id"] != session["professor_id"] or parsed["professor_name"] != session["professor_name"]:
        if request.is_json:
            return jsonify({"success": False, "message": "Professor QR mismatch."}), 403
        return render_template("verify_professor_qr.html", error="Professor QR mismatch.")

    session["verified_professor_id"] = parsed["professor_id"]
    if request.is_json:
        return jsonify({"success": True, "message": "Professor verified."})

    return render_template("verify_professor_qr.html", success="Professor verified. You may now generate attendance QR codes.")

@app.route("/active_attendance")
def active_attendance():
    if "role" not in session or session["role"] != "professor":
        return redirect("/professor_login")

    professor_id = session["professor_id"]
    conn = db.connect()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, professor_id, professor_name, subject_code, subject_name, day, schedule, date, expires_at, token
        FROM attendance_sessions
        WHERE professor_id=? AND active=1
        ORDER BY id DESC
        LIMIT 1
    """, (professor_id,))
    active_session = cursor.fetchone()
    attendance = []
    if active_session:
        token = active_session[9]
        cursor.execute("""
            SELECT student_id, fullname, subject_code, subject_name, date, time, status
            FROM attendance
            WHERE token=?
            ORDER BY fullname
        """, (token,))
        attendance = cursor.fetchall()
    conn.close()

    return render_template("active_attendance.html", active_session=active_session, attendance=attendance)

@app.route("/close_attendance_session/<int:session_id>", methods=["POST"])
def close_attendance_session(session_id):
    if "role" not in session or session["role"] != "professor":
        return redirect("/professor_login")

    conn = db.connect()
    cursor = conn.cursor()
    cursor.execute("UPDATE attendance_sessions SET active=0 WHERE id=? AND professor_id=?", (session_id, session["professor_id"]))
    conn.commit()
    conn.close()

    return redirect("/active_attendance")

@app.route("/scan_qr")
def scan_qr():

    return render_template("scan_qr.html")

@app.route("/mark_attendance")
def mark_attendance():

    qr = request.args.get("qr")

    if "student_id" not in session:
        session["pending_qr"] = qr
        return redirect("/")

    if not qr:
        return "Invalid QR"

    parsed = parse_qr(qr)
    if not parsed:
        return "Invalid QR Data"

    if parsed["version"] == 2:
        try:
            expires_dt = datetime.strptime(f"{parsed['date']} {parsed['expires_at']}", "%Y-%m-%d %I:%M %p")
        except ValueError:
            return "Invalid expiration format."
        if datetime.now() > expires_dt:
            return "QR code expired."

    now = datetime.now()
    date = parsed["date"] if parsed["version"] == 2 else now.strftime("%Y-%m-%d")
    current_time = now.strftime("%I:%M %p")

    conn = db.connect()
    cursor = conn.cursor()

    if parsed["version"] == 2:
        token = parsed["token"]
        if not attendance_session_active(cursor, parsed):
            conn.close()
            return "Attendance session is not active."
        if attendance_exists(cursor, session["student_id"], parsed["subject_code"], date, token=token):
            conn.close()
            return "Duplicate attendance detected."
    else:
        if attendance_exists(cursor, session["student_id"], parsed["subject_code"], date):
            conn.close()
            return "Duplicate attendance detected."

    insert_attendance(
        cursor,
        session["student_id"],
        session["fullname"],
        parsed,
        date,
        current_time,
        str(uuid.uuid4())
    )

    conn.commit()
    conn.close()

    return redirect("/dashboard")


# ==========================
# STUDENT ATTENDANCE PAGE
# ==========================
@app.route("/student_attendance")
def student_attendance():

    if "student_id" not in session:
        return redirect("/")

    conn = db.connect()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT subject_code,
               subject_name,
               professor,
               date,
               time,
               status
        FROM attendance
        WHERE student_id=?
        ORDER BY id DESC
    """, (session["student_id"],))

    records = cursor.fetchall()

    conn.close()

    return render_template(
        "student_attendance.html",
        records=records,
        fullname=session["fullname"]
    )

@app.route("/admin_students")
def admin_students():

    if "role" not in session:
        return redirect("/")

    if session["role"] != "admin":
        return redirect("/dashboard")

    conn = db.connect()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT id,
               student_id,
               fullname,
               email
        FROM students
        WHERE role='student'
        ORDER BY fullname
    """)

    students = cursor.fetchall()

    conn.close()

    return render_template(
        "students.html",
        fullname=session["fullname"],
        students=students
    )


@app.route("/add_student", methods=["GET", "POST"])
def add_student():

    if "role" not in session:
        return redirect("/")

    if session["role"] != "admin":
        return redirect("/dashboard")

    if request.method == "POST":
        student_id = request.form["student_id"]
        fullname = request.form["fullname"]
        email = request.form["email"]
        password = request.form["password"]

        conn = db.connect()
        cursor = conn.cursor()

        try:
            cursor.execute(
                "INSERT INTO students(student_id, fullname, email, password, password_hash, role) VALUES (?, ?, ?, ?, ?, ?)",
                (student_id, fullname, email, "", hash_password(password), "student")
            )
            conn.commit()
        except sqlite3.IntegrityError:
            conn.close()
            return render_template(
                "add_student.html",
                fullname=session["fullname"],
                error="Student ID already exists!"
            )
        finally:
            conn.close()

        return redirect("/admin_students")

    return render_template(
        "add_student.html",
        fullname=session["fullname"]
    )


@app.route("/admin_reports")
def admin_reports():

    if "role" not in session:
        return redirect("/")

    if session["role"] != "admin":
        return redirect("/dashboard")

    conn = db.connect()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT fullname,
               subject_name,
               professor,
               date,
               time,
               status
        FROM attendance
        ORDER BY id DESC
    """)

    attendance = cursor.fetchall()

    conn.close()

    return render_template(
        "reports.html",
        attendance=attendance
    )


@app.route("/admin_attendance")
def admin_attendance():

    if "role" not in session:
        return redirect("/")

    if session["role"] != "admin":
        return redirect("/dashboard")

    conn = db.connect()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT *
        FROM attendance
        ORDER BY id DESC
    """)

    attendance = cursor.fetchall()

    conn.close()

    return render_template(
        "attendance.html",
        attendance=attendance
    )

@app.route("/professor_login", methods=["GET","POST"])
def professor_login():

    if request.method == "GET":
        return render_template("professor_login.html")


    email = request.form["email"]
    password = request.form["password"]

    if rate_limit_hit("professor_login:%s" % client_ip()):
        log.warning("rate limit: professor login from %s", client_ip())
        return render_template(
            "professor_login.html",
            error="Too many login attempts. Please wait a few minutes and try again."
        ), 429


    conn = db.connect()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()


    cursor.execute("""
        SELECT *
        FROM professors
        WHERE email=?
    """,
    (email,))


    row = cursor.fetchone()

    professor = None
    if check_password_with_migration(conn, "professors", "employee_id", row, password):
        professor = row

    conn.close()


    if professor:

        rate_limit_reset("professor_login:%s" % client_ip())
        log.info("login ok: professor=%s from %s",
                 professor["employee_id"], client_ip())

        session.clear()

        session["professor_id"] = professor["employee_id"]
        session["professor_name"] = professor["fullname"]
        session["role"] = "professor"

        return redirect("/professor_dashboard")


    else:

        log.warning("login failed: professor email=%r from %s", email, client_ip())
        return render_template(
            "professor_login.html",
            error="Invalid Professor Email or Password"
        )


@app.route("/professor_dashboard")
def professor_dashboard():

    if "professor_id" not in session:
        return redirect("/professor_login")

    conn = db.connect()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT COUNT(*) FROM attendance_sessions WHERE professor_id=? AND active=1",
        (session["professor_id"],)
    )

    active_sessions = cursor.fetchone()[0]
    conn.close()

    return render_template(
        "professor_dashboard.html",
        name=session["professor_name"],
        active_sessions=active_sessions
    )


@app.route("/professor_signup", methods=["GET", "POST"])
def professor_signup():

    if request.method == "GET":
        return render_template("professor_signup.html")

    employee_id = request.form["employee_id"]
    fullname = request.form["fullname"]
    email = request.form["email"]
    password = request.form["password"]
    department = request.form["department"]

    try:

        conn = db.connect()
        cursor = conn.cursor()

        cursor.execute("""
        INSERT INTO professors
        (employee_id,fullname,email,password,password_hash,department)
        VALUES (?,?,?,?,?,?)
        """, (
            employee_id,
            fullname,
            email,
            "",
            hash_password(password),
            department
        ))

        conn.commit()
        conn.close()

        return redirect("/professor_login")

    except sqlite3.IntegrityError:

        return render_template(
            "professor_signup.html",
            error="Professor ID or Email already exists!"
        )


@app.route("/professor_logout")
def professor_logout():

    session.clear()

    return redirect("/professor_login")


@app.route("/test")
def test():
    return "Server is working!"


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)

