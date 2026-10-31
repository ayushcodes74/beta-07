-- ============================================================================
-- TrustGrade — Phase 2A.6: Supabase RLS Remediation Migration (Hardened)
-- ============================================================================
-- Notice: REVIEWED MIGRATION PROPOSAL — NOT EXECUTED AGAINST PRODUCTION.
--
-- Objectives:
-- 1. Eliminate infinite recursion (42P17) between courses and course_enrollments
--    using SECURITY DEFINER helper functions isolated in a non-exposed schema (private).
-- 2. Provide a course-scoped, least-privilege RPC in public schema for teachers
--    to validate prospective student accounts without student enumeration or profile leakage.
-- 3. Protect all SECURITY DEFINER functions with SET search_path = '' and fully qualified
--    schema references.
-- 4. Guard against unknown/unexpected policies using a strict preflight policy inventory check.
-- 5. Detect existing full UNIQUE (course_id, student_id) constraint to avoid creating
--    redundant indexes while preserving the single-row mutable enrollment lifecycle.
-- 6. Provide verified non-recursive application rollback and legacy restoration procedures.
--
-- Target Database: PostgreSQL 15+ / Supabase
-- Target Schemas: public, private
-- ============================================================================

-- ============================================================================
-- PREFLIGHT AUDIT & INVENTORY (Read-Only Diagnostics to Run Before Migration)
-- ============================================================================
-- Execute these queries before running the migration to inspect current database state:
/*
-- 1. Inspect existing RLS policies on courses and course_enrollments:
SELECT schemaname, tablename, policyname, cmd, roles, qual, with_check
FROM pg_policies
WHERE schemaname = 'public'
  AND tablename IN ('courses', 'course_enrollments')
ORDER BY tablename, policyname;

-- 2. Inspect existing constraints on course_enrollments:
SELECT
  c.conname AS constraint_name,
  c.contype AS constraint_type,
  pg_get_constraintdef(c.oid) AS definition
FROM pg_constraint c
WHERE c.conrelid = 'public.course_enrollments'::regclass
ORDER BY c.conname;

-- 3. Check for duplicate active enrollments (blocks migration if count > 0):
SELECT course_id, student_id, COUNT(*) AS active_count
FROM public.course_enrollments
WHERE status = 'active'
GROUP BY course_id, student_id
HAVING COUNT(*) > 1;

-- 4. Verify PostgREST exposed schemas (private MUST NOT be present):
SHOW pgrst.db_schemas;
*/


-- ============================================================================
-- TRANSACTIONAL MIGRATION
-- ============================================================================
BEGIN;

-- ----------------------------------------------------------------------------
-- STEP 0.1: Pre-migration Consistency & Duplication Assertion
-- ----------------------------------------------------------------------------
-- The migration aborts immediately if duplicate active enrollments exist.
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
    RAISE EXCEPTION 'Migration aborted: % duplicate active enrollment pairs found in public.course_enrollments. Reconcile historical data before applying migration.', dup_count;
  END IF;
END $$;


-- ----------------------------------------------------------------------------
-- STEP 0.2: Policy Inventory Guard (Blocks on Unexpected Policies)
-- ----------------------------------------------------------------------------
-- Prevents silently leaving unexpected or overly permissive policies active.
DO $$
DECLARE
  rec RECORD;
  known_policies TEXT[] := ARRAY[
    -- Recognized public.courses legacy and remediation policy names
    'courses_select', 'courses_insert', 'courses_update', 'courses_delete',
    'courses_owner_select', 'courses_student_select', 'courses_policy',
    'courses_select_policy', 'courses_insert_policy', 'courses_update_policy', 'courses_delete_policy',
    -- Recognized public.course_enrollments legacy and remediation policy names
    'course_enrollments_select', 'course_enrollments_insert', 'course_enrollments_update', 'course_enrollments_delete',
    'course_enrollments_policy', 'course_enrollments_select_policy', 'course_enrollments_insert_policy',
    'course_enrollments_update_policy', 'course_enrollments_delete_policy'
  ];
