import { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { ChevronRight, MessageSquareWarning, RefreshCw, ScanText, ShieldAlert } from "lucide-react";
import { useAppState } from "../../App";
import { Badge, Button, Panel, StatusBadge, useToast } from "../../components/ui";
import { formatDate } from "../../lib/utils";
import { useStudentNames } from "../../lib/useStudentNames";
import {
  extractErrorMessage,
  reviewService,
  type ReviewQueue,
  type ReviewQueueItem,
} from "../../services/api";

type TabKey = "ocr" | "trust" | "requests";

const TABS: { key: TabKey; label: string; icon: typeof ScanText; description: string }[] = [
  {
    key: "ocr",
    label: "OCR review",
    icon: ScanText,
    description: "OCR failed, finished with warnings, or read the handwriting with low confidence. Check the extracted text before grading.",
  },
  {
    key: "trust",
    label: "Low trust score",
    icon: ShieldAlert,
    description: "AI grade suggestions with low confidence or flagged by the AI for a teacher check. Not yet published.",
  },
  {
    key: "requests",
    label: "Student requests",
    icon: MessageSquareWarning,
    description: "Students who are not satisfied with a published grade and asked you to review it.",
  },
];

function isTab(value: string | null): value is TabKey {
  return value === "ocr" || value === "trust" || value === "requests";
}

const pct = (value: number | null) => (value === null ? "—" : `${Math.round(value * 100)}%`);

/** Status label for an OCR / grading status code, e.g. "ocr_completed_with_warnings" -> "Completed with warnings". */
function humanStatus(code: string | null) {
  if (!code) return "—";
  const text = code.replace(/^ocr_/, "").replace(/_/g, " ");
  return text.charAt(0).toUpperCase() + text.slice(1);
}

export function ReviewQueuePage() {
  const { courses, assignments } = useAppState();
  const navigate = useNavigate();
  const toast = useToast();
  const [params, setParams] = useSearchParams();
  const tab: TabKey = isTab(params.get("tab")) ? (params.get("tab") as TabKey) : "ocr";
  const [queue, setQueue] = useState<ReviewQueue | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  // Student names come from the course rosters (the queue only carries student ids).
  const names = useStudentNames(courses);

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      setQueue(await reviewService.getQueue());
    } catch (reason) {
      setError(extractErrorMessage(reason, "Could not load the review queue."));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);


  const counts: Record<TabKey, number> = {
    ocr: queue?.ocr.length ?? 0,
    trust: queue?.low_trust.length ?? 0,
    requests: queue?.student_requests.length ?? 0,
  };
  const rows = queue ? (tab === "ocr" ? queue.ocr : tab === "trust" ? queue.low_trust : queue.student_requests) : [];
  const activeTab = TABS.find((item) => item.key === tab)!;
  const assignmentById = useMemo(() => new Map(assignments.map((a) => [a.id, a])), [assignments]);

  const removeRequest = (requestId: string) =>
    setQueue((current) =>
      current
        ? { ...current, student_requests: current.student_requests.filter((i) => i.review_request?.id !== requestId) }
        : current
    );

  return (
    <>
      <div className="page-heading">
        <div>
          <div className="eyebrow">MANUAL REVIEW</div>
          <h1>Review queue</h1>
          <p className="page-subtitle">
            Everything that needs your judgement in one place: OCR problems, low-trust AI grades, and student review requests.
          </p>
        </div>
        <div className="heading-actions">
          <Button variant="secondary" disabled={loading} onClick={() => void load()}>
            <RefreshCw size={14} className={loading ? "spin" : undefined} />
            {loading ? "Checking…" : "Refresh"}
          </Button>
        </div>
      </div>

      <div className="review-summary">
        {TABS.map(({ key, label, icon: Icon }) => (
          <button
            key={key}
            type="button"
            className={`review-summary-card${tab === key ? " active" : ""}${counts[key] > 0 ? " has-items" : ""}`}
            onClick={() => setParams({ tab: key }, { replace: true })}
            aria-pressed={tab === key}
          >
            <span className="review-summary-icon"><Icon size={16} /></span>
            <span className="review-summary-copy">
              <small>{label}</small>
              <strong>{loading && !queue ? "…" : counts[key]}</strong>
            </span>
          </button>
        ))}
      </div>

      {error && <p role="alert" className="form-error">{error}</p>}
      {queue?.notes.map((note) => (
        <p key={note} className="review-note" role="status">{note}</p>
      ))}

      <Panel className="review-panel">
        <div className="section-heading">
          <div>
            <h2>{activeTab.label}</h2>
            <p>
              {activeTab.description}
              {queue && tab === "ocr" && ` Threshold: ${pct(queue.thresholds.ocr_confidence)} OCR confidence.`}
              {queue && tab === "trust" && ` Threshold: ${pct(queue.thresholds.trust_score)} AI confidence.`}
            </p>
          </div>
        </div>

        {loading && !queue ? (
          <p className="table-empty review-empty" role="status">Checking submissions…</p>
        ) : rows.length === 0 ? (
          <p className="table-empty review-empty">
            {error ? "The queue could not be loaded." : "Nothing needs review here right now."}
          </p>
        ) : (
          <div className="review-list">
            {rows.map((item) => {
              const assignment = assignmentById.get(item.assignment_id);
              return (
                <ReviewRow
                  key={`${item.category}-${item.submission_id}`}
                  item={item}
                  studentName={names[item.student_id]?.name ?? "Student"}
                  assignmentTitle={assignment?.title ?? "Assignment"}
                  totalMarks={item.max_score ?? assignment?.totalMarks ?? null}
                  onOpen={(path) => navigate(path)}
                  onResolved={(requestId, status) => {
                    removeRequest(requestId);
                    toast(status === "resolved" ? "Request marked as resolved." : "Request dismissed.", "success");
                  }}
                />
              );
            })}
          </div>
        )}
      </Panel>
    </>
  );
}

