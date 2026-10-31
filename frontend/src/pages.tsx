import { useRef, useState, type Dispatch, type DragEvent, type FormEvent, type SetStateAction } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import {
  Activity, AlertCircle, ArrowLeft, ArrowRight, BookOpen, CalendarDays,
  Check, CheckCircle2, ChevronLeft, ChevronRight, CloudUpload,
  FileCheck2, FileText, GraduationCap, MoreHorizontal, Plus,
  Search, ShieldCheck, Sparkles, Upload, Users, X,
} from "lucide-react";
import {
  Area, AreaChart, Bar, BarChart, CartesianGrid, Cell, ResponsiveContainer,
  Tooltip, XAxis, YAxis,
} from "recharts";
import { motion } from "framer-motion";
import * as Dialog from "@radix-ui/react-dialog";
import {
  assignmentService,
  authService,
  courseService,
  extractErrorMessage,
  submissionService,
} from "./services/api";
import { mockService } from "./services/mock-service";
import { rubrics } from "./lib/mock-data";
import { formatDate } from "./lib/utils";
import { useAppState } from "./App";
import { Avatar, Badge, Button, ConfirmDialog, GlassPanel, Panel, StatusBadge, useToast } from "./components/ui";
import type { Assignment, Course, CourseMaterial, Question, Submission, User } from "./types/models";

function PageHeader({ eyebrow = "TRUSTGRADE WORKSPACE", title, subtitle, action }: { eyebrow?: string; title: string; subtitle: string; action?: React.ReactNode }) {
  return <div className="page-heading"><div><div className="eyebrow">{eyebrow}</div><h1>{title}</h1><p className="page-subtitle">{subtitle}</p></div>{action && <div className="heading-actions">{action}</div>}</div>;
}

function SectionTitle({ title, subtitle, action }: { title: string; subtitle?: string; action?: React.ReactNode }) {
  return <div className="section-heading"><div><h2>{title}</h2>{subtitle && <p>{subtitle}</p>}</div>{action}</div>;
}

function TrendChart({ height = 190 }: { height?: number }) {
  const data = [
    { week: "W1", average: 76 }, { week: "W2", average: 78 }, { week: "W3", average: 77 },
    { week: "W4", average: 81 }, { week: "W5", average: 84 }, { week: "W6", average: 83 },
    { week: "W7", average: 86 }, { week: "W8", average: 88 },
  ];
  return <div className="chart-area" style={{ height }}>
    <ResponsiveContainer width="100%" height="100%">
      <AreaChart data={data} margin={{ top: 16, right: 12, bottom: 0, left: -20 }}>
        <defs><linearGradient id="roseWash" x1="0" x2="0" y1="0" y2="1"><stop offset="0%" stopColor="#b44446" stopOpacity={0.15} /><stop offset="95%" stopColor="#b44446" stopOpacity={0} /></linearGradient></defs>
        <CartesianGrid vertical={false} stroke="#ecebe5" strokeDasharray="3 5" />
        <XAxis dataKey="week" axisLine={false} tickLine={false} tick={{ fill: "#96978f", fontSize: 10 }} dy={10} />
        <YAxis domain={[60, 100]} ticks={[60, 70, 80, 90, 100]} axisLine={false} tickLine={false} tick={{ fill: "#96978f", fontSize: 9 }} />
        <Tooltip cursor={{ stroke: "#d7d9d1", strokeDasharray: "3 4" }} contentStyle={{ borderRadius: 9, border: "1px solid #eeede8", boxShadow: "0 6px 20px #20231f12", fontSize: 10 }} formatter={(value) => [`${value} / 100`, "Average mark"]} />
        <Area type="monotone" dataKey="average" stroke="#64242f" strokeWidth={2.2} fill="url(#roseWash)" activeDot={{ r: 4, fill: "#fff", stroke: "#64242f", strokeWidth: 2 }} />
      </AreaChart>
    </ResponsiveContainer>
  </div>;
}

const distribution = [{ name: "A", value: 38, fill: "#64242f" }, { name: "B", value: 61, fill: "#8e4249" }, { name: "C", value: 74, fill: "#b44446" }, { name: "D", value: 51, fill: "#d68b88" }, { name: "F", value: 24, fill: "#ead4d2" }];

function DistributionChart() {
  return <div className="distribution-bars"><ResponsiveContainer width="100%" height="100%"><BarChart data={distribution} margin={{ top: 10, right: 4, bottom: 0, left: -20 }} barCategoryGap="28%">
    <CartesianGrid vertical={false} stroke="#eee9e7" strokeDasharray="3 5" />
    <XAxis dataKey="name" axisLine={false} tickLine={false} tick={{ fill: "#969091", fontSize: 10 }} dy={8} />
    <YAxis axisLine={false} tickLine={false} tick={{ fill: "#969091", fontSize: 9 }} />
    <Tooltip cursor={{ fill: "#f8f2f1" }} contentStyle={{ borderRadius: 9, border: "1px solid #eee8e7", boxShadow: "0 6px 20px #29252512", fontSize: 10 }} formatter={(value) => [`${value} students`, "Grade"]} />
    <Bar dataKey="value" radius={[4, 4, 0, 0]}>{distribution.map((item) => <Cell key={item.name} fill={item.fill} />)}</Bar>
  </BarChart></ResponsiveContainer></div>;
}

function StatCard({ title, value, note, change, icon: Icon, featured = false, alert = false }: { title: string; value: string; note: string; change: string; icon: typeof Users; featured?: boolean; alert?: boolean }) {
  return <Panel className={`stat-card ${featured ? "stat-feature" : ""} ${alert ? "stat-alert" : ""}`}><div className="stat-top"><span>{title}</span><span className="stat-icon"><Icon size={16} /></span></div><div className="stat-value-row"><strong>{value}</strong><span className="stat-change">{change}</span></div><div className="stat-foot">{note}</div><svg className="stat-spark" viewBox="0 0 84 30" aria-hidden="true"><polyline points="0,23 12,19 24,20 36,12 48,15 60,7 72,10 84,3" fill="none" stroke="#b44446" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" /></svg></Panel>;
}

function RecentSubmissions({ rows }: { rows: Submission[] }) {
  const { user, assignments: assignmentList, people } = useAppState();
  const navigate = useNavigate();
  if (!rows.length) {
    return <div className="table-empty" style={{ padding: "1.5rem", textAlign: "center" }}>No student submissions received yet.</div>;
  }
  const submissionDetails = rows.map((submission) => ({
    submission,
    student: people.find((person) => person.id === submission.studentId),
    assignment: assignmentList.find((item) => item.id === submission.assignmentId),
  }));
  return <div className="table-scroll"><table className="data-table"><thead><tr><th>Student</th><th>Assignment</th><th>Submitted</th><th>OCR</th><th>AI grade</th><th>Status</th><th>Action</th></tr></thead><tbody>
    {submissionDetails.map(({ submission, student, assignment }) => <tr key={submission.id}>
      <td><span className="student-name">{student && <Avatar name={student.name} initials={student.initials} />}{student?.name ?? "Student"}</span></td>
      <td>{assignment?.title ?? "Assignment"}</td><td>{formatDate(submission.submittedAt)}</td>
      <td><StatusBadge status={submission.ocr.state} /></td>
      <td className="score-cell">{submission.grading ? `${submission.grading.suggestedScore} / ${assignment?.totalMarks ?? 20}` : "—"}</td>
      <td><StatusBadge status={submission.state} /></td>
      <td><button className="text-button" onClick={() => navigate(user?.role === "teacher" ? `/app/grading/${submission.id}` : `/app/student/submit/${submission.assignmentId}`)}>{user?.role === "teacher" ? "Review" : "Open"}<ChevronRight size={13} /></button></td>
    </tr>)}
  </tbody></table></div>;
}

