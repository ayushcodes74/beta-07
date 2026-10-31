import { useEffect, useRef, useState, type Dispatch, type SetStateAction } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { ArrowLeft, Check, ShieldCheck } from "lucide-react";
import { useAppState } from "../../App";
import { Badge, Button, Panel, StatusBadge, useToast } from "../../components/ui";
import { IntegrationNotice } from "../../components/common/IntegrationNotice";
import { formatDate } from "../../lib/utils";
import { extractErrorMessage, submissionService, withPublishedGrade, type BackendGradingSuggestion } from "../../services/api";
import type { Submission } from "../../types/models";

export function GradingReviewPage({
  submissions: rows,
  setSubmissions,
}: {
  submissions: Submission[];
  setSubmissions: Dispatch<SetStateAction<Submission[]>>;
}) {
  const { submissionId } = useParams();
  const navigate = useNavigate();
  const toast = useToast();
  const { assignments: assignmentList, people } = useAppState();

  const submission = rows.find((item) => item.id === submissionId);
  const assignment = submission ? assignmentList.find((a) => a.id === submission.assignmentId) : undefined;
  const student = submission ? people.find((p) => p.id === submission.studentId) : undefined;

  const [score, setScore] = useState<number>(submission?.grading?.suggestedScore ?? 0);
  const [feedback, setFeedback] = useState<string>(
    submission?.grading?.feedback?.comment ?? ""
  );
  const [approving, setApproving] = useState(false);
  const [publishError, setPublishError] = useState("");
  const [integrityReport, setIntegrityReport] = useState<Awaited<ReturnType<typeof submissionService.getIntegrity>> | null>(null);
  const [integrityError, setIntegrityError] = useState("");
  const [integrityLoading, setIntegrityLoading] = useState(false);
  const [ocrText, setOcrText] = useState("");
  const [ocrConfidence, setOcrConfidence] = useState<number | null>(null);
  const [ocrNotice, setOcrNotice] = useState("");
  const [answerCheck, setAnswerCheck] = useState<BackendGradingSuggestion | null>(null);
  const [answerCheckError, setAnswerCheckError] = useState("");
  const [checkingAnswers, setCheckingAnswers] = useState(false);
  const autoCheckedIds = useRef(new Set<string>());

  // Show the last stored AI answer check; if none exists yet, run one automatically (once per
  // submission per visit) so the teacher sees correctness without hunting for the button.
  useEffect(() => {
    setAnswerCheck(null);
    setAnswerCheckError("");
    if (!submission) return;
    let active = true;
    const id = submission.id;
    submissionService
      .getAnswerCheck(id)
      .then((saved) => {
        if (!active) return;
        if (saved) {
          setAnswerCheck(saved);
          if (submission.state !== "Published") {
            setScore(Math.round(saved.total_awarded_marks * 100) / 100);
            setFeedback((current) => current || saved.overall_feedback);
          }
        } else if (!autoCheckedIds.current.has(id)) {
          autoCheckedIds.current.add(id);
          void runAnswerCheck();
        }
      })
      .catch(() => {
        /* Storage unavailable: the teacher can still run a check with the button. */
      });
    if (submission.state === "Published") {
      submissionService
        .getPublishedResult(id)
        .then((grade) => {
          if (!active || !grade) return;
          setScore(grade.final_score);
          setFeedback(grade.final_feedback);
        })
        .catch(() => {
          /* Fall back to the AI suggestion values. */
        });
    }
    return () => {
      active = false;
    };
  }, [submission?.id]);

  const runAnswerCheck = async () => {
    if (!submission) return;
    setCheckingAnswers(true);
    setAnswerCheckError("");
    try {
      const result = await submissionService.checkAnswers(submission.id);
      setAnswerCheck(result);
      setScore(Math.round(result.total_awarded_marks * 100) / 100);
      if (!feedback.trim()) setFeedback(result.overall_feedback);
    } catch (error) {
      setAnswerCheckError(extractErrorMessage(error, "Could not check the answers."));
    } finally {
      setCheckingAnswers(false);
    }
  };

  // The submissions list carries no OCR text, so fetch the OCR service result for this submission.
  useEffect(() => {
    setOcrText("");
    setOcrConfidence(null);
    setOcrNotice("");
    if (!submission || submission.ocr.extractedText) return;

    let active = true;
    setOcrNotice("Loading OCR text...");
    submissionService
      .getOcrResult(submission.id)
      .then((result) => {
        if (!active) return;
        if (!("pages" in result)) {
          setOcrNotice(`OCR is still running (${result.stage}, ${result.progress}%). Reopen this page shortly.`);
          return;
        }
        const pages = [...result.pages].sort((a, b) => a.page_number - b.page_number);
        const text = pages
          .filter((page) => page.full_text.trim())
          .map((page) => (pages.length > 1 ? `— Page ${page.page_number} —\n${page.full_text}` : page.full_text))
          .join("\n\n");
        const confidences = pages.flatMap((page) =>
          page.text_blocks.map((block) => block.confidence).filter((c): c is number => c !== null)
        );
        setOcrText(text);
        setOcrConfidence(confidences.length ? confidences.reduce((sum, c) => sum + c, 0) / confidences.length : null);
        setOcrNotice(text ? "" : "OCR finished but found no readable text in this submission.");
      })
      .catch((error: unknown) => {
        if (active) setOcrNotice(extractErrorMessage(error, "Could not load OCR text."));
      });

    return () => {
      active = false;
    };
  }, [submission?.id]);

  useEffect(() => {
    if (!submission) {
      setIntegrityReport(null);
      setIntegrityError("");
      return;
    }

    let active = true;
    setIntegrityLoading(true);
    setIntegrityError("");
    submissionService
      .getIntegrity(submission.id)
      .then((report) => {
        if (active) setIntegrityReport(report);
      })
      .catch((error: unknown) => {
        if (active) {
          setIntegrityError(extractErrorMessage(error, "Could not load integrity evidence."));
        }
      })
      .finally(() => {
        if (active) setIntegrityLoading(false);
      });

    return () => {
      active = false;
    };
  }, [submission?.id]);

  if (!submission) {
    return (
      <div style={{ padding: "4rem", textAlign: "center" }}>
        <h2>Submission not found</h2>
        <p style={{ margin: "1rem 0", color: "#5C6E61" }}>
          Submission record {submissionId} was not found in the current workspace queue.
        </p>
        <Button variant="secondary" onClick={() => navigate("/app/submissions")}>
          <ArrowLeft size={14} />
          Back to Submissions
        </Button>
      </div>
    );
  }

  const maxMarks = assignment?.totalMarks ?? answerCheck?.total_max_marks ?? 0;
  const scoreInvalid = !Number.isFinite(score) || score < 0 || (maxMarks > 0 && score > maxMarks);
  const alreadyPublished = submission.state === "Published";

  const approveGrade = async () => {
    if (scoreInvalid) return;
    setApproving(true);
    setPublishError("");
    try {
      const grade = await submissionService.publishGrade(submission.id, score, feedback);
      setSubmissions((current) =>
        current.map((item) => (item.id === submission.id ? withPublishedGrade(item, grade) : item))
      );
      toast(`Grade (${grade.final_score}/${grade.max_score ?? maxMarks}) published to ${student?.name ?? "the student"}.`);
      navigate("/app/submissions");
    } catch (error) {
      setPublishError(extractErrorMessage(error, "Could not publish the grade."));
    } finally {
      setApproving(false);
    }
  };

  return (
    <>
      <div className="page-heading">
        <div>
          <div className="eyebrow">EVALUATION CONSOLE</div>
          <h1>Grading & Assessment Review</h1>
          <p className="page-subtitle">
            {assignment?.title ?? "Assignment"} · Student: {student?.name ?? "Student"}
          </p>
        </div>
        <div className="heading-actions">
          <Button variant="secondary" onClick={() => navigate("/app/submissions")}>
            <ArrowLeft size={14} />
            Back to queue
          </Button>
        </div>
      </div>

      <div className="grading-review-split">
        {/* LEFT COLUMN: OCR & SUBMISSION EXTRACT */}
        <Panel className="ocr-pane-content">
          <div className="section-heading">
            <div>
              <h2>Extracted Student Work</h2>
              <p>Submitted {formatDate(submission.submittedAt)} · OCR processed text</p>
            </div>
            <StatusBadge status={submission.ocr.state} />
          </div>

          <div style={{ display: "flex", gap: "10px", margin: "10px 0" }}>
            {(submission.ocr.confidence ?? ocrConfidence) !== null && (
              <Badge tone="sage">
                OCR Confidence: {Math.round((submission.ocr.confidence ?? ocrConfidence ?? 0) * 100)}%
              </Badge>
            )}
            {submission.fileName && <Badge tone="ink">{submission.fileName}</Badge>}
          </div>

          <div className="ocr-box">
            {submission.ocr.extractedText ||
              ocrText ||
              submission.answer ||
              ocrNotice ||
              "OCR text is not available yet. Open OCR review to inspect the service result."}
          </div>
          <Button
            variant="secondary"
            size="sm"
            style={{ marginTop: "10px" }}
            onClick={() => navigate(`/app/ocr/${submission.id}`)}
          >
            Review OCR regions
          </Button>

          {submission.ocr.expressions && submission.ocr.expressions.length > 0 && (
            <div style={{ marginTop: "14px" }}>
              <strong style={{ fontSize: "11px", color: "#173D2B" }}>Detected Mathematical Expressions:</strong>
              <div style={{ display: "flex", flexWrap: "wrap", gap: "6px", marginTop: "6px" }}>
                {submission.ocr.expressions.map((exp, i) => (
                  <code
                    key={i}
                    style={{
                      padding: "3px 7px",
                      background: "rgba(200, 241, 105, 0.2)",
                      borderRadius: "6px",
                      fontSize: "11px",
                    }}
                  >
                    {exp}
                  </code>
                ))}
              </div>
            </div>
          )}

          {/* Integrity evidence */}
            <div style={{ marginTop: "18px" }}>
              <h3 style={{ fontSize: "13px" }}>Integrity review</h3>
              {integrityLoading && <p role="status">Loading authorized comparison evidence…</p>}
              {integrityError && <p role="alert">{integrityError}</p>}
              {integrityReport && (
                <>
                  <p>
                    Status: {integrityReport.review_status.replaceAll("_", " ")} · compared{" "}
                    {integrityReport.comparisons_completed} of{" "}
                    {integrityReport.comparisons_completed + integrityReport.comparisons_skipped} submissions
                  </p>
                  <p>
                    Exact matching compares OCR text within this assignment. Semantic similarity and handwriting
                    analysis are unavailable; matches are review signals, not findings of misconduct.
                  </p>
                  {integrityReport.notes.map((note, index) => <p key={`note-${index}`}>{note}</p>)}
                  {integrityReport.evidence.map((evidence, index) => (
                    <div className="integration-notice-card" key={`${evidence.source_submission_id}-${index}`}>
                      <div className="integration-notice-content">
                        <h4>Potential text overlap · {Math.round(evidence.exact_match_score * 100)}% token match</h4>
                        <p>Source reference: {evidence.source_reference}</p>
                        <div style={{ display: "grid", gap: "8px", marginTop: "8px" }}>
                          <div><strong>Current passage</strong><p>{evidence.current_passage}</p></div>
                          <div><strong>Comparison passage</strong><p>{evidence.source_passage}</p></div>
                        </div>
                        {evidence.ocr_uncertain && <p>OCR uncertainty applies to this evidence.</p>}
                        {evidence.context_note && <p>{evidence.context_note}</p>}
                      </div>
                    </div>
                  ))}
                  {!integrityReport.evidence.length && integrityReport.comparison_complete && (
                    <p>No matching passage was found in the authorized same-assignment comparison set.</p>
                  )}
                  {!integrityReport.comparison_complete && (
                    <p>Comparison is incomplete; skipped submissions prevent a conclusive no-match result.</p>
                  )}
                  {integrityReport.ocr_quality.low_confidence_regions.length > 0 && (
                    <p>{integrityReport.ocr_quality.low_confidence_regions.length} OCR region(s) require review.</p>
                  )}
                </>
              )}
            </div>
        </Panel>

        {/* RIGHT COLUMN: TEACHER GRADING & RUBRIC SCORING */}
        <Panel className="ocr-pane-content">
          <div className="section-heading">
            <div>
              <h2>Teacher Assessment</h2>
              <p>Verify scoring criteria and qualitative feedback</p>
            </div>
          </div>

          <div className="answer-check">
            <div className="answer-check-head">
              <div>
                <strong>AI answer check</strong>
                <p>Compares the OCR text with each question's answer key. Suggestions only; you decide the grade.</p>
              </div>
              <Button size="sm" disabled={checkingAnswers} onClick={() => void runAnswerCheck()}>
                {checkingAnswers ? "Checking… (up to a minute)" : answerCheck ? "Re-check answers" : "Check answers"}
              </Button>
            </div>

            {answerCheckError && <p className="answer-check-error">{answerCheckError}</p>}

            {answerCheck && (
              <>
                <div className="answer-check-total">
                  <span>
                    Suggested score: <strong>{answerCheck.total_awarded_marks}</strong> / {answerCheck.total_max_marks} (
                    {Math.round(answerCheck.percentage)}%)
                  </span>
                  {answerCheck.review_required && <Badge tone="gold">Needs teacher review</Badge>}
                </div>
                {answerCheck.overall_feedback && <p className="answer-check-feedback">{answerCheck.overall_feedback}</p>}

                {answerCheck.questions.map((q) => {
                  const verdict =
                    q.awarded_marks >= q.max_marks ? "correct" : q.awarded_marks > 0 ? "partial" : "incorrect";
                  return (
                    <div key={q.number} className={`answer-check-question answer-check-${verdict}`}>
                      <div className="answer-check-question-top">
                        <strong>
                          Q{q.number} · {verdict === "correct" ? "Correct" : verdict === "partial" ? "Partly correct" : "Incorrect / not found"}
                        </strong>
                        <span>
                          {q.awarded_marks} / {q.max_marks}
                        </span>
                      </div>
                      <p className="answer-check-question-text">{q.question_text}</p>
                      <p>{q.explanation}</p>
                      {q.matched_concepts.length > 0 && <p>✓ {q.matched_concepts.join(" · ")}</p>}
                      {q.missing_concepts.length > 0 && <p>✗ Missing: {q.missing_concepts.join(" · ")}</p>}
                      {q.review_reasons.length > 0 && <p className="answer-check-review">⚑ {q.review_reasons.join(" ")}</p>}
                    </div>
                  );
                })}
                <p className="answer-check-meta">
                  Checked {formatDate(answerCheck.graded_at)}
                  {answerCheck.saved ? " · saved for review" : " · not saved"}
                </p>
              </>
            )}
          </div>

          <div className="grade-publish">
            {alreadyPublished && (
              <IntegrationNotice
                title="Grade published"
                description="The student can see this grade. Publishing again replaces the score and feedback they see."
                tone="info"
              />
            )}
          <div className="rubric-criteria-list">
            <div className="rubric-item-card">
              <div className="rubric-item-top">
                <div>
                  <strong>Total Score Awarded</strong>
                  <p style={{ margin: "2px 0 0", fontSize: "9px", color: "#5C6E61" }}>
                    Maximum marks: {maxMarks || "—"}
                    {answerCheck && ` · AI suggested ${answerCheck.total_awarded_marks}`}
                  </p>
                </div>
                <div className="rubric-score-input">
                  <input
                    type="number"
                    min={0}
                    max={maxMarks || undefined}
                    step={0.5}
                    value={score}
                    onChange={(e) => setScore(Number(e.target.value))}
                  />
                  <span>/ {maxMarks || "—"}</span>
                </div>
              </div>
            </div>
          </div>

          <div style={{ marginTop: "16px" }}>
            <label style={{ display: "block", marginBottom: "6px", fontWeight: 700, fontSize: "11px" }}>
              Formative Feedback for Student
            </label>
            <textarea
              className="feedback-textarea"
              value={feedback}
              onChange={(e) => setFeedback(e.target.value)}
              placeholder="Highlight strengths, address misconceptions, and recommend specific syllabus topics for review..."
            />
          </div>

          <div style={{ marginTop: "20px", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <span style={{ fontSize: "10px", color: "#5C6E61", display: "inline-flex", alignItems: "center", gap: "4px" }}>
              <ShieldCheck size={14} style={{ color: "#173D2B" }} />
              Only you can publish; the AI suggestion is never shown to the student
            </span>
            <Button disabled={approving || scoreInvalid} onClick={() => void approveGrade()}>
              <Check size={14} />
              {approving ? "Publishing…" : alreadyPublished ? "Update Published Grade" : "Approve & Publish Grade"}
            </Button>
          </div>
          {scoreInvalid && <p className="answer-check-error">Score must be between 0 and {maxMarks}.</p>}
          {publishError && <p className="answer-check-error">{publishError}</p>}
          </div>
        </Panel>
      </div>
    </>
  );
}
