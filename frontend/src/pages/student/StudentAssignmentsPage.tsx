import { useState, type Dispatch, type FormEvent, type SetStateAction } from "react";
import { useNavigate } from "react-router-dom";
import { CalendarDays, ChevronRight, FileText, Plus, X } from "lucide-react";
import * as Dialog from "@radix-ui/react-dialog";
import { useAppState } from "../../App";
import { Button, Panel, StatusBadge, useToast } from "../../components/ui";
import { IntegrationNotice } from "../../components/common/IntegrationNotice";
import { isDemoSession } from "../../services/demo-session";
import { formatDate } from "../../lib/utils";
import type { Course, Submission } from "../../types/models";

export function StudentAssignmentsPage({
  courses: courseList,
  joinedCourseIds,
  setJoinedCourseIds,
}: {
  courses: Course[];
  joinedCourseIds: string[];
  setJoinedCourseIds: Dispatch<SetStateAction<string[]>>;
  submissions: Submission[];
}) {
  const { assignments: assignmentList } = useAppState();
  const navigate = useNavigate();
  const toast = useToast();
  const demoSession = isDemoSession();
  const [dialogOpen, setDialogOpen] = useState(false);
  const visibleAssignments = assignmentList.filter((item) => item.state === "Published");

  const joinCourse = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!demoSession) {
      toast("Course enrollment is managed by your instructor in the connected backend.", "info");
      return;
    }
    const form = new FormData(event.currentTarget);
    const code = String(form.get("inviteCode") ?? "").trim().toUpperCase();
    const course = courseList.find(
      (item) => item.code.toUpperCase() === code || item.name.toUpperCase().includes(code)
    );
    if (!course) {
      toast("Course code not found. Confirm with your instructor.", "info");
      return;
    }
    if (joinedCourseIds.includes(course.id)) {
      toast(`You are already enrolled in ${course.name}.`, "info");
      return;
    }
    setJoinedCourseIds((current) => [...current, course.id]);
    setDialogOpen(false);
    toast(`Enrolled in ${course.name}!`);
  };

  return (
    <>
      <div className="page-heading">
        <div>
          <div className="eyebrow">STUDENT COURSEWORK</div>
          <h1>My assignments</h1>
          <p className="page-subtitle">A calm, clear view of what’s due, what format to prepare, and what you’ve handed in.</p>
        </div>
        <div className="heading-actions">
          <Dialog.Root open={dialogOpen} onOpenChange={setDialogOpen}>
            <Dialog.Trigger asChild>
              <Button variant="secondary" disabled={!demoSession}>
                <Plus size={15} />
                {demoSession ? "Join a course" : "Instructor enrollment"}
              </Button>
            </Dialog.Trigger>
            <Dialog.Portal>
              <Dialog.Overlay className="modal-backdrop" />
              <Dialog.Content className="modal" aria-describedby="join-course-description">
                <div className="modal-head">
                  <Dialog.Title className="modal-title">Join a course</Dialog.Title>
                  <Dialog.Close asChild>
                    <Button variant="quiet" size="icon" aria-label="Close">
                      <X size={15} />
                    </Button>
                  </Dialog.Close>
                </div>
                <Dialog.Description id="join-course-description" className="modal-description">
                  Enter the course code shared by your instructor (e.g. CS 240) to join.
                </Dialog.Description>
                <form onSubmit={joinCourse}>
                  <div className="field-block">
                    <label htmlFor="course-invite-code">Course code</label>
                    <input
                      id="course-invite-code"
                      name="inviteCode"
                      className="field-input"
                      placeholder="e.g. CS 240"
                      required
                    />
                  </div>
                  <div className="modal-actions">
                    <Dialog.Close asChild>
                      <Button type="button" variant="secondary">
                        Cancel
                      </Button>
                    </Dialog.Close>
                    <Button type="submit">Join course</Button>
                  </div>
                </form>
              </Dialog.Content>
            </Dialog.Portal>
          </Dialog.Root>
        </div>
      </div>

      {!demoSession && (
        <IntegrationNotice
          title="Course self-enrollment is unavailable"
          description="There is no student invite-code endpoint. Ask your instructor to add you; only backend-confirmed enrollments appear here."
          endpoint="Enrollment management is teacher-operated"
          tone="info"
        />
      )}

      <div className="student-assignment-list">
        {visibleAssignments.length > 0 ? (
          visibleAssignments.map((item) => {
            const course = courseList.find((c) => c.id === item.courseId);
            const actionLabel = item.submissionType === "MCQ" ? "Start assessment" : "Submit PDF";
            return (
              <Panel className="student-assignment-row" key={item.id}>
                <span className="student-assignment-icon">
                  <FileText size={17} />
                </span>
                <span className="assignment-row-copy">
                  <strong>{item.title}</strong>
                  <small>
                    {course?.code ? `${course.code} · ` : ""}
                    {item.totalMarks} marks · {item.submissionType} format
                  </small>
                </span>
                <span className="assignment-row-due">
                  <CalendarDays size={13} />
                  Due {formatDate(item.dueAt)}
                </span>
                <StatusBadge status="Published" />
                <Button
                  size="sm"
                  variant="secondary"
                  onClick={() =>
                    navigate(
                      item.submissionType === "MCQ"
                        ? `/app/student/assessment/${item.id}`
                        : `/app/student/submit/${item.id}`
                    )
                  }
                >
                  {actionLabel}
                  <ChevronRight size={13} />
                </Button>
              </Panel>
            );
          })
        ) : (
          <Panel className="empty-state" style={{ padding: "3rem", textAlign: "center", color: "#5C6E61" }}>
            No published assignments available for your enrolled courses right now. Check back as term gets underway.
          </Panel>
        )}
      </div>
    </>
  );
}