function TeacherOverview() {
  const navigate = useNavigate();
  const { user, courses: courseList, assignments: assignmentList, submissions } = useAppState();
  const recentSubmissions = [...submissions].sort((a, b) => Date.parse(b.submittedAt) - Date.parse(a.submittedAt)).slice(0, 4);
  const activeAssignment = assignmentList[0];
  const upcomingDeadlines = assignmentList.slice(0, 3);
  const totalStudents = courseList.reduce((acc, c) => acc + (c.students || 0), 0);

  return <>
    <div className="welcome-row">
      <div>
        <div className="eyebrow">FACULTY WORKSPACE · SPRING TERM 2026</div>
        <h1>Good morning, {user?.name.split(" ")[0] ?? "Professor"}.</h1>
        <p className="page-subtitle">Your classroom, intelligently organized.</p>
        <div className="welcome-context">
          <span>{courseList.length} course{courseList.length === 1 ? "" : "s"}</span><i />
          <span>{assignmentList.length} assignment{assignmentList.length === 1 ? "" : "s"}</span><i />
          <span>{submissions.length} submission{submissions.length === 1 ? "" : "s"}</span>
        </div>
      </div>
      <Button onClick={() => navigate("/app/assignment/new")}><Plus size={16} />Create assignment</Button>
    </div>
    <div className="stat-grid dashboard-stats">{[
      { title: "Active courses", value: String(courseList.length), note: "Connected via backend", change: `${courseList.length} registered`, icon: BookOpen, featured: true },
      { title: "Assignments", value: String(assignmentList.length), note: "Total created", change: `${assignmentList.filter(a => a.state === "Published").length} published`, icon: FileText, alert: assignmentList.length === 0 },
      { title: "Enrolled students", value: String(totalStudents), note: "Across your courses", change: "Roster count", icon: Users },
      { title: "Submissions", value: String(submissions.length), note: "In evaluation queue", change: "Live count", icon: Activity },
    ].map((item) => <StatCard key={item.title} {...item} />)}</div>
    <div className="dashboard-grid">
      <Panel className="grading-feature">
        <div className="feature-top">
          <div className="feature-title"><span className="feature-symbol"><Sparkles size={16} /></span><span><strong>Assignment Velocity</strong><small>Review progress across active assignments.</small></span></div>
          {activeAssignment && <Badge tone="sage"><i className="live-dot" />{activeAssignment.state}</Badge>}
        </div>
        {activeAssignment ? (
          <>
            <h2 className="feature-assignment">{activeAssignment.title}</h2>
            <p className="feature-course">Due {formatDate(activeAssignment.dueAt)}</p>
            <div className="progress-row"><span><strong>{submissions.length}</strong> submissions received</span><span>{activeAssignment.totalMarks} marks</span></div>
            <div className="progress-track"><span style={{ width: submissions.length > 0 ? "40%" : "5%" }} /></div>
            <div className="feature-bottom">
              <div className="feature-meta"><span><CheckCircle2 size={13} />{activeAssignment.submissionType} format</span></div>
              <Button variant="secondary" size="sm" onClick={() => navigate("/app/submissions")}>View queue<ArrowRight size={14} /></Button>
            </div>
          </>
        ) : (
          <div style={{ padding: "2rem 0", color: "var(--color-text-muted, #71717a)" }}>
            <p>No assignments created yet. Set up an assignment to begin receiving submissions.</p>
            <Button size="sm" onClick={() => navigate("/app/assignment/new")} style={{ marginTop: "1rem" }}><Plus size={14} />Create first assignment</Button>
          </div>
        )}
        <span className="feature-watermark"><ShieldCheck size={138} strokeWidth={0.55} /></span>
      </Panel>
      <Panel className="deadline-card dashboard-deadlines">
        <SectionTitle title="Upcoming deadlines" subtitle="Assignments created for your classes" action={<button className="text-button" onClick={() => navigate("/app/assignments")}>View all<ArrowRight size={13} /></button>} />
        <div className="timeline">
          {upcomingDeadlines.length > 0 ? (
            upcomingDeadlines.map((item) => (
              <div className="timeline-item" key={item.id}>
                <strong>{item.title}</strong>
                <div><span>{item.totalMarks} marks · {item.submissionType}</span><b>Due {formatDate(item.dueAt)}</b></div>
              </div>
            ))
          ) : (
            <p className="table-empty">No deadlines scheduled yet.</p>
          )}
        </div>
      </Panel>
    </div>
    <div className="analytics-grid">
      <Panel className="chart-card"><SectionTitle title="Class performance trend" subtitle="Weekly distribution" /><div className="chart-total">84.6 <span>↑ Stable</span></div><TrendChart /></Panel>
      <Panel className="chart-card"><SectionTitle title="Grade distribution" subtitle="Class grade overview" /><DistributionChart /></Panel>
    </div>
    <Panel className="recent-card dashboard-recent">
      <SectionTitle title="Recent submissions" subtitle="Your latest classroom activity" action={<button className="text-button" onClick={() => navigate("/app/submissions")}>View all<ArrowRight size={13} /></button>} />
      <RecentSubmissions rows={recentSubmissions} />
    </Panel>
  </>;
}

function StudentOverview() {
  const navigate = useNavigate();
  const { user, courses: courseList, assignments: assignmentList, joinedCourseIds, submissions: studentRows } = useAppState();
  const myCourses = courseList.filter((course) => joinedCourseIds.includes(course.id) || joinedCourseIds.length === 0);
  const myAssignments = assignmentList.filter((assignment) => assignment.state === "Published");
  const published = studentRows.filter((item) => item.studentId === user?.id && item.state === "Published" && item.grading?.teacherApproved);
  const latestPublished = published[0];
  const latestAssignment = latestPublished && assignmentList.find((item) => item.id === latestPublished.assignmentId);

  return <>
    <div className="page-heading">
      <div>
        <div className="eyebrow">STUDENT WORKSPACE · SPRING TERM 2026</div>
        <h1>Welcome back, {user?.name.split(" ")[0] ?? "there"}.</h1>
        <p className="page-subtitle">Stay on top of your coursework. You’re making steady progress.</p>
      </div>
      <Button variant="secondary" onClick={() => navigate("/app/student/assignments")}><Plus size={15} />Join a course</Button>
    </div>
    <Panel className="student-welcome">
      <div className="student-welcome-copy">
        <span className="eyebrow">YOUR ACADEMIC JOURNEY</span>
        <h2>Small steps add up.</h2>
        <p>{latestPublished ? "Your teacher has published feedback. Take a moment to review what went well and what to try next." : "Your coursework and teacher feedback will appear here as your classes get underway."}</p>
        <Button variant="secondary" size="sm" onClick={() => navigate("/app/student/assignments")}>See assignments<ArrowRight size={14} /></Button>
      </div>
      <div className="student-progress-orb"><span>{myAssignments.length}</span><small>tasks ready</small><svg viewBox="0 0 120 120"><circle cx="60" cy="60" r="52" /><circle className="progress-circle" cx="60" cy="60" r="52" /></svg></div>
    </Panel>
    <div className="student-stat-row">
      <Panel className="student-stat"><span>Enrolled courses</span><strong>{myCourses.length}</strong><small>Active this term</small></Panel>
      <Panel className="student-stat"><span>Assignments available</span><strong>{myAssignments.length}</strong><small>Published for study</small></Panel>
      <Panel className="student-stat"><span>Submissions made</span><strong>{studentRows.length}</strong><small>Handed in for review</small></Panel>
    </div>
    <div className="student-columns">
      <div>
        <SectionTitle title="Coming up" subtitle="Plan your next study session" action={<button className="text-button" onClick={() => navigate("/app/student/assignments")}>All assignments<ArrowRight size={13} /></button>} />
        {myAssignments.slice(0, 3).map((assignment) => {
          const ownSubmission = studentRows.find((item) => item.studentId === user?.id && item.assignmentId === assignment.id);
          const status = ownSubmission?.state ?? "Not Started";
          const destination = status === "Published" ? "/app/results" : assignment.submissionType === "MCQ" ? `/app/student/assessment/${assignment.id}` : `/app/student/submit/${assignment.id}`;
          return (
            <Panel key={assignment.id} className="student-assignment-card">
              <span className="course-icon"><FileText size={16} /></span>
              <span className="assignment-card-copy">
                <strong>{assignment.title}</strong>
                <small>{courseList.find((course) => course.id === assignment.courseId)?.code ?? "Course"} · Due {formatDate(assignment.dueAt)}</small>
              </span>
              <StatusBadge status={status} />
              <Button size="sm" variant="secondary" onClick={() => navigate(destination)}>{status === "Published" ? "View feedback" : "Open"}<ChevronRight size={13} /></Button>
            </Panel>
          );
        })}
        {!myAssignments.length && <Panel className="empty-state">No published assignments at the moment.</Panel>}
        <SectionTitle title="Recently published" subtitle="Only teacher-approved results appear here" />
        {latestPublished && latestAssignment ? (
          <Panel className="published-result-card">
            <span className="result-seal"><Check size={16} /></span>
            <span><strong>{latestAssignment.title}</strong><small>Teacher approved</small></span>
            <strong className="result-score">{latestPublished.grading?.suggestedScore} <small>/ {latestAssignment.totalMarks}</small></strong>
            <Button size="sm" variant="secondary" onClick={() => navigate("/app/results")}>View feedback<ChevronRight size={13} /></Button>
          </Panel>
        ) : (
          <Panel className="empty-state">No published feedback available yet.</Panel>
        )}
      </div>
      <aside>
        <SectionTitle title="Your courses" subtitle="This term" />
        <div className="course-summary-list">
          {myCourses.slice(0, 3).map((course) => (
            <Panel className="course-summary" key={course.id}>
              <span className="course-summary-icon"><BookOpen size={15} /></span>
              <span><strong>{course.name}</strong><small>{course.code}</small></span>
              <ChevronRight size={15} />
            </Panel>
          ))}
          {!myCourses.length && <Panel className="empty-state">Join a course to see your classes here.</Panel>}
        </div>
      </aside>
    </div>
  </>;
}

