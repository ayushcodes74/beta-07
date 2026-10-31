-- ============================================================================
-- TrustGrade: student review (re-evaluation) requests  (review_requests + RLS)
-- ============================================================================
-- Run once in the Supabase SQL Editor (one transaction; nothing changes on error).
--
-- A student who is not satisfied with a PUBLISHED grade can flag the submission for
-- teacher review with a written reason. The owning teacher sees it in the dashboard
-- "Review queue" (Student requests tab) and resolves or dismisses it with a response.
--
-- Access, scoped strictly to the caller's own data:
--   students: read their own requests; create one for their own PUBLISHED submission
--             (only submission_id, student_id, reason are writable -> always starts 'open')
--   teachers: read and resolve/dismiss requests on submissions to THEIR OWN assignments
--             (only status, teacher_response, resolved_by, resolved_at, updated_at writable)
-- At most one OPEN request per submission (partial unique index).
-- No recursion: policies read submissions/assignments/profiles, which never read review_requests.
-- ============================================================================

BEGIN;

CREATE TABLE IF NOT EXISTS public.review_requests (
  id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  submission_id    uuid NOT NULL REFERENCES public.submissions(id) ON DELETE CASCADE,
  student_id       uuid NOT NULL REFERENCES public.profiles(id) ON DELETE CASCADE,
  reason           text NOT NULL CHECK (char_length(btrim(reason)) BETWEEN 10 AND 2000),
  status           text NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'resolved', 'dismissed')),
  teacher_response text CHECK (teacher_response IS NULL OR char_length(teacher_response) <= 2000),
  resolved_by      uuid REFERENCES public.profiles(id),
  resolved_at      timestamptz,
  created_at       timestamptz NOT NULL DEFAULT now(),
  updated_at       timestamptz NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS review_requests_one_open_per_submission
  ON public.review_requests (submission_id) WHERE status = 'open';
CREATE INDEX IF NOT EXISTS review_requests_submission_idx ON public.review_requests (submission_id);
CREATE INDEX IF NOT EXISTS review_requests_student_idx ON public.review_requests (student_id);

ALTER TABLE public.review_requests ENABLE ROW LEVEL SECURITY;

-- Column-level privileges: RLS filters rows, these limit which columns each write may touch.
REVOKE ALL ON public.review_requests FROM anon, authenticated;
GRANT SELECT ON public.review_requests TO authenticated;
GRANT INSERT (submission_id, student_id, reason) ON public.review_requests TO authenticated;
GRANT UPDATE (status, teacher_response, resolved_by, resolved_at, updated_at) ON public.review_requests TO authenticated;

-- ---- Students: own requests, own published submissions ----------------------------
DROP POLICY IF EXISTS "Students read own review requests" ON public.review_requests;
CREATE POLICY "Students read own review requests" ON public.review_requests
FOR SELECT TO authenticated
USING (student_id = (SELECT auth.uid()));

DROP POLICY IF EXISTS "Students request review of own published grade" ON public.review_requests;
CREATE POLICY "Students request review of own published grade" ON public.review_requests
FOR INSERT TO authenticated
WITH CHECK (
  student_id = (SELECT auth.uid())
  AND EXISTS (
    SELECT 1 FROM public.submissions s
    WHERE s.id = review_requests.submission_id
      AND s.student_id = (SELECT auth.uid())
      AND s.status = 'published'
  )
);

-- ---- Teachers: submissions to their own assignments --------------------------------
DROP POLICY IF EXISTS "Teachers read review requests" ON public.review_requests;
CREATE POLICY "Teachers read review requests" ON public.review_requests
FOR SELECT TO authenticated
USING (EXISTS (
  SELECT 1 FROM public.submissions s
  JOIN public.assignments a ON a.id = s.assignment_id
  JOIN public.profiles p ON p.id = a.teacher_id
  WHERE s.id = review_requests.submission_id AND a.teacher_id = (SELECT auth.uid())
    AND p.role = 'teacher' AND p.is_disabled = false
));

DROP POLICY IF EXISTS "Teachers resolve review requests" ON public.review_requests;
CREATE POLICY "Teachers resolve review requests" ON public.review_requests
FOR UPDATE TO authenticated
USING (EXISTS (
  SELECT 1 FROM public.submissions s
  JOIN public.assignments a ON a.id = s.assignment_id
  JOIN public.profiles p ON p.id = a.teacher_id
  WHERE s.id = review_requests.submission_id AND a.teacher_id = (SELECT auth.uid())
    AND p.role = 'teacher' AND p.is_disabled = false
))
WITH CHECK (
  resolved_by = (SELECT auth.uid())
  AND EXISTS (
    SELECT 1 FROM public.submissions s
    JOIN public.assignments a ON a.id = s.assignment_id
    WHERE s.id = review_requests.submission_id AND a.teacher_id = (SELECT auth.uid())
  )
);

-- ---- Self-test: querying as a signed-in user must not error (e.g. no policy recursion) ----
SET LOCAL ROLE authenticated;
SELECT set_config('request.jwt.claims',
  '{"sub":"00000000-0000-0000-0000-000000000000","role":"authenticated"}', true);
SELECT count(*) AS review_requests_visible_to_test_user FROM public.review_requests;
RESET ROLE;

COMMIT;

-- Rollback (not executed):
-- DROP TABLE IF EXISTS public.review_requests;
