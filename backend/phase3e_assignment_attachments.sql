-- ============================================================================
-- TrustGrade: files attached to assignment questions (pictures / PDFs)
--   storage bucket "assignment-files" + public.assignment_attachments + RLS
-- ============================================================================
-- Run once in the Supabase SQL Editor (one transaction; nothing changes on error).
-- Requires phase2a_rls_recursion_fix.sql (private.is_active_enrolled_student).
--
-- A teacher attaches pictures or PDFs to individual questions (a diagram, a source text, a graph).
-- Students see them under the question on the submit page. The backend extracts each file's text with
-- the OCR pipeline and gives it to the AI as that question's material when checking answers.
--
-- Access, scoped strictly to the caller's own data:
--   teachers: upload / list / delete files of assignments THEY OWN (any status, incl. drafts)
--   students: view files of PUBLISHED assignments in courses they are ACTIVELY enrolled in
--   everyone else: nothing (the bucket is private; files are served through short-lived signed URLs)
--
-- Object path convention: '<assignment_id>/<random uuid>.<ext>' (first folder = assignment id).
-- No recursion: policies only call SECURITY DEFINER helpers, which never read assignment_attachments.
--
-- Used by backend/app/database/attachment_repository.py
-- ============================================================================

BEGIN;

-- ---- Helpers ---------------------------------------------------------------------------------

-- Caller is the active teacher who owns the assignment.
CREATE OR REPLACE FUNCTION private.owns_assignment(check_assignment_id UUID)
RETURNS BOOLEAN
LANGUAGE sql
SECURITY DEFINER
SET search_path = ''
STABLE
AS $$
  SELECT EXISTS (
    SELECT 1
    FROM public.assignments a
    JOIN public.profiles p ON p.id = a.teacher_id
    WHERE a.id = check_assignment_id
      AND a.teacher_id = auth.uid()
      AND p.role = 'teacher'
      AND p.is_disabled = false
  );
$$;

-- Caller may view the assignment's files: its owner, or an actively enrolled student once published.
CREATE OR REPLACE FUNCTION private.can_view_assignment_files(check_assignment_id UUID)
RETURNS BOOLEAN
LANGUAGE sql
SECURITY DEFINER
SET search_path = ''
STABLE
AS $$
  SELECT private.owns_assignment(check_assignment_id)
      OR EXISTS (
        SELECT 1
        FROM public.assignments a
        WHERE a.id = check_assignment_id
          AND a.status = 'published'
          AND a.course_id IS NOT NULL
          AND private.is_active_enrolled_student(a.course_id)
      );
$$;

-- Assignment id from an object path ('<assignment_id>/<file>'); NULL for anything else (never errors,
-- so a malformed path is simply denied instead of failing the policy).
CREATE OR REPLACE FUNCTION private.assignment_file_owner_id(object_name TEXT)
RETURNS UUID
LANGUAGE sql
IMMUTABLE
SET search_path = ''
AS $$
  SELECT CASE
    WHEN split_part(object_name, '/', 1) ~* '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
    THEN split_part(object_name, '/', 1)::uuid
  END;
$$;

REVOKE ALL ON FUNCTION private.owns_assignment(UUID) FROM PUBLIC, anon;
REVOKE ALL ON FUNCTION private.can_view_assignment_files(UUID) FROM PUBLIC, anon;
REVOKE ALL ON FUNCTION private.assignment_file_owner_id(TEXT) FROM PUBLIC, anon;
GRANT EXECUTE ON FUNCTION private.owns_assignment(UUID) TO authenticated;
GRANT EXECUTE ON FUNCTION private.can_view_assignment_files(UUID) TO authenticated;
GRANT EXECUTE ON FUNCTION private.assignment_file_owner_id(TEXT) TO authenticated;

