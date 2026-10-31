-- ============================================================================
-- TrustGrade — Phase 2A.4: Supabase RLS Remediation Migration Proposal
-- ============================================================================
-- Notice: REVIEWED MIGRATION PROPOSAL — NOT EXECUTED AGAINST PRODUCTION.
--
-- Objectives:
-- 1. Break infinite recursion between courses and course_enrollments RLS policies
--    using narrow, non-recursive SECURITY DEFINER helper functions.
-- 2. Provide a secure, least-privilege RPC for course-owning teachers to
--    validate prospective student enrollments for their OWN courses without
--    exposing public.profiles globally or allowing student enumeration across
--    courses they do not own.
-- 3. Prevent duplicate active enrollments under concurrency with a partial unique index.
-- 4. Provide a complete, verified rollback strategy restoring baseline policies.
--
-- Target Database: PostgreSQL 15+ / Supabase
-- Target Schema: public
-- ============================================================================

BEGIN;

-- ----------------------------------------------------------------------------
-- STEP 0: Pre-migration Consistency & Duplication Check (Diagnostic only)
-- ----------------------------------------------------------------------------
-- The following check MUST be executed before applying the partial unique index.
-- If duplicate active enrollments exist, they must be manually resolved prior
-- to running this script to avoid index creation failure.
DO $$
DECLARE
  dup_count INTEGER;
BEGIN
  SELECT COUNT(*) INTO dup_count
  FROM (
    SELECT course_id, student_id
    FROM public.course_enrollments
    WHERE status = 'active'
    GROUP BY course_id, student_id
    HAVING COUNT(*) > 1
  ) dups;

  IF dup_count > 0 THEN
    RAISE EXCEPTION 'Migration aborted: % duplicate active enrollment pairs found. Reconcile historical data before applying partial unique index.', dup_count;
  END IF;
END $$;


-- ----------------------------------------------------------------------------
-- STEP 1: Helper Functions for Non-Recursive Access Verification
-- ----------------------------------------------------------------------------

-- Function 1: Checks whether the authenticated caller owns the specified course.
-- Security: Derives identity strictly from auth.uid(); accepts zero client user IDs.
-- Hardened: SET search_path = '' with fully qualified schema references.
CREATE OR REPLACE FUNCTION public.is_course_owner(check_course_id UUID)
RETURNS BOOLEAN
LANGUAGE sql
SECURITY DEFINER
SET search_path = ''
STABLE
AS $$
  SELECT EXISTS (
    SELECT 1
    FROM public.courses
    WHERE id = check_course_id
      AND teacher_id = auth.uid()
  );
$$;

COMMENT ON FUNCTION public.is_course_owner(UUID) IS
  'TrustGrade Phase 2A: Non-recursive security-definer check for course ownership.';

REVOKE ALL ON FUNCTION public.is_course_owner(UUID) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION public.is_course_owner(UUID) TO authenticated;


-- Function 2: Checks whether the authenticated caller has an active enrollment in the course.
-- Security: Derives identity strictly from auth.uid(); accepts zero client user IDs.
-- Hardened: SET search_path = '' with fully qualified schema references.
CREATE OR REPLACE FUNCTION public.is_enrolled_student(check_course_id UUID)
RETURNS BOOLEAN
LANGUAGE sql
SECURITY DEFINER
SET search_path = ''
STABLE
AS $$
  SELECT EXISTS (
    SELECT 1
    FROM public.course_enrollments
    WHERE course_id = check_course_id
      AND student_id = auth.uid()
      AND status = 'active'
  );
$$;

COMMENT ON FUNCTION public.is_enrolled_student(UUID) IS
  'TrustGrade Phase 2A: Non-recursive security-definer check for active student course enrollment.';

REVOKE ALL ON FUNCTION public.is_enrolled_student(UUID) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION public.is_enrolled_student(UUID) TO authenticated;


-- ----------------------------------------------------------------------------
-- STEP 2: Replace Recursive RLS Policies on public.courses
-- ----------------------------------------------------------------------------

