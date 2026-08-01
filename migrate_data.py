"""Copy the CampusConnect+ SQLite database into Supabase PostgreSQL.

    $env:DATABASE_URL   = "postgresql://...pooler.supabase.com:6543/postgres"
    $env:ADMIN_PASSWORD = "<your admin password>"

    python migrate_data.py --dry-run    # reports only, writes nothing
    python migrate_data.py --apply      # creates schema, copies, verifies

WHAT --apply DOES
─────────────────
1.  Builds the schema in PostgreSQL by calling the application's own
    init_db.init_database(), so the migrated schema is by definition the one
    the application expects. db.py rewrites the SQLite DDL on the way through
    (AUTOINCREMENT to IDENTITY, ALTER TABLE to ADD COLUMN IF NOT EXISTS).
    Anything init_db seeds is discarded in step 3 by TRUNCATE.
2.  Reports duplicate attendance rows and drops all but the earliest.
3.  Copies every row of every table, values preserved exactly.
4.  Resets identity sequences past the copied ids so new inserts do not
    collide with migrated ones.
5.  Verifies row counts table by table.

FAILURE HANDLING
────────────────
A bulk insert that fails is retried row by row so the exact offending rows
can be named, with the database's own error message. Nothing is swallowed:
any failed row makes the whole run exit non-zero and leaves the transaction
uncommitted.

Re-runnable: --apply truncates each target table before copying, so a failed
run can simply be repeated. The SQLite file is only ever read, unless
--dedupe-source is passed.
"""

import argparse
import os
import sqlite3
import sys

SQLITE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "campusconnect.db")

# Parents before children, so any foreign keys added later still hold.
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

# Tables with a generated integer primary key, whose sequence must be advanced
# past the copied rows.
IDENTITY_TABLES = [
    "students", "professors", "subjects", "schedules",
    "announcements", "attendance_sessions", "attendance",
]

DUPLICATE_KEY = ("student_id", "subject_code", "date")


# ---------------------------------------------------------------------------
# SOURCE
# ---------------------------------------------------------------------------

