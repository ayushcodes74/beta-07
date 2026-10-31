import { CheckCircle2, ShieldCheck } from "lucide-react";
import { useAppState } from "../../App";
import { Badge, Panel } from "../../components/ui";
import { formatDate } from "../../lib/utils";
import type { Submission } from "../../types/models";

export function ResultsPage({ submissions: rows }: { submissions: Submission[] }) {
  const { user, assignments: assignmentList } = useAppState();
  const student = user?.role === "student";
  const approved = student
    ? rows.filter((item) => item.studentId === user?.id && item.state === "Published")
    : rows.filter((item) => item.state === "Published");

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
            return (
              <Panel key={item.id} style={{ padding: "20px" }}>
                <div className="section-heading">
                  <div>
                    <h2>{assignment?.title ?? "Course Assignment"}</h2>
                    <p>Submitted {formatDate(item.submittedAt)}</p>
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