ALTER TABLE public.courses ENABLE ROW LEVEL SECURITY;

-- Drop existing/legacy policies
DROP POLICY IF EXISTS "courses_select" ON public.courses;
DROP POLICY IF EXISTS "courses_insert" ON public.courses;
DROP POLICY IF EXISTS "courses_update" ON public.courses;
DROP POLICY IF EXISTS "courses_delete" ON public.courses;
DROP POLICY IF EXISTS "courses_owner_select" ON public.courses;
DROP POLICY IF EXISTS "courses_student_select" ON public.courses;
DROP POLICY IF EXISTS "courses_policy" ON public.courses;
DROP POLICY IF EXISTS "courses_select_policy" ON public.courses;
DROP POLICY IF EXISTS "courses_insert_policy" ON public.courses;
DROP POLICY IF EXISTS "courses_update_policy" ON public.courses;
DROP POLICY IF EXISTS "courses_delete_policy" ON public.courses;

-- SELECT Policy: Teacher owns course OR student has active enrollment
CREATE POLICY "courses_select_policy" ON public.courses
FOR SELECT TO authenticated
USING (
  teacher_id = auth.uid()
  OR
  public.is_enrolled_student(id)
);

-- INSERT Policy: Authenticated teacher creating course owned by themselves
CREATE POLICY "courses_insert_policy" ON public.courses
FOR INSERT TO authenticated
WITH CHECK (
  teacher_id = auth.uid()
);

-- UPDATE Policy: Owning teacher only
CREATE POLICY "courses_update_policy" ON public.courses
FOR UPDATE TO authenticated
USING (
  teacher_id = auth.uid()
)
WITH CHECK (
  teacher_id = auth.uid()
);

-- DELETE Policy: Owning teacher only
CREATE POLICY "courses_delete_policy" ON public.courses
FOR DELETE TO authenticated
USING (
  teacher_id = auth.uid()
);


-- ----------------------------------------------------------------------------
-- STEP 3: Replace Recursive RLS Policies on public.course_enrollments
-- ----------------------------------------------------------------------------

ALTER TABLE public.course_enrollments ENABLE ROW LEVEL SECURITY;

-- Drop existing/legacy policies
DROP POLICY IF EXISTS "course_enrollments_select" ON public.course_enrollments;
DROP POLICY IF EXISTS "course_enrollments_insert" ON public.course_enrollments;
DROP POLICY IF EXISTS "course_enrollments_update" ON public.course_enrollments;
DROP POLICY IF EXISTS "course_enrollments_delete" ON public.course_enrollments;
DROP POLICY IF EXISTS "course_enrollments_policy" ON public.course_enrollments;
DROP POLICY IF EXISTS "course_enrollments_select_policy" ON public.course_enrollments;
DROP POLICY IF EXISTS "course_enrollments_insert_policy" ON public.course_enrollments;
DROP POLICY IF EXISTS "course_enrollments_update_policy" ON public.course_enrollments;
DROP POLICY IF EXISTS "course_enrollments_delete_policy" ON public.course_enrollments;

-- SELECT Policy: Student reads their own enrollment OR course-owning teacher reads roster
CREATE POLICY "course_enrollments_select_policy" ON public.course_enrollments
FOR SELECT TO authenticated
USING (
  student_id = auth.uid()
  OR
  public.is_course_owner(course_id)
);

-- INSERT Policy: Course-owning teacher enrolls a student
CREATE POLICY "course_enrollments_insert_policy" ON public.course_enrollments
FOR INSERT TO authenticated
WITH CHECK (
  public.is_course_owner(course_id)
);

-- UPDATE Policy: Course-owning teacher modifies enrollment (e.g., status changes)
CREATE POLICY "course_enrollments_update_policy" ON public.course_enrollments
FOR UPDATE TO authenticated
USING (
  public.is_course_owner(course_id)
)
WITH CHECK (
  public.is_course_owner(course_id)
);

