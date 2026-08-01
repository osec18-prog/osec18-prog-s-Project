"""SQLite -> PostgreSQL compatibility layer for CampusConnect+.

WHY THIS EXISTS
───────────────
The application was written directly against Python's ``sqlite3`` module:
connections are opened inline in route handlers, queries use ``?``
placeholders, rows are read with ``sqlite3.Row``, and failures are caught as
``sqlite3.OperationalError`` / ``sqlite3.IntegrityError``. Rewriting all of
that to native psycopg2 would have touched ~128 call sites in app.py and
api.py, in a project with no automated test suite.

Instead this module presents the *exact* ``sqlite3`` API the application
already expects, and translates to PostgreSQL underneath. The application
keeps its SQL, its placeholders and its exception handling unchanged.

EVERY piece of dialect translation lives in this file. Nothing outside this
module knows which database is in use. That is deliberate: to move to native
PostgreSQL later, delete this file and rewrite the call sites — no
compatibility code is scattered anywhere else to hunt down.

BACKEND SELECTION
─────────────────
    DATABASE_URL set   -> PostgreSQL (Supabase)
    DATABASE_URL unset -> SQLite, exactly as before

That fallback is the rollback procedure: unset one environment variable and
the application returns to SQLite behaviour with no code change.

USAGE
─────
    import db
    conn = db.connect()          # replaces sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT * FROM students WHERE student_id=?", (sid,))

CONNECTION POOLING
──────────────────
The application opens a connection per request (49 call sites). Against a
remote PostgreSQL that would be far too expensive, so PostgreSQL connections
are leased from a pool and ``close()`` returns them to it rather than
tearing them down. Use Supabase's *transaction pooler* (port 6543).
"""

import os
import re
import sqlite3
import threading

# The application catches these by their sqlite3 names. The shim re-raises
# psycopg2 failures as these exact classes so that every existing
# ``except sqlite3.OperationalError`` / ``except sqlite3.IntegrityError``
# block keeps working untouched.
OperationalError = sqlite3.OperationalError
IntegrityError = sqlite3.IntegrityError
DatabaseError = sqlite3.DatabaseError

SQLITE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "campusconnect.db")

# Statement-level error recovery (PostgreSQL only). In SQLite a failed
# statement leaves the transaction usable; in PostgreSQL it aborts the whole
# transaction, so every later statement fails until a rollback. api.py relies
# on the SQLite behaviour: it catches a failed INSERT and immediately retries
# on the same connection. A SAVEPOINT before each statement restores that.
# Costs one extra round trip per statement; set to "0" to disable.
STATEMENT_RECOVERY = os.environ.get("DB_STATEMENT_RECOVERY", "1") != "0"

_pool = None
_pool_lock = threading.Lock()
_id_tables = None
_id_lock = threading.Lock()


def database_url():
    return (os.environ.get("DATABASE_URL") or "").strip()


def is_postgres():
    return bool(database_url())


def backend():
    return "postgres" if is_postgres() else "sqlite"


# ---------------------------------------------------------------------------
# SQL TRANSLATION
# ---------------------------------------------------------------------------
# Everything below rewrites SQLite SQL into PostgreSQL SQL. It runs only when
# the PostgreSQL backend is active; on SQLite the statement is passed through
# byte-for-byte.

_TRANSLATION_CACHE = {}
_CACHE_LOCK = threading.Lock()


def _split_sql(sql):
    """Split *sql* into (code, literal) segments.

    Placeholder and dialect rewriting must never touch the inside of a string
    literal, a quoted identifier or a comment -- a ``?`` in a message string
    is data, not a parameter marker. Returns a list of ``(text, is_code)``.
    """
    parts = []
    buf = []
    i = 0
    n = len(sql)

    while i < n:
        ch = sql[i]

        # line comment
        if ch == "-" and i + 1 < n and sql[i + 1] == "-":
            parts.append(("".join(buf), True))
            buf = []
            j = sql.find("\n", i)
            j = n if j == -1 else j + 1
            parts.append((sql[i:j], False))
            i = j
            continue

        # block comment
        if ch == "/" and i + 1 < n and sql[i + 1] == "*":
            parts.append(("".join(buf), True))
            buf = []
            j = sql.find("*/", i)
            j = n if j == -1 else j + 2
            parts.append((sql[i:j], False))
            i = j
            continue

        # single-quoted string literal ('' escapes a quote)
        if ch == "'":
            parts.append(("".join(buf), True))
            buf = []
            j = i + 1
            while j < n:
                if sql[j] == "'":
                    if j + 1 < n and sql[j + 1] == "'":
                        j += 2
                        continue
                    j += 1
                    break
                j += 1
            parts.append((sql[i:j], False))
            i = j
            continue

        # double-quoted identifier
        if ch == '"':
            parts.append(("".join(buf), True))
            buf = []
            j = i + 1
            while j < n:
                if sql[j] == '"':
                    if j + 1 < n and sql[j + 1] == '"':
                        j += 2
                        continue
                    j += 1
                    break
                j += 1
            parts.append((sql[i:j], False))
            i = j
            continue

        buf.append(ch)
        i += 1

    parts.append(("".join(buf), True))
    return [p for p in parts if p[0]]


