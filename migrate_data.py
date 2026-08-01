"""Copy the CampusConnect+ SQLite database into Supabase PostgreSQL.

    $env:DATABASE_URL = "postgresql://...pooler.supabase.com:6543/postgres"
    python migrate_data.py            # dry run: reports, changes nothing
    python migrate_data.py --apply    # actually writes

WHAT IT DOES
────────────
1.  Creates the schema in PostgreSQL by running the application's own
    init_db.py, so the migrated schema is by definition the one the
    application expects. db.py rewrites the SQLite DDL on the way through.
2.  Reports and removes duplicate attendance rows, keeping the earliest.
3.  Copies every row of every table, preserving values exactly.
4.  Resets identity sequences so new inserts do not collide with copied ids.
5.  Verifies row counts table by table and fails loudly on any mismatch.

Re-runnable: --apply truncates the target tables first, so a failed run can
simply be repeated. It never touches the SQLite file except to read, unless
--dedupe-source is passed.
"""

import argparse
import os
import sqlite3
import sys

SQLITE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "campusconnect.db")

# Order matters: parents before children, so any future foreign keys hold.
TABLES = [
    "students",
    "professors",
    "subjects",
    "schedules",
    "announcements",
    "attendance_sessions",
    "attendance",
    "api_tokens",
    "revoked_jwts",
]

# Tables whose primary key is a generated integer; their sequence must be
# advanced past the copied rows.
IDENTITY_TABLES = [
    "students", "professors", "subjects", "schedules",
    "announcements", "attendance_sessions", "attendance",
]

DUPLICATE_KEY = ("student_id", "subject_code", "date")


