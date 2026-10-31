-- ============================================================================
-- TrustGrade: in-app dashboard notifications  (notifications + RLS)
-- ============================================================================
-- Run once in the Supabase SQL Editor (one transaction; nothing changes on error).
--
-- Messages shown in the dashboard bell:
--   teacher -> students : assignment published / updated, result published / updated,
--                         late-submission decision, review request answered
--   student -> teacher  : assignment submitted, review request opened
--
-- The backend writes notifications under the ACTOR's JWT (never service role).
-- Access:
--   everyone : read and mark-as-read ONLY their own notifications (recipient_id = caller)
--   insert   : only as yourself (actor_id = caller), never to yourself, and only to someone
--              you have a real course relationship with (private.can_notify):
--                * a teacher -> a student actively enrolled in one of the teacher's courses,
--                  or a student who submitted to one of the teacher's assignments
--                * a student -> the teacher who owns an assignment the student submitted to,
--                  or the teacher of a course the student is actively enrolled in
-- Inserts must use Prefer: return=minimal (the actor cannot SELECT the recipient's row).
-- No recursion: the helper is SECURITY DEFINER and never reads public.notifications.
-- ============================================================================

BEGIN;

CREATE TABLE IF NOT EXISTS public.notifications (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  recipient_id  uuid NOT NULL REFERENCES public.profiles(id) ON DELETE CASCADE,
  actor_id      uuid REFERENCES public.profiles(id) ON DELETE SET NULL,
  type          text NOT NULL CHECK (type IN (
                  'assignment_published', 'assignment_updated',
                  'result_published', 'result_updated',
                  'late_decision', 'review_resolved',
                  'submission_received', 'review_requested'
                )),
  title         text NOT NULL CHECK (char_length(title) BETWEEN 1 AND 200),
  body          text CHECK (body IS NULL OR char_length(body) <= 1000),
  link          text CHECK (link IS NULL OR (char_length(link) <= 300 AND link LIKE '/app%')),
  assignment_id uuid REFERENCES public.assignments(id) ON DELETE CASCADE,
  submission_id uuid REFERENCES public.submissions(id) ON DELETE CASCADE,
  read_at       timestamptz,
  created_at    timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS notifications_recipient_created_idx
  ON public.notifications (recipient_id, created_at DESC);
CREATE INDEX IF NOT EXISTS notifications_recipient_unread_idx
  ON public.notifications (recipient_id) WHERE read_at IS NULL;

ALTER TABLE public.notifications ENABLE ROW LEVEL SECURITY;

-- Column-level privileges: RLS filters rows, these limit which columns each write may touch.
REVOKE ALL ON public.notifications FROM anon, authenticated;
GRANT SELECT ON public.notifications TO authenticated;
GRANT INSERT (recipient_id, actor_id, type, title, body, link, assignment_id, submission_id)
  ON public.notifications TO authenticated;
GRANT UPDATE (read_at) ON public.notifications TO authenticated;

-- ---- Relationship check (SECURITY DEFINER: reads base tables without RLS recursion) ----
CREATE SCHEMA IF NOT EXISTS private;
GRANT USAGE ON SCHEMA private TO authenticated;

CREATE OR REPLACE FUNCTION private.can_notify(target uuid)
RETURNS boolean
LANGUAGE sql
SECURITY DEFINER
SET search_path = ''
STABLE
AS $$
  SELECT EXISTS (
    SELECT 1 FROM public.profiles me
    WHERE me.id = auth.uid() AND me.is_disabled = false
  )
  AND (
    -- teacher -> student enrolled in one of the teacher's courses
    EXISTS (
      SELECT 1
      FROM public.courses c
      JOIN public.course_enrollments e ON e.course_id = c.id
      WHERE c.teacher_id = auth.uid() AND e.student_id = target AND e.status = 'active'
    )
    -- teacher -> student who submitted to one of the teacher's assignments
    OR EXISTS (
      SELECT 1
      FROM public.submissions s
      JOIN public.assignments a ON a.id = s.assignment_id
      WHERE a.teacher_id = auth.uid() AND s.student_id = target
    )
    -- student -> teacher who owns an assignment the student submitted to
    OR EXISTS (
      SELECT 1
      FROM public.submissions s
      JOIN public.assignments a ON a.id = s.assignment_id
      WHERE s.student_id = auth.uid() AND a.teacher_id = target
    )
    -- student -> teacher of a course the student is actively enrolled in
    OR EXISTS (
      SELECT 1
      FROM public.course_enrollments e
      JOIN public.courses c ON c.id = e.course_id
      WHERE e.student_id = auth.uid() AND e.status = 'active' AND c.teacher_id = target
    )
  );
$$;

REVOKE ALL ON FUNCTION private.can_notify(uuid) FROM PUBLIC, anon;
GRANT EXECUTE ON FUNCTION private.can_notify(uuid) TO authenticated;

-- ---- Policies --------------------------------------------------------------------
DROP POLICY IF EXISTS "Users read own notifications" ON public.notifications;
CREATE POLICY "Users read own notifications" ON public.notifications
FOR SELECT TO authenticated
USING (recipient_id = (SELECT auth.uid()));

DROP POLICY IF EXISTS "Users mark own notifications read" ON public.notifications;
CREATE POLICY "Users mark own notifications read" ON public.notifications
FOR UPDATE TO authenticated
USING (recipient_id = (SELECT auth.uid()))
WITH CHECK (recipient_id = (SELECT auth.uid()));

DROP POLICY IF EXISTS "Users notify related users" ON public.notifications;
CREATE POLICY "Users notify related users" ON public.notifications
FOR INSERT TO authenticated
WITH CHECK (
  actor_id = (SELECT auth.uid())
  AND recipient_id <> (SELECT auth.uid())
  AND private.can_notify(recipient_id)
);

-- ---- Self-test: querying as a signed-in user must not error (e.g. no policy recursion) ----
SET LOCAL ROLE authenticated;
SELECT set_config('request.jwt.claims',
  '{"sub":"00000000-0000-0000-0000-000000000000","role":"authenticated"}', true);
SELECT count(*) AS notifications_visible_to_test_user FROM public.notifications;
SELECT private.can_notify('00000000-0000-0000-0000-000000000001') AS can_notify_test;
RESET ROLE;

COMMIT;

-- Rollback (not executed):
-- DROP TABLE IF EXISTS public.notifications;
-- DROP FUNCTION IF EXISTS private.can_notify(uuid);
