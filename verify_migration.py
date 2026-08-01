"""Exercise the real CampusConnect+ routes against whichever backend is live.

    python verify_migration.py                  # runs against the current backend
    python verify_migration.py --save before    # write a snapshot
    python verify_migration.py --compare before # run and diff against one

Unlike verify_production.py, which tests a DEPLOYED site over HTTP, this
drives the Flask application in-process. That makes it the right tool for
proving the SQLite -> PostgreSQL migration changed nothing: capture a
snapshot on SQLite, switch DATABASE_URL on, run again, and compare.

    # on SQLite
    python verify_migration.py --save sqlite_baseline
    # then, with DATABASE_URL set
    python verify_migration.py --compare sqlite_baseline

IMPORTANT: both runs must start from the SAME database state. Logging in with
a legacy plaintext password upgrades that row to a hash and blanks the
plaintext (core.check_password_with_migration), so a second run against an
already-exercised database will fail those logins and report differences that
are not regressions. Take the SQLite snapshot immediately before running
migrate_data.py, so the PostgreSQL copy starts from exactly what was
snapshotted.

Response bodies are reduced to a stable shape -- length, row markers and a
hash of the content with CSRF tokens and timestamps normalised away -- so the
comparison catches real differences without tripping over values that
legitimately change between runs.
"""

import argparse
import hashlib
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

os.environ.setdefault("SECRET_KEY", "verify-migration-secret")
os.environ.setdefault("JWT_SECRET", "verify-migration-jwt")
if not os.environ.get("ADMIN_PASSWORD"):
    raise SystemExit(
        "ADMIN_PASSWORD is not set. It is needed to exercise the admin and "
        'API login paths.\n  $env:ADMIN_PASSWORD = "<password>"')

import db          # noqa: E402
import app as appmod  # noqa: E402

flask_app = appmod.app
flask_app.config["WTF_CSRF_ENABLED"] = False   # test-only; production untouched
flask_app.config["TESTING"] = True

OUT = []


def emit(section, name, value):
    OUT.append("%-12s %-44s %s" % (section, name, value))


def shape(data):
    if isinstance(data, bytes):
        data = data.decode("utf-8", "replace")
    data = re.sub(r'name="csrf_token"[^>]*value="[^"]*"', "CSRF", data)
    data = re.sub(r'name="csrf-token"[^>]*content="[^"]*"', "CSRF", data)
    data = re.sub(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}(:\d{2})?", "TS", data)
    data = re.sub(r"\d{1,2}:\d{2} [AP]M", "TIME", data)
    return "len~%d tr=%d td=%d h=%s" % (
        len(data) // 50, data.count("<tr"), data.count("<td"),
        hashlib.md5(data.encode()).hexdigest()[:8])


def anon_pages(client):
    for route in ["/", "/login", "/signup", "/admin_login", "/professor_login",
                  "/professor_signup", "/scan_qr", "/test", "/api/ping"]:
        r = client.get(route)
        emit("anon", route, "%s %s" % (r.status_code, shape(r.data)))


def admin_pages(client):
    r = client.post("/admin_login",
                    data={"username": os.environ.get("ADMIN_USERNAME", "admin"),
                          "password": os.environ["ADMIN_PASSWORD"]})
    emit("admin", "POST /admin_login", r.status_code)
    for route in ["/admin_dashboard", "/admin_students", "/admin_professors",
                  "/admin_subjects", "/admin_schedules", "/admin_announcements",
                  "/admin_attendance", "/admin_reports", "/edit_admin",
                  "/generate_qr", "/active_attendance"]:
        r = client.get(route)
        emit("admin", route, "%s %s" % (r.status_code, shape(r.data)))
    client.get("/logout")


def student_pages(client, sid, pw):
    r = client.post("/login", data={"student_id": sid, "password": pw})
    emit("student", "POST /login", r.status_code)
    for route in ["/dashboard", "/student_schedule", "/student_attendance",
                  "/student_announcements", "/mark_attendance"]:
        r = client.get(route)
        emit("student", route, "%s %s" % (r.status_code, shape(r.data)))
    client.get("/logout")


def professor_pages(client, emp, pw):
    r = client.post("/professor_login", data={"employee_id": emp, "password": pw})
    emit("prof", "POST /professor_login", r.status_code)
    for route in ["/professor_dashboard", "/professor_qr"]:
        r = client.get(route)
        emit("prof", route, "%s %s" % (r.status_code, shape(r.data)))
    client.get("/professor_logout")


