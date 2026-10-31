import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { CalendarDays, ChevronRight, FileText, Pencil, Plus } from "lucide-react";
import { useAppState } from "../../App";
import { Button, Panel, StatusBadge } from "../../components/ui";
import { formatDate } from "../../lib/utils";

export function AssignmentsPage() {
  const navigate = useNavigate();
  const { user, assignments: assignmentList, courses: courseList } = useAppState();
  const student = user?.role === "student";
  const [selectedCourse, setSelectedCourse] = useState("all");

  const items = student
    ? assignmentList.filter((assignment) => assignment.state === "Published")
    : selectedCourse === "all"
    ? assignmentList
    : assignmentList.filter((a) => a.courseId === selectedCourse);

  return (
    <>
      <div className="page-heading">
        <div>
          <div className="eyebrow">COURSE ASSIGNMENTS</div>
          <h1>{student ? "My assignments" : "Assignments"}</h1>
          <p className="page-subtitle">
            {student
              ? "A clear view of what’s due and what you’ve submitted."
              : "Thoughtfully set up, clearly tracked, and always teacher-led."}
          </p>
        </div>
        <div className="heading-actions">
          {!student && (
            <Button onClick={() => navigate("/app/assignment/new")}>
              <Plus size={15} />
              Create assignment
            </Button>
          )}
        </div>
      </div>

      <div className="toolbar">
        <select
          className="filter-select"
          value={selectedCourse}
          onChange={(e) => setSelectedCourse(e.target.value)}
          aria-label="Filter assignments by course"
        >
          <option value="all">All courses</option>
          {courseList.map((course) => (
            <option key={course.id} value={course.id}>
              {course.name} ({course.code})
            </option>
          ))}
        </select>
      </div>

      <div className="assignment-list">
        {items.length > 0 ? (
          items.map((assignment) => {
            const course = courseList.find((c) => c.id === assignment.courseId);
            const state = student ? "Not Started" : assignment.state;
            const route =
              assignment.submissionType === "MCQ"
                ? `/app/student/assessment/${assignment.id}`
                : `/app/student/submit/${assignment.id}`;

            return (
              <Panel className="assignment-list-card" key={assignment.id}>
                <span className="course-icon">
                  <FileText size={17} />
                </span>
                <div className="assignment-list-main">
                  <strong>{assignment.title}</strong>
                  <small>
                    {course?.code ? `${course.code} · ` : ""}
                    {assignment.totalMarks} marks · {assignment.submissionType} submission
                  </small>
                </div>
                <div className="assignment-list-meta">
                  <span>
                    <CalendarDays size={13} />
                    Due {formatDate(assignment.dueAt)}
                  </span>
                </div>
                <StatusBadge status={state} />
                {!student && (
                  <Button
                    variant="secondary"
                    size="sm"
                    onClick={() => navigate(`/app/assignment/${assignment.id}/edit`)}
                  >
                    <Pencil size={13} />
                    Edit
                  </Button>
                )}
                <Button
                  variant="secondary"
                  size="sm"
                  onClick={() => navigate(student ? route : `/app/submissions`)}
                >
                  {student ? "Open assignment" : "View submissions"}
                  <ChevronRight size={13} />
                </Button>
              </Panel>
            );
          })
        ) : (
          <Panel className="empty-state" style={{ padding: "3rem 1.5rem", textAlign: "center", color: "#5C6E61" }}>
            {student
              ? "No published assignments currently available for your enrolled courses."
              : "No assignments created yet. Click 'Create assignment' to get started."}
          </Panel>
        )}
      </div>
    </>
  );
}

