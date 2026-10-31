import { useEffect, useRef, useState } from "react";
import { CheckCircle2, MessageSquareWarning, ShieldCheck } from "lucide-react";
import { useAppState } from "../../App";
import { Badge, Button, Panel, useToast } from "../../components/ui";
import { formatDate } from "../../lib/utils";
import { useStudentNames } from "../../lib/useStudentNames";
import { extractErrorMessage, reviewService, type ReviewRequest } from "../../services/api";
import type { QuestionResult, Submission } from "../../types/models";

const MIN_REASON = 10;

/** Student: flag a published grade for teacher review and follow the request's status. */
/** One question's mark and the reasons for it; students can ask for this question to be rechecked. */
function QuestionResultRow({
  result,
  onRecheck,
}: {
  result: QuestionResult;
  onRecheck?: () => void;
}) {
  const marks = result.awardedMarks;
  const verdict =
    marks === null ? "unmarked" : marks >= result.maxMarks ? "correct" : marks > 0 ? "partial" : "incorrect";
  return (
    <div className={`answer-check-question answer-check-${verdict}`}>
      <div className="answer-check-question-top">
        <strong>Question {result.number}</strong>
        <span>{marks === null ? `${result.maxMarks} marks` : `${marks} / ${result.maxMarks}`}</span>
      </div>
      {result.questionText && <p className="answer-check-question-text">{result.questionText}</p>}
      {result.teacherComment ? (
        <p>
          <strong>Teacher's note:</strong> {result.teacherComment}
        </p>
      ) : (
        result.explanation && <p>{result.explanation}</p>
      )}
      {result.strengths.length > 0 && <p className="result-question-good">✓ {result.strengths.join(" · ")}</p>}
      {result.areasForImprovement.length > 0 && (
        <p className="result-question-improve">To improve: {result.areasForImprovement.join(" · ")}</p>
      )}
      {result.expectedSolution && (
        <details className="result-question-solution">
          <summary>Show expected solution</summary>
          <p>{result.expectedSolution}</p>
        </details>
      )}
      {onRecheck && (
        <button type="button" className="result-question-recheck" onClick={onRecheck}>
          Ask for this question to be rechecked
        </button>
      )}
    </div>
  );
}