-- ---- Attachment records ----------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS public.assignment_attachments (
  id                 uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  assignment_id      uuid NOT NULL REFERENCES public.assignments(id) ON DELETE CASCADE,
  question_number    int  NOT NULL CHECK (question_number BETWEEN 1 AND 200),
  storage_path       text NOT NULL UNIQUE,
  filename           text NOT NULL CHECK (char_length(filename) BETWEEN 1 AND 255),
  content_type       text NOT NULL CHECK (content_type IN ('application/pdf', 'image/png', 'image/jpeg', 'image/webp')),
  size_bytes         int  NOT NULL CHECK (size_bytes > 0 AND size_bytes <= 10485760),
  extraction_status  text NOT NULL DEFAULT 'pending'
                       CHECK (extraction_status IN ('pending', 'ready', 'no_text', 'failed')),
  extracted_text     text CHECK (extracted_text IS NULL OR char_length(extracted_text) <= 60000),
  extraction_error   text CHECK (extraction_error IS NULL OR char_length(extraction_error) <= 500),
  uploaded_by        uuid NOT NULL REFERENCES public.profiles(id),
  created_at         timestamptz NOT NULL DEFAULT now(),
  updated_at         timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS assignment_attachments_assignment_idx
  ON public.assignment_attachments (assignment_id, question_number, created_at);

ALTER TABLE public.assignment_attachments ENABLE ROW LEVEL SECURITY;

REVOKE ALL ON public.assignment_attachments FROM anon, authenticated;
GRANT SELECT, DELETE ON public.assignment_attachments TO authenticated;
GRANT INSERT (assignment_id, question_number, storage_path, filename, content_type, size_bytes, uploaded_by)
  ON public.assignment_attachments TO authenticated;
GRANT UPDATE (question_number, extraction_status, extracted_text, extraction_error, updated_at)
  ON public.assignment_attachments TO authenticated;

DROP POLICY IF EXISTS "Teachers manage own assignment attachments" ON public.assignment_attachments;
CREATE POLICY "Teachers manage own assignment attachments" ON public.assignment_attachments
FOR ALL TO authenticated
USING (private.owns_assignment(assignment_id))
WITH CHECK (private.owns_assignment(assignment_id) AND uploaded_by = (SELECT auth.uid()));

DROP POLICY IF EXISTS "Students read attachments of published assignments" ON public.assignment_attachments;
CREATE POLICY "Students read attachments of published assignments" ON public.assignment_attachments
FOR SELECT TO authenticated
USING (private.can_view_assignment_files(assignment_id));

-- ---- Storage bucket + object policies -----------------------------------------------------------

INSERT INTO storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
VALUES ('assignment-files', 'assignment-files', false, 10485760,
        ARRAY['application/pdf', 'image/png', 'image/jpeg', 'image/webp'])
ON CONFLICT (id) DO UPDATE
  SET public = false,
      file_size_limit = EXCLUDED.file_size_limit,
      allowed_mime_types = EXCLUDED.allowed_mime_types;

DROP POLICY IF EXISTS "Teachers upload assignment files" ON storage.objects;
CREATE POLICY "Teachers upload assignment files" ON storage.objects
FOR INSERT TO authenticated
WITH CHECK (
  bucket_id = 'assignment-files'
  AND private.owns_assignment(private.assignment_file_owner_id(name))
);

DROP POLICY IF EXISTS "Teachers delete assignment files" ON storage.objects;
CREATE POLICY "Teachers delete assignment files" ON storage.objects
FOR DELETE TO authenticated
USING (
  bucket_id = 'assignment-files'
  AND private.owns_assignment(private.assignment_file_owner_id(name))
);

-- Reading (and creating signed URLs, which requires read access) for the owner and enrolled students.
DROP POLICY IF EXISTS "Read assignment files" ON storage.objects;
CREATE POLICY "Read assignment files" ON storage.objects
FOR SELECT TO authenticated
USING (
  bucket_id = 'assignment-files'
  AND private.can_view_assignment_files(private.assignment_file_owner_id(name))
);

-- ---- Self-test: querying as a signed-in user must not error (e.g. no policy recursion) ----
SET LOCAL ROLE authenticated;
SELECT set_config('request.jwt.claims',
  '{"sub":"00000000-0000-0000-0000-000000000000","role":"authenticated"}', true);
SELECT count(*) AS attachments_visible_to_test_user FROM public.assignment_attachments;
SELECT count(*) AS files_visible_to_test_user FROM storage.objects WHERE bucket_id = 'assignment-files';
RESET ROLE;

COMMIT;

-- Rollback (not executed):
-- DROP POLICY IF EXISTS "Teachers upload assignment files" ON storage.objects;
-- DROP POLICY IF EXISTS "Teachers delete assignment files" ON storage.objects;
-- DROP POLICY IF EXISTS "Read assignment files" ON storage.objects;
-- DELETE FROM storage.objects WHERE bucket_id = 'assignment-files';  -- removes the stored files
-- DELETE FROM storage.buckets WHERE id = 'assignment-files';
-- DROP TABLE IF EXISTS public.assignment_attachments;
-- DROP FUNCTION IF EXISTS private.can_view_assignment_files(UUID);
-- DROP FUNCTION IF EXISTS private.owns_assignment(UUID);
-- DROP FUNCTION IF EXISTS private.assignment_file_owner_id(TEXT);
