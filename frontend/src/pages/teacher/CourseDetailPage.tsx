import { useCallback, useEffect, useState, type FormEvent } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { ArrowLeft, FileCheck2, Plus, UserPlus, X } from "lucide-react";
import { useAppState } from "../../App";
import { Button, Panel, StatusBadge, useToast } from "../../components/ui";
import { formatDate } from "../../lib/utils";
import { courseService, extractErrorMessage, type EnrolledStudentResponse } from "../../services/api";
import type { Course } from "../../types/models";

function StudentsPanel({ courseId, onCountChange }: { courseId: string; onCountChange: (count: number) => void }) {
  const toast = useToast();
  const [students, setStudents] = useState<EnrolledStudentResponse[]>([]);
  const [loading, setLoading] = useState(true);
  const [email, setEmail] = useState("");
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      const roster = await courseService.getStudents(courseId);
      setStudents(roster);
      onCountChange(roster.length);
    } catch (err) {
      toast(extractErrorMessage(err, "Could not load the student roster."), "info");
    } finally {
      setLoading(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [courseId]);

  useEffect(() => {
    void load();
  }, [load]);

  const enroll = async (event: FormEvent) => {
    event.preventDefault();
    if (!email.trim()) return;
    setBusy(true);
    try {
      await courseService.enrollStudentByEmail(courseId, email);
      toast(`Enrolled ${email.trim()}. They can now see this course's published assignments.`);
      setEmail("");
      await load();
    } catch (err) {
      toast(extractErrorMessage(err, "Could not enroll that student."), "info");
    } finally {
      setBusy(false);
    }
  };

  const remove = async (student: EnrolledStudentResponse) => {
    const label = student.email || student.name || "this student";
    if (!window.confirm(`Remove ${label} from this course? They will stop seeing its assignments.`)) return;
    try {
      await courseService.removeStudent(courseId, student.student_id);
      toast(`Removed ${label}.`, "info");
      await load();
    } catch (err) {
      toast(extractErrorMessage(err, "Could not remove that student."), "info");
    }
  };

  return (
    <Panel className="recent-card">
      <div className="section-heading">
        <div>
          <h2>Students</h2>
          <p>Enrolled students see this course's published assignments</p>
        </div>
      </div>
      <form className="field-block" onSubmit={enroll}>
        <label htmlFor="enroll-email">Enroll by email</label>
        <input
          id="enroll-email"
          className="field-input"
          type="email"
          placeholder="student@school.edu"
          value={email}
          onChange={(event) => setEmail(event.target.value)}
          required
        />
        <Button className="full-button" disabled={busy || !email.trim()} style={{ marginTop: 8 }}>
          <UserPlus size={14} />
          {busy ? "Enrolling…" : "Enroll student"}
        </Button>
      </form>
      {loading ? (
        <p style={{ color: "#5C6E61" }}>Loading roster…</p>
      ) : students.length ? (
        <ul style={{ listStyle: "none", padding: 0, margin: 0 }}>
          {students.map((student) => (
            <li
              key={student.student_id}
              style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 8, padding: "8px 0", borderTop: "1px solid rgba(0,0,0,.06)" }}
            >
              <span style={{ minWidth: 0 }}>
                <strong style={{ display: "block" }}>{student.name || student.email || "Student"}</strong>
                <small style={{ color: "#5C6E61", overflowWrap: "anywhere" }}>
                  {student.email || `ID ${student.student_id.slice(0, 8)}…`}
                </small>
              </span>
              <button
                type="button"
                className="icon-button"
                aria-label={`Remove ${student.email || student.name || "student"}`}
                onClick={() => void remove(student)}
              >
                <X size={14} />
              </button>
            </li>
          ))}
        </ul>
      ) : (
        <p style={{ color: "#5C6E61" }}>No students enrolled yet.</p>
      )}
    </Panel>
  );
}

export function CourseDetailPage({ courses: courseList }: { courses: Course[] }) {
  const { assignments: assignmentList, setCourses } = useAppState();
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

  const courseAssignments = assignmentList.filter((item) => item.courseId === course.id);
  const updateStudentCount = (count: number) =>
    setCourses((current) =>
      current.map((item) => (item.id === course.id && item.students !== count ? { ...item, students: count } : item))
    );

  return (
    <>
      <div className="page-heading">
        <div>
          <div className="eyebrow">COURSE DETAILS</div>
          <h1>{course.name}</h1>
          <p className="page-subtitle">
            {course.code} · {course.instructor}
          </p>
        </div>
        <div className="heading-actions">
          <Button variant="secondary" disabled onClick={() => navigate("/app/materials")}>
            <FileCheck2 size={15} />
            Materials unavailable
          </Button>
          <Button onClick={() => navigate(`/app/assignment/new?courseId=${encodeURIComponent(course.id)}`)}>
            <Plus size={15} />
            Create assignment
          </Button>
        </div>
      </div>

      <div className="metric-strip">
        {[
          ["Course enrollments", course.students, "Current roster"],
          ["Course assignments", courseAssignments.length, "Assigned to this class"],
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
        <StudentsPanel courseId={course.id} onCountChange={updateStudentCount} />
      </div>
    </>
  );
}
