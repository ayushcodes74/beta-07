import { useEffect, useRef, type Dispatch, type SetStateAction } from "react";
import { submissionService } from "../services/api";
import type { Submission } from "../types/models";

/** Backend statuses that change on their own while the OCR engine works on the file. */
const IN_FLIGHT = new Set(["ocr_queued", "ocr_processing"]);
const POLL_MS = 10_000;

/**
 * Keeps submission statuses in lists current.
 *
 * The backend only moves a submission on from "queued"/"processing" when that submission's own
 * status endpoint is asked (it checks the OCR engine then). The list endpoint just reads the stored
 * status, so without this a list kept showing "In Progress" long after OCR had finished. While any
 * loaded submission is in flight, ask each one's status every few seconds (which also stores the
 * new status) and reload the list once something has moved on. The list is also reloaded when the
 * tab regains focus, to pick up grades and new submissions made elsewhere.
 */
export function useSubmissionStatusSync(
  submissions: Submission[],
  setSubmissions: Dispatch<SetStateAction<Submission[]>>,
  enabled: boolean,
) {
  const inFlight = submissions.filter((item) => IN_FLIGHT.has(item.backendStatus ?? ""));
  const inFlightKey = inFlight.map((item) => `${item.id}:${item.backendStatus}`).join(",");
  const reloading = useRef(false);

  const reload = () => {
    if (reloading.current) return;
    reloading.current = true;
    submissionService
      .getSubmissions()
      .then(setSubmissions)
      .catch(() => undefined)
      .finally(() => {
        reloading.current = false;
      });
  };

  useEffect(() => {
    if (!enabled || !inFlightKey) return;
    const tracked = inFlightKey.split(",").map((entry) => entry.split(":") as [string, string]);
    let active = true;
    const timer = window.setInterval(() => {
      if (document.hidden) return; // don't poll a background tab
      void Promise.all(
        tracked.map(([id, status]) =>
          submissionService
            .getStatus(id)
            .then((fresh) => fresh.status !== status)
            .catch(() => false),
        ),
      ).then((changed) => {
        if (active && changed.some(Boolean)) reload();
      });
    }, POLL_MS);
    return () => {
      active = false;
      window.clearInterval(timer);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [inFlightKey, enabled]);

  useEffect(() => {
    if (!enabled) return;
    let last = Date.now();
    const onVisible = () => {
      // Throttled: switching tabs back and forth shouldn't refetch every time.
      if (document.hidden || Date.now() - last < 30_000) return;
      last = Date.now();
      reload();
    };
    document.addEventListener("visibilitychange", onVisible);
    return () => document.removeEventListener("visibilitychange", onVisible);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [enabled]);
}