export function OverviewPage() {
  const { user } = useAppState();
  return user?.role === "student" ? <StudentOverview /> : <TeacherOverview />;
}

export function CoursesPage({ courses: courseList, setCourses }: { courses: Course[]; setCourses: Dispatch<SetStateAction<Course[]>> }) {
  const { user, joinedCourseIds } = useAppState();
  const [query, setQuery] = useState("");
  const [dialogOpen, setDialogOpen] = useState(false);
  const [courseFilter, setCourseFilter] = useState("All courses");
  const [creating, setCreating] = useState(false);
  const navigate = useNavigate();
  const toast = useToast();
  const student = user?.role === "student";
  const visibleCourses = student ? courseList.filter((course) => joinedCourseIds.includes(course.id) || joinedCourseIds.length === 0) : courseList;
  const filtered = visibleCourses.filter((course) => `${course.name} ${course.code} ${course.instructor}`.toLowerCase().includes(query.toLowerCase()));

  const createCourse = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const name = String(form.get("courseName") ?? "").trim();
    const code = String(form.get("courseCode") ?? "").trim().toUpperCase();
    if (!name || !code) return;
    if (courseList.some((course) => course.code.toLowerCase() === code.toLowerCase())) {
      toast("A course with this code already exists in your workspace.", "info");
      return;
    }
    setCreating(true);
    try {
      const created = await courseService.createCourse({
        name: `${name} (${code})`,
        description: `Course Code: ${code}`,
      });
      setCourses((current) => [created, ...current]);
      setDialogOpen(false);
      toast(`${created.name} added successfully!`);
    } catch (err) {
      toast(extractErrorMessage(err, "Could not create course. Please try again."), "info");
    } finally {
      setCreating(false);
    }
  };

  return <>
    <PageHeader
      title={student ? "My courses" : "Your courses"}
      subtitle={student ? "The classes you’re enrolled in this term." : "Every class, thoughtfully brought together."}
      action={
        student ? (
          <Button onClick={() => navigate("/app/student/assignments")}><Plus size={15} />Join a course</Button>
        ) : (
          <Dialog.Root open={dialogOpen} onOpenChange={setDialogOpen}>
            <Dialog.Trigger asChild><Button><Plus size={15} />Create course</Button></Dialog.Trigger>
            <Dialog.Portal>
              <Dialog.Overlay className="modal-backdrop" />
              <Dialog.Content className="modal" aria-describedby="course-create-description">
                <div className="modal-head">
                  <Dialog.Title className="modal-title">Create a course</Dialog.Title>
                  <Dialog.Close asChild><Button variant="quiet" size="icon" aria-label="Close"><X size={15} /></Button></Dialog.Close>
                </div>
                <Dialog.Description id="course-create-description" className="modal-description">
                  Set up a course workspace for assignments, materials, and student progress.
                </Dialog.Description>
                <form onSubmit={createCourse}>
                  <div className="field-block"><label htmlFor="course-name">Course name</label><input id="course-name" name="courseName" className="field-input" placeholder="e.g. Applied Computing" required /></div>
                  <div className="field-block"><label htmlFor="course-code">Course code</label><input id="course-code" name="courseCode" className="field-input" placeholder="e.g. CS 240" required /></div>
                  <div className="modal-actions">
                    <Dialog.Close asChild><Button type="button" variant="secondary">Cancel</Button></Dialog.Close>
                    <Button type="submit" disabled={creating}>{creating ? "Creating…" : "Create course"}</Button>
                  </div>
                </form>
              </Dialog.Content>
            </Dialog.Portal>
          </Dialog.Root>
        )
      }
    />
    <div className="toolbar">
      <label className="inline-search">
        <Search size={14} />
        <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search courses..." aria-label="Search courses" />
      </label>
      <select className="filter-select" aria-label="Term"><option>Spring term 2026</option></select>
      <select className="filter-select" aria-label="Activity filter" value={courseFilter} onChange={(event) => setCourseFilter(event.target.value)}><option>All courses</option></select>
    </div>
    <div className="course-grid">
      {filtered.length ? (
        filtered.map((course, index) => (
          <motion.div key={course.id} initial={{ opacity: 0, y: 7 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: index * 0.035 }}>
            <Panel className="course-card">
              <div className={`course-accent accent-${index % 4}`} />
              <div className="course-card-top"><span className="course-icon"><BookOpen size={18} /></span><Badge>{course.code}</Badge></div>
              <h3>{course.name}</h3>
              <span className="course-instructor">{course.instructor}</span>
              <div className="course-stats">
                <div><strong>{course.students}</strong><small>Students</small></div>
                <div><strong>{course.assignments}</strong><small>Assignments</small></div>
              </div>
              <button className="text-button" onClick={() => navigate(`/app/courses/${course.id}`)}>Open course<ArrowRight size={13} /></button>
            </Panel>
          </motion.div>
        ))
      ) : (
        <Panel className="empty-state">
          {student ? "You are not enrolled in any courses yet." : "No courses found. Click 'Create course' to set up a new class."}
        </Panel>
      )}
    </div>
  </>;
}