def _map_code(sql, fn):
    """Apply *fn* to the code segments of *sql*, leaving literals alone."""
    return "".join(fn(text) if is_code else text for text, is_code in _split_sql(sql))


# -- DDL ---------------------------------------------------------------------
# Column types are deliberately NOT normalised. announcements.date_created
# holds '2026-07-31 08:04 PM' while attendance_sessions.created_at holds
# '2026-07-28 23:21:12' -- two different formats in columns both declared
# TIMESTAMP. Declaring them as a real timestamp type would make PostgreSQL
# return datetime objects and silently change how every dashboard renders
# dates. They stay TEXT, and INTEGER flags stay INTEGER. Behavioural
# compatibility beats normalisation here; this is a recorded decision, not an
# oversight.

_DDL_TYPE_RULES = [
    # Autoincrementing primary keys.
    (re.compile(r"\bINTEGER\s+PRIMARY\s+KEY\s+AUTOINCREMENT\b", re.I),
     "INTEGER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY"),
    (re.compile(r"\bINTEGER\s+PRIMARY\s+KEY\b(?!\s+AUTOINCREMENT)", re.I),
     "INTEGER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY"),
    # SQLite CURRENT_TIMESTAMP yields 'YYYY-MM-DD HH:MM:SS' as text. Keep the
    # column textual and reproduce that exact format as the default.
    (re.compile(r"\bTIMESTAMP\s+DEFAULT\s+CURRENT_TIMESTAMP\b", re.I),
     "TEXT DEFAULT (to_char(now(), 'YYYY-MM-DD HH24:MI:SS'))"),
    (re.compile(r"\bTIMESTAMP\b", re.I), "TEXT"),
    (re.compile(r"\bREAL\b", re.I), "DOUBLE PRECISION"),
]

_ALTER_ADD_RE = re.compile(
    r"\bALTER\s+TABLE\s+(\S+)\s+ADD\s+COLUMN\s+(?!IF\s+NOT\s+EXISTS)", re.I)

_INSERT_OR_IGNORE_RE = re.compile(r"\bINSERT\s+OR\s+IGNORE\s+INTO\b", re.I)
_INSERT_TABLE_RE = re.compile(r"\bINSERT\s+INTO\s+[\"']?([A-Za-z_][A-Za-z0-9_]*)", re.I)
_RETURNING_RE = re.compile(r"\bRETURNING\b", re.I)


def _translate_ddl(code):
    for pattern, repl in _DDL_TYPE_RULES:
        code = pattern.sub(repl, code)
    # SQLite has no ADD COLUMN IF NOT EXISTS, so the application wraps every
    # ALTER in try/except OperationalError. In PostgreSQL a failed statement
    # poisons the transaction, so use the native guard instead.
    code = _ALTER_ADD_RE.sub(lambda m: "ALTER TABLE %s ADD COLUMN IF NOT EXISTS " % m.group(1), code)
    return code


def translate(sql, has_params=False):
    """Rewrite SQLite *sql* for PostgreSQL. Idempotent and cached."""
    key = (sql, has_params)
    cached = _TRANSLATION_CACHE.get(key)
    if cached is not None:
        return cached

    out = sql

    # INSERT OR IGNORE -> ON CONFLICT DO NOTHING
    is_or_ignore = bool(_INSERT_OR_IGNORE_RE.search(out))
    if is_or_ignore:
        out = _map_code(out, lambda c: _INSERT_OR_IGNORE_RE.sub("INSERT INTO", c))

    out = _map_code(out, _translate_ddl)

    def code_fixups(code):
        # ? -> %s
        code = code.replace("?", "%s")
        return code

    out = _map_code(out, code_fixups)

    if is_or_ignore:
        out = out.rstrip().rstrip(";") + " ON CONFLICT DO NOTHING"

    # psycopg2 only treats '%' specially when parameters are supplied. A bare
    # '%' in the SQL would then be read as the start of a placeholder, so
    # double it -- but only in that case, and never inside a literal we have
    # already protected.
    if has_params:
        def escape_percent(code):
            return re.sub(r"%(?!s\b)(?!\()", "%%", code)
        out = _map_code(out, escape_percent)

    with _CACHE_LOCK:
        _TRANSLATION_CACHE[key] = out
    return out


# ---------------------------------------------------------------------------
# ROWS
# ---------------------------------------------------------------------------

