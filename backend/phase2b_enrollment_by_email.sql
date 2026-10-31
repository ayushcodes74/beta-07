-- ============================================================================
-- TrustGrade: enroll students by email + course roster with names/emails
-- ============================================================================
-- Run once in the Supabase SQL Editor (one transaction; nothing changes on error).
--
-- Why database functions: student emails live in auth.users, which the app cannot
-- read, and the "Users read own profile" policy stops teachers reading student
-- profiles. These SECURITY DEFINER functions expose only what a course's owning
-- teacher needs, and nothing to anyone else.
--
-- Used by:
--   backend/app/database/course_repository.py
--     find_student_id_by_email -> rpc("find_student_for_enrollment")
--     list_enrolled_students   -> rpc("course_roster")
-- ============================================================================

BEGIN;

-- ----------------------------------------------------------------------------
-- Resolve a student's email to their user id, for the course's owning teacher only.
-- Returns NULL for every failure (not a teacher, not the owner, unknown email, not a
-- student, disabled) so callers cannot tell those cases apart.
-- ----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.find_student_for_enrollment(
  target_course_id UUID,
  student_email TEXT
)
RETURNS UUID
LANGUAGE sql
SECURITY DEFINER
SET search_path = ''
STABLE
AS $$
  SELECT p.id
  FROM auth.users u
  JOIN public.profiles p ON p.id = u.id
  WHERE lower(u.email) = lower(btrim(student_email))
    AND p.role = 'student'
    AND p.is_disabled = false
    -- caller must be an active teacher who owns the course
    AND EXISTS (
      SELECT 1
      FROM public.courses c
      JOIN public.profiles t ON t.id = c.teacher_id
      WHERE c.id = target_course_id
        AND c.teacher_id = auth.uid()
        AND t.role = 'teacher'
        AND t.is_disabled = false
    )
  LIMIT 1;
$$;

COMMENT ON FUNCTION public.find_student_for_enrollment(UUID, TEXT) IS
  'TrustGrade: course-owning teacher resolves a student email to a student id for enrollment.';

REVOKE ALL ON FUNCTION public.find_student_for_enrollment(UUID, TEXT) FROM PUBLIC, anon;
GRANT EXECUTE ON FUNCTION public.find_student_for_enrollment(UUID, TEXT) TO authenticated;

-- ----------------------------------------------------------------------------
-- Active roster (name + email) for the course's owning teacher only; empty otherwise.
-- ----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.course_roster(target_course_id UUID)
RETURNS TABLE (
  student_id UUID,
  display_name TEXT,
  email TEXT,
  status TEXT,
  enrolled_at TIMESTAMPTZ
)
LANGUAGE sql
SECURITY DEFINER
SET search_path = ''
STABLE
AS $$
  SELECT e.student_id, p.display_name::TEXT, u.email::TEXT, e.status::TEXT, e.enrolled_at
  FROM public.course_enrollments e
  JOIN public.profiles p ON p.id = e.student_id
  JOIN auth.users u ON u.id = e.student_id
  WHERE e.course_id = target_course_id
    AND e.status = 'active'
    AND EXISTS (
      SELECT 1
      FROM public.courses c
      JOIN public.profiles t ON t.id = c.teacher_id
      WHERE c.id = target_course_id
        AND c.teacher_id = auth.uid()
        AND t.role = 'teacher'
        AND t.is_disabled = false
    )
  ORDER BY e.enrolled_at;
$$;

COMMENT ON FUNCTION public.course_roster(UUID) IS
  'TrustGrade: active course roster with student names/emails, visible only to the owning teacher.';

REVOKE ALL ON FUNCTION public.course_roster(UUID) FROM PUBLIC, anon;
GRANT EXECUTE ON FUNCTION public.course_roster(UUID) TO authenticated;

-- ----------------------------------------------------------------------------
-- Self-test: as a signed-in non-owner, both functions must return nothing.
-- ----------------------------------------------------------------------------
SET LOCAL ROLE authenticated;
SELECT set_config('request.jwt.claims',
  '{"sub":"00000000-0000-0000-0000-000000000000","role":"authenticated"}', true);
DO $$
BEGIN
  IF (SELECT public.find_student_for_enrollment(c.id, 'nobody@example.invalid') FROM public.courses c LIMIT 1) IS NOT NULL
     OR EXISTS (SELECT 1 FROM public.courses c, public.course_roster(c.id)) THEN
    RAISE EXCEPTION 'Self-test failed: functions returned data to a non-owner';
  END IF;
END $$;
RESET ROLE;

COMMIT;

-- Rollback (not executed):
-- DROP FUNCTION IF EXISTS public.find_student_for_enrollment(UUID, TEXT);
-- DROP FUNCTION IF EXISTS public.course_roster(UUID);
