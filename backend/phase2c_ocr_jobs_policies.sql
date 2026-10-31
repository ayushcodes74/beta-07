-- ============================================================================
-- TrustGrade: let the backend record OCR progress for submissions (ocr_jobs RLS)
-- ============================================================================
-- Run once in the Supabase SQL Editor (one transaction; nothing changes on error).
--
-- Before this, ocr_jobs had only "Teachers read own OCR jobs" (SELECT). The backend
-- acts as the signed-in user, so when a student submits a PDF it could not create the
-- submission's ocr_jobs row, and students could not read their own OCR status.
--
-- Adds, scoped strictly to the caller's own data:
--   students: read / create / update the OCR job of THEIR OWN submissions
--   teachers: create / update the OCR job of submissions to THEIR OWN assignments
-- Existing policy "Teachers read own OCR jobs" is left unchanged.
-- No recursion: these policies read submissions/assignments, whose policies never read ocr_jobs.
-- ============================================================================

BEGIN;

ALTER TABLE public.ocr_jobs ENABLE ROW LEVEL SECURITY;

-- Table privileges. RLS policies only filter rows; the role also needs the privilege itself.
-- Without INSERT here, student submissions failed with "permission denied for table ocr_jobs".
-- The policies below still restrict every row to the caller's own submissions/assignments.
GRANT SELECT, INSERT, UPDATE ON public.ocr_jobs TO authenticated;
-- Resubmission and OCR status refresh update the caller's own submission row
-- (rows are limited by the existing "Students update editable submissions" /
-- "Teachers update submissions" policies). Harmless if already granted.
GRANT UPDATE ON public.submissions TO authenticated;

-- ---- Students: own submissions only ------------------------------------------------
DROP POLICY IF EXISTS "Students read own OCR jobs" ON public.ocr_jobs;
CREATE POLICY "Students read own OCR jobs" ON public.ocr_jobs
FOR SELECT TO authenticated
USING (EXISTS (
  SELECT 1 FROM public.submissions s
  WHERE s.id = ocr_jobs.submission_id AND s.student_id = (SELECT auth.uid())
));

DROP POLICY IF EXISTS "Students create own OCR jobs" ON public.ocr_jobs;
CREATE POLICY "Students create own OCR jobs" ON public.ocr_jobs
FOR INSERT TO authenticated
WITH CHECK (EXISTS (
  SELECT 1 FROM public.submissions s
  WHERE s.id = ocr_jobs.submission_id AND s.student_id = (SELECT auth.uid())
));

DROP POLICY IF EXISTS "Students update own OCR jobs" ON public.ocr_jobs;
CREATE POLICY "Students update own OCR jobs" ON public.ocr_jobs
FOR UPDATE TO authenticated
USING (EXISTS (
  SELECT 1 FROM public.submissions s
  WHERE s.id = ocr_jobs.submission_id AND s.student_id = (SELECT auth.uid())
))
WITH CHECK (EXISTS (
  SELECT 1 FROM public.submissions s
  WHERE s.id = ocr_jobs.submission_id AND s.student_id = (SELECT auth.uid())
));

-- ---- Teachers: submissions to their own assignments (same rule as "Teachers read own OCR jobs") ----
DROP POLICY IF EXISTS "Teachers create OCR jobs" ON public.ocr_jobs;
CREATE POLICY "Teachers create OCR jobs" ON public.ocr_jobs
FOR INSERT TO authenticated
WITH CHECK (EXISTS (
  SELECT 1 FROM public.submissions s
  JOIN public.assignments a ON a.id = s.assignment_id
  JOIN public.profiles p ON p.id = a.teacher_id
  WHERE s.id = ocr_jobs.submission_id AND a.teacher_id = (SELECT auth.uid())
    AND p.role = 'teacher' AND p.is_disabled = false
));

DROP POLICY IF EXISTS "Teachers update OCR jobs" ON public.ocr_jobs;
CREATE POLICY "Teachers update OCR jobs" ON public.ocr_jobs
FOR UPDATE TO authenticated
USING (EXISTS (
  SELECT 1 FROM public.submissions s
  JOIN public.assignments a ON a.id = s.assignment_id
  JOIN public.profiles p ON p.id = a.teacher_id
  WHERE s.id = ocr_jobs.submission_id AND a.teacher_id = (SELECT auth.uid())
    AND p.role = 'teacher' AND p.is_disabled = false
))
WITH CHECK (EXISTS (
  SELECT 1 FROM public.submissions s
  JOIN public.assignments a ON a.id = s.assignment_id
  JOIN public.profiles p ON p.id = a.teacher_id
  WHERE s.id = ocr_jobs.submission_id AND a.teacher_id = (SELECT auth.uid())
    AND p.role = 'teacher' AND p.is_disabled = false
));

-- ---- Self-test: querying as a signed-in user must not error (e.g. no policy recursion) ----
SET LOCAL ROLE authenticated;
SELECT set_config('request.jwt.claims',
  '{"sub":"00000000-0000-0000-0000-000000000000","role":"authenticated"}', true);
SELECT count(*) AS ocr_jobs_visible_to_test_user FROM public.ocr_jobs;
RESET ROLE;

COMMIT;

-- Rollback (not executed):
-- REVOKE INSERT, UPDATE ON public.ocr_jobs FROM authenticated;
-- DROP POLICY IF EXISTS "Students read own OCR jobs" ON public.ocr_jobs;
-- DROP POLICY IF EXISTS "Students create own OCR jobs" ON public.ocr_jobs;
-- DROP POLICY IF EXISTS "Students update own OCR jobs" ON public.ocr_jobs;
-- DROP POLICY IF EXISTS "Teachers create OCR jobs" ON public.ocr_jobs;
-- DROP POLICY IF EXISTS "Teachers update OCR jobs" ON public.ocr_jobs;
