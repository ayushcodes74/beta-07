-- ============================================================================
-- TrustGrade: fix RLS infinite recursion (42P17) between courses <-> course_enrollments
-- ============================================================================
-- Supersedes the policy portion of phase2a_rls_remediation.sql, which targeted
-- policy names that do not exist in the live database.
--
-- Cause (live policies as of 2026-10-31):
--   courses."Students read enrolled courses"        -> reads course_enrollments
--   course_enrollments."Teachers manage enrollments" -> reads courses
-- Postgres expands every permissive policy, so any query touching courses (and
-- assignments, via "Students read published assignments") loops forever.
--
-- Fix: keep both policies with the SAME names and the SAME access rules, but do the
-- cross-table lookup inside SECURITY DEFINER helpers in a non-exposed `private`
-- schema. Those helpers read the other table without re-applying its RLS, which
-- breaks the cycle. No other policy is touched.
--
-- Safe to run as a whole in the Supabase SQL Editor: it is one transaction, it
-- aborts unless the policy set is exactly what it expects, and it self-tests as an
-- `authenticated` user before committing. If anything fails, nothing is changed.
-- ============================================================================

BEGIN;

-- ----------------------------------------------------------------------------
-- Guard: the policy set on these two tables must be exactly what this was written for.
-- ----------------------------------------------------------------------------
DO $$
DECLARE
  expected TEXT[] := ARRAY[
    'courses|Students read enrolled courses',
    'courses|Teachers manage own courses',
    'course_enrollments|Teachers manage enrollments',
    'course_enrollments|Users read own enrollments'
  ];
  actual TEXT[];
BEGIN
  SELECT coalesce(array_agg(tablename || '|' || policyname), '{}')
  INTO actual
  FROM pg_policies
  WHERE schemaname = 'public' AND tablename IN ('courses', 'course_enrollments');

  IF NOT (actual @> expected AND actual <@ expected) THEN
    RAISE EXCEPTION 'Aborted: unexpected policy set on courses/course_enrollments: %', actual;
  END IF;
END $$;

-- Guard: the helper functions below run as the role executing this script. They only
-- break the cycle if that role is exempt from RLS on both tables (table owner without
-- FORCE ROW LEVEL SECURITY, or a BYPASSRLS role). Otherwise abort rather than "fix" nothing.
DO $$
DECLARE
  t RECORD;
  bypass BOOLEAN;
BEGIN
  SELECT rolbypassrls INTO bypass FROM pg_roles WHERE rolname = current_user;
  FOR t IN
    SELECT c.relname, pg_get_userbyid(c.relowner) AS owner, c.relforcerowsecurity AS forced
    FROM pg_class c
    WHERE c.oid IN ('public.courses'::regclass, 'public.course_enrollments'::regclass)
  LOOP
    IF NOT bypass AND (t.owner <> current_user OR t.forced) THEN
      RAISE EXCEPTION 'Aborted: % is owned by % (force_rls=%); run this as that owner so helper functions bypass RLS.',
        t.relname, t.owner, t.forced;
    END IF;
  END LOOP;
END $$;

-- ----------------------------------------------------------------------------
-- Private helper schema (not exposed through the Supabase REST API)
-- ----------------------------------------------------------------------------
CREATE SCHEMA IF NOT EXISTS private;
REVOKE ALL ON SCHEMA private FROM PUBLIC;
REVOKE ALL ON SCHEMA private FROM anon;
GRANT USAGE ON SCHEMA private TO authenticated;

-- Same condition as the original "Students read enrolled courses" policy.
CREATE OR REPLACE FUNCTION private.is_active_enrolled_student(check_course_id UUID)
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
      AND e.student_id = auth.uid()
      AND e.status = 'active'
      AND p.is_disabled = false
  );
$$;

-- Same condition as the original "Teachers manage enrollments" policy.
CREATE OR REPLACE FUNCTION private.is_active_course_teacher(check_course_id UUID)
RETURNS BOOLEAN
LANGUAGE sql
SECURITY DEFINER
SET search_path = ''
STABLE
AS $$
  SELECT EXISTS (
    SELECT 1
    FROM public.courses c
    JOIN public.profiles p ON p.id = c.teacher_id
    WHERE c.id = check_course_id
      AND c.teacher_id = auth.uid()
      AND p.role = 'teacher'
      AND p.is_disabled = false
  );
$$;

REVOKE ALL ON FUNCTION private.is_active_enrolled_student(UUID) FROM PUBLIC, anon;
REVOKE ALL ON FUNCTION private.is_active_course_teacher(UUID) FROM PUBLIC, anon;
GRANT EXECUTE ON FUNCTION private.is_active_enrolled_student(UUID) TO authenticated;
GRANT EXECUTE ON FUNCTION private.is_active_course_teacher(UUID) TO authenticated;

-- ----------------------------------------------------------------------------
-- Recreate the two cyclic policies (same names, same rules, no cross-table RLS)
-- ----------------------------------------------------------------------------
DROP POLICY "Students read enrolled courses" ON public.courses;
CREATE POLICY "Students read enrolled courses" ON public.courses
FOR SELECT TO authenticated
USING (private.is_active_enrolled_student(id));

DROP POLICY "Teachers manage enrollments" ON public.course_enrollments;
CREATE POLICY "Teachers manage enrollments" ON public.course_enrollments
FOR ALL TO authenticated
USING (private.is_active_course_teacher(course_id))
WITH CHECK (private.is_active_course_teacher(course_id));