def api_endpoints(client):
    r = client.get("/api/ping")
    emit("api", "GET /api/ping", "%s %s" % (r.status_code, sorted((r.get_json() or {}).keys())))

    r = client.post("/api/login", json={"username": os.environ.get("ADMIN_USERNAME", "admin"),
                                        "password": os.environ["ADMIN_PASSWORD"]})
    j = r.get_json() or {}
    emit("api", "POST /api/login", "%s keys=%s" % (r.status_code, sorted(j.keys())))
    token = j.get("token")

    r = client.post("/api/auth/login", json={"identifier": os.environ.get("ADMIN_USERNAME", "admin"),
                                             "password": os.environ["ADMIN_PASSWORD"]})
    emit("api", "POST /api/auth/login",
         "%s keys=%s" % (r.status_code, sorted((r.get_json() or {}).keys())))

    hdr = {"Authorization": "Bearer %s" % token} if token else {}
    for route in ["/api/me", "/api/schedules", "/api/students", "/api/professors",
                  "/api/subjects", "/api/announcements", "/api/attendance",
                  "/api/stats", "/api/departments", "/api/courses",
                  "/api/sections", "/api/events", "/api/notifications",
                  "/api/attendance/sessions"]:
        r = client.get(route, headers=hdr)
        j = r.get_json()
        if isinstance(j, dict):
            desc = "dict keys=%s" % sorted(j.keys())[:6]
        elif isinstance(j, list):
            desc = "list n=%d keys=%s" % (
                len(j), sorted(j[0].keys())[:8] if j and isinstance(j[0], dict) else [])
        else:
            desc = type(j).__name__
        emit("api", "GET " + route, "%s %s" % (r.status_code, desc))

    for route in ["/api/me", "/api/students"]:
        emit("api-noauth", "GET " + route, client.get(route).status_code)


def row_counts():
    conn = db.connect()
    cur = conn.cursor()
    for t in ["students", "professors", "subjects", "schedules", "announcements",
              "attendance", "attendance_sessions", "api_tokens", "revoked_jwts"]:
        cur.execute('SELECT COUNT(*) FROM "%s"' % t)
        emit("dbcount", t, cur.fetchone()[0])
    conn.close()


def pick_fixtures():
    conn = db.get_db()
    cur = conn.cursor()
    cur.execute("SELECT student_id, password FROM students "
                "WHERE role IS NULL OR role!='admin' ORDER BY id LIMIT 1")
    stu = cur.fetchone()
    cur.execute("SELECT employee_id, password FROM professors ORDER BY id LIMIT 1")
    prof = cur.fetchone()
    conn.close()
    return stu, prof


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--save", metavar="NAME", help="write the report to NAME.txt")
    ap.add_argument("--compare", metavar="NAME", help="diff against NAME.txt")
    args = ap.parse_args()

    emit("backend", "database", db.backend())
    emit("routes", "count", len(list(flask_app.url_map.iter_rules())))

    stu, prof = pick_fixtures()
    emit("fixture", "student", stu["student_id"] if stu else None)
    emit("fixture", "professor", prof["employee_id"] if prof else None)

    with flask_app.test_client() as c:
        anon_pages(c)
    with flask_app.test_client() as c:
        admin_pages(c)
    with flask_app.test_client() as c:
        student_pages(c, stu["student_id"] if stu else "x",
                      (stu["password"] if stu and stu["password"] else "prof123"))
    with flask_app.test_client() as c:
        professor_pages(c, prof["employee_id"] if prof else "T001",
                        (prof["password"] if prof and prof["password"] else "prof123"))
    with flask_app.test_client() as c:
        api_endpoints(c)

    row_counts()

    report = "\n".join(OUT)
    print(report)

    if args.save:
        path = args.save if args.save.endswith(".txt") else args.save + ".txt"
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(report + "\n")
        print("\nSaved snapshot: %s" % path)

    if args.compare:
        path = args.compare if args.compare.endswith(".txt") else args.compare + ".txt"
        if not os.path.exists(path):
            raise SystemExit("No snapshot at %s" % path)
        with open(path, encoding="utf-8") as fh:
            baseline = fh.read().strip().splitlines()
        current = report.strip().splitlines()

        # The backend line is expected to differ -- that is the point.
        base_cmp = [l for l in baseline if not l.startswith("backend")]
        cur_cmp = [l for l in current if not l.startswith("backend")]

        import difflib
        diff = list(difflib.unified_diff(base_cmp, cur_cmp,
                                         fromfile=path, tofile="current", lineterm=""))
        print()
        print("=" * 74)
        if not diff:
            print("IDENTICAL — %d checks match the snapshot." % len(cur_cmp))
            print("=" * 74)
            return 0
        print("DIFFERENCES FOUND — %d line(s)" % len([d for d in diff if d[:1] in "+-"]))
        print("=" * 74)
        print("\n".join(diff))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
