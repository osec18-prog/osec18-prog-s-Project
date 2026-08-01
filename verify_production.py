"""CampusConnect+ production verification.

Runs the full health + endpoint + functional check against a LIVE deployment.

    python verify_production.py https://your-service.onrender.com ADMIN_PASSWORD

The admin password is the value you set for ADMIN_PASSWORD on Render. Without
it the authenticated tests are skipped and the run is reported as incomplete.

Read-only by default: it creates nothing except one attendance session, which
it closes again. Pass --no-write to skip even that.
"""
import json
import sys
import time
import urllib.error
import urllib.request

RESULTS = []


def record(section, name, ok, detail=""):
    RESULTS.append((section, name, ok, detail))
    print("   %-52s %s" % (name[:52], "PASS" if ok else "FAIL"))
    if detail and not ok:
        print("        %s" % detail)


def http(method, url, body=None, token=None, timeout=60):
    """Return (status, parsed_json_or_text, elapsed_seconds)."""
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Accept", "application/json")
    if data:
        req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", "Bearer " + token)
    started = time.time()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read().decode("utf-8", "replace")
            status = r.getcode()
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", "replace")
        status = e.code
    except Exception as e:                      # noqa: BLE001
        return 0, str(e), time.time() - started
    try:
        return status, json.loads(raw), time.time() - started
    except ValueError:
        return status, raw, time.time() - started


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return 2

    base = sys.argv[1].rstrip("/")
    admin_pw = sys.argv[2] if len(sys.argv) > 2 else None
    allow_write = "--no-write" not in sys.argv

    print("=" * 74)
    print("CampusConnect+ PRODUCTION VERIFICATION")
    print("=" * 74)
    print("   Target : %s" % base)
    print("   Time   : %s" % time.strftime("%Y-%m-%d %H:%M:%S"))
    print("   Mode   : %s" % ("full" if admin_pw else "unauthenticated only"))
    print()

    # ---------------------------------------------------------------- wake up
    # Render free instances sleep. The first request can take ~60s.
    print("-- COLD START --")
    status, _, elapsed = http("GET", base + "/test", timeout=120)
    print("   first request: HTTP %s in %.1fs" % (status, elapsed))
    if status == 0:
        print("\n   Cannot reach the host at all. Is the URL right and the service Live?")
        return 1
    print()

    # ---------------------------------------------------------------- health
    print("-- PUBLIC PAGES --")
    for path, expect in [("/", 200), ("/login", 200), ("/signup", 200),
                         ("/admin_login", 200), ("/professor_login", 200),
                         ("/professor_signup", 200), ("/scan_qr", 200),
                         ("/test", 200), ("/api/ping", 200), ("/app/", 200)]:
        st, body, el = http("GET", base + path)
        record("public", "%-22s -> %s" % (path, st), st == expect,
               "expected %s, got %s" % (expect, st))

    st, body, _ = http("GET", base + "/api/ping")
    record("public", "/api/ping identifies the service",
           isinstance(body, dict) and body.get("service") == "CampusConnect+",
           "body=%r" % (body,))

    print()
    print("-- HTTPS / SECURITY HEADERS --")
    record("security", "served over HTTPS", base.startswith("https://"), base)
    try:
        req = urllib.request.Request(base + "/login")
        with urllib.request.urlopen(req, timeout=60) as r:
            h = {k.lower(): v for k, v in r.getheaders()}
    except Exception as e:                       # noqa: BLE001
        h = {}
        print("   (could not read headers: %s)" % e)

    for name, expected in [("x-content-type-options", "nosniff"),
                           ("x-frame-options", "SAMEORIGIN"),
                           ("referrer-policy", "same-origin")]:
        record("security", "%s: %s" % (name, expected),
               h.get(name) == expected, "got %r" % h.get(name))
    record("security", "HSTS present (FLASK_ENV=production)",
           "strict-transport-security" in h, "got %r" % h.get("strict-transport-security"))
    record("security", "session cookie marked Secure",
           "secure" in h.get("set-cookie", "").lower() or "set-cookie" not in h,
           "set-cookie=%r" % h.get("set-cookie"))

    print()
    print("-- NO 500s ON PUBLIC SURFACE --")
    bad = []
    for path in ["/", "/login", "/signup", "/admin_login", "/professor_login",
                 "/scan_qr", "/test", "/api/ping", "/app/", "/dashboard",
                 "/admin_dashboard", "/professor_dashboard", "/nonexistent-page"]:
        st, _, _ = http("GET", base + path)
        if st >= 500:
            bad.append((path, st))
    record("stability", "no 5xx from any public route", not bad, "5xx=%s" % bad)

    print()
    print("-- API AUTH REJECTION --")
    st, body, _ = http("GET", base + "/api/me")
    record("api", "/api/me without token -> 401", st == 401, "got %s" % st)
    st, _, _ = http("GET", base + "/api/me", token="forged.token.value")
    record("api", "/api/me with forged token -> 401", st == 401, "got %s" % st)
    st, body, _ = http("POST", base + "/api/login", body={"identifier": "", "password": ""})
    record("api", "/api/login with empty body -> 400", st == 400, "got %s" % st)

    if not admin_pw:
        print()
        print("-- AUTHENTICATED TESTS SKIPPED --")
        print("   Re-run with the admin password to exercise login, QR and attendance:")
        print("     python verify_production.py %s <ADMIN_PASSWORD>" % base)
    else:
        print()
        print("-- ADMIN LOGIN --")
        st, body, _ = http("POST", base + "/api/login",
                           body={"role": "admin", "identifier": "admin",
                                 "password": admin_pw})
        ok = st == 200 and isinstance(body, dict) and body.get("success")
        record("auth", "POST /api/login (admin) -> 200", ok,
               "status=%s body=%r" % (st, str(body)[:160]))

        if not ok:
            print("\n   Admin login failed — later tests cannot run.")
            print("   Check ADMIN_PASSWORD in the Render dashboard matches what you passed.")
        else:
            token = body.get("token")
            jwt = body.get("jwt")
            record("auth", "response carries token + jwt + user",
                   bool(token) and bool(jwt) and isinstance(body.get("user"), dict))

            st, me, _ = http("GET", base + "/api/me", token=token)
            record("auth", "GET /api/me with bearer token -> 200",
                   st == 200 and me.get("user", {}).get("role") == "admin",
                   "status=%s" % st)

            print()
            print("-- READ ENDPOINTS --")
            for path, key in [("/api/announcements", "announcements"),
                              ("/api/subjects", "subjects"),
                              ("/api/schedules", "schedules"),
                              ("/api/professors", "professors"),
                              ("/api/students", "students"),
                              ("/api/stats", None),
                              ("/api/attendance", "attendance"),
                              ("/api/attendance/sessions", "sessions")]:
                st, b, el = http("GET", base + path, token=token)
                shape = (key is None) or (isinstance(b, dict) and key in b)
                record("api", "GET %-28s -> %s" % (path, st),
                       st == 200 and shape, "status=%s keys=%s"
                       % (st, list(b)[:6] if isinstance(b, dict) else b))

            print()
            print("-- QR GENERATION + ATTENDANCE --")
            st, scheds, _ = http("GET", base + "/api/schedules", token=token)
            rows = scheds.get("schedules", []) if isinstance(scheds, dict) else []
            if not rows:
                record("qr", "a schedule exists to generate a QR for", False,
                       "no schedules on the server — run init_db.py or add one")
            elif not allow_write:
                print("   (--no-write: skipping QR creation)")
            else:
                sched_id = rows[0].get("id")
                st, b, _ = http("POST", base + "/api/qr/create", token=token,
                                body={"schedule_id": sched_id, "expires_at": "23:59"})
                ok = st == 200 and isinstance(b, dict) and "session" in b
                record("qr", "POST /api/qr/create -> 200", ok,
                       "status=%s body=%r" % (st, str(b)[:160]))
                if ok:
                    sess = b["session"]
                    payload = sess.get("payload", "")
                    record("qr", "payload has the 9 v2 fields",
                           len(payload.split("|")) == 9, "payload=%r" % payload[:90])
                    record("qr", "session row has an id and token",
                           bool(sess.get("id")) and bool(sess.get("token")))

                    st, b2, _ = http("POST",
                                     base + "/api/attendance/sessions/%s/close"
                                     % sess["id"], token=token)
                    record("qr", "POST close session -> 200", st == 200,
                           "status=%s" % st)

            print()
            print("-- RATE LIMITING --")
            codes = []
            for _ in range(12):
                st, _, _ = http("POST", base + "/api/login",
                                body={"role": "student", "identifier": "no-such-user",
                                      "password": "wrong"})
                codes.append(st)
            record("security", "login rate limited after ~10 attempts",
                   429 in codes, "codes=%s" % codes)

    # ---------------------------------------------------------------- summary
    print()
    print("=" * 74)
    print("SUMMARY")
    print("=" * 74)
    sections = {}
    for section, _, ok, _ in RESULTS:
        p, f = sections.get(section, (0, 0))
        sections[section] = (p + (1 if ok else 0), f + (0 if ok else 1))
    for section in sorted(sections):
        p, f = sections[section]
        print("   %-12s %2d passed, %2d failed" % (section, p, f))

    failed = [(s, n, d) for s, n, ok, d in RESULTS if not ok]
    total = len(RESULTS)
    print()
    print("   TOTAL: %d passed, %d failed, out of %d"
          % (total - len(failed), len(failed), total))
    if failed:
        print()
        print("   FAILURES:")
        for s, n, d in failed:
            print("     [%s] %s" % (s, n))
            if d:
                print("           %s" % d)
    print()
    print("   VERDICT:", "PRODUCTION HEALTHY" if not failed else "ISSUES FOUND")
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
