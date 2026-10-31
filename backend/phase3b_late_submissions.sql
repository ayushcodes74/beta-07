-- ============================================================================
-- TrustGrade: belated (late) submissions - teacher accept / reject / reduced marks
-- ============================================================================
-- Run once in the Supabase SQL Editor (one transaction; nothing changes on error).
--
-- A submission handed in after the assignment's due_at is flagged late_status = 'pending'.
-- The owning teacher then decides:
--   accepted  -> graded normally, with late_penalty_percent (0-100) deducted from the final
--                score when the grade is published (0 = full marks, 50 = half marks, ...)
--   rejected  -> not accepted; no grade can be published unless the teacher changes the decision
--
-- Lateness is decided HERE, by a trigger, never by the client: students write their own
-- submission rows with their own JWT, so a client-supplied flag could be forged.
--   * INSERT: submitted_at := now(); late_status := 'pending' if now() > assignments.due_at
--   * student UPDATE: late_* columns are read-only. Changing submitted_at means "resubmission":
--     submitted_at := now() and lateness is re-evaluated (refused once the teacher has decided)
--   * owning-teacher UPDATE: may set late_status / late_penalty_percent / late_decision_note;
--     late_decided_by / late_decided_at are stamped by the trigger; submitted_at is read-only
-- Existing "Students update editable submissions" / "Teachers update submissions" policies still
-- decide WHICH rows a caller may update; this trigger only governs the late_* columns.
-- ============================================================================

BEGIN;

ALTER TABLE public.submissions
  ADD COLUMN IF NOT EXISTS submitted_at         timestamptz,
  ADD COLUMN IF NOT EXISTS late_status          text,
  ADD COLUMN IF NOT EXISTS late_penalty_percent numeric(5,2),
  ADD COLUMN IF NOT EXISTS late_decision_note   text,
  ADD COLUMN IF NOT EXISTS late_decided_by      uuid REFERENCES public.profiles(id) ON DELETE SET NULL,
  ADD COLUMN IF NOT EXISTS late_decided_at      timestamptz;

ALTER TABLE public.submissions DROP CONSTRAINT IF EXISTS submissions_late_status_check;
ALTER TABLE public.submissions ADD CONSTRAINT submissions_late_status_check
  CHECK (late_status IS NULL OR late_status IN ('pending', 'accepted', 'rejected'));

ALTER TABLE public.submissions DROP CONSTRAINT IF EXISTS submissions_late_penalty_check;
ALTER TABLE public.submissions ADD CONSTRAINT submissions_late_penalty_check
  CHECK (late_penalty_percent IS NULL OR (late_penalty_percent >= 0 AND late_penalty_percent <= 100));

ALTER TABLE public.submissions DROP CONSTRAINT IF EXISTS submissions_late_note_check;
ALTER TABLE public.submissions ADD CONSTRAINT submissions_late_note_check
  CHECK (late_decision_note IS NULL OR char_length(late_decision_note) <= 2000);

CREATE OR REPLACE FUNCTION public.submissions_late_guard()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
DECLARE
  v_due        timestamptz;
  v_teacher_id uuid;
  v_uid        uuid := auth.uid();
