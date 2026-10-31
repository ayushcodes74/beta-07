import { useState, type Dispatch, type SetStateAction } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { ArrowLeft, Check, ShieldCheck } from "lucide-react";
import { useAppState } from "../../App";
import { Badge, Button, Panel, StatusBadge, useToast } from "../../components/ui";
import { IntegrationNotice } from "../../components/common/IntegrationNotice";
import { formatDate } from "../../lib/utils";
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

  const [score, setScore] = useState<number>(submission?.grading?.suggestedScore ?? 18);
  const [feedback, setFeedback] = useState<string>(
    submission?.grading?.feedback?.comment ??
    "Strong conceptual grasp demonstrated. Arguments are well structured with clear references to course topics."
  );
  const [approving, setApproving] = useState(false);

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
            <Badge tone="sage">
              OCR Confidence: {Math.round((submission.ocr.confidence || 0.95) * 100)}%
            </Badge>
            {submission.fileName && <Badge tone="ink">{submission.fileName}</Badge>}
          </div>

          <div className="ocr-box">
            {submission.ocr.extractedText ||
              submission.answer ||
              "No extracted text found for this submission. The PDF document was queued for OCR analysis."}
          </div>

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
        </Panel>

        {/* RIGHT COLUMN: TEACHER GRADING & RUBRIC SCORING */}
        <Panel className="ocr-pane-content">
          <div className="section-heading">
            <div>
              <h2>Teacher Assessment</h2>
              <p>Verify scoring criteria and qualitative feedback</p>
            </div>
          </div>

          <IntegrationNotice
            title="AI Grading Backend Status"
            description="Automated AI grading route (POST /api/v1/submissions/:id/grade) is awaiting router mount. You maintain complete human authority to evaluate, score, and publish results."
            endpoint="POST /api/v1/submissions/{id}/grade"
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
        </Panel>
      </div>
    </>
  );
}
