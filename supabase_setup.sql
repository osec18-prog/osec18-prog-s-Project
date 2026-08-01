-- ===========================================================================
-- CampusConnect+ — Supabase configuration
-- ===========================================================================
-- Run this in the Supabase SQL Editor AFTER migrate_data.py has finished.
-- Order matters: the UNIQUE constraint in section 2 will fail if duplicate
-- attendance rows are still present, and migrate_data.py is what removes them.
--
-- Sections 3, 4 and 5 are PREPARED BUT INTENTIONALLY INACTIVE. They put the
-- security, realtime and storage plumbing in place without switching on any
-- application feature. No web UI, Flutter UI, upload page or realtime client
-- exists that uses them, and none is created by this migration.
-- ===========================================================================


-- ---------------------------------------------------------------------------
-- 1. INDEXES
-- ---------------------------------------------------------------------------
-- The SQLite database carried exactly one index (idx_attendance_uuid).
-- These cover the lookups the application actually performs; each one
-- corresponds to a WHERE clause in app.py, api.py or core.py.

-- core.py attendance_exists(): WHERE student_id=? AND token=?
CREATE INDEX IF NOT EXISTS idx_attendance_student_token
    ON attendance (student_id, token);

-- core.py attendance_exists(): WHERE student_id=? AND subject_code=? AND date=?
CREATE INDEX IF NOT EXISTS idx_attendance_student_subject_date
    ON attendance (student_id, subject_code, date);

-- Attendance reports and dashboards filter and sort by date.
CREATE INDEX IF NOT EXISTS idx_attendance_date
    ON attendance (date);

-- Per-professor attendance views.
CREATE INDEX IF NOT EXISTS idx_attendance_professor_id
    ON attendance (professor_id);

-- Scan de-duplication: WHERE uuid=?  (was the only SQLite index)
CREATE UNIQUE INDEX IF NOT EXISTS idx_attendance_uuid
    ON attendance (uuid) WHERE uuid IS NOT NULL;

-- core.py attendance_session_active(): WHERE token=? AND professor_id=?
CREATE INDEX IF NOT EXISTS idx_sessions_token_professor
    ON attendance_sessions (token, professor_id);

-- Sweeping expired/closed QR sessions.
CREATE INDEX IF NOT EXISTS idx_sessions_active_date
    ON attendance_sessions (active, date);

-- Login paths.
CREATE INDEX IF NOT EXISTS idx_students_student_id ON students (student_id);
CREATE INDEX IF NOT EXISTS idx_students_email      ON students (email);
CREATE INDEX IF NOT EXISTS idx_professors_emp_id   ON professors (employee_id);
CREATE INDEX IF NOT EXISTS idx_professors_email    ON professors (email);

-- Professor lookup by name — app.py and api.py join on TRIM(LOWER(fullname)),
-- so the index has to match that expression to be usable.
CREATE INDEX IF NOT EXISTS idx_professors_fullname_norm
    ON professors (TRIM(LOWER(fullname)));

-- Schedule listings.
CREATE INDEX IF NOT EXISTS idx_schedules_professor_id ON schedules (professor_id);
CREATE INDEX IF NOT EXISTS idx_schedules_subject_code ON schedules (subject_code);

-- Token checks on every authenticated API request.
CREATE INDEX IF NOT EXISTS idx_revoked_jwts_expires ON revoked_jwts (expires_at);


-- ---------------------------------------------------------------------------
-- 2. DUPLICATE ATTENDANCE PREVENTION
-- ---------------------------------------------------------------------------
-- Until now this was enforced only in Python (core.attendance_exists), which
-- leaves a race between two simultaneous scans. This makes the database the
-- authority.
--
-- Run migrate_data.py FIRST. If duplicates remain this statement fails, and
-- that failure is the correct outcome — it means cleanup did not happen.

ALTER TABLE attendance
    ADD CONSTRAINT uq_attendance_student_subject_date
    UNIQUE (student_id, subject_code, date);