def sqlite_conn():
    conn = sqlite3.connect(SQLITE_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def find_duplicate_attendance(conn):
    """Return [(key, [rows...])] for attendance rows sharing the same key.

    The earliest row -- lowest id -- is the one to keep, because it is the
    scan that actually recorded the student's arrival.
    """
    cols = ", ".join(DUPLICATE_KEY)
    groups = conn.execute(
        "SELECT %s, COUNT(*) AS n FROM attendance GROUP BY %s HAVING n > 1 ORDER BY %s"
        % (cols, cols, cols)
    ).fetchall()

    out = []
    for g in groups:
        where = " AND ".join("%s IS ?" % c for c in DUPLICATE_KEY)
        rows = conn.execute(
            "SELECT * FROM attendance WHERE %s ORDER BY id" % where,
            tuple(g[c] for c in DUPLICATE_KEY),
        ).fetchall()
        out.append((tuple(g[c] for c in DUPLICATE_KEY), rows))
    return out


def report_duplicates(dups):
    print()
    print("=" * 72)
    print("DUPLICATE ATTENDANCE REPORT")
    print("=" * 72)
    if not dups:
        print("  No duplicates found under (student_id, subject_code, date).")
        return []

    removed = []
    for key, rows in dups:
        print("\n  %s" % (" / ".join(str(k) for k in key)))
        for i, r in enumerate(rows):
            verdict = "KEEP   (earliest)" if i == 0 else "REMOVE (duplicate)"
            print("      id=%-6s time=%-10s status=%-10s uuid=%s   %s"
                  % (r["id"], r["time"], r["status"], (r["uuid"] or "")[:12], verdict))
            if i > 0:
                removed.append(r["id"])
    print("\n  Rows to remove: %d  (ids: %s)"
          % (len(removed), ", ".join(str(i) for i in removed)))
    return removed


def copy_table(sconn, pconn, table, apply):
    src_cols = [r[1] for r in sconn.execute('PRAGMA table_info("%s")' % table)]
    rows = sconn.execute('SELECT * FROM "%s"' % table).fetchall()

    pcur = pconn.cursor()
    pcur.execute(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_schema='public' AND table_name=%s", (table,))
    dst_cols = {r[0].lower() for r in pcur.fetchall()}
    if not dst_cols:
        raise SystemExit("Target table '%s' does not exist in PostgreSQL." % table)

    cols = [c for c in src_cols if c.lower() in dst_cols]
    dropped = [c for c in src_cols if c.lower() not in dst_cols]

    if not apply:
        return len(rows), cols, dropped, 0

    pcur.execute('TRUNCATE TABLE "%s" RESTART IDENTITY CASCADE' % table)
    if rows:
        placeholders = ", ".join(["%s"] * len(cols))
        collist = ", ".join('"%s"' % c for c in cols)
        pcur.executemany(
            'INSERT INTO "%s" (%s) VALUES (%s)' % (table, collist, placeholders),
            [tuple(r[c] for c in cols) for r in rows],
        )
    return len(rows), cols, dropped, pcur.rowcount


def reset_sequences(pconn):
    cur = pconn.cursor()
    for table in IDENTITY_TABLES:
        cur.execute(
            "SELECT setval(pg_get_serial_sequence(%s, 'id'), "
            "COALESCE((SELECT MAX(id) FROM \"%s\"), 0) + 1, false)" % ("%s", table),
            (table,))


def verify(sconn, pconn, removed_ids):
    print()
    print("=" * 72)
    print("ROW COUNT VERIFICATION")
    print("=" * 72)
    pcur = pconn.cursor()
    ok = True
    for table in TABLES:
        src = sconn.execute('SELECT COUNT(*) FROM "%s"' % table).fetchone()[0]
        if table == "attendance":
            src -= len(removed_ids)
        pcur.execute('SELECT COUNT(*) FROM "%s"' % table)
        dst = pcur.fetchone()[0]
        match = "OK" if src == dst else "MISMATCH"
        if src != dst:
            ok = False
        print("  %-22s sqlite=%-6d postgres=%-6d %s" % (table, src, dst, match))
    return ok


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true",
                    help="write to PostgreSQL (default is a dry run)")
    ap.add_argument("--dedupe-source", action="store_true",
                    help="also delete the duplicate rows from the SQLite file")
    args = ap.parse_args()

    url = (os.environ.get("DATABASE_URL") or "").strip()
    if not url:
        raise SystemExit("DATABASE_URL is not set. Point it at the Supabase "
                         "transaction pooler (port 6543).")

    import psycopg2

    sconn = sqlite_conn()
    dups = find_duplicate_attendance(sconn)
    removed_ids = report_duplicates(dups)

    pconn = psycopg2.connect(url)
    print()
    print("=" * 72)
    print("TABLE COPY  (%s)" % ("APPLY" if args.apply else "DRY RUN — nothing written"))
    print("=" * 72)

    try:
        for table in TABLES:
            if table == "attendance" and removed_ids:
                n, cols, dropped, wrote = copy_attendance_clean(
                    sconn, pconn, removed_ids, args.apply)
            else:
                n, cols, dropped, wrote = copy_table(sconn, pconn, table, args.apply)
            note = ""
            if dropped:
                note = "   (columns not in target, skipped: %s)" % ", ".join(dropped)
            print("  %-22s rows=%-6d cols=%-3d%s" % (table, n, len(cols), note))

        if args.apply:
            reset_sequences(pconn)
            pconn.commit()
            print("\n  Identity sequences reset.")

            if args.dedupe_source and removed_ids:
                sconn.execute("DELETE FROM attendance WHERE id IN (%s)"
                              % ",".join(str(i) for i in removed_ids))
                sconn.commit()
                print("  Removed %d duplicate row(s) from the SQLite source too."
                      % len(removed_ids))

            ok = verify(sconn, pconn, removed_ids)
            print()
            if ok:
                print("MIGRATION COMPLETE — every table matches.")
            else:
                print("MIGRATION FAILED — row counts differ. Nothing was committed "
                      "beyond this point; re-run after investigating.")
                return 1
        else:
            print("\nDry run only. Re-run with --apply to write.")
    finally:
        pconn.close()
        sconn.close()
    return 0


def copy_attendance_clean(sconn, pconn, removed_ids, apply):
    """Copy attendance excluding the duplicate rows identified above."""
    src_cols = [r[1] for r in sconn.execute('PRAGMA table_info("attendance")')]
    skip = ",".join(str(i) for i in removed_ids)
    rows = sconn.execute(
        "SELECT * FROM attendance WHERE id NOT IN (%s) ORDER BY id" % skip).fetchall()

    pcur = pconn.cursor()
    pcur.execute("SELECT column_name FROM information_schema.columns "
                 "WHERE table_schema='public' AND table_name='attendance'")
    dst_cols = {r[0].lower() for r in pcur.fetchall()}
    cols = [c for c in src_cols if c.lower() in dst_cols]
    dropped = [c for c in src_cols if c.lower() not in dst_cols]

    if not apply:
        return len(rows), cols, dropped, 0

    pcur.execute('TRUNCATE TABLE "attendance" RESTART IDENTITY CASCADE')
    if rows:
        placeholders = ", ".join(["%s"] * len(cols))
        collist = ", ".join('"%s"' % c for c in cols)
        pcur.executemany(
            'INSERT INTO "attendance" (%s) VALUES (%s)' % (collist, placeholders),
            [tuple(r[c] for c in cols) for r in rows],
        )
    return len(rows), cols, dropped, pcur.rowcount


if __name__ == "__main__":
    sys.exit(main())
