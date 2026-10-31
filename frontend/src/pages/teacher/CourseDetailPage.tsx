import { useCallback, useEffect, useState, type FormEvent } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { ArrowLeft, MessageCircle, Pencil, Plus, TrendingUp, UserPlus, X } from "lucide-react";
import { useAppState } from "../../App";
import { Button, Panel, StatusBadge, useToast } from "../../components/ui";
import { formatDate } from "../../lib/utils";
import { courseService, extractErrorMessage, type EnrolledStudentResponse } from "../../services/api";
import type { Course } from "../../types/models";
import { StudentPerformanceDialog } from "./StudentPerformance";
import { clearStudentNameCache } from "../../lib/useStudentNames";

function StudentsPanel({ courseId, onCountChange }: { courseId: string; onCountChange: (count: number) => void }) {
  const toast = useToast();
  const [students, setStudents] = useState<EnrolledStudentResponse[]>([]);
  const [loading, setLoading] = useState(true);
  const [email, setEmail] = useState("");
  const [busy, setBusy] = useState(false);
  // Student whose assignment-by-assignment performance chart is open.
  const [performanceFor, setPerformanceFor] = useState<{ id: string; name: string } | null>(null);

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
      clearStudentNameCache();
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
      clearStudentNameCache();
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
              <span style={{ display: "flex", flex: "0 0 auto" }}>
                <button
                  type="button"
                  className="icon-button"
                  aria-label={`Performance of ${student.name || student.email || "student"}`}
                  title="Performance"
                  onClick={() =>
                    setPerformanceFor({ id: student.student_id, name: student.name || student.email || "Student" })
                  }
                >
                  <TrendingUp size={14} />
                </button>
                <Link
                  className="icon-button"
                  to={`/app/messages?course=${courseId}&student=${student.student_id}`}
                  aria-label={`Message ${student.name || student.email || "student"}`}
                  title="Message"
                >
                  <MessageCircle size={14} />
                </Link>
                <button
                  type="button"
                  className="icon-button"
                  aria-label={`Remove ${student.email || student.name || "student"}`}
                  onClick={() => void remove(student)}
                >
                  <X size={14} />
                </button>
              </span>
            </li>
          ))}
        </ul>
      ) : (
        <p style={{ color: "#5C6E61" }}>No students enrolled yet.</p>
      )}
      <StudentPerformanceDialog courseId={courseId} student={performanceFor} onClose={() => setPerformanceFor(null)} />
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
                  <th aria-label="Actions" />
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
                      <td>
                        <Button
                          variant="secondary"
                          size="sm"
                          onClick={() => navigate(`/app/assignment/${item.id}/edit`)}
                        >
                          <Pencil size={13} />
                          Edit
                        </Button>
                      </td>
                    </tr>
                  ))
                ) : (
                  <tr>
                    <td colSpan={6} style={{ textAlign: "center", padding: "2rem", color: "#5C6E61" }}>
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