export function CourseDetailPage({ courses: courseList }: { courses: Course[] }) {
  const { assignments: assignmentList } = useAppState();
  const { courseId } = useParams();
  const navigate = useNavigate();
  const course = courseList.find((item) => item.id === courseId);
  if (!course) return <NotFoundPage />;
  const courseAssignments = assignmentList.filter((item) => item.courseId === course.id || !item.courseId);

  return <>
    <PageHeader
      title={course.name}
      subtitle={`${course.code} · ${course.instructor} · Spring term 2026`}
      action={
        <>
          <Button variant="secondary" onClick={() => navigate("/app/materials")}><FileCheck2 size={15} />Course materials</Button>
          <Button onClick={() => navigate("/app/assignment/new")}><Plus size={15} />Create assignment</Button>
        </>
      }
    />
    <div className="metric-strip">
      {[
        ["Enrolled students", course.students, "Active this term"],
        ["Assignments", courseAssignments.length, "Across this course"],
      ].map(([label, value, note]) => (
        <Panel className="metric-card" key={label.toString()}><span>{label}</span><strong>{value}</strong><small>{note}</small></Panel>
      ))}
    </div>
    <div className="course-detail-grid">
      <Panel className="recent-card">
        <SectionTitle title="Course assignments" subtitle="Recent work and grading progress" />
        <div className="table-scroll">
          <table className="data-table">
            <thead><tr><th>Assignment</th><th>Due</th><th>Grading state</th></tr></thead>
            <tbody>
              {courseAssignments.length ? (
                courseAssignments.map((item) => (
                  <tr key={item.id}>
                    <td>{item.title}</td>
                    <td>{formatDate(item.dueAt)}</td>
                    <td><StatusBadge status={item.state} /></td>
                  </tr>
                ))
              ) : (
                <tr><td colSpan={3}>No assignments yet for this course.</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </Panel>
    </div>
  </>;
}

export function AssignmentsPage() {
  const navigate = useNavigate();
  const { user, assignments: assignmentList, courses: courseList } = useAppState();
  const student = user?.role === "student";
  const items = student ? assignmentList.filter((assignment) => assignment.state === "Published") : assignmentList;

  return <>
    <PageHeader
      title={student ? "My assignments" : "Assignments"}
      subtitle={student ? "A clear view of what’s due and what you’ve submitted." : "Thoughtfully set up, clearly tracked, and always teacher-led."}
      action={!student && <Button onClick={() => navigate("/app/assignment/new")}><Plus size={15} />Create assignment</Button>}
    />
    <div className="toolbar">
      <div className="segmented"><button className="segment active">All</button></div>
      <select className="filter-select">
        <option>All courses</option>
        {courseList.map((course) => <option key={course.id}>{course.name}</option>)}
      </select>
    </div>
    <div className="assignment-list">
      {items.length > 0 ? (
        items.map((assignment) => {
          const state = student ? "Not Started" : assignment.state;
          const route = assignment.submissionType === "MCQ" ? `/app/student/assessment/${assignment.id}` : `/app/student/submit/${assignment.id}`;
          return (
            <Panel className="assignment-list-card" key={assignment.id}>
              <span className="course-icon"><FileText size={17} /></span>
              <div className="assignment-list-main">
                <strong>{assignment.title}</strong>
                <small>{assignment.totalMarks} marks · {assignment.submissionType} submission</small>
              </div>
              <div className="assignment-list-meta">
                <span><CalendarDays size={13} />Due {formatDate(assignment.dueAt)}</span>
              </div>
              <StatusBadge status={state} />
              <Button variant="secondary" size="sm" onClick={() => navigate(student ? route : `/app/submissions`)}>
                {student ? "Open assignment" : "View submissions"}<ChevronRight size={13} />
              </Button>
            </Panel>
          );
        })
      ) : (
        <Panel className="empty-state">
          {student ? "No published assignments currently available." : "No assignments created yet. Click 'Create assignment' to get started."}
        </Panel>
      )}
    </div>
  </>;
}

export function AssignmentEditor({ courses: courseList, assignments: _assignmentList, setAssignments }: {
  courses: Course[];
  assignments: Assignment[];
  setAssignments: Dispatch<SetStateAction<Assignment[]>>;
}) {
  const navigate = useNavigate();
  const toast = useToast();
  const [questions, setQuestions] = useState<Question[]>([
    { id: crypto.randomUUID(), prompt: "", type: "Subjective", marks: 5, expectedAnswer: "" },
  ]);
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [dueAt, setDueAt] = useState("2026-11-07T23:59");
  const [rubricId, setRubricId] = useState(rubrics[0].id);
  const [difficulty, setDifficulty] = useState("Mixed");
  const [count, setCount] = useState("3");
  const [type, setType] = useState<"Subjective" | "MCQ" | "Mixed">("Mixed");
  const [generating, setGenerating] = useState(false);
  const [saving, setSaving] = useState(false);
  const [courseId, setCourseId] = useState(courseList[0]?.id ?? "");
  const total = questions.reduce((sum, item) => sum + item.marks, 0);

  const updateQuestion = (id: string, patch: Partial<Question>) =>
    setQuestions((current) => current.map((item) => (item.id === id ? { ...item, ...patch } : item)));

  const generate = async () => {
    setGenerating(true);
    try {
      const generated = await mockService.generateQuestions(Number(count), type, difficulty);
      setQuestions((current) => [...current.filter((q) => q.prompt.trim()), ...generated]);
      toast(`${generated.length} draft question suggestions ready. Review each before saving.`, "info");
    } finally {
      setGenerating(false);
    }
  };

  const saveAssignment = async (state: Assignment["state"]) => {
    const cleanTitle = title.trim();
    if (!cleanTitle) { toast("Add an assignment title before saving.", "info"); return; }
    if (!questions.length || questions.some((q) => !q.prompt.trim()) || total <= 0) {
      toast("Add question prompts and valid marks before saving.", "info");
      return;
    }
    const deadline = new Date(dueAt);
    if (Number.isNaN(deadline.valueOf())) { toast("Choose a valid due date before saving.", "info"); return; }

    setSaving(true);
    try {
      let created = await assignmentService.createAssignment({
        title: cleanTitle,
        description: description.trim(),
        dueAt: deadline.toISOString(),
        totalMarks: total,
        questions: questions.map((q) => ({ ...q, prompt: q.prompt.trim() })),
      });

      if (state === "Published") {
        created = await assignmentService.publishAssignment(created.id);
      }
      created.courseId = courseId;
      setAssignments((current) => [created, ...current]);
      toast(state === "Published" ? "Assignment created and published to students!" : "Assignment draft saved successfully.");
      navigate("/app/assignments");
    } catch (err) {
      toast(extractErrorMessage(err, "Could not save assignment. Check all fields and try again."), "info");
    } finally {
      setSaving(false);
    }
  };

  return <>
    <PageHeader
      title="Create assignment"
      subtitle="Give your class a clear, thoughtful next step."
      action={
        <>
          <Button variant="secondary" disabled={saving} onClick={() => saveAssignment("Draft")}><FileText size={15} />Save draft</Button>
          <Button disabled={saving} onClick={() => saveAssignment("Published")}><Upload size={15} />Publish assignment</Button>
        </>
      }
    />
    <div className="editor-layout">
      <div className="editor-main">
        <Panel className="editor-card">
          <SectionTitle title="Assignment details" />
          <div className="field-block"><label htmlFor="assignment-title">Assignment title</label><input id="assignment-title" className="field-input" value={title} onChange={(event) => setTitle(event.target.value)} placeholder="e.g. Data Structures — Assignment 04" /></div>
          <div className="field-block"><label htmlFor="assignment-description">Description for students</label><textarea id="assignment-description" className="field-textarea" value={description} onChange={(event) => setDescription(event.target.value)} placeholder="Set the context and let students know what they’ll learn..." /></div>
        </Panel>
        <Panel className="editor-card">
          <SectionTitle title="Questions" subtitle={`${questions.length} questions · ${total} marks total`} />
          <div className="question-list">
            {questions.map((question, index) => (
              <QuestionEditor key={question.id} question={question} index={index} onChange={(patch) => updateQuestion(question.id, patch)} onDelete={() => setQuestions((current) => current.filter((item) => item.id !== question.id))} onMove={() => setQuestions((current) => { if (!index) return current; const next = [...current]; [next[index - 1], next[index]] = [next[index], next[index - 1]]; return next; })} />
            ))}
          </div>
          <Button className="add-question-button" variant="secondary" onClick={() => setQuestions((current) => [...current, { id: crypto.randomUUID(), prompt: "", type: "Subjective", marks: 5, expectedAnswer: "" }])}><Plus size={14} />Add a question</Button>
        </Panel>
      </div>
      <aside className="editor-side">
        <Panel className="ai-panel">
          <div className="ai-title"><span className="feature-symbol"><Sparkles size={15} /></span><div><strong>Generate with AI</strong><small>A starting point, always yours to review.</small></div></div>
          <div className="field-block"><label>Difficulty</label><div className="difficulty-options">{["Easy", "Medium", "Hard", "Mixed"].map((item) => <button key={item} className={difficulty === item ? "active" : ""} onClick={() => setDifficulty(item)}>{item}</button>)}</div></div>
          <div className="field-block"><label htmlFor="question-count">Question count</label><select id="question-count" className="field-select" value={count} onChange={(event) => setCount(event.target.value)}>{["3", "5", "8"].map((item) => <option key={item} value={item}>{item} questions</option>)}</select></div>
          <div className="field-block"><label htmlFor="question-type">Question type</label><select id="question-type" className="field-select" value={type} onChange={(event) => setType(event.target.value as typeof type)}><option value="Mixed">Mix of subjective &amp; MCQ</option><option value="Subjective">Subjective only</option><option value="MCQ">MCQ only</option></select></div>
          <Button className="full-button" disabled={generating} onClick={generate}>{generating ? "Drafting suggestions…" : "Generate question prompts"}</Button>
        </Panel>
        <Panel className="editor-card">
          <SectionTitle title="Assignment settings" />
          <div className="field-block">
            <label htmlFor="course-select">Course</label>
            <select id="course-select" className="field-select" value={courseId} onChange={(event) => setCourseId(event.target.value)}>
              {courseList.map((course) => <option value={course.id} key={course.id}>{course.name} · {course.code}</option>)}
              {!courseList.length && <option value="">No courses created yet</option>}
            </select>
          </div>
          <div className="field-block"><label htmlFor="due-date">Due date</label><input id="due-date" className="field-input" type="datetime-local" value={dueAt} onChange={(event) => setDueAt(event.target.value)} /></div>
          <div className="field-block"><label htmlFor="total-marks">Total marks</label><input id="total-marks" className="field-input" type="number" value={total} readOnly /></div>
          <div className="field-block"><label htmlFor="rubric-select">Rubric template</label><select id="rubric-select" className="field-select" value={rubricId} onChange={(event) => setRubricId(event.target.value)}>{rubrics.map((rubric) => <option value={rubric.id} key={rubric.id}>{rubric.name}</option>)}</select></div>
        </Panel>
      </aside>
    </div>
  </>;
}

function QuestionEditor({ question, index, onChange, onDelete, onMove }: { question: Question; index: number; onChange: (patch: Partial<Question>) => void; onDelete: () => void; onMove: () => void }) {
  return <article className="question-card"><div className="question-head"><div className="question-label"><span className="question-number">{index + 1}</span>Question {index + 1}<Badge>{question.type}</Badge></div><div className="question-tools"><button className="icon-button" aria-label="Move question up" onClick={onMove}><ChevronLeft size={14} /></button><button className="icon-button" aria-label="Delete question" onClick={onDelete}><X size={14} /></button></div></div><div className="question-two-col"><div className="field-block"><label>Question prompt</label><textarea className="field-textarea" value={question.prompt} onChange={(event) => onChange({ prompt: event.target.value })} placeholder="Write your question..." /></div><div className="field-block"><label>Type · marks</label><select className="field-select" value={question.type} onChange={(event) => onChange({ type: event.target.value as Question["type"] })}><option value="Subjective">Subjective</option><option value="MCQ">MCQ</option></select><input className="field-input question-mark-input" type="number" min={1} value={question.marks} onChange={(event) => onChange({ marks: Number(event.target.value) })} aria-label={`Marks for question ${index + 1}`} /></div></div><div className="field-block expected-answer"><label>{question.type === "MCQ" ? "Correct answer" : "Expected answer / marking guidance"}</label><textarea className="field-textarea" value={question.expectedAnswer} onChange={(event) => onChange({ expectedAnswer: event.target.value })} placeholder="Provide expected reasoning, not just keywords." /></div>{question.type === "MCQ" && <div className="mcq-options">{(question.options ?? ["Option A", "Option B", "Option C", "Option D"]).map((option, optionIndex) => <label key={optionIndex}><input type="radio" name={`correct-${question.id}`} checked={(question.correctOption ?? 0) === optionIndex} onChange={() => onChange({ correctOption: optionIndex })} /><input value={option} onChange={(event) => onChange({ options: (question.options ?? ["Option A", "Option B", "Option C", "Option D"]).map((item, current) => current === optionIndex ? event.target.value : item) })} aria-label={`Option ${optionIndex + 1}`} /></label>)}</div>}</article>;
}

export function MaterialsPage({ materials: fileList, setMaterials }: { materials: CourseMaterial[]; setMaterials: Dispatch<SetStateAction<CourseMaterial[]>> }) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [filter, setFilter] = useState("All files");
  const [dragging, setDragging] = useState(false);
  const toast = useToast();
  const addFiles = (files: FileList | null) => {
    if (!files) return;
    const valid: CourseMaterial[] = [];
    for (const file of Array.from(files)) {
      const extension = file.name.split(".").pop()?.toLowerCase();
      if (!["pdf", "ppt", "pptx", "doc", "docx", "txt"].includes(extension ?? "")) { toast(`${file.name}: use PDF, PPTX, DOCX, or TXT files.`, "info"); continue; }
      if (file.size > 25 * 1024 * 1024) { toast(`${file.name}: file exceeds 25 MB limit.`, "info"); continue; }
      valid.push({ id: crypto.randomUUID(), name: file.name, category: extension?.startsWith("ppt") ? "Lecture slides" : extension === "doc" || extension === "docx" ? "Notes" : "Reference", size: `${(file.size / 1024 / 1024).toFixed(1)} MB`, uploadedAt: new Date().toISOString(), state: "Ready", indexing: "Ready" });
    }
    if (valid.length) { setMaterials((current) => [...valid, ...current]); toast(`${valid.length} file(s) staged.`); }
  };
  const visible = fileList.filter((file) => filter === "All files" || (filter === "Course docs" ? ["Syllabus", "Rulebook", "Rubric"].includes(file.category) : ["Notes", "Reference"].includes(file.category)));

  return <>
    <PageHeader title="Course materials" subtitle="Keep the knowledge behind every assignment in one place." action={<Button onClick={() => inputRef.current?.click()}><Plus size={15} />Add materials</Button>} />
    <div className="toolbar">
      <div className="segmented">{["All files", "Course docs", "Reference"].map((item) => <button className={filter === item ? "segment active" : "segment"} key={item} onClick={() => setFilter(item)}>{item}</button>)}</div>
    </div>
    <GlassPanel className={`upload-zone ${dragging ? "drag-active" : ""}`} onDragOver={(event: DragEvent<HTMLElement>) => { event.preventDefault(); setDragging(true); }} onDragLeave={() => setDragging(false)} onDrop={(event: DragEvent<HTMLElement>) => { event.preventDefault(); setDragging(false); addFiles(event.dataTransfer.files); }}>
      <input ref={inputRef} className="visually-hidden" type="file" multiple accept=".pdf,.ppt,.pptx,.doc,.docx,.txt" onChange={(event) => { addFiles(event.target.files); event.target.value = ""; }} />
      <span className="upload-icon"><CloudUpload size={20} /></span><strong>Drop course materials here</strong><p>PDF, PPTX, DOCX, or TXT · Up to 25 MB each</p><Button variant="secondary" size="sm" onClick={() => inputRef.current?.click()}>Browse files</Button>
    </GlassPanel>
    <SectionTitle title="Course library" subtitle="Uploaded resources for student reference" />
    <Panel className="file-list">
      <div className="file-header"><span>Name</span><span>Category</span><span>Size</span><span>Uploaded</span><span>Status</span><span /></div>
      {visible.map((file) => (
        <div className="file-row" key={file.id}>
          <span className="file-name"><span className="file-icon"><FileText size={16} /></span><span><strong>{file.name}</strong></span></span>
          <span>{file.category}</span><span>{file.size}</span><span>{formatDate(file.uploadedAt)}</span>
          <StatusBadge status={file.state} />
          <button className="icon-button" aria-label={`Options for ${file.name}`}><MoreHorizontal size={15} /></button>
        </div>
      ))}
      {!visible.length && <div className="table-empty" style={{ padding: "1.5rem", textAlign: "center" }}>No course materials uploaded yet.</div>}
    </Panel>
  </>;
}

export function SubmissionsPage({ submissions: rows }: { submissions: Submission[] }) {
  const { user, assignments: assignmentList, people } = useAppState();
  const [filter, setFilter] = useState("All");
  const [query, setQuery] = useState("");
  const navigate = useNavigate();
  const student = user?.role === "student";
  const studentRows = rows.filter((item) => item.studentId === user?.id);
  const visible = (student ? studentRows : rows).filter((item) => {
    const person = people.find((userItem) => userItem.id === item.studentId)?.name ?? "";
    const matchesText = `${person} ${assignmentList.find((assignment) => assignment.id === item.assignmentId)?.title ?? ""}`.toLowerCase().includes(query.toLowerCase());
    const matchesFilter = filter === "All" || item.state === filter;
    return matchesText && matchesFilter;
  });

  return <>
    <PageHeader
      title={student ? "My submissions" : "Submissions"}
      subtitle={student ? "Keep track of work you’ve handed in and what’s being reviewed." : "A considered review queue. Late work always gets a human decision."}
    />
    <div className="toolbar">
      <div className="segmented">
        {["All", "Submitted", "Under Review"].map((f) => (
          <button key={f} className={filter === f ? "segment active" : "segment"} onClick={() => setFilter(f)}>
            {f}
          </button>
        ))}
      </div>
      <label className="inline-search">
        <Search size={14} />
        <input placeholder={student ? "Find an assignment..." : "Find a submission..."} value={query} onChange={(event) => setQuery(event.target.value)} />
      </label>
    </div>
    <Panel className="table-card">
      <div className="table-scroll">
        <table className="data-table">
          <thead>
            <tr>
              {student ? (
                <><th>Assignment</th><th>Submitted</th><th>OCR Status</th><th>Grading Status</th><th /></>
              ) : (
                <><th>Student</th><th>Assignment</th><th>Submitted</th><th>OCR Status</th><th>Grading Status</th><th>Action</th></>
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
                      <td><strong>{assignment?.title ?? "Assignment"}</strong></td>
                      <td>{formatDate(item.submittedAt)}</td>
                      <td><StatusBadge status={item.ocr.state} /></td>
                      <td><StatusBadge status={item.state} /></td>
                      <td><Button size="sm" variant="secondary" onClick={() => navigate(`/app/student/submit/${item.assignmentId}`)}>View<ChevronRight size={13} /></Button></td>
                    </>
                  ) : (
                    <>
                      <td>{person?.name ?? "Student"}</td>
                      <td>{assignment?.title ?? "Assignment"}</td>
                      <td>{formatDate(item.submittedAt)}</td>
                      <td><StatusBadge status={item.ocr.state} /></td>
                      <td><StatusBadge status={item.state} /></td>
                      <td><button className="text-button" onClick={() => navigate(`/app/grading/${item.id}`)}>Review<ChevronRight size={13} /></button></td>
                    </>
                  )}
                </tr>
              );
            })}
            {!visible.length && (
              <tr>
                <td className="table-empty" colSpan={student ? 5 : 6} style={{ textAlign: "center", padding: "2rem" }}>
                  {student
                    ? "You haven't submitted any assignments yet."
                    : "No submissions recorded. (Note: Dedicated teacher submission listing endpoint GET /api/v1/submissions is pending backend implementation; student uploads made in this session appear here)."}
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </Panel>
  </>;
}

export function GradingReviewPage({ submissions: rows }: { submissions: Submission[]; setSubmissions: Dispatch<SetStateAction<Submission[]>> }) {
  const { submissionId } = useParams();
  const submission = rows.find((item) => item.id === submissionId);
  return (
    <>
      <PageHeader title="Grading Review" subtitle="Teacher assessment and feedback verification" />
      <Panel className="empty-state">
        {submission ? (
          <div>
            <h3>Reviewing Submission {submission.id}</h3>
            <p>OCR State: {submission.ocr.state} · Confidence: {Math.round(submission.ocr.confidence * 100)}%</p>
            <p style={{ marginTop: "1rem", color: "var(--color-text-muted, #71717a)" }}>
              Note: The AI Grading and Teacher Scoring backend endpoint (POST /api/v1/submissions/:id/grade) is pending backend implementation.
            </p>
          </div>
        ) : (
          <div>
            <p>Submission record not found in active session queue.</p>
            <p style={{ marginTop: "0.5rem", color: "var(--color-text-muted, #71717a)" }}>
              Teacher submission listing endpoint (GET /api/v1/submissions) is pending backend implementation.
            </p>
          </div>
        )}
      </Panel>
    </>
  );
}

export function OCRReviewPage({ submissions: rows }: { submissions: Submission[]; setSubmissions: Dispatch<SetStateAction<Submission[]>> }) {
  const { submissionId } = useParams();
  const submission = rows.find((item) => item.id === submissionId);

  return (
    <>
      <PageHeader title="OCR review" subtitle="Verify uncertain text before grading handoff." />
      <Panel className="empty-state">
        {submission ? (
          <div>
            <h3>Submission {submission.id}</h3>
            <p>OCR Processing Status: {submission.ocr.state}</p>
            <p>Extracted Output: {submission.ocr.extractedText}</p>
          </div>
        ) : (
          <div>
            <p>No active OCR review selected.</p>
            <p style={{ marginTop: "0.5rem", color: "var(--color-text-muted, #71717a)" }}>
              Submit a scanned PDF from the student portal to inspect live OCR microservice pipeline progress.
            </p>
          </div>
        )}
      </Panel>
    </>
  );
}

export function StudentAssignmentsPage({ courses: courseList, joinedCourseIds, setJoinedCourseIds }: {
  courses: Course[];
  joinedCourseIds: string[];
  setJoinedCourseIds: Dispatch<SetStateAction<string[]>>;
  submissions: Submission[];
}) {
  const { assignments: assignmentList } = useAppState();
  const navigate = useNavigate();
  const toast = useToast();
  const [dialogOpen, setDialogOpen] = useState(false);
  const visibleAssignments = assignmentList.filter((item) => item.state === "Published");

  const joinCourse = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const code = String(form.get("inviteCode") ?? "").trim().toUpperCase();
    const course = courseList.find((item) => item.code.toUpperCase() === code || item.name.toUpperCase().includes(code));
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
    toast(`Enrolled in ${course.name}.`);
  };

  return <>
    <PageHeader
      title="My assignments"
      subtitle="A calm, clear view of what’s due and what you’ve completed."
      action={
        <Dialog.Root open={dialogOpen} onOpenChange={setDialogOpen}>
          <Dialog.Trigger asChild><Button variant="secondary"><Plus size={15} />Join a course</Button></Dialog.Trigger>
          <Dialog.Portal>
            <Dialog.Overlay className="modal-backdrop" />
            <Dialog.Content className="modal" aria-describedby="join-course-description">
              <div className="modal-head">
                <Dialog.Title className="modal-title">Join a course</Dialog.Title>
                <Dialog.Close asChild><Button variant="quiet" size="icon" aria-label="Close"><X size={15} /></Button></Dialog.Close>
              </div>
              <Dialog.Description id="join-course-description" className="modal-description">
                Enter the course code shared by your instructor to join.
              </Dialog.Description>
              <form onSubmit={joinCourse}>
                <div className="field-block"><label htmlFor="course-invite-code">Course code</label><input id="course-invite-code" name="inviteCode" className="field-input" placeholder="e.g. CS 240" required /></div>
                <div className="modal-actions">
                  <Dialog.Close asChild><Button type="button" variant="secondary">Cancel</Button></Dialog.Close>
                  <Button type="submit">Join course</Button>
                </div>
              </form>
            </Dialog.Content>
          </Dialog.Portal>
        </Dialog.Root>
      }
    />
    <div className="student-assignment-list">
      {visibleAssignments.length > 0 ? (
        visibleAssignments.map((item) => {
          const actionLabel = item.submissionType === "MCQ" ? "Start assessment" : "Open assignment";
          return (
            <Panel className="student-assignment-row" key={item.id}>
              <span className="student-assignment-icon"><FileText size={17} /></span>
              <span className="assignment-row-copy">
                <strong>{item.title}</strong>
                <small>{item.totalMarks} marks · {item.submissionType} format</small>
              </span>
              <span className="assignment-row-due"><CalendarDays size={13} />Due {formatDate(item.dueAt)}</span>
              <StatusBadge status="Published" />
              <Button size="sm" variant="secondary" onClick={() => navigate(item.submissionType === "MCQ" ? `/app/student/assessment/${item.id}` : `/app/student/submit/${item.id}`)}>
                {actionLabel}<ChevronRight size={13} />
              </Button>
            </Panel>
          );
        })
      ) : (
        <Panel className="empty-state">No published assignments available for your enrolled courses.</Panel>
      )}
    </div>
  </>;
}

