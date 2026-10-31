import { useState, type Dispatch, type FormEvent, type SetStateAction } from "react";
import { useNavigate } from "react-router-dom";
import { ArrowRight, BookOpen, Plus, Search, X } from "lucide-react";
import { motion } from "framer-motion";
import * as Dialog from "@radix-ui/react-dialog";
import { courseService, extractErrorMessage } from "../../services/api";
import { useAppState } from "../../App";
import { Badge, Button, Panel, useToast } from "../../components/ui";
import type { Course } from "../../types/models";

export function CoursesPage({
  courses: courseList,
  setCourses,
}: {
  courses: Course[];
  setCourses: Dispatch<SetStateAction<Course[]>>;
}) {
  const { user, joinedCourseIds } = useAppState();
  const [query, setQuery] = useState("");
  const [dialogOpen, setDialogOpen] = useState(false);
  const [creating, setCreating] = useState(false);
  const navigate = useNavigate();
  const toast = useToast();
  const student = user?.role === "student";
  const visibleCourses = student
    ? courseList.filter((course) => joinedCourseIds.includes(course.id))
    : courseList;
  const filtered = visibleCourses.filter((course) =>
    `${course.name} ${course.code} ${course.instructor}`.toLowerCase().includes(query.toLowerCase())
  );

  const createCourse = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const name = String(form.get("courseName") ?? "").trim();
    if (!name) return;
    setCreating(true);
    try {
      const created = await courseService.createCourse({ name });
      setCourses((current) => [created, ...current]);
      setDialogOpen(false);
      toast(`${created.name} added successfully!`);
    } catch (err) {
      toast(extractErrorMessage(err, "Could not create course. Please try again."), "info");
    } finally {
      setCreating(false);
    }
  };

  return (
    <>
      <div className="page-heading">
        <div>
          <div className="eyebrow">ACADEMIC CURRICULUM</div>
          <h1>{student ? "My courses" : "Your courses"}</h1>
          <p className="page-subtitle">
            {student
              ? "The classes you’re enrolled in this term."
              : "Every class, thoughtfully organized with assignments and materials."}
          </p>
        </div>
        <div className="heading-actions">
          {student ? (
            <Button onClick={() => navigate("/app/student/assignments")}>
              View assignments
            </Button>
          ) : (
            <Dialog.Root open={dialogOpen} onOpenChange={setDialogOpen}>
              <Dialog.Trigger asChild>
                <Button>
                  <Plus size={15} />
                  Create course
                </Button>
              </Dialog.Trigger>
              <Dialog.Portal>
                <Dialog.Overlay className="modal-backdrop" />
                <Dialog.Content className="modal" aria-describedby="course-create-description">
                  <div className="modal-head">
                    <Dialog.Title className="modal-title">Create a course</Dialog.Title>
                    <Dialog.Close asChild>
                      <Button variant="quiet" size="icon" aria-label="Close">
                        <X size={15} />
                      </Button>
                    </Dialog.Close>
                  </div>
                  <Dialog.Description id="course-create-description" className="modal-description">
                    Set up a course workspace for assignments, materials, and student progress.
                  </Dialog.Description>
                  <form onSubmit={createCourse}>
                    <div className="field-block">
                      <label htmlFor="course-name">Course name</label>
                      <input
                        id="course-name"
                        name="courseName"
                        className="field-input"
                        placeholder="e.g. Advanced Operating Systems"
                        required
                      />
                    </div>
                    <p className="modal-description">
                      The connected backend derives a display code from the course name; custom codes are not stored.
                    </p>
                    <div className="modal-actions">
                      <Dialog.Close asChild>
                        <Button type="button" variant="secondary">
                          Cancel
                        </Button>
                      </Dialog.Close>
                      <Button type="submit" disabled={creating}>
                        {creating ? "Creating…" : "Create course"}
                      </Button>
                    </div>
                  </form>
                </Dialog.Content>
              </Dialog.Portal>
            </Dialog.Root>
          )}
        </div>
      </div>

      <div className="toolbar">
        <label className="inline-search">
          <Search size={14} />
          <input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Search courses by title or code..."
            aria-label="Search courses"
          />
        </label>
      </div>

      <div className="course-grid">
        {filtered.length ? (
          filtered.map((course, index) => (
            <motion.div
              key={course.id}
              initial={{ opacity: 0, y: 7 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: index * 0.035 }}
            >
              <Panel className="course-card">
                <div className={`course-accent accent-${index % 4}`} />
                <div className="course-card-top">
                  <span className="course-icon">
                    <BookOpen size={18} />
                  </span>
                  <Badge tone="sage">{course.code}</Badge>
                </div>
                <h3>{course.name}</h3>
                <span className="course-instructor">{course.instructor}</span>
                <div className="course-stats">
                  <div>
                    <strong>{course.students}</strong>
                    <small>Students</small>
                  </div>
                  <div>
                    <strong>{course.assignments}</strong>
                    <small>Assignments</small>
                  </div>
                </div>
                <button className="text-button" onClick={() => navigate(`/app/courses/${course.id}`)}>
                  Open course
                  <ArrowRight size={13} />
                </button>
              </Panel>
            </motion.div>
          ))
        ) : (
          <Panel className="empty-state" style={{ padding: "3rem 1.5rem", textAlign: "center", color: "#5C6E61" }}>
            {student
              ? "No instructor-managed course enrollments are available for this account yet."
              : "No courses found matching your search. Click 'Create course' to set up a new class."}
          </Panel>
        )}
      </div>
    </>
  );
}