class Row:
    """A PostgreSQL row that behaves like ``sqlite3.Row``.

    ``sqlite3.Row`` supports positional access, access by column name, and
    ``dict(row)``. The application uses all three -- core.py's
    ``check_password_with_migration`` calls ``dict(row)``, templates index by
    name, and plenty of routes unpack tuples -- so all three are supported
    here. psycopg2's own row factories each support only one.
    """

    __slots__ = ("_values", "_columns", "_index")

    def __init__(self, columns, index, values):
        self._columns = columns
        self._index = index
        self._values = values

    def __getitem__(self, key):
        if isinstance(key, str):
            try:
                return self._values[self._index[key.lower()]]
            except KeyError:
                raise IndexError("No item with that key") from None
        return self._values[key]

    def keys(self):
        return list(self._columns)

    def __iter__(self):
        return iter(self._values)

    def __len__(self):
        return len(self._values)

    def __contains__(self, key):
        if isinstance(key, str):
            return key.lower() in self._index
        return key in self._values

    def __eq__(self, other):
        if isinstance(other, Row):
            return self._values == other._values
        if isinstance(other, (tuple, list)):
            return list(self._values) == list(other)
        return NotImplemented

    def __repr__(self):
        return "<Row %s>" % dict(zip(self._columns, self._values))


def _make_rows(cursor_description, rows, want_dict_rows):
    if not want_dict_rows or cursor_description is None:
        return rows
    columns = [d[0] for d in cursor_description]
    index = {c.lower(): i for i, c in enumerate(columns)}
    return [Row(columns, index, tuple(r)) for r in rows]


# ---------------------------------------------------------------------------
# POSTGRESQL POOL
# ---------------------------------------------------------------------------

def _get_pool():
    global _pool
    if _pool is not None:
        return _pool
    with _pool_lock:
        if _pool is None:
            try:
                import psycopg2.pool
            except ImportError:
                raise OperationalError(
                    "DATABASE_URL is set but psycopg2 is not installed.\n"
                    "  pip install psycopg2-binary\n"
                    "Or unset DATABASE_URL to fall back to SQLite."
                ) from None
            minconn = int(os.environ.get("DB_POOL_MIN", "1"))
            maxconn = int(os.environ.get("DB_POOL_MAX", "10"))
            _pool = psycopg2.pool.ThreadedConnectionPool(
                minconn, maxconn, dsn=database_url(),
                connect_timeout=int(os.environ.get("DB_CONNECT_TIMEOUT", "15")),
                application_name="campusconnect",
            )
    return _pool


def close_pool():
    """Release every pooled connection. Used by scripts and tests."""
    global _pool
    with _pool_lock:
        if _pool is not None:
            _pool.closeall()
            _pool = None


def _table_has_id(raw_conn, table):
    """True when *table* has an ``id`` column, cached for the process.

    Needed because ``cursor.lastrowid`` is emulated with ``RETURNING id``,
    which is invalid on tables keyed by something else (api_tokens.token,
    revoked_jwts.jti).
    """
    global _id_tables
    if _id_tables is None:
        with _id_lock:
            if _id_tables is None:
                cur = raw_conn.cursor()
                cur.execute(
                    "SELECT table_name FROM information_schema.columns "
                    "WHERE table_schema='public' AND column_name='id'"
                )
                _id_tables = {r[0].lower() for r in cur.fetchall()}
                cur.close()
    return table.lower() in _id_tables


def _translate_exception(exc):
    """Re-raise a psycopg2 error as the sqlite3 class the application expects."""
    import psycopg2
    if isinstance(exc, psycopg2.IntegrityError):
        return IntegrityError(str(exc))
    if isinstance(exc, psycopg2.Error):
        return OperationalError(str(exc))
    return exc


# ---------------------------------------------------------------------------
# CURSOR
# ---------------------------------------------------------------------------

