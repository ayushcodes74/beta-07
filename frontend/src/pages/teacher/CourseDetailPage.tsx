import { useNavigate, useParams } from "react-router-dom";
import { ArrowLeft, FileCheck2, Plus } from "lucide-react";
import { useAppState } from "../../App";
import { Button, Panel, StatusBadge } from "../../components/ui";
import { formatDate } from "../../lib/utils";
import type { Course } from "../../types/models";

export function CourseDetailPage({ courses: courseList }: { courses: Course[] }) {
  const { assignments: assignmentList } = useAppState();
  const { courseId } = useParams();
  const navigate = useNavigate();
  const course = courseList.find((item) => item.id === courseId);

  if (!course) {
    return (
      <div style={{ padding: "4rem", textAlign: "center" }}>
        <h2>Course not found</h2>
        <p style={{ margin: "1rem 0", color: "#5C6E61" }}>
          The requested course could not be located in this workspace.
        </p>
        <Button variant="secondary" onClick={() => navigate("/app/courses")}>
          <ArrowLeft size={14} />
          Back to Courses
        </Button>
      </div>
    );
  }

  const courseAssignments = assignmentList.filter(
    (item) => item.courseId === course.id || !item.courseId
  );

  return (
    <>
      <div className="page-heading">
        <div>
          <div className="eyebrow">COURSE DETAILS</div>
          <h1>{course.name}</h1>
          <p className="page-subtitle">
            {course.code} · {course.instructor} · Spring term 2026
          </p>
        </div>
        <div className="heading-actions">
          <Button variant="secondary" onClick={() => navigate("/app/materials")}>
            <FileCheck2 size={15} />
            Course materials
          </Button>
          <Button onClick={() => navigate("/app/assignment/new")}>
            <Plus size={15} />
            Create assignment
          </Button>
        </div>
      </div>

      <div className="metric-strip">
        {[
          ["Enrolled students", course.students, "Active this term"],
          ["Course assignments", courseAssignments.length, "Scheduled for this class"],
        ].map(([label, value, note]) => (
          <Panel className="metric-card" key={label.toString()}>
            <span>{label}</span>
            <strong>{value}</strong>
            <small>{note}</small>
          </Panel>
        ))}
      </div>

      <div className="course-detail-grid">
        <Panel className="recent-card">
          <div className="section-heading">
            <div>
              <h2>Course assignments</h2>
              <p>Work assigned to enrolled students</p>
            </div>
          </div>
          <div className="table-scroll">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Assignment</th>
                  <th>Format</th>
                  <th>Marks</th>
                  <th>Due Date</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {courseAssignments.length ? (
                  courseAssignments.map((item) => (
                    <tr key={item.id}>
                      <td>
                        <strong>{item.title}</strong>
                      </td>
                      <td>{item.submissionType}</td>
                      <td>{item.totalMarks} marks</td>
                      <td>{formatDate(item.dueAt)}</td>
                      <td>
                        <StatusBadge status={item.state} />
                      </td>
                    </tr>
                  ))
                ) : (
                  <tr>
                    <td colSpan={5} style={{ textAlign: "center", padding: "2rem", color: "#5C6E61" }}>
                      No assignments created yet for this course. Click "Create assignment" above to add one.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </Panel>
      </div>
    </>
  );
}

