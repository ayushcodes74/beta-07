import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { ChevronRight, Search } from "lucide-react";
import { useAppState } from "../../App";
import { Button, Panel, StatusBadge } from "../../components/ui";
import { formatDate } from "../../lib/utils";
import type { Submission } from "../../types/models";

export function SubmissionsPage({ submissions: rows }: { submissions: Submission[] }) {
  const { user, assignments: assignmentList, people } = useAppState();
  const [filter, setFilter] = useState("All");
  const [query, setQuery] = useState("");
  const navigate = useNavigate();
  const student = user?.role === "student";
  const studentRows = rows.filter((item) => item.studentId === user?.id);
  const visible = (student ? studentRows : rows).filter((item) => {
    const person = people.find((userItem) => userItem.id === item.studentId)?.name ?? "";
    const matchesText = `${person} ${
      assignmentList.find((assignment) => assignment.id === item.assignmentId)?.title ?? ""
    }`.toLowerCase().includes(query.toLowerCase());
    const matchesFilter = filter === "All" || item.state === filter;
    return matchesText && matchesFilter;
  });

  return (
    <>
      <div className="page-heading">
        <div>
          <div className="eyebrow">SUBMISSION QUEUE</div>
          <h1>{student ? "My submissions" : "Submissions"}</h1>
          <p className="page-subtitle">
            {student
              ? "Keep track of work you’ve handed in, OCR extraction progress, and teacher feedback."
              : "Review student hand-ins with integrated OCR and transparent assessment rubrics."}
          </p>
        </div>
      </div>

      <div className="toolbar">
        <div className="segmented">
          {["All", "Submitted", "Under Review", "Graded"].map((f) => (
            <button
              key={f}
              className={filter === f ? "segment active" : "segment"}
              onClick={() => setFilter(f)}
            >
              {f}
            </button>
          ))}
        </div>
        <label className="inline-search">
          <Search size={14} />
          <input
            placeholder={student ? "Find an assignment..." : "Find a student or submission..."}
            value={query}
            onChange={(event) => setQuery(event.target.value)}
          />
        </label>
      </div>

      <Panel className="table-card">
        <div className="table-scroll">
          <table className="data-table">
            <thead>
              <tr>
                {student ? (
                  <>
                    <th>Assignment</th>
                    <th>Submitted</th>
                    <th>OCR Status</th>
                    <th>Grading Status</th>
                    <th>Action</th>
                  </>
                ) : (
                  <>
                    <th>Student</th>
                    <th>Assignment</th>
                    <th>Submitted</th>
                    <th>OCR Status</th>
                    <th>Grading Status</th>
                    <th>Action</th>
                  </>
                )}
              </tr>
            </thead>
            <tbody>
              {visible.map((item) => {
                const assignment = assignmentList.find((a) => a.id === item.assignmentId);
                const person = people.find((p) => p.id === item.studentId);
                return (
                  <tr key={item.id}>
                    {student ? (
                      <>
                        <td>
                          <strong>{assignment?.title ?? "Assignment"}</strong>
                        </td>
                        <td>{formatDate(item.submittedAt)}</td>
                        <td>
                          <StatusBadge status={item.ocr.state} />
                        </td>
                        <td>
                          <StatusBadge status={item.state} />
                        </td>
                        <td>
                          <Button
                            size="sm"
                            variant="secondary"
                            onClick={() => navigate(`/app/student/submit/${item.assignmentId}`)}
                          >
                            View
                            <ChevronRight size={13} />
                          </Button>
                        </td>
                      </>
                    ) : (
                      <>
                        <td>
                          <strong>{person?.name ?? "Student"}</strong>
                        </td>
                        <td>{assignment?.title ?? "Assignment"}</td>
                        <td>{formatDate(item.submittedAt)}</td>
                        <td>
                          <StatusBadge status={item.ocr.state} />
                        </td>
                        <td>
                          <StatusBadge status={item.state} />
                        </td>
                        <td>
                          <button
                            className="text-button"
                            onClick={() => navigate(`/app/grading/${item.id}`)}
                          >
                            Review
                            <ChevronRight size={13} />
                          </button>
                        </td>
                      </>
                    )}
                  </tr>
                );
              })}
              {!visible.length && (
                <tr>
                  <td
                    className="table-empty"
                    colSpan={student ? 5 : 6}
                    style={{ textAlign: "center", padding: "2.5rem", color: "#5C6E61" }}
                  >
                    {student
                      ? "You haven't submitted any assignments yet. Go to 'Assignments' to upload your work."
                      : "No submissions recorded in this view. Student PDF uploads received during this session appear here for OCR and grading review."}
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </Panel>
    </>
  );
}