function ReviewRequestBox({
  submissionId,
  latest,
  onCreated,
  draft,
}: {
  submissionId: string;
  latest: ReviewRequest | undefined;
  onCreated: (request: ReviewRequest) => void;
  /** Opens the form pre-filled (e.g. "Question 2: "); ``nonce`` changes on every click. */
  draft?: { text: string; nonce: number };
}) {
  const toast = useToast();
  const [open, setOpen] = useState(false);
  const [reason, setReason] = useState("");
  const formRef = useRef<HTMLTextAreaElement | null>(null);

  useEffect(() => {
    if (!draft) return;
    setOpen(true);
    setReason((current) => (current.trim() ? current : draft.text));
    window.setTimeout(() => formRef.current?.focus(), 0);
  }, [draft?.nonce]);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  const submit = async () => {
    setSaving(true);
    setError("");
    try {
      onCreated(await reviewService.requestReview(submissionId, reason));
      setOpen(false);
      setReason("");
      toast("Recheck requested. Your teacher will take another look.", "success");
    } catch (failure) {
      setError(extractErrorMessage(failure, "Could not send the recheck request."));
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="result-review">
      {latest?.status === "open" ? (
        <div className="result-review-status">
          <Badge tone="gold"><MessageSquareWarning size={13} />Recheck requested</Badge>
          <span>Sent {formatDate(latest.created_at)} · waiting for your teacher.</span>
        </div>
      ) : (
        <>
          {latest && (
            <div>
              <div className="result-review-status">
                <Badge tone={latest.status === "resolved" ? "sage" : "neutral"}>
                  Recheck {latest.status === "resolved" ? "completed" : "closed"}
                </Badge>
                {latest.resolved_at && <span>{formatDate(latest.resolved_at)}</span>}
              </div>
              {latest.teacher_response && <p className="result-review-response">{latest.teacher_response}</p>}
            </div>
          )}
          {open ? (
            <div className="result-review-form">
              <label htmlFor={`review-reason-${submissionId}`}>Why should this be rechecked? Mention the question and what was missed.</label>
              <textarea
                ref={formRef}
                id={`review-reason-${submissionId}`}
                className="field-textarea"
                maxLength={2000}
                value={reason}
                onChange={(event) => setReason(event.target.value)}
                placeholder="e.g. Question 2: my answer on page 3 was not counted."
              />
              <div className="result-review-actions">
                <Button size="sm" disabled={saving || reason.trim().length < MIN_REASON} onClick={() => void submit()}>
                  {saving ? "Sending…" : "Submit recheck request"}
                </Button>
                <Button size="sm" variant="quiet" disabled={saving} onClick={() => setOpen(false)}>
                  Cancel
                </Button>
                {reason.trim().length < MIN_REASON && (
                  <span className="result-review-hint">At least {MIN_REASON} characters.</span>
                )}
              </div>
              {error && <p role="alert" className="form-error">{error}</p>}
            </div>
          ) : (
            <div className="result-review-actions" style={{ marginTop: latest ? 8 : 0 }}>
              <Button size="sm" variant="secondary" onClick={() => setOpen(true)}>
                <MessageSquareWarning size={13} />
                Not satisfied? Apply for recheck
              </Button>
            </div>
          )}
        </>
      )}
    </div>
  );
}

export function ResultsPage({ submissions: rows }: { submissions: Submission[] }) {
  const { user, assignments: assignmentList, courses } = useAppState();
  const student = user?.role === "student";
  // Teachers see every student's result, so each card is labelled with whose result it is.
  const studentNames = useStudentNames(courses, !student);
  const approved = student
    ? rows.filter((item) => item.studentId === user?.id && item.state === "Published")
    : rows.filter((item) => item.state === "Published");
  const [requests, setRequests] = useState<ReviewRequest[]>([]);
  const [drafts, setDrafts] = useState<Record<string, { text: string; nonce: number }>>({});

  useEffect(() => {
    if (!student) return;
    let active = true;
    // Requests are optional context: if the table is not set up yet, results still render.
    reviewService.listRequests().then((list) => active && setRequests(list)).catch(() => undefined);
    return () => {
      active = false;
    };
  }, [student]);

  /** Most recent request per submission. */
  const latestRequest = (submissionId: string) =>
    requests
      .filter((request) => request.submission_id === submissionId)
      .sort((a, b) => Date.parse(b.created_at) - Date.parse(a.created_at))[0];

  return (
    <>
      <div className="page-heading">
        <div>
          <div className="eyebrow">ACADEMIC EVALUATIONS</div>
          <h1>{student ? "My results" : "Results & performance"}</h1>
          <p className="page-subtitle">
            {student
              ? "Teacher-approved grades, evidence-based rubric scoring, and formative feedback."
              : "Review all published evaluations and student grade breakdowns across classes."}
          </p>
        </div>
      </div>

      <div className="published-results" style={{ display: "grid", gap: "16px" }}>
        {approved.length > 0 ? (
          approved.map((item) => {
            const assignment = assignmentList.find((a) => a.id === item.assignmentId);
            const owner = studentNames[item.studentId];
            return (
              <Panel key={item.id} style={{ padding: "20px" }}>
                <div className="section-heading">
                  <div>
                    {student ? (
                      <>
                        <h2>{assignment?.title ?? "Course Assignment"}</h2>
                        <p>Submitted {formatDate(item.submittedAt)}</p>
                      </>
                    ) : (
                      <>
                        <h2>{owner?.name ?? "Student"}</h2>
                        <p>
                          {owner?.email ? `${owner.email} · ` : ""}
                          {assignment?.title ?? "Course Assignment"} · Submitted {formatDate(item.submittedAt)}
                        </p>
                      </>
                    )}
                  </div>
                  <Badge tone="sage">
                    <CheckCircle2 size={13} />
                    Verified & Published
                  </Badge>
                </div>

                <div
                  style={{
                    display: "flex",
                    alignItems: "baseline",
                    gap: "12px",
                    margin: "12px 0 16px",
                    padding: "12px 16px",
                    background: "rgba(200, 241, 105, 0.15)",
                    borderRadius: "10px",
                    border: "1px solid rgba(168, 201, 138, 0.4)",
                  }}
                >
                  <span style={{ fontSize: "11px", fontWeight: 700, color: "#173D2B" }}>
                    Final Score Awarded:
                  </span>
                  <strong style={{ fontSize: "22px", color: "#173D2B" }}>
                    {item.grading
                      ? `${item.grading.suggestedScore} / ${assignment?.totalMarks ?? "—"}`
                      : "No grade record"}
                  </strong>
                  {item.grading?.teacherApproved && (
                    <span style={{ fontSize: "10px", color: "#5C6E61", marginLeft: "auto", display: "inline-flex", alignItems: "center", gap: "4px" }}>
                      <ShieldCheck size={14} style={{ color: "#173D2B" }} />
                      Teacher Approved
                    </span>
                  )}
                </div>

                {item.late?.status === "accepted" && item.late.penaltyPercent ? (
                  <p style={{ margin: "-6px 0 12px", fontSize: "10px", color: "#b5524b" }}>
                    Handed in late: this score includes a {item.late.penaltyPercent}% late deduction.
                    {item.late.note ? ` Teacher's note: “${item.late.note}”` : ""}
                  </p>
                ) : null}

                {item.grading?.reasoning && (
                  <div style={{ marginTop: "12px" }}>
                    <strong style={{ display: "block", marginBottom: "4px", fontSize: "11px" }}>
                      Instructor Comments:
                    </strong>
                    <p
                      style={{
                        margin: 0,
                        padding: "10px 14px",
                        background: "#F8F9F4",
                        borderRadius: "8px",
                        border: "1px solid #E7EBE3",
                        fontSize: "11px",
                        lineHeight: 1.6,
                        color: "#202820",
                      }}
                    >
                      {item.grading.reasoning}
                    </p>
                  </div>
                )}

                {(item.grading?.questionResults?.length ?? 0) > 0 && (
                  <div className="result-questions">
                    <strong className="result-questions-title">How each question was marked</strong>
                    {item.grading?.solutionsAvailableAt && (
                      <p className="result-questions-note">
                        Expected solutions will appear here after the due date (
                        {formatDate(item.grading.solutionsAvailableAt)}), once everyone has handed in.
                      </p>
                    )}
                    {item.grading!.questionResults!.map((result) => (
                      <QuestionResultRow
                        key={result.number}
                        result={result}
                        onRecheck={
                          student && latestRequest(item.id)?.status !== "open"
                            ? () =>
                                setDrafts((current) => ({
                                  ...current,
                                  [item.id]: { text: `Question ${result.number}: `, nonce: Date.now() },
                                }))
                            : undefined
                        }
                      />
                    ))}
                  </div>
                )}

                {student && (
                  <ReviewRequestBox
                    submissionId={item.id}
                    latest={latestRequest(item.id)}
                    onCreated={(request) => setRequests((list) => [...list, request])}
                    draft={drafts[item.id]}
                  />
                )}
              </Panel>
            );
          })
        ) : (
          <Panel className="empty-state" style={{ padding: "3rem", textAlign: "center", color: "#5C6E61" }}>
            <p>No teacher-approved results have been published for your account yet.</p>
            <p style={{ marginTop: "0.5rem", fontSize: "10px" }}>
              In TrustGrade, grades remain private and unlisted until reviewed and officially authorized by the course instructor.
            </p>
          </Panel>
        )}
      </div>
    </>
  );
}