BEGIN
  FOR rec IN
    SELECT schemaname, tablename, policyname
    FROM pg_policies
    WHERE schemaname = 'public'
      AND tablename IN ('courses', 'course_enrollments')
  LOOP
    IF NOT (rec.policyname = ANY(known_policies)) THEN
      RAISE EXCEPTION 'Migration blocked: Unexpected policy "%" detected on table "public.%". Inspect and manually reconcile unexpected policies before running this migration.', rec.policyname, rec.tablename;
    END IF;
  END LOOP;
END $$;


-- ----------------------------------------------------------------------------
-- STEP 1: Private Schema Setup & Isolated SECURITY DEFINER Helper Functions
-- ----------------------------------------------------------------------------
-- PostgREST exposes schemas listed in pgrst.db_schemas (typically 'public').
-- Placing internal Boolean access helpers in schema 'private' prevents them
-- from being invoked directly via the public Supabase RPC HTTP API.

CREATE SCHEMA IF NOT EXISTS private;

-- Lock down private schema permissions:
-- Revoke all permissions from PUBLIC and anonymous users.
-- Grant USAGE to authenticated role so that RLS policies can resolve function calls.
REVOKE ALL ON SCHEMA private FROM PUBLIC;
REVOKE ALL ON SCHEMA private FROM anon;
GRANT USAGE ON SCHEMA private TO authenticated;


-- Helper Function 1: Check course ownership (isolated in private schema)
-- Derives identity strictly from auth.uid(); accepts zero client user IDs.
CREATE OR REPLACE FUNCTION private.is_course_owner(check_course_id UUID)
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

COMMENT ON FUNCTION private.is_course_owner(UUID) IS
  'TrustGrade Phase 2A: Non-recursive security-definer check for course ownership (isolated in private schema).';

REVOKE ALL ON FUNCTION private.is_course_owner(UUID) FROM PUBLIC;
REVOKE ALL ON FUNCTION private.is_course_owner(UUID) FROM anon;
GRANT EXECUTE ON FUNCTION private.is_course_owner(UUID) TO authenticated;


-- Helper Function 2: Check active student enrollment (isolated in private schema)
-- Derives identity strictly from auth.uid(); accepts zero client user IDs.
CREATE OR REPLACE FUNCTION private.is_enrolled_student(check_course_id UUID)
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

COMMENT ON FUNCTION private.is_enrolled_student(UUID) IS
  'TrustGrade Phase 2A: Non-recursive security-definer check for active student course enrollment (isolated in private schema).';

REVOKE ALL ON FUNCTION private.is_enrolled_student(UUID) FROM PUBLIC;
REVOKE ALL ON FUNCTION private.is_enrolled_student(UUID) FROM anon;
GRANT EXECUTE ON FUNCTION private.is_enrolled_student(UUID) TO authenticated;


-- Remove legacy helper functions from public schema if they exist
DROP FUNCTION IF EXISTS public.is_course_owner(UUID);
DROP FUNCTION IF EXISTS public.is_enrolled_student(UUID);


-- ----------------------------------------------------------------------------
-- STEP 2: Replace Recursive RLS Policies on public.courses
-- ----------------------------------------------------------------------------
-- Ensure RLS is active. In Supabase, end-users connect as 'authenticated' or 'anon'
-- which are non-owners, so standard ENABLE ROW LEVEL SECURITY applies full RLS.
-- (FORCE ROW LEVEL SECURITY is optional; if enabled, it applies policies to table
-- owners as well, which can break maintenance scripts running under owner roles).
ALTER TABLE public.courses ENABLE ROW LEVEL SECURITY;

-- Drop recognized existing/legacy policies
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

-- SELECT Policy: Owning teacher OR actively enrolled student
CREATE POLICY "courses_select_policy" ON public.courses
FOR SELECT TO authenticated
USING (
  teacher_id = auth.uid()
  OR
  private.is_enrolled_student(id)
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

-- Drop recognized existing/legacy policies
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
  private.is_course_owner(course_id)
);

-- INSERT Policy: Course-owning teacher enrolls a student
CREATE POLICY "course_enrollments_insert_policy" ON public.course_enrollments
FOR INSERT TO authenticated
WITH CHECK (
  private.is_course_owner(course_id)
);

-- UPDATE Policy: Course-owning teacher modifies enrollment (e.g., status changes)
CREATE POLICY "course_enrollments_update_policy" ON public.course_enrollments
FOR UPDATE TO authenticated
USING (
  private.is_course_owner(course_id)
)
WITH CHECK (
  private.is_course_owner(course_id)
);