-- DELETE Policy: Course-owning teacher deletes enrollment
CREATE POLICY "course_enrollments_delete_policy" ON public.course_enrollments
FOR DELETE TO authenticated
USING (
  public.is_course_owner(course_id)
);


-- ----------------------------------------------------------------------------
-- STEP 4: Course-Scoped Student Profile Validation RPC Function
-- ----------------------------------------------------------------------------
-- Requires both target_course_id and target_student_id.
-- Enforces that:
--   1. Caller is an authenticated user (auth.uid()).
--   2. Caller is an active teacher (profiles.role = 'teacher' AND is_disabled = false).
--   3. Caller owns the course target_course_id (courses.teacher_id = auth.uid()).
--   4. Target student exists in public.profiles.
--   5. Target role is 'student'.
--   6. Target account is not disabled.
-- Prevents a teacher from enumerating students for courses they do not own.
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
  -- 1. Verify caller authentication
  IF auth.uid() IS NULL THEN
    RETURN pg_catalog.jsonb_build_object(
      'is_valid', FALSE,
      'error_code', 'unauthorized',
      'error_message', 'Authentication required.'
    );
  END IF;

  -- 2. Verify caller is an active teacher
  SELECT role, is_disabled INTO caller_role, caller_disabled
  FROM public.profiles
  WHERE id = auth.uid();

  IF caller_role IS NULL OR caller_role != 'teacher' OR caller_disabled IS TRUE THEN
    RETURN pg_catalog.jsonb_build_object(
      'is_valid', FALSE,
      'error_code', 'forbidden',
      'error_message', 'Only active teachers can validate student accounts.'
    );
  END IF;

  -- 3. Verify course ownership: caller must own target_course_id
  SELECT teacher_id INTO course_teacher_id
  FROM public.courses
  WHERE id = target_course_id;

  IF NOT FOUND OR course_teacher_id != auth.uid() THEN
    -- Return course_not_found to preserve privacy convention (do not confirm existence of unowned course)
    RETURN pg_catalog.jsonb_build_object(
      'is_valid', FALSE,
      'error_code', 'course_not_found',
      'error_message', 'Course not found or caller is not the owner teacher.'
    );
  END IF;

  -- 4. Lookup target student profile
  SELECT id, role, is_disabled, display_name
  INTO target_rec
  FROM public.profiles
  WHERE id = target_student_id;

  IF NOT FOUND THEN
    RETURN pg_catalog.jsonb_build_object(
      'is_valid', FALSE,
      'error_code', 'student_not_found',
      'error_message', 'The specified student profile was not found.'
    );
  END IF;

  -- 5. Check role is student
  IF target_rec.role != 'student' THEN
    RETURN pg_catalog.jsonb_build_object(
      'is_valid', FALSE,
      'error_code', 'invalid_role',
      'error_message', 'Only student accounts can be enrolled in courses.'
    );
  END IF;

  -- 6. Check account is not disabled
  IF target_rec.is_disabled IS TRUE THEN
    RETURN pg_catalog.jsonb_build_object(
      'is_valid', FALSE,
      'error_code', 'account_disabled',
      'error_message', 'Cannot enroll a disabled student account.'
    );
  END IF;

  -- 7. Successful validation: return safe public details
  RETURN pg_catalog.jsonb_build_object(
    'is_valid', TRUE,
    'student_id', target_rec.id,
    'role', target_rec.role,
    'is_disabled', target_rec.is_disabled,
    'display_name', target_rec.display_name
  );
END;
$$;

COMMENT ON FUNCTION public.validate_student_enrollment_target(UUID, UUID) IS
  'TrustGrade Phase 2A: Secure, course-scoped RPC for teachers to validate prospective student enrollments.';

REVOKE ALL ON FUNCTION public.validate_student_enrollment_target(UUID, UUID) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION public.validate_student_enrollment_target(UUID, UUID) TO authenticated;