-- ----------------------------------------------------------------------------
-- Student-enrollment validation RPC used by the backend
-- (backend/app/database/course_repository.py -> client.rpc("validate_student_enrollment_target")).
-- Copied unchanged from the reviewed phase2a_rls_remediation.sql, STEP 4.
-- ----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.validate_student_enrollment_target(
  target_course_id UUID,
  target_student_id UUID
)
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
STABLE
AS $$
DECLARE
  caller_role TEXT;
  caller_disabled BOOLEAN;
  course_teacher_id UUID;
  target_rec RECORD;
BEGIN
  IF auth.uid() IS NULL THEN
    RETURN pg_catalog.jsonb_build_object('is_valid', FALSE, 'error_code', 'unauthorized',
      'error_message', 'Authentication required.');
  END IF;

  SELECT role, is_disabled INTO caller_role, caller_disabled
  FROM public.profiles WHERE id = auth.uid();

  IF caller_role IS NULL OR caller_role != 'teacher' OR caller_disabled IS TRUE THEN
    RETURN pg_catalog.jsonb_build_object('is_valid', FALSE, 'error_code', 'forbidden',
      'error_message', 'Only active teachers can validate student accounts.');
  END IF;

  SELECT teacher_id INTO course_teacher_id FROM public.courses WHERE id = target_course_id;

  IF NOT FOUND OR course_teacher_id != auth.uid() THEN
    RETURN pg_catalog.jsonb_build_object('is_valid', FALSE, 'error_code', 'course_not_found',
      'error_message', 'Course not found or caller is not the owner teacher.');
  END IF;

  SELECT id, role, is_disabled, display_name INTO target_rec
  FROM public.profiles WHERE id = target_student_id;

  IF NOT FOUND THEN
    RETURN pg_catalog.jsonb_build_object('is_valid', FALSE, 'error_code', 'student_not_found',
      'error_message', 'The specified student profile was not found.');
  END IF;

  IF target_rec.role != 'student' THEN
    RETURN pg_catalog.jsonb_build_object('is_valid', FALSE, 'error_code', 'invalid_role',
      'error_message', 'Only student accounts can be enrolled in courses.');
  END IF;

  IF target_rec.is_disabled IS TRUE THEN
    RETURN pg_catalog.jsonb_build_object('is_valid', FALSE, 'error_code', 'account_disabled',
      'error_message', 'Cannot enroll a disabled student account.');
  END IF;

  RETURN pg_catalog.jsonb_build_object('is_valid', TRUE, 'student_id', target_rec.id,
    'role', target_rec.role, 'is_disabled', target_rec.is_disabled,
    'display_name', target_rec.display_name);
END;
$$;

REVOKE ALL ON FUNCTION public.validate_student_enrollment_target(UUID, UUID) FROM PUBLIC, anon;
GRANT EXECUTE ON FUNCTION public.validate_student_enrollment_target(UUID, UUID) TO authenticated;

-- ----------------------------------------------------------------------------
-- Self-test: query the affected tables as an `authenticated` user.
-- If recursion still exists, this raises 42P17 and the whole transaction rolls back.
-- ----------------------------------------------------------------------------
SET LOCAL ROLE authenticated;
SELECT set_config('request.jwt.claims',
  '{"sub":"00000000-0000-0000-0000-000000000000","role":"authenticated"}', true);
SELECT count(*) AS courses_visible FROM public.courses;
SELECT count(*) AS enrollments_visible FROM public.course_enrollments;
SELECT count(*) AS assignments_visible FROM public.assignments;
SELECT count(*) AS submissions_visible FROM public.submissions;
RESET ROLE;

COMMIT;

-- ============================================================================
-- ROLLBACK (restores the exact original policies). Not executed: remove the
-- comment markers and run separately only if you need to undo this change.
-- ============================================================================
/*
BEGIN;
DROP POLICY "Students read enrolled courses" ON public.courses;
CREATE POLICY "Students read enrolled courses" ON public.courses
FOR SELECT TO authenticated
USING (EXISTS (
  SELECT 1 FROM public.course_enrollments e JOIN public.profiles p ON p.id = e.student_id
  WHERE e.course_id = courses.id AND e.student_id = (SELECT auth.uid())
    AND e.status = 'active' AND p.is_disabled = false));

DROP POLICY "Teachers manage enrollments" ON public.course_enrollments;
CREATE POLICY "Teachers manage enrollments" ON public.course_enrollments
FOR ALL TO authenticated
USING (EXISTS (
  SELECT 1 FROM public.courses c JOIN public.profiles p ON p.id = c.teacher_id
  WHERE c.id = course_enrollments.course_id AND c.teacher_id = (SELECT auth.uid())
    AND p.role = 'teacher' AND p.is_disabled = false))
WITH CHECK (EXISTS (
  SELECT 1 FROM public.courses c JOIN public.profiles p ON p.id = c.teacher_id
  WHERE c.id = course_enrollments.course_id AND c.teacher_id = (SELECT auth.uid())
    AND p.role = 'teacher' AND p.is_disabled = false));

DROP FUNCTION IF EXISTS private.is_active_enrolled_student(UUID);
DROP FUNCTION IF EXISTS private.is_active_course_teacher(UUID);
COMMIT;
*/