-- DELETE Policy: Course-owning teacher deletes enrollment
CREATE POLICY "course_enrollments_delete_policy" ON public.course_enrollments
FOR DELETE TO authenticated
USING (
  private.is_course_owner(course_id)
);


-- ----------------------------------------------------------------------------
-- STEP 4: Course-Scoped Student Profile Validation RPC (Public Schema)
-- ----------------------------------------------------------------------------
-- Must remain in 'public' schema so that PostgREST can route the backend client
-- RPC call: client.rpc("validate_student_enrollment_target", {...}).
-- Security gates:
--   1. Caller must be authenticated (auth.uid() IS NOT NULL).
--   2. Caller must have an active teacher profile.
--   3. Caller must own target_course_id (anti-enumeration check).
--   4. Target student profile must exist.
--   5. Target account must have role 'student'.
--   6. Target account must not be disabled.
-- Returns strictly minimal public fields (id, role, is_disabled, display_name).

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
REVOKE ALL ON FUNCTION public.validate_student_enrollment_target(UUID, UUID) FROM anon;
GRANT EXECUTE ON FUNCTION public.validate_student_enrollment_target(UUID, UUID) TO authenticated;


-- ----------------------------------------------------------------------------
-- STEP 5: Constraint-Aware Enrollment Concurrency Protection
-- ----------------------------------------------------------------------------
-- Data Model & Constraint Note:
-- The TrustGrade enrollment model maintains at most ONE row per student per course
-- (soft deactivation updates status = 'inactive', and re-enrollment reactivates
-- status = 'active' in-place).
--
-- Logic:
-- 1. Check if public.course_enrollments already has a table-level UNIQUE constraint
--    covering (course_id, student_id).
-- 2. If the full constraint exists, active uniqueness is already strictly enforced
--    across all rows. Do NOT create a redundant partial unique index.
-- 3. If the full constraint is absent, create the partial unique index
--    idx_course_enrollments_unique_active to prevent concurrent duplicate active rows.

DO $$
DECLARE
  has_full_constraint BOOLEAN;
BEGIN
  SELECT EXISTS (
    SELECT 1
    FROM pg_constraint c
    WHERE c.conrelid = 'public.course_enrollments'::regclass
      AND c.contype = 'u'
      AND (
        SELECT array_agg(a.attname::text)
        FROM pg_attribute a
        WHERE a.attrelid = c.conrelid
          AND a.attnum = ANY(c.conkey)
      ) <@ ARRAY['course_id', 'student_id']
      AND array_length(c.conkey, 1) = 2
  ) INTO has_full_constraint;

  IF has_full_constraint THEN
    RAISE NOTICE 'Full UNIQUE (course_id, student_id) constraint detected on public.course_enrollments. Skipping partial unique index creation (redundant).';
  ELSE
    RAISE NOTICE 'Full UNIQUE constraint not found on public.course_enrollments. Creating partial unique index idx_course_enrollments_unique_active.';
    EXECUTE 'CREATE UNIQUE INDEX IF NOT EXISTS idx_course_enrollments_unique_active ON public.course_enrollments (course_id, student_id) WHERE (status = ''active'')';
  END IF;
END $$;

COMMIT;