export function StudentSubmissionPage({ submissions: studentRows, setSubmissions }: { submissions: Submission[]; setSubmissions: Dispatch<SetStateAction<Submission[]>> }) {
  const { user, courses: courseList, assignments: assignmentList } = useAppState();
  const { assignmentId } = useParams();
  const assignment = assignmentList.find((item) => item.id === assignmentId);
  const course = assignment ? courseList.find((item) => item.id === assignment.courseId) : undefined;
  const existing = studentRows.find((item) => item.studentId === user?.id && item.assignmentId === assignmentId);
  const [file, setFile] = useState<File | null>(null);
  const [drag, setDrag] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [submittedItem, setSubmittedItem] = useState<Submission | null>(null);
  const toast = useToast();

  if (!assignment) return <NotFoundPage />;

  const chooseFile = (candidate?: File) => {
    if (!candidate) return;
    if (candidate.type !== "application/pdf" && !candidate.name.toLowerCase().endsWith(".pdf")) {
      toast("Please choose a PDF file.", "info");
      return;
    }
    if (candidate.size > 20 * 1024 * 1024) {
      toast("File exceeds the 20 MB size limit.", "info");
      return;
    }
    setFile(candidate);
  };

  const submit = async () => {
    if (!file) { toast("Choose a PDF before submitting.", "info"); return; }
    setSubmitting(true);
    try {
      const created = await submissionService.submitPdf(assignment.id, file);
      setSubmissions((current) => [created, ...current]);
      setSubmittedItem(created);
      toast("PDF uploaded successfully and sent for OCR analysis!");
    } catch (err) {
      toast(extractErrorMessage(err, "Failed to submit PDF. Please check connection."), "info");
    } finally {
      setSubmitting(false);
    }
  };

  return <>
    <PageHeader title="Submit assignment" subtitle={`${assignment.title} · ${course?.code ?? "Course"}`} action={<Link className="back-link" to="/app/student/assignments"><ArrowLeft size={14} />All assignments</Link>} />
    <div className="student-submit-layout">
      <div>
        <Panel className="instruction-panel">
          <div className="assignment-state-line"><StatusBadge status={existing ? existing.state : "Not Started"} /><span><CalendarDays size={13} />Due {formatDate(assignment.dueAt)}</span></div>
          <h2>Before you submit</h2>
          <p>{assignment.description || "Submit your completed handwritten or typed solutions in PDF format."}</p>
          <ul>
            <li>Submit one PDF containing your complete responses.</li>
            <li>Ensure handwriting and mathematical formulas are clearly legible.</li>
            <li>Late work is held for human teacher review.</li>
          </ul>
          <div className="assignment-instruction-footer">
            <span>{assignment.totalMarks} marks total</span>
          </div>
        </Panel>
        <SectionTitle title="Your submission" subtitle="Accepted format: PDF · Up to 20 MB" />
        <GlassPanel className={`student-dropzone ${drag ? "drag-active" : ""} ${file ? "file-selected" : ""}`} onDragOver={(event: DragEvent<HTMLElement>) => { event.preventDefault(); setDrag(true); }} onDragLeave={() => setDrag(false)} onDrop={(event: DragEvent<HTMLElement>) => { event.preventDefault(); setDrag(false); chooseFile(event.dataTransfer.files[0]); }}>
          <input type="file" accept=".pdf,application/pdf" id="student-pdf" className="visually-hidden" onChange={(event) => chooseFile(event.target.files?.[0])} />
          {file ? (
            <>
              <span className="file-icon-large"><FileCheck2 size={21} /></span>
              <strong>{file.name}</strong>
              <p>{(file.size / 1024 / 1024).toFixed(2)} MB · Ready to submit</p>
              <button className="text-button" onClick={() => setFile(null)}>Choose another file</button>
            </>
          ) : (
            <>
              <span className="upload-icon"><CloudUpload size={21} /></span>
              <strong>Drop your PDF here</strong>
              <p>or browse from your device.</p>
              <Button variant="secondary" size="sm" onClick={() => document.getElementById("student-pdf")?.click()}>Choose PDF</Button>
            </>
          )}
        </GlassPanel>
        <div className="submit-actions">
          <span><ShieldCheck size={14} />You’ll receive a verified submission receipt.</span>
          <ConfirmDialog
            trigger={<Button disabled={!file || submitting || Boolean(existing)}><Upload size={14} />{existing ? "Already submitted" : submitting ? "Uploading…" : "Submit PDF"}</Button>}
            title="Submit your assignment?"
            description={`This will submit ${file?.name ?? "your PDF"} for ${assignment.title}.`}
            confirmLabel="Confirm submission"
            onConfirm={submit}
          />
        </div>
      </div>
      <aside className="submission-side">
        <Panel className="side-detail-card">
          <SectionTitle title="Assignment details" />
          <dl>
            <div><dt>Deadline</dt><dd>{formatDate(assignment.dueAt)}</dd></div>
            <div><dt>Maximum marks</dt><dd>{assignment.totalMarks}</dd></div>
            <div><dt>Submission type</dt><dd>PDF document</dd></div>
            <div><dt>Status</dt><dd><StatusBadge status={existing ? existing.state : "Not Started"} /></dd></div>
          </dl>
        </Panel>
      </aside>
    </div>
    {submittedItem && (
      <div className="modal-backdrop">
        <div className="receipt-modal">
          <span className="receipt-check"><Check size={22} /></span>
          <span className="eyebrow">SUBMISSION RECEIPT</span>
          <h2>All handed in.</h2>
          <p>Your work has been submitted to the FastAPI backend and queued for OCR processing.</p>
          <div className="receipt-line"><span>Assignment</span><strong>{assignment.title}</strong></div>
          <div className="receipt-line"><span>Submission ID</span><code style={{ fontSize: "0.8rem" }}>{submittedItem.id}</code></div>
          <div className="receipt-line"><span>File</span><strong>{submittedItem.fileName}</strong></div>
          <Button className="full-button" onClick={() => setSubmittedItem(null)}>Done</Button>
        </div>
      </div>
    )}
  </>;
}

