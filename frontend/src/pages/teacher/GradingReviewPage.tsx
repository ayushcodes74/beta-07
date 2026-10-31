import { useEffect, useState, type Dispatch, type SetStateAction } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { ArrowLeft, Check, ShieldCheck } from "lucide-react";
import { useAppState } from "../../App";
import { Badge, Button, Panel, StatusBadge, useToast } from "../../components/ui";
import { IntegrationNotice } from "../../components/common/IntegrationNotice";
import { formatDate } from "../../lib/utils";
import { extractErrorMessage, submissionService } from "../../services/api";
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
  const backendGradingConnected = false;

  const submission = rows.find((item) => item.id === submissionId);
  const assignment = submission ? assignmentList.find((a) => a.id === submission.assignmentId) : undefined;
  const student = submission ? people.find((p) => p.id === submission.studentId) : undefined;

  const [score, setScore] = useState<number>(submission?.grading?.suggestedScore ?? 0);
  const [feedback, setFeedback] = useState<string>(
    submission?.grading?.feedback?.comment ?? ""
  );
  const [approving, setApproving] = useState(false);
  const [integrityReport, setIntegrityReport] = useState<Awaited<ReturnType<typeof submissionService.getIntegrity>> | null>(null);
  const [integrityError, setIntegrityError] = useState("");
  const [integrityLoading, setIntegrityLoading] = useState(false);

  useEffect(() => {
    if (!submission || backendGradingConnected) {
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
  }, [backendGradingConnected, submission?.id]);

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

  const approveGrade = () => {
    if (!backendGradingConnected) return;
    setApproving(true);
    setSubmissions((current) =>
      current.map((item) =>
        item.id === submission.id
          ? {
            ...item,
            state: "Published",
            grading: {
              suggestedScore: score,
              confidence: submission.ocr.confidence || 0.95,
              reasoning: feedback,
              rubric: [
                { id: "c1", name: "Concept Understanding", description: "Core concepts", score: Math.round(score * 0.5), maximum: 10 },
                { id: "c2", name: "Methodology & Derivation", description: "Analytical depth", score: Math.round(score * 0.5), maximum: 10 },
              ],
              feedback: {
                id: crypto.randomUUID(),
                comment: feedback,
                deductions: [],
                courseReferences: ["Course Material 01"],
              },
              teacherApproved: true,
            },
          }
          : item
      )
    );

    setTimeout(() => {
      setApproving(false);
      toast(`Grade (${score}/${assignment?.totalMarks ?? 20}) approved and published for ${student?.name ?? "Student"}!`);
      navigate("/app/submissions");
    }, 400);
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
            {submission.ocr.confidence !== null && (
              <Badge tone="sage">
                OCR Confidence: {Math.round(submission.ocr.confidence * 100)}%
              </Badge>
            )}
            {submission.fileName && <Badge tone="ink">{submission.fileName}</Badge>}
          </div>

          <div className="ocr-box">
            {submission.ocr.extractedText ||
              submission.answer ||
              "OCR text is not loaded on this screen. Open OCR review to inspect the service result."}
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

          {!backendGradingConnected && (
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
          )}
        </Panel>

        {/* RIGHT COLUMN: TEACHER GRADING & RUBRIC SCORING */}
        <Panel className="ocr-pane-content">
          <div className="section-heading">
            <div>
              <h2>Teacher Assessment</h2>
              <p>Verify scoring criteria and qualitative feedback</p>
            </div>
          </div>

          {!backendGradingConnected ? (
            <IntegrationNotice
              title="Grade review and publication are not connected"
              description="No grading-result, teacher-review, or publication API is mounted. No score or feedback has been generated, and this screen cannot publish a real grade."
              endpoint="No grading or publication endpoint is currently available"
              tone="warning"
            />
          ) : (
            <>
          <IntegrationNotice
            title="AI grading is not connected"
            description="No grading-result endpoint is currently available. Scores and feedback are not generated or persisted here."
            tone="info"
          />
          <div className="rubric-criteria-list">
            <div className="rubric-item-card">
              <div className="rubric-item-top">
                <div>
                  <strong>Total Score Awarded</strong>
                  <p style={{ margin: "2px 0 0", fontSize: "9px", color: "#5C6E61" }}>
                    Maximum marks: {assignment?.totalMarks ?? 20}
                  </p>
                </div>
                <div className="rubric-score-input">
                  <input
                    type="number"
                    min={0}
                    max={assignment?.totalMarks ?? 20}
                    value={score}
                    onChange={(e) => setScore(Number(e.target.value))}
                  />
                  <span>/ {assignment?.totalMarks ?? 20}</span>
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
              Teacher approved
            </span>
            <Button disabled={approving} onClick={approveGrade}>
              <Check size={14} />
              {approving ? "Publishing…" : "Approve & Publish Grade"}
            </Button>
          </div>
            </>
          )}
        </Panel>
      </div>
    </>
  );
}