def sqlite_conn():
    if not os.path.exists(SQLITE_PATH):
        raise SystemExit("SQLite source not found: %s" % SQLITE_PATH)
    conn = sqlite3.connect(SQLITE_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def find_duplicate_attendance(conn):
    """Attendance rows sharing (student_id, subject_code, date).

    The earliest row -- lowest id -- is kept: it is the scan that actually
    recorded the student's arrival.
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
    print("=" * 74)
    print("DUPLICATE ATTENDANCE REPORT")
    print("=" * 74)
    if not dups:
        print("  None found under (student_id, subject_code, date).")
        return []

    removed = []
    for key, rows in dups:
        print("\n  %s" % (" / ".join(str(k) for k in key)))
        for i, r in enumerate(rows):
            verdict = "KEEP   (earliest)" if i == 0 else "REMOVE (duplicate)"
            print("      id=%-6s time=%-10s status=%-10s  %s"
                  % (r["id"], r["time"], r["status"], verdict))
            if i > 0:
                removed.append(r["id"])
    print("\n  Rows to remove: %d  (ids: %s)"
          % (len(removed), ", ".join(str(i) for i in removed)))
    return removed


# ---------------------------------------------------------------------------
# SCHEMA
# ---------------------------------------------------------------------------

def create_schema():
    """Build the PostgreSQL schema using the application's own definitions."""
    if not os.environ.get("ADMIN_PASSWORD"):
        raise SystemExit(
            "ADMIN_PASSWORD is not set. init_db.py seeds the administrator row "
            "and refuses to fall back to a default.\n"
            '  $env:ADMIN_PASSWORD = "<password>"')
    import init_db
    print()
    print("=" * 74)
    print("SCHEMA")
    print("=" * 74)
    init_db.init_database()
    print("  Schema created/verified. Seeded rows will be replaced by the copy.")


# ---------------------------------------------------------------------------
# COPY
# ---------------------------------------------------------------------------

def target_columns(pcur, table):
    pcur.execute(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_schema='public' AND table_name=%s", (table,))
    return {r[0].lower() for r in pcur.fetchall()}


def read_source(sconn, table, skip_ids=None):
    if table == "attendance" and skip_ids:
        skip = ",".join(str(i) for i in skip_ids)
        return sconn.execute(
            "SELECT * FROM attendance WHERE id NOT IN (%s) ORDER BY id" % skip).fetchall()
    order = " ORDER BY id" if table in IDENTITY_TABLES else ""
    return sconn.execute('SELECT * FROM "%s"%s' % (table, order)).fetchall()


def copy_table(sconn, pconn, table, apply, skip_ids=None):
    """Copy one table. Returns (rows_read, columns_used, skipped_columns, failures)."""
    src_cols = [r[1] for r in sconn.execute('PRAGMA table_info("%s")' % table)]
    rows = read_source(sconn, table, skip_ids)

    pcur = pconn.cursor()
    dst = target_columns(pcur, table)
    if not dst:
        raise SystemExit(
            "Target table '%s' does not exist in PostgreSQL.\n"
            "Run with --apply so the schema is created first, or run "
            "init_db.py against DATABASE_URL." % table)

    cols = [c for c in src_cols if c.lower() in dst]
    dropped = [c for c in src_cols if c.lower() not in dst]

    if not apply or not rows:
        return len(rows), cols, dropped, []

    collist = ", ".join('"%s"' % c for c in cols)
    placeholders = ", ".join(["%s"] * len(cols))
    stmt = 'INSERT INTO "%s" (%s) VALUES (%s)' % (table, collist, placeholders)
    payload = [tuple(r[c] for c in cols) for r in rows]

    pcur.execute('TRUNCATE TABLE "%s" RESTART IDENTITY CASCADE' % table)

    failures = []
    pcur.execute("SAVEPOINT bulk_copy")
    try:
        pcur.executemany(stmt, payload)
        pcur.execute("RELEASE SAVEPOINT bulk_copy")
    except Exception as bulk_error:  # noqa: BLE001
        # Bulk insert tells us nothing about which row broke. Retry one at a
        # time so every failure can be named rather than guessed at.
        pcur.execute("ROLLBACK TO SAVEPOINT bulk_copy")
        print("      bulk insert failed (%s); retrying row by row"
              % str(bulk_error).strip().splitlines()[0])
        for src_row, values in zip(rows, payload):
            pcur.execute("SAVEPOINT one_row")
            try:
                pcur.execute(stmt, values)
                pcur.execute("RELEASE SAVEPOINT one_row")
            except Exception as row_error:  # noqa: BLE001
                pcur.execute("ROLLBACK TO SAVEPOINT one_row")
                ident = src_row["id"] if "id" in src_row.keys() else "?"
                failures.append((table, ident,
                                 str(row_error).strip().splitlines()[0]))
    return len(rows), cols, dropped, failures


def reset_sequences(pconn):
    cur = pconn.cursor()
    for table in IDENTITY_TABLES:
        cur.execute(
            "SELECT setval(pg_get_serial_sequence(%%s, 'id'), "
            "COALESCE((SELECT MAX(id) FROM \"%s\"), 0) + 1, false)" % table,
            (table,))


# ---------------------------------------------------------------------------
# VERIFY
# ---------------------------------------------------------------------------

def verify(sconn, pconn, removed_ids):
    print()
    print("=" * 74)
    print("ROW COUNT VERIFICATION")
    print("=" * 74)
    pcur = pconn.cursor()
    ok = True
    for table in TABLES:
        src = sconn.execute('SELECT COUNT(*) FROM "%s"' % table).fetchone()[0]
        if table == "attendance":
            src -= len(removed_ids)
        pcur.execute('SELECT COUNT(*) FROM "%s"' % table)
        dst = pcur.fetchone()[0]
        if src != dst:
            ok = False
        print("  %-22s sqlite=%-6d postgres=%-6d %s"
              % (table, src, dst, "OK" if src == dst else "MISMATCH"))
    return ok


# ---------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(
        description="Migrate CampusConnect+ from SQLite to Supabase PostgreSQL.")
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true",
                      help="report only, write nothing (default)")
    mode.add_argument("--apply", action="store_true",
                      help="create the schema, copy the data and verify")
    ap.add_argument("--dedupe-source", action="store_true",
                    help="also delete the duplicate rows from the SQLite file")
    args = ap.parse_args()

    apply = args.apply  # --dry-run and the default are both "write nothing"

    url = (os.environ.get("DATABASE_URL") or "").strip()
    if not url:
        raise SystemExit(
            "DATABASE_URL is not set.\n"
            "Point it at the Supabase transaction pooler (port 6543):\n"
            '  $env:DATABASE_URL = "postgresql://postgres.<ref>:<pw>'
            '@aws-0-<region>.pooler.supabase.com:6543/postgres"')

    if ":6543" not in url:
        print("WARNING: DATABASE_URL does not use port 6543. The application "
              "opens a connection per request and needs the transaction "
              "pooler; a direct connection will exhaust the limit.\n")

    try:
        import psycopg2
    except ImportError:
        raise SystemExit("psycopg2 is not installed.  pip install psycopg2-binary")

    sconn = sqlite_conn()
    removed_ids = report_duplicates(find_duplicate_attendance(sconn))

    if apply:
        create_schema()

    pconn = psycopg2.connect(url)
    all_failures = []
    try:
        print()
        print("=" * 74)
        print("TABLE COPY  (%s)" % ("APPLY" if apply else "DRY RUN — nothing written"))
        print("=" * 74)

        for table in TABLES:
            n, cols, dropped, failures = copy_table(
                sconn, pconn, table, apply, removed_ids)
            all_failures.extend(failures)
            note = ""
            if dropped:
                note = "   (not in target, skipped: %s)" % ", ".join(dropped)
            if failures:
                note += "   FAILED ROWS: %d" % len(failures)
            print("  %-22s rows=%-6d cols=%-3d%s" % (table, n, len(cols), note))

        if not apply:
            print("\nDry run only. Nothing was written.")
            print("Re-run with --apply to perform the migration.")
            return 0

        if all_failures:
            print()
            print("=" * 74)
            print("FAILED ROWS")
            print("=" * 74)
            for table, ident, err in all_failures:
                print("  %-22s id=%-8s %s" % (table, ident, err))
            print("\n%d row(s) failed. Rolling back — nothing was committed."
                  % len(all_failures))
            pconn.rollback()
            return 1

        reset_sequences(pconn)
        pconn.commit()
        print("\n  Identity sequences reset past the copied ids.")

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
            print("Next: run supabase_setup.sql in the Supabase SQL Editor.")
            return 0
        print("MIGRATION FAILED — row counts differ. Investigate before using "
              "this database.")
        return 1
    finally:
        pconn.close()
        sconn.close()


if __name__ == "__main__":
    sys.exit(main())