export function AssessmentPage({ submissions: studentRows, setSubmissions }: { submissions: Submission[]; setSubmissions: Dispatch<SetStateAction<Submission[]>> }) {
  const { user, assignments: assignmentList } = useAppState();
  const navigate = useNavigate();
  const toast = useToast();
  const { assignmentId } = useParams();
  const assignment = assignmentList.find((item) => item.id === assignmentId);
  const existing = studentRows.find((item) => item.studentId === user?.id && item.assignmentId === assignmentId);
  const [index, setIndex] = useState(0);
  const [answers, setAnswers] = useState<Record<string, number>>({});
  const [submitted, setSubmitted] = useState(false);

  if (!assignment) return <NotFoundPage />;

  const questions = assignment.questions;
  const current = questions[index];

  const submitAssessment = () => {
    if (existing || !user) return;
    setSubmitted(true);
    toast("Assessment recorded. (Note: Dedicated MCQ submission endpoint POST /api/v1/assignments/:id/mcq-answers is pending on backend; upload scanned answers via PDF to use OCR pipeline).", "info");
    const newSub: Submission = {
      id: `mcq-${crypto.randomUUID()}`,
      studentId: user.id,
      assignmentId: assignment.id,
      submittedAt: new Date().toISOString(),
      deadline: assignment.dueAt,
      state: "Submitted",
      ocr: { confidence: 1, state: "Verified", extractedText: "MCQ answers recorded.", warnings: [], expressions: [] },
      answer: "MCQ submission",
    };
    setSubmissions((curr) => [newSub, ...curr]);
  };

  return <>
    <PageHeader title={assignment.title} subtitle={`Question ${index + 1} of ${questions.length}`} action={<Button variant="secondary" onClick={() => navigate("/app/student/assignments")}><ArrowLeft size={14} />Exit</Button>} />
    <div className="assessment-layout">
      <Panel className="assessment-card">
        {current ? (
          <div>
            <div className="question-prompt" style={{ marginBottom: "1.5rem" }}>
              <span>QUESTION {index + 1} · {current.marks} MARKS</span>
              <h2>{current.prompt}</h2>
            </div>
            <div className="mcq-options" style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
              {(current.options ?? ["Option A", "Option B", "Option C", "Option D"]).map((opt, optIdx) => (
                <label key={optIdx} style={{ display: "flex", alignItems: "center", gap: "0.5rem", cursor: "pointer", padding: "0.5rem", borderRadius: "6px", border: "1px solid var(--color-border, #e4e4e7)" }}>
                  <input type="radio" name={`question-${current.id}`} checked={answers[current.id] === optIdx} onChange={() => setAnswers((curr) => ({ ...curr, [current.id]: optIdx }))} />
                  <span>{opt}</span>
                </label>
              ))}
            </div>
            <div className="assessment-nav" style={{ display: "flex", justifyContent: "space-between", marginTop: "2rem" }}>
              <Button variant="secondary" disabled={index === 0} onClick={() => setIndex((i) => i - 1)}><ChevronLeft size={14} />Previous</Button>
              {index < questions.length - 1 ? (
                <Button onClick={() => setIndex((i) => i + 1)}>Next<ChevronRight size={14} /></Button>
              ) : (
                <Button disabled={submitted || Boolean(existing)} onClick={submitAssessment}>{submitted || existing ? "Submitted" : "Submit Assessment"}</Button>
              )}
            </div>
          </div>
        ) : (
          <p className="table-empty">No questions available for this assignment.</p>
        )}
      </Panel>
    </div>
  </>;
}

