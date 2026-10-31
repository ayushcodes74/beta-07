import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { CalendarDays, Check, ChevronRight, Clock, Lock, RotateCcw, Search, X } from "lucide-react";
import { useAppState } from "../../App";
import { Badge, Button, Panel, useToast } from "../../components/ui";
import { IntegrationNotice } from "../../components/common/IntegrationNotice";
import { formatDate } from "../../lib/utils";
import { courseService, extractErrorMessage, lateAdjustedScore, submissionService } from "../../services/api";
import type { Assignment, LateDecision, Submission } from "../../types/models";

type Filter = "pending" | "accepted" | "rejected" | "all";

/** Marks-kept presets. The backend stores the deduction, i.e. 100 - kept. */
const PRESETS = [
  { key: "full", label: "Full marks", penalty: 0 },
  { key: "half", label: "Half marks", penalty: 50 },
  { key: "low", label: "Low marks (25%)", penalty: 75 },
  { key: "custom", label: "Custom", penalty: null },
] as const;
type PresetKey = (typeof PRESETS)[number]["key"];

function presetFor(penalty: number | null | undefined): PresetKey {
  return PRESETS.find((p) => p.penalty === (penalty ?? 0))?.key ?? "custom";
}

/** "2 days 3 hours late" from the due date and hand-in time. */
function lateness(dueAt: string | undefined, submittedAt: string): string {
  if (!dueAt) return "Late";
  const ms = Date.parse(submittedAt) - Date.parse(dueAt);
  if (!Number.isFinite(ms) || ms <= 0) return "Late";
  const minutes = Math.floor(ms / 60_000);
  const days = Math.floor(minutes / 1440);
  const hours = Math.floor((minutes % 1440) / 60);
  const parts = [
    days ? `${days} day${days === 1 ? "" : "s"}` : "",
    hours ? `${hours} hour${hours === 1 ? "" : "s"}` : "",
    !days && !hours ? `${Math.max(1, minutes)} min` : "",
  ].filter(Boolean);
  return `${parts.join(" ")} late`;
}

function DecisionBadge({ submission }: { submission: Submission }) {
  const late = submission.late;
  if (!late) return null;
  if (late.status === "pending") return <Badge tone="gold"><span className="badge-dot" />Awaiting decision</Badge>;
  if (late.status === "rejected") return <Badge tone="rose"><span className="badge-dot" />Rejected</Badge>;
  return (
    <Badge tone="sage">
      <span className="badge-dot" />
      {late.penaltyPercent ? `Accepted · −${late.penaltyPercent}%` : "Accepted · full marks"}
    </Badge>
  );
}