BEGIN
  SELECT a.due_at, a.teacher_id INTO v_due, v_teacher_id
  FROM public.assignments a WHERE a.id = NEW.assignment_id;

  IF TG_OP = 'INSERT' THEN
    NEW.submitted_at         := now();
    NEW.late_status          := CASE WHEN v_due IS NOT NULL AND now() > v_due THEN 'pending' END;
    NEW.late_penalty_percent := NULL;
    NEW.late_decision_note   := NULL;
    NEW.late_decided_by      := NULL;
    NEW.late_decided_at      := NULL;
    RETURN NEW;
  END IF;

  -- SQL editor / service role: no end-user identity, leave the row as written.
  IF v_uid IS NULL THEN
    RETURN NEW;
  END IF;

  -- ---- Owning teacher: records the decision; cannot alter when the work was handed in ----
  IF v_teacher_id = v_uid THEN
    NEW.submitted_at := OLD.submitted_at;
    IF NEW.late_status          IS DISTINCT FROM OLD.late_status
       OR NEW.late_penalty_percent IS DISTINCT FROM OLD.late_penalty_percent
       OR NEW.late_decision_note   IS DISTINCT FROM OLD.late_decision_note THEN
      IF OLD.late_status IS NULL THEN
        RAISE EXCEPTION 'not_late: only late submissions can receive a late decision'
          USING ERRCODE = 'check_violation';
      END IF;
      IF NEW.late_status IS NULL THEN
        RAISE EXCEPTION 'not_late: a late submission cannot be marked on time'
          USING ERRCODE = 'check_violation';
      END IF;
      IF NEW.late_status = 'pending' THEN
        NEW.late_penalty_percent := NULL;
        NEW.late_decision_note   := NULL;
        NEW.late_decided_by      := NULL;
        NEW.late_decided_at      := NULL;
      ELSE
        IF NEW.late_status = 'accepted' THEN
          NEW.late_penalty_percent := COALESCE(NEW.late_penalty_percent, 0);
        ELSE
          NEW.late_penalty_percent := NULL;
        END IF;
        NEW.late_decided_by := v_uid;
        NEW.late_decided_at := now();
      END IF;
    ELSE
      NEW.late_decided_by := OLD.late_decided_by;
      NEW.late_decided_at := OLD.late_decided_at;
    END IF;
    RETURN NEW;
  END IF;

  -- ---- Anyone else (the student): late_* columns are read-only ----
  NEW.late_status          := OLD.late_status;
  NEW.late_penalty_percent := OLD.late_penalty_percent;
  NEW.late_decision_note   := OLD.late_decision_note;
  NEW.late_decided_by      := OLD.late_decided_by;
  NEW.late_decided_at      := OLD.late_decided_at;

  IF NEW.submitted_at IS DISTINCT FROM OLD.submitted_at THEN
    -- Resubmission. Once the teacher has ruled on a late hand-in, it stays as judged.
    IF OLD.late_status IN ('accepted', 'rejected') THEN
      RAISE EXCEPTION 'late_decision_locked: your teacher has already decided on this late submission, so it can no longer be replaced'
        USING ERRCODE = 'check_violation';
    END IF;
    NEW.submitted_at         := now();
    NEW.late_status          := CASE WHEN v_due IS NOT NULL AND now() > v_due THEN 'pending' END;
    NEW.late_penalty_percent := NULL;
    NEW.late_decision_note   := NULL;
    NEW.late_decided_by      := NULL;
    NEW.late_decided_at      := NULL;
  END IF;
  RETURN NEW;
END;
$$;

REVOKE ALL ON FUNCTION public.submissions_late_guard() FROM PUBLIC;

DROP TRIGGER IF EXISTS submissions_late_guard ON public.submissions;
CREATE TRIGGER submissions_late_guard
BEFORE INSERT OR UPDATE ON public.submissions
FOR EACH ROW EXECUTE FUNCTION public.submissions_late_guard();

-- Backfill (runs with no end-user identity, so the trigger leaves these rows as written).
UPDATE public.submissions SET submitted_at = created_at WHERE submitted_at IS NULL;
UPDATE public.submissions s
SET late_status = 'pending'
FROM public.assignments a
WHERE a.id = s.assignment_id
  AND s.late_status IS NULL
  AND s.submitted_at > a.due_at
  AND s.status NOT IN ('graded', 'published');

-- ---- Self-test: querying as a signed-in user must not error ----
SET LOCAL ROLE authenticated;
SELECT set_config('request.jwt.claims',
  '{"sub":"00000000-0000-0000-0000-000000000000","role":"authenticated"}', true);
SELECT count(*) AS late_submissions_visible_to_test_user
FROM public.submissions WHERE late_status IS NOT NULL;
RESET ROLE;

COMMIT;

-- Rollback (not executed):
-- DROP TRIGGER IF EXISTS submissions_late_guard ON public.submissions;
-- DROP FUNCTION IF EXISTS public.submissions_late_guard();
-- ALTER TABLE public.submissions
--   DROP COLUMN IF EXISTS late_status, DROP COLUMN IF EXISTS late_penalty_percent,
--   DROP COLUMN IF EXISTS late_decision_note, DROP COLUMN IF EXISTS late_decided_by,
--   DROP COLUMN IF EXISTS late_decided_at;