function ReviewRow({
  item,
  studentName,
  assignmentTitle,
  totalMarks,
  onOpen,
  onResolved,
}: {
  item: ReviewQueueItem;
  studentName: string;
  assignmentTitle: string;
  totalMarks: number | null;
  onOpen: (path: string) => void;
  onResolved: (requestId: string, status: "resolved" | "dismissed") => void;
}) {
  const [replying, setReplying] = useState(false);
  const [response, setResponse] = useState("");
  const [busy, setBusy] = useState<"resolved" | "dismissed" | null>(null);
  const [error, setError] = useState("");
  const request = item.review_request;
  const score = item.final_score ?? item.ai_score;

  const close = async (status: "resolved" | "dismissed") => {
    if (!request) return;
    setBusy(status);
    setError("");
    try {
      await reviewService.resolveRequest(request.id, status, response);
      onResolved(request.id, status);
    } catch (reason) {
      setError(extractErrorMessage(reason, "Could not update the request."));
      setBusy(null);
    }
  };

  return (
    <article className={`review-row review-row-${item.category}`}>
      <div className="review-row-main">
        <div className="review-row-title">
          <strong>{studentName}</strong>
          <span>{assignmentTitle}</span>
        </div>
        <div className="review-row-meta">
          {item.category === "ocr" && (
            <>
              <StatusBadge status={humanStatus(item.submission_status)} />
              <Badge tone={item.ocr_confidence === null ? "neutral" : "gold"}>OCR {pct(item.ocr_confidence)}</Badge>
            </>
          )}
          {item.category === "low_trust" && (
            <>
              <Badge tone="gold">Trust {pct(item.trust_score)}</Badge>
              {item.ocr_confidence !== null && <Badge tone="neutral">OCR {pct(item.ocr_confidence)}</Badge>}
              {score !== null && <Badge tone="neutral">AI score {score}{totalMarks !== null ? ` / ${totalMarks}` : ""}</Badge>}
            </>
          )}
          {item.category === "student_request" && (
            <>
              {score !== null && <Badge tone="sage">Published {score}{totalMarks !== null ? ` / ${totalMarks}` : ""}</Badge>}
              {request && <span className="review-row-date">Requested {formatDate(request.created_at)}</span>}
            </>
          )}
          <span className="review-row-date">Submitted {formatDate(item.submitted_at)}</span>
        </div>

        {item.category === "student_request" ? (
          <blockquote className="review-reason">{request?.reason ?? item.reasons[0]}</blockquote>
        ) : (
          <ul className="review-reasons">
            {item.reasons.map((reason) => (
              <li key={reason}>{reason}</li>
            ))}
          </ul>
        )}

        {item.category === "student_request" && replying && (
          <div className="review-reply">
            <label htmlFor={`reply-${request?.id}`}>Reply to the student (optional)</label>
            <textarea
              id={`reply-${request?.id}`}
              className="field-textarea"
              maxLength={2000}
              value={response}
              onChange={(event) => setResponse(event.target.value)}
              placeholder="e.g. Re-checked Q2 and added 1 mark. The updated grade is published."
            />
            <div className="review-reply-actions">
              <Button size="sm" disabled={busy !== null} onClick={() => void close("resolved")}>
                {busy === "resolved" ? "Saving…" : "Mark resolved"}
              </Button>
              <Button size="sm" variant="secondary" disabled={busy !== null} onClick={() => void close("dismissed")}>
                {busy === "dismissed" ? "Saving…" : "Dismiss"}
              </Button>
              <Button size="sm" variant="quiet" disabled={busy !== null} onClick={() => setReplying(false)}>
                Cancel
              </Button>
            </div>
            {error && <p role="alert" className="form-error">{error}</p>}
          </div>
        )}
      </div>

      <div className="review-row-actions">
        {item.category === "ocr" && (
          <>
            <Button size="sm" onClick={() => onOpen(`/app/ocr/${item.submission_id}`)}>
              Check OCR <ChevronRight size={13} />
            </Button>
            <button className="text-button" onClick={() => onOpen(`/app/grading/${item.submission_id}`)}>
              Grade manually
            </button>
          </>
        )}
        {item.category === "low_trust" && (
          <Button size="sm" onClick={() => onOpen(`/app/grading/${item.submission_id}`)}>
            Review grade <ChevronRight size={13} />
          </Button>
        )}
        {item.category === "student_request" && (
          <>
            <Button size="sm" onClick={() => onOpen(`/app/grading/${item.submission_id}`)}>
              Re-grade <ChevronRight size={13} />
            </Button>
            {!replying && (
              <button className="text-button" onClick={() => setReplying(true)}>
                Respond
              </button>
            )}
          </>
        )}
      </div>
    </article>
  );
}