function LateSubmissionCard({
  submission,
  assignment,
  studentName,
  courseCode,
  onDecided,
}: {
  submission: Submission;
  assignment?: Assignment;
  studentName: string;
  courseCode?: string;
  onDecided: (updated: Submission) => void;
}) {
  const toast = useToast();
  const navigate = useNavigate();
  const late = submission.late!;
  const published = submission.backendStatus === "published";
  const [editing, setEditing] = useState(late.status === "pending");
  const [preset, setPreset] = useState<PresetKey>(presetFor(late.penaltyPercent));
  const [customPenalty, setCustomPenalty] = useState(String(late.penaltyPercent ?? 30));
  const [note, setNote] = useState(late.note ?? "");
  const [busy, setBusy] = useState(false);

  const penalty = preset === "custom" ? Number(customPenalty) : PRESETS.find((p) => p.key === preset)!.penalty!;
  const penaltyValid = Number.isFinite(penalty) && penalty >= 0 && penalty <= 100;
  const maxMarks = assignment?.totalMarks;

  const decide = async (decision: LateDecision) => {
    if (decision === "accepted" && !penaltyValid) {
      toast("Enter a deduction between 0 and 100%.", "info");
      return;
    }
    setBusy(true);
    try {
      const updated = await submissionService.decideLateSubmission(
        submission.id,
        decision,
        decision === "accepted" ? penalty : 0,
        note.trim()
      );
      onDecided(updated);
      setEditing(decision === "pending");
      toast(
        decision === "accepted"
          ? penalty
            ? `Accepted with a ${penalty}% deduction. It's applied when you publish the grade.`
            : "Accepted for full marks."
          : decision === "rejected"
          ? "Late submission rejected."
          : "Decision undone; the submission is awaiting a decision again."
      );
    } catch (err) {
      toast(extractErrorMessage(err, "Could not save the decision."), "info");
    } finally {
      setBusy(false);
    }
  };

  return (
    <Panel className="late-card">
      <div className="late-card-head">
        <span className="course-icon">
          <Clock size={17} />
        </span>
        <div className="late-card-main">
          <strong>{studentName}</strong>
          <small>
            {courseCode ? `${courseCode} · ` : ""}
            {assignment?.title ?? "Assignment"}
            {maxMarks ? ` · ${maxMarks} marks` : ""}
          </small>
        </div>
        <div className="late-card-times">
          <span>
            <CalendarDays size={12} /> Due {assignment ? formatDate(assignment.dueAt) : "—"}
          </span>
          <span>
            <Clock size={12} /> Handed in {formatDate(submission.submittedAt)}
          </span>
        </div>
        <Badge tone="rose">{lateness(assignment?.dueAt, submission.submittedAt)}</Badge>
        <DecisionBadge submission={submission} />
      </div>

      {published ? (
        <p className="late-card-locked">
          <Lock size={12} /> A grade has been published for this submission, so the decision is locked.
          {late.note ? ` Note: “${late.note}”` : ""}
        </p>
      ) : editing ? (
        <div className="late-card-decision">
          <div className="field-block">
            <label>If accepted, the student can earn</label>
            <div className="difficulty-options">
              {PRESETS.map((item) => (
                <button
                  key={item.key}
                  type="button"
                  className={preset === item.key ? "active" : ""}
                  onClick={() => setPreset(item.key)}
                  disabled={busy}
                >
                  {item.label}
                </button>
              ))}
            </div>
            {preset === "custom" && (
              <label className="late-custom-penalty">
                Deduct
                <input
                  className="field-input"
                  type="number"
                  min={0}
                  max={100}
                  step={5}
                  value={customPenalty}
                  onChange={(event) => setCustomPenalty(event.target.value)}
                  aria-label="Deduction percentage"
                />
                % of the marks
              </label>
            )}
            <small className="late-preview">
              {penaltyValid
                ? penalty === 0
                  ? "No deduction: graded like an on-time submission."
                  : `−${penalty}% of the final score` +
                    (maxMarks ? ` (e.g. full marks ${maxMarks} → ${lateAdjustedScore(maxMarks, penalty)}).` : ".")
                : "Enter a deduction between 0 and 100%."}
            </small>
          </div>
          <div className="field-block">
            <label htmlFor={`late-note-${submission.id}`}>Note to the student (optional)</label>
            <textarea
              id={`late-note-${submission.id}`}
              className="field-textarea late-decision-note"
              value={note}
              maxLength={2000}
              onChange={(event) => setNote(event.target.value)}
              placeholder="e.g. Extension granted for illness / Submitted a week after the deadline."
            />
          </div>
          <div className="late-card-actions">
            <Button variant="secondary" size="sm" disabled={busy} onClick={() => void decide("rejected")}>
              <X size={13} />
              Reject submission
            </Button>
            <Button size="sm" disabled={busy || !penaltyValid} onClick={() => void decide("accepted")}>
              <Check size={13} />
              {penalty ? `Accept with −${penaltyValid ? penalty : "?"}%` : "Accept for full marks"}
            </Button>
            {late.status !== "pending" && (
              <Button variant="secondary" size="sm" disabled={busy} onClick={() => setEditing(false)}>
                Cancel
              </Button>
            )}
          </div>
        </div>
      ) : (
        <div className="late-card-summary">
          <p>
            {late.status === "rejected"
              ? "Not accepted. No grade can be published unless you change this decision."
              : late.penaltyPercent
              ? `Accepted. ${late.penaltyPercent}% will be deducted from the final score when you publish the grade.`
              : "Accepted for full marks."}
            {late.note ? ` Note to student: “${late.note}”` : ""}
            {late.decidedAt ? ` · Decided ${formatDate(late.decidedAt)}` : ""}
          </p>
          <div className="late-card-actions">
            <Button variant="secondary" size="sm" disabled={busy} onClick={() => void decide("pending")}>
              <RotateCcw size={13} />
              Undo
            </Button>
            <Button variant="secondary" size="sm" disabled={busy} onClick={() => setEditing(true)}>
              Change decision
            </Button>
          </div>
        </div>
      )}

      <div className="late-card-footer">
        <button
          className="text-button"
          onClick={() => navigate(`/app/grading/${submission.id}`)}
          disabled={late.status === "rejected"}
          title={late.status === "rejected" ? "Rejected submissions are not graded." : undefined}
        >
          {late.status === "pending" ? "Open submission" : "Review & grade"}
          <ChevronRight size={13} />
        </button>
      </div>
    </Panel>
  );
}

