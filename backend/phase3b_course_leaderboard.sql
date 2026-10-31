-- ============================================================================
-- TrustGrade: course leaderboard (public.course_leaderboard RPC)
-- ============================================================================
-- Run once in the Supabase SQL Editor (one transaction; nothing changes on error).
--
-- Ranks the active students of ONE course by TOTAL MARKS EARNED across teacher-PUBLISHED
-- grades. Only published grades count; pending/approved AI suggestions never appear.
--
-- Who can call it: the course's owning (active) teacher, or an actively enrolled student.
-- Students see classmates' names and totals (product decision), never emails, feedback,
-- or per-assignment details. Anyone else gets an empty result.
--
-- Columns:
--   leaderboard_rank       RANK() by total marks (ties share a rank: 1, 2, 2, 4)
--   total_score            sum of final_score over the student's published grades
--   total_possible         sum of total_marks over the course's assignments that have at least
--                          one published grade (same for every student)
--   assignments_graded     how many of those assignments the student has a published grade for
--   assignments_counted    how many assignments count (same for every student)
--   last_published_at      most recent published grade for the student
--
-- SECURITY DEFINER because students cannot read classmates' grading_results under RLS.
-- Access is checked inside with the existing private.is_active_* helpers (phase2a).
-- ============================================================================

BEGIN;

CREATE OR REPLACE FUNCTION public.course_leaderboard(target_course_id UUID)
RETURNS TABLE (
  leaderboard_rank INT,
  student_id UUID,
  display_name TEXT,
  total_score NUMERIC,
  total_possible NUMERIC,
  assignments_graded INT,
  assignments_counted INT,
  last_published_at TIMESTAMPTZ
)
LANGUAGE sql
SECURITY DEFINER
SET search_path = ''
STABLE
AS $$
  WITH allowed AS (
    SELECT (private.is_active_course_teacher(target_course_id)
            OR private.is_active_enrolled_student(target_course_id)) AS ok
  ),
  counted_assignments AS (
    SELECT a.id, a.total_marks
    FROM public.assignments a
    WHERE a.course_id = target_course_id
      AND EXISTS (
        SELECT 1
        FROM public.submissions s
        JOIN public.grading_results g ON g.submission_id = s.id
        WHERE s.assignment_id = a.id AND g.status = 'published'
      )
  ),
  roster AS (
    SELECT e.student_id, p.display_name
    FROM public.course_enrollments e
    JOIN public.profiles p ON p.id = e.student_id
    WHERE e.course_id = target_course_id
      AND e.status = 'active'
      AND p.is_disabled = false
  ),
  scores AS (
    SELECT s.student_id,
           SUM(g.final_score) AS total,
           COUNT(DISTINCT s.assignment_id) AS graded,
           MAX(g.published_at) AS last_published
    FROM public.submissions s
    JOIN public.grading_results g ON g.submission_id = s.id AND g.status = 'published'
    JOIN counted_assignments ca ON ca.id = s.assignment_id
    GROUP BY s.student_id
  )
  SELECT
    (RANK() OVER (ORDER BY COALESCE(sc.total, 0) DESC))::INT,
    r.student_id,
    r.display_name::TEXT,
    COALESCE(sc.total, 0)::NUMERIC,
    (SELECT COALESCE(SUM(ca.total_marks), 0) FROM counted_assignments ca)::NUMERIC,
    COALESCE(sc.graded, 0)::INT,
    (SELECT COUNT(*) FROM counted_assignments)::INT,
    sc.last_published
  FROM roster r
  LEFT JOIN scores sc ON sc.student_id = r.student_id
  WHERE (SELECT ok FROM allowed)
  ORDER BY 1, r.display_name NULLS LAST;
$$;

COMMENT ON FUNCTION public.course_leaderboard(UUID) IS
  'TrustGrade: course standings by total published marks; owning teacher or enrolled students only.';

REVOKE ALL ON FUNCTION public.course_leaderboard(UUID) FROM PUBLIC, anon;
GRANT EXECUTE ON FUNCTION public.course_leaderboard(UUID) TO authenticated;

-- ---- Self-test: a signed-in non-member must get nothing for ANY course -----------------
-- Course ids are collected before switching role (a non-member cannot list courses under RLS,
-- which would make the check vacuous).
DO $$
DECLARE
  course_ids UUID[];
BEGIN
  SELECT array_agg(id) INTO course_ids FROM public.courses;
  PERFORM set_config('request.jwt.claims',
    '{"sub":"00000000-0000-0000-0000-000000000000","role":"authenticated"}', true);
  EXECUTE 'SET LOCAL ROLE authenticated';
  IF EXISTS (SELECT 1 FROM unnest(COALESCE(course_ids, '{}')) AS c(id), public.course_leaderboard(c.id)) THEN
    RAISE EXCEPTION 'Self-test failed: course_leaderboard returned data to a non-member';
  END IF;
  EXECUTE 'RESET ROLE';
END $$;

COMMIT;

-- Rollback (not executed):
-- DROP FUNCTION IF EXISTS public.course_leaderboard(UUID);