-- ----------------------------------------------------------------------------
-- STEP 5: Concurrency Protection & Index Verification
-- ----------------------------------------------------------------------------
-- Data Model & Constraint Note:
-- The TrustGrade enrollment model maintains at most ONE row per student per course
-- (soft deactivation updates status = 'inactive', and re-enrollment reactivates
-- status = 'active' in-place).
--
-- Redundancy Check:
-- If the database table already has the table-level constraint:
--   UNIQUE (course_id, student_id)
-- then active enrollment uniqueness is ALREADY strictly enforced across the table,
-- and the partial index below is technically redundant.
--
-- However, if the table was initially created without that total constraint,
-- this partial index is required to prevent concurrent race conditions from
-- creating duplicate active enrollments.
CREATE UNIQUE INDEX IF NOT EXISTS idx_course_enrollments_unique_active
ON public.course_enrollments (course_id, student_id)
WHERE (status = 'active');

COMMIT;

-- ============================================================================
-- VERIFIED ROLLBACK SCRIPT
-- ============================================================================
-- Restores pre-migration baseline state rather than leaving tables unmanaged.
-- Execute only if migration rollback is required.
/*
BEGIN;
  -- 1. Drop partial unique index
  DROP INDEX IF EXISTS public.idx_course_enrollments_unique_active;

  -- 2. Drop validation RPC
  DROP FUNCTION IF EXISTS public.validate_student_enrollment_target(UUID, UUID);

  -- 3. Drop remediation policies
  DROP POLICY IF EXISTS "course_enrollments_delete_policy" ON public.course_enrollments;
  DROP POLICY IF EXISTS "course_enrollments_update_policy" ON public.course_enrollments;
  DROP POLICY IF EXISTS "course_enrollments_insert_policy" ON public.course_enrollments;
  DROP POLICY IF EXISTS "course_enrollments_select_policy" ON public.course_enrollments;

  DROP POLICY IF EXISTS "courses_delete_policy" ON public.courses;
  DROP POLICY IF EXISTS "courses_update_policy" ON public.courses;
  DROP POLICY IF EXISTS "courses_insert_policy" ON public.courses;
  DROP POLICY IF EXISTS "courses_select_policy" ON public.courses;

  -- 4. Drop non-recursive helper functions
  DROP FUNCTION IF EXISTS public.is_enrolled_student(UUID);
  DROP FUNCTION IF EXISTS public.is_course_owner(UUID);

  -- 5. Restore baseline original policies (with recursive checks)
  CREATE POLICY "courses_select" ON public.courses
  FOR SELECT TO authenticated
  USING (
    teacher_id = auth.uid()
    OR
    id IN (SELECT course_id FROM public.course_enrollments WHERE student_id = auth.uid())
  );

  CREATE POLICY "courses_insert" ON public.courses
  FOR INSERT TO authenticated
  WITH CHECK (teacher_id = auth.uid());

  CREATE POLICY "courses_update" ON public.courses
  FOR UPDATE TO authenticated
  USING (teacher_id = auth.uid());

  CREATE POLICY "courses_delete" ON public.courses
  FOR DELETE TO authenticated
  USING (teacher_id = auth.uid());

  CREATE POLICY "course_enrollments_select" ON public.course_enrollments
  FOR SELECT TO authenticated
  USING (
    student_id = auth.uid()
    OR
    course_id IN (SELECT id FROM public.courses WHERE teacher_id = auth.uid())
  );

  CREATE POLICY "course_enrollments_insert" ON public.course_enrollments
  FOR INSERT TO authenticated
  WITH CHECK (
    course_id IN (SELECT id FROM public.courses WHERE teacher_id = auth.uid())
  );

  CREATE POLICY "course_enrollments_update" ON public.course_enrollments
  FOR UPDATE TO authenticated
  USING (
    course_id IN (SELECT id FROM public.courses WHERE teacher_id = auth.uid())
  );

  CREATE POLICY "course_enrollments_delete" ON public.course_enrollments
  FOR DELETE TO authenticated
  USING (
    course_id IN (SELECT id FROM public.courses WHERE teacher_id = auth.uid())
  );

COMMIT;
*/