export function ResultsPage({ submissions: rows }: { submissions: Submission[] }) {
  const { user } = useAppState();
  const student = user?.role === "student";
  const approved = rows.filter((item) => item.studentId === user?.id && item.state === "Published");

  return <>
    <PageHeader
      title={student ? "My results" : "Results & performance"}
      subtitle={student ? "Teacher-approved grades and evidence-based feedback." : "A thoughtful picture of learning across your courses."}
    />
    <div className="published-results">
      {!approved.length && (
        <Panel className="empty-state">
          No teacher-approved results have been published for your account yet. Grades remain private until reviewed and approved by the course instructor.
        </Panel>
      )}
    </div>
  </>;
}

export function LeaderboardPage() {
  return <>
    <PageHeader title="Leaderboard" subtitle="Celebrate steady effort and progress across the class." />
    <Panel className="empty-state">
      Leaderboard metrics will appear once student submissions are evaluated and approved by teachers.
    </Panel>
  </>;
}

export function SettingsPage() {
  const { user } = useAppState();
  return <>
    <PageHeader title="Settings" subtitle="Your profile and workspace configuration." />
    <Panel className="editor-card">
      <SectionTitle title="Account Profile" />
      <div className="field-block"><label>Account ID</label><input className="field-input" value={user?.id ?? ""} readOnly /></div>
      <div className="field-block"><label>Email address</label><input className="field-input" value={user?.email ?? ""} readOnly /></div>
      <div className="field-block"><label>Trusted role</label><input className="field-input" value={user?.role ?? ""} readOnly /></div>
    </Panel>
  </>;
}

