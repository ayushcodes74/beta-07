import { useState, type Dispatch, type SetStateAction } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { ArrowLeft, ChevronLeft, ChevronRight } from "lucide-react";
import { useAppState } from "../../App";
import { Button, Panel, useToast } from "../../components/ui";
import type { Submission } from "../../types/models";

export function AssessmentPage({
  submissions: studentRows,
  setSubmissions,
}: {
  submissions: Submission[];
  setSubmissions: Dispatch<SetStateAction<Submission[]>>;
}) {
  const { user, assignments: assignmentList } = useAppState();
  const navigate = useNavigate();
  const toast = useToast();
  const { assignmentId } = useParams();
  const assignment = assignmentList.find((item) => item.id === assignmentId);
  const existing = studentRows.find((item) => item.studentId === user?.id && item.assignmentId === assignmentId);
  const [index, setIndex] = useState(0);
  const [answers, setAnswers] = useState<Record<string, number>>({});
  const [submitted, setSubmitted] = useState(false);

  if (!assignment) {
    return (
      <div style={{ padding: "4rem", textAlign: "center" }}>
        <h2>Assessment not found</h2>
        <Button variant="secondary" onClick={() => navigate("/app/student/assignments")}>
          Back to Assignments
        </Button>
      </div>
    );
  }

  const questions = assignment.questions;
  const current = questions[index];

  const submitAssessment = () => {
    if (existing || !user) return;
    setSubmitted(true);
    toast("Assessment recorded in your student learning session.", "info");
    const newSub: Submission = {
      id: `mcq-${crypto.randomUUID()}`,
      studentId: user.id,
      assignmentId: assignment.id,
      submittedAt: new Date().toISOString(),
      deadline: assignment.dueAt,
      state: "Submitted",
      ocr: { confidence: 1, state: "Verified", extractedText: "MCQ answers recorded successfully.", warnings: [], expressions: [] },
      answer: "MCQ interactive submission",
    };
    setSubmissions((curr) => [newSub, ...curr]);
  };

  return (
    <>
      <div className="page-heading">
        <div>
          <div className="eyebrow">ONLINE ASSESSMENT</div>
          <h1>{assignment.title}</h1>
          <p className="page-subtitle">
            Question {index + 1} of {questions.length} · {assignment.totalMarks} marks total
          </p>
        </div>
        <div className="heading-actions">
          <Button variant="secondary" onClick={() => navigate("/app/student/assignments")}>
            <ArrowLeft size={14} />
            Exit assessment
          </Button>
        </div>
      </div>

      <div className="assessment-layout">
        <Panel className="assessment-card">
          {current ? (
            <div>
              <div className="question-prompt" style={{ marginBottom: "1.5rem" }}>
                <span className="eyebrow" style={{ color: "#173D2B" }}>
                  QUESTION {index + 1} · {current.marks} MARKS
                </span>
                <h2 style={{ fontSize: "16px", marginTop: "6px" }}>{current.prompt}</h2>
              </div>
              <div className="mcq-options" style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
                {(current.options ?? ["Option A", "Option B", "Option C", "Option D"]).map((opt, optIdx) => (
                  <label
                    key={optIdx}
                    style={{
                      display: "flex",
                      alignItems: "center",
                      gap: "0.75rem",
                      cursor: "pointer",
                      padding: "0.75rem 1rem",
                      borderRadius: "10px",
                      border: answers[current.id] === optIdx ? "1.5px solid #173D2B" : "1px solid #E7EBE3",
                      background: answers[current.id] === optIdx ? "rgba(200, 241, 105, 0.15)" : "#FFFFFF",
                      transition: "border-color .18s, background .18s",
                    }}
                  >
                    <input
                      type="radio"
                      name={`question-${current.id}`}
                      checked={answers[current.id] === optIdx}
                      onChange={() => setAnswers((curr) => ({ ...curr, [current.id]: optIdx }))}
                    />
                    <span style={{ fontSize: "11px", fontWeight: answers[current.id] === optIdx ? 650 : 400 }}>
                      {opt}
                    </span>
                  </label>
                ))}
              </div>
              <div
                className="assessment-nav"
                style={{ display: "flex", justifyContent: "space-between", marginTop: "2rem" }}
              >
                <Button
                  variant="secondary"
                  disabled={index === 0}
                  onClick={() => setIndex((i) => i - 1)}
                >
                  <ChevronLeft size={14} />
                  Previous
                </Button>
                {index < questions.length - 1 ? (
                  <Button onClick={() => setIndex((i) => i + 1)}>
                    Next
                    <ChevronRight size={14} />
                  </Button>
                ) : (
                  <Button
                    disabled={submitted || Boolean(existing)}
                    onClick={submitAssessment}
                  >
                    {submitted || existing ? "Submitted" : "Submit Assessment"}
                  </Button>
                )}
              </div>
            </div>
          ) : (
            <p className="table-empty" style={{ padding: "2rem", textAlign: "center" }}>
              No questions configured for this assessment.
            </p>
          )}
        </Panel>
      </div>
    </>
  );
}