class _PgCursor:
    """A psycopg2 cursor wearing sqlite3's interface."""

    def __init__(self, connection, raw_cursor):
        self._conn = connection
        self._cur = raw_cursor
        self._lastrowid = None

    # -- sqlite3 API --------------------------------------------------------

    @property
    def lastrowid(self):
        return self._lastrowid

    @property
    def rowcount(self):
        return self._cur.rowcount

    @property
    def description(self):
        return self._cur.description

    def execute(self, sql, parameters=()):
        translated = translate(sql, has_params=bool(parameters))
        wants_id = False

        # Emulate cursor.lastrowid: PostgreSQL only reports a generated key
        # when the statement asks for it.
        m = _INSERT_TABLE_RE.search(translated)
        if m and not _RETURNING_RE.search(translated):
            if _table_has_id(self._conn._raw, m.group(1)):
                translated = translated.rstrip().rstrip(";") + " RETURNING id"
                wants_id = True

        self._lastrowid = None
        savepoint = self._conn._begin_statement()
        try:
            self._cur.execute(translated, tuple(parameters) if parameters else None)
        except Exception as exc:  # noqa: BLE001 - re-raised as a sqlite3 error
            self._conn._recover_statement(savepoint)
            raise _translate_exception(exc) from None

        if wants_id:
            try:
                row = self._cur.fetchone()
                if row:
                    self._lastrowid = row[0]
            except Exception:  # noqa: BLE001 - nothing returned; not an error
                pass
        return self

    def executemany(self, sql, seq_of_parameters):
        seq = list(seq_of_parameters)
        translated = translate(sql, has_params=True)
        savepoint = self._conn._begin_statement()
        try:
            self._cur.executemany(translated, [tuple(p) for p in seq])
        except Exception as exc:  # noqa: BLE001
            self._conn._recover_statement(savepoint)
            raise _translate_exception(exc) from None
        return self

    def fetchone(self):
        row = self._cur.fetchone()
        if row is None:
            return None
        return _make_rows(self._cur.description, [row], self._conn._dict_rows)[0]

    def fetchall(self):
        rows = self._cur.fetchall()
        return _make_rows(self._cur.description, rows, self._conn._dict_rows)

    def fetchmany(self, size=None):
        rows = self._cur.fetchmany(size or self._cur.arraysize)
        return _make_rows(self._cur.description, rows, self._conn._dict_rows)

    def __iter__(self):
        return iter(self.fetchall())

    def close(self):
        try:
            self._cur.close()
        except Exception:  # noqa: BLE001 - closing must never raise
            pass


# ---------------------------------------------------------------------------
# CONNECTION
# ---------------------------------------------------------------------------

class _PgConnection:
    """A pooled psycopg2 connection wearing sqlite3's interface."""

    def __init__(self, raw, pool):
        self._raw = raw
        self._pool = pool
        self._closed = False
        self._dict_rows = False
        self._savepoint_seq = 0

    # ``conn.row_factory = sqlite3.Row`` is how the application asks for
    # rows addressable by column name.
    @property
    def row_factory(self):
        return sqlite3.Row if self._dict_rows else None

    @row_factory.setter
    def row_factory(self, value):
        self._dict_rows = value is not None

    def cursor(self):
        return _PgCursor(self, self._raw.cursor())

    def execute(self, sql, parameters=()):
        """sqlite3 connections can execute directly; psycopg2's cannot.

        api.py relies on this in 39 places.
        """
        return self.cursor().execute(sql, parameters)

    def executemany(self, sql, seq_of_parameters):
        return self.cursor().executemany(sql, seq_of_parameters)

    # -- statement-level recovery ------------------------------------------

    def _begin_statement(self):
        """Mark a rollback point so one failed statement cannot poison the
        transaction, matching SQLite's behaviour."""
        if not STATEMENT_RECOVERY or self._raw.autocommit:
            return None
        self._savepoint_seq += 1
        name = "cc_sp_%d" % self._savepoint_seq
        try:
            cur = self._raw.cursor()
            cur.execute("SAVEPOINT %s" % name)
            cur.close()
            return name
        except Exception:  # noqa: BLE001 - recovery is best-effort
            return None

    def _recover_statement(self, savepoint):
        if savepoint is None:
            return
        try:
            cur = self._raw.cursor()
            cur.execute("ROLLBACK TO SAVEPOINT %s" % savepoint)
            cur.close()
        except Exception:  # noqa: BLE001
            pass

    # -- transaction / lifecycle -------------------------------------------

    def commit(self):
        try:
            self._raw.commit()
        except Exception as exc:  # noqa: BLE001
            raise _translate_exception(exc) from None

    def rollback(self):
        try:
            self._raw.rollback()
        except Exception:  # noqa: BLE001
            pass

    def close(self):
        """Return the connection to the pool rather than dropping it."""
        if self._closed:
            return
        self._closed = True
        try:
            # Never hand a connection back mid-transaction.
            self._raw.rollback()
        except Exception:  # noqa: BLE001
            pass
        try:
            self._pool.putconn(self._raw)
        except Exception:  # noqa: BLE001
            pass

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        if exc_type is None:
            self.commit()
        else:
            self.rollback()
        return False


# ---------------------------------------------------------------------------
# PUBLIC ENTRY POINT
# ---------------------------------------------------------------------------

def connect():
    """Open a connection to whichever backend is configured.

    Drop-in replacement for ``sqlite3.connect(DB_PATH)``.
    """
    if not is_postgres():
        return sqlite3.connect(SQLITE_PATH)
    pool = _get_pool()
    return _PgConnection(pool.getconn(), pool)


def get_db():
    """Connection with rows addressable by column name."""
    conn = connect()
    conn.row_factory = sqlite3.Row
    return conn
