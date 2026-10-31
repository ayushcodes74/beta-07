import { useEffect, useRef, useState, type Dispatch, type SetStateAction } from "react";
import axios from "axios";
import { submissionService } from "../services/api";
import type { Submission } from "../types/models";

/**
 * Automatic AI answer checks for teachers.
 *
 * While a teacher is signed in, handed-in work is checked against the answer keys in the background as
 * soon as its OCR has finished, so the suggestion is ready when the teacher opens the submission.
 * Results are only suggestions (stored as pending review); nothing is ever published automatically.
 *
 * Runs in the teacher's session on purpose: grading reads answer keys and writes grading_results under
 * the teacher's own RLS permissions, so the student's upload cannot start it.
 *
 * Status freshness comes from useSubmissionStatusSync (moves submissions out of OCR states); this hook
 * reacts to the list and only adds a slow refresh to notice brand-new uploads.
 */

/** Submissions checked (or being checked) in this browser session; shared with the grading page. */
const claimed = new Set<string>();

/** Reserve a submission for an automatic check. False if one already ran or is running. */
export function claimAutoCheck(id: string): boolean {
  if (claimed.has(id)) return false;
  claimed.add(id);
  return true;
}

export function releaseAutoCheck(id: string) {
  claimed.delete(id);
}

const NEW_UPLOADS_REFRESH_MS = 120_000;
/** After the AI is rate limited or unavailable, stop trying for a while instead of burning quota. */
const PAUSE_MS = 10 * 60_000;
/** OCR not finished yet (useSubmissionStatusSync moves these on), or finished without usable text. */
const NOT_CHECKABLE = new Set(["submitted", "ocr_queued", "ocr_processing", "ocr_failed", "ocr_cancelled"]);

function needsCheck(submission: Submission): boolean {
  // "Graded" = an AI check (or teacher review) already exists in grading_results; "Published" = done.
  if (submission.state === "Graded" || submission.state === "Published") return false;
  if (submission.late?.status === "rejected") return false;
  return !NOT_CHECKABLE.has(submission.backendStatus ?? "submitted");
}

function errorInfo(error: unknown): { status?: number; code?: string } {
  if (!axios.isAxiosError(error)) return {};
  const detail = (error.response?.data as { detail?: { code?: string } } | undefined)?.detail;
  return { status: error.response?.status, code: typeof detail === "object" ? detail?.code : undefined };
}

export function useAutoAnswerChecks(
  enabled: boolean,
  submissions: Submission[],
  setSubmissions: Dispatch<SetStateAction<Submission[]>>
) {
  const running = useRef(false);
  const pausedUntil = useRef(0);
  const mounted = useRef(true);
  // Bumped after every attempt (and on refresh) so the next waiting submission is picked up even when
  // the attempt didn't change the list (e.g. it failed and stays claimed).
  const [tick, setTick] = useState(0);
  const pending = submissions.filter((item) => needsCheck(item) && !claimed.has(item.id));
  const pendingKey = pending.map((item) => item.id).join(",");

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);

  // Check one waiting submission at a time (each check is several LLM calls); the next one starts when
  // this attempt settles. Not cancelled by re-renders: a check in flight always finishes and is saved.
  useEffect(() => {
    if (!enabled || running.current || Date.now() < pausedUntil.current) return;
    const id = pendingKey.split(",")[0];
    if (!id || !claimAutoCheck(id)) return;
    running.current = true;
    submissionService
      .checkAnswers(id)
      .then(() => {
        if (!mounted.current) return;
        setSubmissions((list) =>
          list.map((item) => (item.id === id && item.state !== "Published" ? { ...item, state: "Graded" } : item))
        );
      })
      .catch((error: unknown) => {
        const { status, code } = errorInfo(error);
        if (code === "ocr_not_ready") {
          releaseAutoCheck(id); // retried when its status changes
        } else if (status === undefined || status === 429 || status === 502 || status === 503 || status === 504) {
          releaseAutoCheck(id); // AI busy/unavailable: retry after a pause
          pausedUntil.current = Date.now() + PAUSE_MS;
        }
        // Anything else (e.g. no readable OCR text) stays claimed; the grading page shows the reason.
      })
      .finally(() => {
        running.current = false;
        if (mounted.current) setTick((n) => n + 1);
      });
  }, [enabled, pendingKey, tick, setSubmissions]);

  // Notice uploads made while the teacher stays on one page (focus changes are handled elsewhere),
  // and resume after a pause.
  useEffect(() => {
    if (!enabled) return;
    const timer = window.setInterval(() => {
      if (document.hidden) return;
      submissionService
        .getSubmissions()
        .then(setSubmissions)
        .catch(() => undefined)
        .finally(() => setTick((n) => n + 1));
    }, NEW_UPLOADS_REFRESH_MS);
    return () => window.clearInterval(timer);
  }, [enabled, setSubmissions]);
}