export function LandingPage() {
  const navigate = useNavigate();
  return (
    <div className="landing-page">
      <header className="landing-topbar">
        <Link to="/" className="brand">
          <span className="brand-mark"><Check size={19} /></span>
          <span className="brand-word">Trust<span>Grade</span></span>
        </Link>
        <div className="landing-actions">
          <Button variant="secondary" onClick={() => navigate("/login")}>Sign in</Button>
          <Button onClick={() => navigate("/register")}>Get started</Button>
        </div>
      </header>
      <main className="landing-hero">
        <span className="eyebrow">AI-ASSISTED GRADING YOU CAN TRUST</span>
        <h1>Every mark has a reason.<br /><em>Every decision has evidence.</em></h1>
        <p className="hero-copy">TrustGrade combines OCR technology, AI evaluation, and teacher supervision to make grading faster, transparent, and fair.</p>
        <div className="hero-cta-row">
          <Button onClick={() => navigate("/register")}>Create an account<ArrowRight size={15} /></Button>
          <Button variant="secondary" onClick={() => navigate("/login")}>Sign in to workspace</Button>
        </div>
      </main>
      <footer className="landing-footer">
        <span>© 2026 TrustGrade</span>
        <span>AI assists. Teachers decide. Students understand.</span>
      </footer>
    </div>
  );
}

export function AuthPage({ mode, onAuthenticated }: { mode: "login" | "register"; onAuthenticated: (user: User) => void }) {
  const navigate = useNavigate();
  const [role, setRole] = useState<"teacher" | "student">("teacher");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const register = mode === "register";

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setError("");
    const form = new FormData(event.currentTarget);
    const email = String(form.get("email") ?? "").trim();
    const password = String(form.get("password") ?? "");
    const name = String(form.get("name") ?? "").trim();

    if (register && !name) { setError("Enter your name to create an account."); return; }
    if (!email.includes("@") || password.length < 6) { setError("Use a valid email and a password of at least 6 characters."); return; }

    setLoading(true);
    try {
      const user = register
        ? await authService.register(name, email, password, role)
        : await authService.login(email, password);
      onAuthenticated(user);
      navigate("/app");
    } catch (reason) {
      setError(extractErrorMessage(reason, "Authentication failed. Check your credentials and server status."));
    } finally {
      setLoading(false);
    }
  };

  return <div className="auth-page">
    <div className="auth-backdrop" />
    <Link to="/" className="brand auth-brand">
      <span className="brand-mark"><Check size={19} /></span>
      <span className="brand-word">Trust<span>Grade</span></span>
    </Link>
    <div className="auth-layout">
      <section className="auth-story">
        <span className="eyebrow">A MORE THOUGHTFUL CLASSROOM</span>
        <h1>Clarity for your work.<br /><em>Confidence in every grade.</em></h1>
        <p>Course-grounded assistance that respects the people at the heart of learning.</p>
        <div className="auth-promise"><ShieldCheck size={18} /><span><strong>AI assists. Teachers decide.</strong><small>Human judgment is always the last word.</small></span></div>
      </section>
      <Panel className="auth-card">
        <span className="eyebrow">{register ? "YOUR CLASSROOM, IN GOOD HANDS" : "WELCOME BACK"}</span>
        <h2>{register ? "Create your account" : "Welcome back"}</h2>
        <p>{register ? "Join a calmer, clearer way to teach and learn." : "Sign in to your TrustGrade workspace."}</p>
        <form onSubmit={submit}>
          {register && <div className="field-block"><label htmlFor="name">Your name</label><input className="field-input" id="name" name="name" autoComplete="name" placeholder="Professor Morgan" required /></div>}
          <div className="field-block"><label htmlFor="email">Email address</label><input className="field-input" id="email" name="email" type="email" autoComplete="email" placeholder="you@university.edu" required /></div>
          <div className="field-block"><div className="field-label-row"><label htmlFor="password">Password</label></div><input className="field-input" id="password" name="password" type="password" autoComplete={register ? "new-password" : "current-password"} minLength={6} placeholder="At least 6 characters" required /></div>
          {register && (
            <div className="field-block">
              <label>Role</label>
              <div className="role-picker">
                {(["teacher", "student"] as const).map((value) => (
                  <button type="button" key={value} className={role === value ? "active" : ""} onClick={() => setRole(value)}>
                    <span>{value === "teacher" ? <GraduationCap size={16} /> : <BookOpen size={16} />}</span>
                    {value === "teacher" ? "Teacher" : "Student"}
                    {role === value && <Check size={13} />}
                  </button>
                ))}
              </div>
            </div>
          )}
          {error && <div role="alert" className="form-error"><AlertCircle size={14} />{error}</div>}
          <Button className="full-button" disabled={loading}>
            {loading ? <><span className="button-spinner" />Signing in…</> : <>{register ? "Create account" : "Sign in"}<ArrowRight size={14} /></>}
          </Button>
        </form>
        <div className="auth-switch">
          {register ? "Already have an account?" : "New to TrustGrade?"} <Link to={register ? "/login" : "/register"}>{register ? "Sign in" : "Create account"}</Link>
        </div>
      </Panel>
    </div>
    <footer className="auth-footer">
      <span>© 2026 TrustGrade</span>
      <span>AI assists. Teachers decide. Students understand.</span>
    </footer>
  </div>;
}

export function NotFoundPage() {
  const navigate = useNavigate();
  return <div style={{ padding: "4rem", textAlign: "center" }}>
    <h2>Page not found</h2>
    <p style={{ margin: "1rem 0", color: "var(--color-text-muted, #71717a)" }}>The requested page or resource could not be found.</p>
    <Button variant="secondary" onClick={() => navigate("/app")}>Back to Overview</Button>
  </div>;
}
