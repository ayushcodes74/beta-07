import { useNavigate } from "react-router-dom";
import { ArrowRight, BookOpen, Check, ChevronRight, FileText, Plus } from "lucide-react";
import { useAppState } from "../../App";
import { Button, Panel, StatusBadge } from "../../components/ui";
import { formatDate } from "../../lib/utils";

export function StudentOverview() {
  const navigate = useNavigate();
  const { user, courses: courseList, assignments: assignmentList, joinedCourseIds, submissions: studentRows } = useAppState();
  const myCourses = courseList.filter((course) => joinedCourseIds.includes(course.id) || joinedCourseIds.length === 0);
  const myAssignments = assignmentList.filter((assignment) => assignment.state === "Published");
  const published = studentRows.filter(
    (item) => item.studentId === user?.id && item.state === "Published" && item.grading?.teacherApproved
  );
  const latestPublished = published[0];
  const latestAssignment = latestPublished && assignmentList.find((item) => item.id === latestPublished.assignmentId);

  return (
    <>
      <div className="page-heading">
        <div>
          <div className="eyebrow">STUDENT WORKSPACE · SPRING TERM 2026</div>
          <h1>Welcome back, {user?.name.split(" ")[0] ?? "there"}.</h1>
          <p className="page-subtitle">Stay on top of your coursework and receive transparent, teacher-approved feedback.</p>
        </div>
        <div className="heading-actions">
          <Button variant="secondary" onClick={() => navigate("/app/student/assignments")}>
            <Plus size={15} />
            Join a course
          </Button>
        </div>
      </div>

      <Panel className="student-welcome">
        <div className="student-welcome-copy">
          <span className="eyebrow">YOUR ACADEMIC JOURNEY</span>
          <h2>Small steps add up to mastery.</h2>
          <p>
            {latestPublished
              ? "Your teacher has published your evaluation. Review your feedback, strengths, and recommendations below."
              : "Your coursework, deadlines, and teacher feedback will appear here as your classes get underway."}
          </p>
          <Button variant="secondary" size="sm" onClick={() => navigate("/app/student/assignments")}>
            See assignments
            <ArrowRight size={14} />
          </Button>
        </div>
        <div className="student-progress-orb">
          <span>{myAssignments.length}</span>
          <small>tasks ready</small>
          <svg viewBox="0 0 120 120">
            <circle cx="60" cy="60" r="52" />
            <circle className="progress-circle" cx="60" cy="60" r="52" />
          </svg>
        </div>
      </Panel>

      <div className="student-stat-row">
        <Panel className="student-stat">
          <span>Enrolled courses</span>
          <strong>{myCourses.length}</strong>
          <small>Active this term</small>
        </Panel>
        <Panel className="student-stat">
          <span>Assignments available</span>
          <strong>{myAssignments.length}</strong>
          <small>Published for study</small>
        </Panel>
        <Panel className="student-stat">
          <span>Submissions made</span>
          <strong>{studentRows.length}</strong>
          <small>Handed in for review</small>
        </Panel>
      </div>

      <div className="student-columns">
        <div>
          <div className="section-heading">
            <div>
              <h2>Coming up</h2>
              <p>Plan your next study session</p>
            </div>
            <button className="text-button" onClick={() => navigate("/app/student/assignments")}>
              All assignments
              <ArrowRight size={13} />
            </button>
          </div>

          {myAssignments.slice(0, 3).map((assignment) => {
            const ownSubmission = studentRows.find(
              (item) => item.studentId === user?.id && item.assignmentId === assignment.id
            );
            const status = ownSubmission?.state ?? "Not Started";
            const destination =
              status === "Published"
                ? "/app/results"
                : assignment.submissionType === "MCQ"
                ? `/app/student/assessment/${assignment.id}`
                : `/app/student/submit/${assignment.id}`;

            return (
              <Panel key={assignment.id} className="student-assignment-card">
                <span className="course-icon">
                  <FileText size={16} />
                </span>
                <span className="assignment-card-copy">
                  <strong>{assignment.title}</strong>
                  <small>
                    {courseList.find((course) => course.id === assignment.courseId)?.code ?? "Course"} · Due{" "}
                    {formatDate(assignment.dueAt)}
                  </small>
                </span>
                <StatusBadge status={status} />
                <Button size="sm" variant="secondary" onClick={() => navigate(destination)}>
                  {status === "Published" ? "View feedback" : "Open"}
                  <ChevronRight size={13} />
                </Button>
              </Panel>
            );
          })}
          {!myAssignments.length && (
            <Panel className="empty-state" style={{ padding: "2rem", textAlign: "center", color: "#5C6E61" }}>
              No published assignments at the moment.
            </Panel>
          )}

          <div className="section-heading" style={{ marginTop: "20px" }}>
            <div>
              <h2>Recently published</h2>
              <p>Only verified, teacher-approved evaluations appear here</p>
            </div>
          </div>
          {latestPublished && latestAssignment ? (
            <Panel className="published-result-card">
              <span className="result-seal">
                <Check size={16} />
              </span>
              <span>
                <strong>{latestAssignment.title}</strong>
                <small>Teacher approved</small>
              </span>
              <strong className="result-score">
                {latestPublished.grading?.suggestedScore} <small>/ {latestAssignment.totalMarks}</small>
              </strong>
              <Button size="sm" variant="secondary" onClick={() => navigate("/app/results")}>
                View feedback
                <ChevronRight size={13} />
              </Button>
            </Panel>
          ) : (
            <Panel className="empty-state" style={{ padding: "2rem", textAlign: "center", color: "#5C6E61" }}>
              No published feedback available yet. Once your teacher approves an evaluation, it will appear here.
            </Panel>
          )}
        </div>

        <aside>
          <div className="section-heading">
            <div>
              <h2>Your courses</h2>
              <p>Enrolled this term</p>
            </div>
          </div>
          <div className="course-summary-list">
            {myCourses.slice(0, 4).map((course) => (
              <Panel className="course-summary" key={course.id}>
                <span className="course-summary-icon">
                  <BookOpen size={15} />
                </span>
                <span>
                  <strong>{course.name}</strong>
                  <small>{course.code}</small>
                </span>
                <ChevronRight size={15} />
              </Panel>
            ))}
            {!myCourses.length && (
              <Panel className="empty-state" style={{ padding: "2rem", textAlign: "center", color: "#5C6E61" }}>
                Join a course to see your classes here.
              </Panel>
            )}
          </div>
        </aside>
      </div>
    </>
  );
}