export function LateSubmissionsPage() {
  const { assignments, courses, submissions, setSubmissions } = useAppState();
  const [filter, setFilter] = useState<Filter>("pending");
  const [query, setQuery] = useState("");
  const [names, setNames] = useState<Record<string, string>>({});

  const lateRows = useMemo(
    () =>
      submissions
        .filter((item) => item.late)
        .sort((a, b) => Date.parse(b.submittedAt) - Date.parse(a.submittedAt)),
    [submissions]
  );
  const assignmentById = useMemo(() => new Map(assignments.map((a) => [a.id, a])), [assignments]);

  // Student names come from the rosters of the courses that have late work (best-effort).
  useEffect(() => {
    const courseIds = [
      ...new Set(lateRows.map((row) => assignmentById.get(row.assignmentId)?.courseId).filter(Boolean)),
    ] as string[];
    if (!courseIds.length) return;
    let cancelled = false;
    void Promise.all(courseIds.map((id) => courseService.getStudents(id).catch(() => []))).then((rosters) => {
      if (cancelled) return;
      const found: Record<string, string> = {};
      for (const student of rosters.flat()) {
        found[student.student_id] = student.name || student.email || "Student";
      }
      setNames(found);
    });
    return () => {
      cancelled = true;
    };
  }, [lateRows, assignmentById]);

  const counts = {
    pending: lateRows.filter((r) => r.late?.status === "pending").length,
    accepted: lateRows.filter((r) => r.late?.status === "accepted").length,
    rejected: lateRows.filter((r) => r.late?.status === "rejected").length,
    all: lateRows.length,
  };

  const visible = lateRows.filter((row) => {
    if (filter !== "all" && row.late?.status !== filter) return false;
    const text = `${names[row.studentId] ?? ""} ${assignmentById.get(row.assignmentId)?.title ?? ""}`;
    return text.toLowerCase().includes(query.trim().toLowerCase());
  });

  const onDecided = (updated: Submission) =>
    setSubmissions((current) =>
      current.map((item) => (item.id === updated.id ? { ...item, late: updated.late } : item))
    );

  return (
    <>
      <div className="page-heading">
        <div>
          <div className="eyebrow">REVIEW · LATE SUBMISSIONS</div>
          <h1>Belated submissions</h1>
          <p className="page-subtitle">
            Work handed in after the due date waits here for your decision: accept it for full marks, accept it with
            reduced marks, or reject it.
          </p>
        </div>
      </div>

      <IntegrationNotice
        title="How decisions affect grades"
        description={
          "Late work is flagged automatically by the time it was handed in. A deduction is applied to the score you " +
          "enter when you publish the grade, and the student sees both. Rejected work can't be graded, and a decision " +
          "is locked once its grade is published."
        }
      />

      <div className="toolbar">
        <div className="segmented">
          {(
            [
              ["pending", "Awaiting decision"],
              ["accepted", "Accepted"],
              ["rejected", "Rejected"],
              ["all", "All"],
            ] as [Filter, string][]
          ).map(([key, label]) => (
            <button
              key={key}
              className={filter === key ? "segment active" : "segment"}
              onClick={() => setFilter(key)}
            >
              {label} ({counts[key]})
            </button>
          ))}
        </div>
        <label className="inline-search">
          <Search size={14} />
          <input
            placeholder="Find a student or assignment..."
            value={query}
            onChange={(event) => setQuery(event.target.value)}
          />
        </label>
      </div>

      <div className="assignment-list">
        {visible.length ? (
          visible.map((row) => {
            const assignment = assignmentById.get(row.assignmentId);
            return (
              <LateSubmissionCard
                key={row.id}
                submission={row}
                assignment={assignment}
                studentName={names[row.studentId] ?? "Student"}
                courseCode={courses.find((c) => c.id === assignment?.courseId)?.code}
                onDecided={onDecided}
              />
            );
          })
        ) : (
          <Panel className="empty-state" style={{ padding: "3rem 1.5rem", textAlign: "center", color: "#5C6E61" }}>
            {lateRows.length
              ? "Nothing in this view."
              : "No late submissions. Work handed in after an assignment's due date will appear here."}
          </Panel>
        )}
      </div>
    </>
  );
}