-- ============================================================================
-- POST-MIGRATION VERIFICATION QUERIES (Read-Only Diagnostics)
-- ============================================================================
-- Execute following successful migration to verify security posture:
/*
-- 1. Verify function schemas, ownership, SECURITY DEFINER status, and search_path:
SELECT
  n.nspname AS schema_name,
  p.proname AS function_name,
  pg_get_userbyid(p.proowner) AS owner_name,
  p.prosecdef AS is_security_definer,
  p.proconfig AS search_path_config
FROM pg_proc p
JOIN pg_namespace n ON p.pronamespace = n.oid
WHERE (n.nspname = 'private' AND p.proname IN ('is_course_owner', 'is_enrolled_student'))
   OR (n.nspname = 'public' AND p.proname = 'validate_student_enrollment_target')
ORDER BY n.nspname, p.proname;

-- 2. Verify routine privileges (PUBLIC and anon MUST be revoked):
SELECT
  specific_schema,
  routine_name,
  grantee,
  privilege_type
FROM information_schema.routine_privileges
WHERE specific_schema IN ('public', 'private')
  AND routine_name IN ('is_course_owner', 'is_enrolled_student', 'validate_student_enrollment_target')
ORDER BY specific_schema, routine_name, grantee;

-- 3. Verify exactly the intended policy set is active:
SELECT tablename, policyname, cmd, roles, qual, with_check
FROM pg_policies
WHERE schemaname = 'public'
  AND tablename IN ('courses', 'course_enrollments')
ORDER BY tablename, policyname;

-- 4. Verify uniqueness enforcement on course_enrollments:
SELECT
  i.relname AS index_name,
  ix.indisunique AS is_unique,
  pg_get_expr(ix.indpred, ix.indrelid) AS partial_predicate
FROM pg_class t
JOIN pg_index ix ON t.oid = ix.indrelid
JOIN pg_class i ON i.oid = ix.indexrelid
JOIN pg_namespace n ON t.relnamespace = n.oid
WHERE n.nspname = 'public'
  AND t.relname = 'course_enrollments'
  AND ix.indisunique = TRUE;
*/


-- ============================================================================
-- ROLLBACK PROCEDURES
-- ============================================================================

-- ----------------------------------------------------------------------------
-- PROCEDURE A: SAFE NON-RECURSIVE APPLICATION ROLLBACK (RECOMMENDED)
-- ----------------------------------------------------------------------------
-- Use this procedure if the migration must be rolled back without re-introducing
-- PostgreSQL infinite recursion error 42P17.
-- Replaces remediated policies with simple, non-circular teacher-isolated policies.
-- Does NOT leave tables unmanaged.
/*
BEGIN;
  -- 1. Drop partial unique index if it was created
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

  -- 4. Drop private helper functions and private schema
  DROP FUNCTION IF EXISTS private.is_enrolled_student(UUID);
  DROP FUNCTION IF EXISTS private.is_course_owner(UUID);
  -- Only drop private schema if no other objects reside in it
  DROP SCHEMA IF EXISTS private;

  -- 5. Establish safe non-recursive baseline policies
  -- Teachers manage their own courses; student course reads restricted during rollback
  CREATE POLICY "courses_select_rollback" ON public.courses
  FOR SELECT TO authenticated
  USING (teacher_id = auth.uid());

  CREATE POLICY "courses_insert_rollback" ON public.courses
  FOR INSERT TO authenticated
  WITH CHECK (teacher_id = auth.uid());

  CREATE POLICY "courses_update_rollback" ON public.courses
  FOR UPDATE TO authenticated
  USING (teacher_id = auth.uid());

  CREATE POLICY "courses_delete_rollback" ON public.courses
  FOR DELETE TO authenticated
  USING (teacher_id = auth.uid());

  -- Students read own enrollment; teachers access enrollments for their own courses
  CREATE POLICY "course_enrollments_select_rollback" ON public.course_enrollments
  FOR SELECT TO authenticated
  USING (student_id = auth.uid());

  CREATE POLICY "course_enrollments_insert_rollback" ON public.course_enrollments
  FOR INSERT TO authenticated
  WITH CHECK (student_id = auth.uid());

COMMIT;
*/


-- ----------------------------------------------------------------------------
-- PROCEDURE B: LEGACY BASELINE RESTORATION (HISTORICAL REVERT ONLY)
-- ----------------------------------------------------------------------------
-- CRITICAL WARNING: DO NOT USE IN PRODUCTION.
-- This procedure restores the original mutual subquery policies that trigger
-- PostgreSQL Error 42P17 (infinite recursion detected in policy for relation "courses").
-- Restoring this state will break Course Management API endpoints with HTTP 503 errors.
-- It is preserved strictly for historical rollback or testing baseline reproduction.
/*
BEGIN;
  -- 1. Drop partial unique index if it was created
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

  -- 4. Drop private helper functions and private schema
  DROP FUNCTION IF EXISTS private.is_enrolled_student(UUID);
  DROP FUNCTION IF EXISTS private.is_course_owner(UUID);
  DROP SCHEMA IF EXISTS private;

  -- 5. Restore original mutual subquery policies (RECURSIVE — CAUSES 42P17)
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