-- ---------------------------------------------------------------------------
-- 3. ROW LEVEL SECURITY  — PREPARED BUT INTENTIONALLY INACTIVE
-- ---------------------------------------------------------------------------
-- The Flask backend connects through DATABASE_URL as the table owner, and in
-- PostgreSQL a table owner BYPASSES row level security unless FORCE ROW LEVEL
-- SECURITY is set. FORCE is deliberately NOT used here.
--
-- The effect is therefore:
--   * Flask  — completely unaffected. Every existing query behaves as before.
--   * anon / authenticated (the PostgREST roles reachable with the public
--     SUPABASE_ANON_KEY) — denied on every table.
--
-- This is defence in depth: if the anon key ever leaks, it grants nothing.
-- Real per-user policies cannot be written yet, because authorisation lives
-- in Flask sessions (session['role']) and no per-user JWT ever reaches
-- PostgreSQL. Writing role-based policies now would be theatre.

ALTER TABLE students            ENABLE ROW LEVEL SECURITY;
ALTER TABLE professors          ENABLE ROW LEVEL SECURITY;
ALTER TABLE subjects            ENABLE ROW LEVEL SECURITY;
ALTER TABLE schedules           ENABLE ROW LEVEL SECURITY;
ALTER TABLE announcements       ENABLE ROW LEVEL SECURITY;
ALTER TABLE attendance          ENABLE ROW LEVEL SECURITY;
ALTER TABLE attendance_sessions ENABLE ROW LEVEL SECURITY;
ALTER TABLE api_tokens          ENABLE ROW LEVEL SECURITY;
ALTER TABLE revoked_jwts        ENABLE ROW LEVEL SECURITY;

-- No policies are created. In PostgreSQL, RLS enabled with zero policies
-- means "deny everything" for non-owner roles, which is exactly what is
-- wanted. Explicitly revoke the API roles as well, so the intent is visible
-- rather than implied.
REVOKE ALL ON ALL TABLES IN SCHEMA public FROM anon, authenticated;
REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM anon, authenticated;


-- ---------------------------------------------------------------------------
-- 4. REALTIME PUBLICATION  — PREPARED BUT INTENTIONALLY INACTIVE
-- ---------------------------------------------------------------------------
-- This only tells PostgreSQL to publish row changes. Nothing subscribes:
-- neither the Jinja templates nor the Flutter app contains a Supabase client.
-- Live-updating UI is a separate piece of work that requires frontend
-- changes, which this migration explicitly does not make.
--
-- Note: the requested "notifications" table does not exist. It is defined in
-- core.migrate_schema(), which is dead code — never called, never created.
-- attendance_sessions is published instead, since that is what actually
-- changes when a professor opens or closes a QR session.

ALTER PUBLICATION supabase_realtime ADD TABLE announcements;
ALTER PUBLICATION supabase_realtime ADD TABLE schedules;
ALTER PUBLICATION supabase_realtime ADD TABLE attendance;
ALTER PUBLICATION supabase_realtime ADD TABLE attendance_sessions;


-- ---------------------------------------------------------------------------
-- 5. STORAGE BUCKETS  — PREPARED BUT INTENTIONALLY INACTIVE
-- ---------------------------------------------------------------------------
-- Buckets only. No upload route, no form, no column referencing them, and no
-- UI change. The application has zero file-upload capability today: there is
-- not a single request.files reference in the codebase.
--
-- All four are created private (public = false). Nothing can read them
-- without a signed URL issued by the service role, so creating them now
-- carries no exposure.

INSERT INTO storage.buckets (id, name, public)
VALUES
    ('profile-pictures',    'profile-pictures',    false),
    ('announcement-images', 'announcement-images', false),
    ('lost-found-images',   'lost-found-images',   false),
    ('documents',           'documents',           false)
ON CONFLICT (id) DO NOTHING;

-- No storage policies are created, so only the service role can reach these
-- buckets. Policies belong with the upload feature that will eventually use
-- them, not with this migration.
