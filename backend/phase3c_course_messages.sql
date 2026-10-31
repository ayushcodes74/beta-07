-- ============================================================================
-- TrustGrade: student <-> teacher chat  (course_messages + RLS + thread-list RPC)
-- ============================================================================
-- Run once in the Supabase SQL Editor (one transaction; nothing changes on error).
-- Requires phase2a_rls_recursion_fix.sql (private.is_active_* helpers).
--
-- One private conversation per (course, student) with that course's teacher. Every message
-- row carries the thread key (course_id, student_id) plus who sent it.
--
-- Access, scoped strictly to the caller's own data:
--   students: read and write ONLY their own thread, in courses they are actively enrolled in
--   teachers: read and write the threads of courses THEY OWN, and only with students who are
--             actively enrolled in that course
--   either:   mark messages THEY RECEIVED as read (only read_at is updatable)
-- Messages are never edited or deleted through the API (no UPDATE of body, no DELETE grant).
-- No recursion: policies use the private SECURITY DEFINER helpers, which never read course_messages.
--
-- Used by backend/app/database/message_repository.py
--   table course_messages            -> list / send / mark read
--   rpc   course_message_threads()   -> conversation list with names, last message, unread count
-- ============================================================================

BEGIN;

CREATE TABLE IF NOT EXISTS public.course_messages (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  course_id   uuid NOT NULL REFERENCES public.courses(id) ON DELETE CASCADE,
  student_id  uuid NOT NULL REFERENCES public.profiles(id) ON DELETE CASCADE,  -- thread owner
  sender_id   uuid NOT NULL REFERENCES public.profiles(id) ON DELETE CASCADE,
  body        text NOT NULL CHECK (char_length(btrim(body)) BETWEEN 1 AND 4000),
  read_at     timestamptz,
  created_at  timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS course_messages_thread_idx
  ON public.course_messages (course_id, student_id, created_at);
CREATE INDEX IF NOT EXISTS course_messages_unread_idx
  ON public.course_messages (course_id, student_id) WHERE read_at IS NULL;

ALTER TABLE public.course_messages ENABLE ROW LEVEL SECURITY;

-- Column-level privileges: RLS filters rows, these limit which columns each write may touch.
REVOKE ALL ON public.course_messages FROM anon, authenticated;
GRANT SELECT ON public.course_messages TO authenticated;
GRANT INSERT (course_id, student_id, sender_id, body) ON public.course_messages TO authenticated;
GRANT UPDATE (read_at) ON public.course_messages TO authenticated;

-- ----------------------------------------------------------------------------
-- Helper: is target_student an active (not disabled) student enrolled in the course?
-- Used so a teacher can only open a thread with someone actually on the roster.
-- ----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION private.is_active_student_of_course(check_course_id UUID, check_student_id UUID)
RETURNS BOOLEAN
LANGUAGE sql
SECURITY DEFINER
SET search_path = ''
STABLE
AS $$
  SELECT EXISTS (
    SELECT 1
    FROM public.course_enrollments e
    JOIN public.profiles p ON p.id = e.student_id
    WHERE e.course_id = check_course_id
      AND e.student_id = check_student_id
      AND e.status = 'active'
      AND p.role = 'student'
      AND p.is_disabled = false
  );
$$;

REVOKE ALL ON FUNCTION private.is_active_student_of_course(UUID, UUID) FROM PUBLIC, anon;
GRANT EXECUTE ON FUNCTION private.is_active_student_of_course(UUID, UUID) TO authenticated;

-- ---- Students: own thread, actively enrolled courses ------------------------------
DROP POLICY IF EXISTS "Students read own course messages" ON public.course_messages;
CREATE POLICY "Students read own course messages" ON public.course_messages
FOR SELECT TO authenticated
USING (
  student_id = (SELECT auth.uid())
  AND private.is_active_enrolled_student(course_id)
);

DROP POLICY IF EXISTS "Students message their course teacher" ON public.course_messages;
CREATE POLICY "Students message their course teacher" ON public.course_messages
FOR INSERT TO authenticated
WITH CHECK (
  sender_id = (SELECT auth.uid())
  AND student_id = (SELECT auth.uid())
  AND private.is_active_enrolled_student(course_id)
);

-- ---- Teachers: threads in their own courses ----------------------------------------
DROP POLICY IF EXISTS "Teachers read course messages" ON public.course_messages;
CREATE POLICY "Teachers read course messages" ON public.course_messages
FOR SELECT TO authenticated
USING (private.is_active_course_teacher(course_id));

DROP POLICY IF EXISTS "Teachers message enrolled students" ON public.course_messages;
CREATE POLICY "Teachers message enrolled students" ON public.course_messages
FOR INSERT TO authenticated
WITH CHECK (
  sender_id = (SELECT auth.uid())
  AND private.is_active_course_teacher(course_id)
  AND private.is_active_student_of_course(course_id, student_id)
);

-- ---- Either side: mark messages they RECEIVED as read ------------------------------
DROP POLICY IF EXISTS "Recipients mark course messages read" ON public.course_messages;
CREATE POLICY "Recipients mark course messages read" ON public.course_messages
FOR UPDATE TO authenticated
USING (
  sender_id <> (SELECT auth.uid())
  AND (
    (student_id = (SELECT auth.uid()) AND private.is_active_enrolled_student(course_id))
    OR private.is_active_course_teacher(course_id)
  )
)
WITH CHECK (
  sender_id <> (SELECT auth.uid())
  AND (
    (student_id = (SELECT auth.uid()) AND private.is_active_enrolled_student(course_id))
    OR private.is_active_course_teacher(course_id)
  )
);

-- ----------------------------------------------------------------------------
-- Conversation list for the caller: one row per thread they may see, with display names,
-- the latest message, and how many messages addressed TO the caller are still unread.
-- SECURITY DEFINER only because teachers cannot read student profiles (names) under RLS;
-- the WHERE clause applies exactly the same access rules as the SELECT policies above.
-- ----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.course_message_threads()
RETURNS TABLE (
  course_id        UUID,
  course_name      TEXT,
  student_id       UUID,
  student_name     TEXT,
  teacher_id       UUID,
  teacher_name     TEXT,
  last_body        TEXT,
  last_sender_id   UUID,
  last_at          TIMESTAMPTZ,
  unread_count     INT
)
LANGUAGE sql
SECURITY DEFINER
SET search_path = ''
STABLE
AS $$
  WITH visible AS (
    SELECT m.*
    FROM public.course_messages m
    WHERE (m.student_id = auth.uid() AND private.is_active_enrolled_student(m.course_id))
       OR private.is_active_course_teacher(m.course_id)
  ),
  latest AS (
    SELECT DISTINCT ON (v.course_id, v.student_id)
           v.course_id, v.student_id, v.body, v.sender_id, v.created_at
    FROM visible v
    ORDER BY v.course_id, v.student_id, v.created_at DESC, v.id DESC
  ),
  unread AS (
    SELECT v.course_id, v.student_id, COUNT(*)::INT AS n
    FROM visible v
    WHERE v.read_at IS NULL AND v.sender_id <> auth.uid()
    GROUP BY v.course_id, v.student_id
  )
  SELECT
    l.course_id,
    c.name::TEXT,
    l.student_id,
    sp.display_name::TEXT,
    c.teacher_id,
    tp.display_name::TEXT,
    l.body,
    l.sender_id,
    l.created_at,
    COALESCE(u.n, 0)
  FROM latest l
  JOIN public.courses c ON c.id = l.course_id
  JOIN public.profiles sp ON sp.id = l.student_id
  LEFT JOIN public.profiles tp ON tp.id = c.teacher_id
  LEFT JOIN unread u ON u.course_id = l.course_id AND u.student_id = l.student_id
  ORDER BY l.created_at DESC;
$$;

COMMENT ON FUNCTION public.course_message_threads() IS
  'TrustGrade: the caller''s student-teacher conversations with names, last message and unread count.';

REVOKE ALL ON FUNCTION public.course_message_threads() FROM PUBLIC, anon;
GRANT EXECUTE ON FUNCTION public.course_message_threads() TO authenticated;

-- ---- Self-test: querying as a signed-in user must not error (e.g. no policy recursion) ----
SET LOCAL ROLE authenticated;
SELECT set_config('request.jwt.claims',
  '{"sub":"00000000-0000-0000-0000-000000000000","role":"authenticated"}', true);
SELECT count(*) AS course_messages_visible_to_test_user FROM public.course_messages;
SELECT count(*) AS threads_visible_to_test_user FROM public.course_message_threads();
RESET ROLE;

COMMIT;

-- Rollback (not executed):
-- DROP FUNCTION IF EXISTS public.course_message_threads();
-- DROP TABLE IF EXISTS public.course_messages;
-- DROP FUNCTION IF EXISTS private.is_active_student_of_course(UUID, UUID);
