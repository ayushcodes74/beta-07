import { useEffect, useRef, useState, type Dispatch, type DragEvent, type FormEvent, type SetStateAction } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import {
  Activity, AlertCircle, ArrowLeft, ArrowRight, ArrowUpRight, BookOpen, CalendarDays,
  Check, CheckCircle2, ChevronLeft, ChevronRight, CloudUpload,
  FileCheck2, FileText, GraduationCap, Menu, MoreHorizontal, Plus,
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
  type BackendIntegrityReport,
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
  const { user } = useAppState();
  const submission = rows.find((item) => item.id === submissionId);
  const [integrity, setIntegrity] = useState<BackendIntegrityReport | null>(null);
  const [integrityLoading, setIntegrityLoading] = useState(false);
  const [integrityError, setIntegrityError] = useState<string | null>(null);
  const [integrityRefresh, setIntegrityRefresh] = useState(0);

  useEffect(() => {
    let active = true;
    setIntegrity(null);
    setIntegrityError(null);
    if (!submissionId || user?.role !== "teacher" || import.meta.env.VITE_USE_API_AUTH !== "true") {
      setIntegrityLoading(false);
      return () => { active = false; };
    }

    setIntegrityLoading(true);
    void submissionService.getIntegrity(submissionId)
      .then((report) => {
        if (active) setIntegrity(report);
      })
      .catch((error: unknown) => {
        if (active) setIntegrityError(extractErrorMessage(error));
      })
      .finally(() => {
        if (active) setIntegrityLoading(false);
      });

    return () => { active = false; };
  }, [submissionId, user?.role, integrityRefresh]);

  const regionSummary = (regions: BackendIntegrityReport["evidence"][number]["current_regions"]) =>
    regions.map((region) => `p. ${region.page_number}${region.region_id ? ` · ${region.region_id}` : ""}`).join(", ");

  return (
    <>
      <PageHeader title="Grading Review" subtitle="Teacher assessment and feedback verification" />
      <Panel className="integrity-panel">
        {submission ? (
          <div>
            <h3>Reviewing Submission {submission.id}</h3>
            <p>OCR State: {submission.ocr.state} · Confidence: {submission.ocr.confidence === null ? "Unavailable" : `${Math.round(submission.ocr.confidence * 100)}%`}</p>
            <p style={{ marginTop: "1rem", color: "var(--color-text-muted, #71717a)" }}>
              Note: The AI Grading and Teacher Scoring backend endpoint (POST /api/v1/submissions/:id/grade) is pending backend implementation.
            </p>
            <div className="integrity-heading">
              <div>
                <h2><ShieldCheck size={17} /> Submission integrity</h2>
                <p>Authorized same-assignment OCR comparison. Similarity is a prompt for teacher review, never a misconduct verdict.</p>
              </div>
              {integrity && <StatusBadge status={
                integrity.review_status === "needs_teacher_review"
                  ? "Needs teacher review"
                  : integrity.review_status === "processing"
                    ? "OCR processing"
                    : "No matching passages"
              } />}
            </div>

            {import.meta.env.VITE_USE_API_AUTH !== "true" && (
              <p className="integrity-message" role="status">Connect the authenticated backend to run integrity analysis. Demo data is not compared.</p>
            )}
            {integrityLoading && <p className="integrity-message" role="status" aria-live="polite">Comparing completed OCR for this assignment…</p>}
            {integrityError && <p className="integrity-message integrity-error" role="alert">{integrityError}</p>}
            {integrity?.review_status === "processing" && (
              <div className="integrity-message" role="status">
                <span>{integrity.notes[0]}</span>
                <Button variant="secondary" size="sm" onClick={() => setIntegrityRefresh((value) => value + 1)}>Check again</Button>
              </div>
            )}
            {integrityError && <Button variant="secondary" size="sm" onClick={() => setIntegrityRefresh((value) => value + 1)}>Retry integrity analysis</Button>}
            {integrity && integrity.review_status !== "processing" && (
              <>
                <div className="integrity-summary" aria-label="Comparison summary">
                  <span><strong>{integrity.comparisons_completed}</strong> completed comparisons</span>
                  {integrity.comparisons_skipped > 0 && <span><strong>{integrity.comparisons_skipped}</strong> skipped</span>}
                  <span>{integrity.comparison_complete ? "Comparison coverage complete" : "Comparison coverage incomplete"}</span>
                  {integrity.ocr_quality.mean_confidence !== null && (
                    <span>Mean OCR confidence {(integrity.ocr_quality.mean_confidence * 100).toFixed(0)}%</span>
                  )}
                  {integrity.ocr_quality.missing_pages.length > 0 && (
                    <span>Missing pages: {integrity.ocr_quality.missing_pages.join(", ")}</span>
                  )}
                  {integrity.ocr_quality.unreadable_pages.length > 0 && (
                    <span>Unreadable pages: {integrity.ocr_quality.unreadable_pages.join(", ")}</span>
                  )}
                </div>
                <p className="integrity-limitation">
                  Exact text matching uses normalized tokens. Semantic similarity is unavailable; no embedding model or external-web search is configured.
                </p>
                <p className="integrity-limitation" role="status">
                  Handwriting-style analysis unavailable: {integrity.handwriting_analysis.reason}
                </p>

                {integrity.evidence.map((item, index) => (
                  <article className="integrity-evidence" key={`${item.source_submission_id}-${index}`}>
                    <div className="integrity-evidence-head">
                      <strong>Potential passage match</strong>
                      <span>Token similarity {(item.exact_match_score * 100).toFixed(0)}%</span>
                    </div>
                    <p className="integrity-source">Authorized source: {item.source_reference}</p>
                    <div className="integrity-passages">
                      <div><h3>This submission · {regionSummary(item.current_regions) || "page reference unavailable"}</h3><blockquote><mark>{item.current_passage}</mark></blockquote></div>
                      <div><h3>Comparison source · {regionSummary(item.source_regions) || "page reference unavailable"}</h3><blockquote><mark>{item.source_passage}</mark></blockquote></div>
                    </div>
                    {item.ocr_uncertain && <p className="integrity-warning" role="status">OCR confidence is low or unavailable for one or more matched regions. Check the original scan before drawing conclusions.</p>}
                    {item.context_note && <p className="integrity-warning">{item.context_note}</p>}
                  </article>
                ))}
                {integrity.evidence.length === 0 && integrity.review_status === "no_matches" && (
                  <p className="integrity-message">No matching passages were found in completed submissions for this assignment. This is not an internet-wide plagiarism check.</p>
                )}
                {integrity.ocr_quality.low_confidence_regions.length > 0 && (
                  <section className="integrity-ocr-review" aria-labelledby="ocr-low-confidence-title">
                    <h3 id="ocr-low-confidence-title">OCR passages needing verification</h3>
                    {integrity.ocr_quality.low_confidence_regions.map((region) => (
                      <p key={`${region.page_number}-${region.region_id}`}>
                        <strong>Page {region.page_number}{region.region_id ? ` · ${region.region_id}` : ""}</strong>
                        {region.confidence !== null && ` · ${(region.confidence * 100).toFixed(0)}% confidence`}
                        <span>{region.original_text || "No text was confidently recognized."}</span>
                      </p>
                    ))}
                    <small>Original OCR text is shown unchanged. Corrections and review decisions are not yet persisted.</small>
                  </section>
                )}
                <ul className="integrity-notes">
                  {integrity.notes.map((note) => <li key={note}>{note}</li>)}
                </ul>
              </>
            )}
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
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const [scrollIndex, setScrollIndex] = useState(0);

  const capabilities = [
    {
      id: "rubric",
      title: "Automated Rubric Grading",
      desc: "Evaluates multi-tier rubrics with criteria-specific evidence and customizable weight distributions.",
      icon: <FileCheck2 size={18} />,
      badge: "Spring Semester",
      image: "https://images.unsplash.com/photo-1434030216411-0b793f4b4173?auto=format&fit=crop&w=800&q=80",
    },
    {
      id: "syllabus",
      title: "Syllabus & Material Alignment",
      desc: "Verifies questions and student answers against your uploaded lecture notes, PPTs, and course readings.",
      icon: <BookOpen size={18} />,
      badge: "Core Feature",
      image: "https://images.unsplash.com/photo-1497633762265-9d179a990aa6?auto=format&fit=crop&w=800&q=80",
    },
    {
      id: "ocr",
      title: "Handwritten OCR & Diagrams",
      desc: "Extracts formulas, sketches, and handwritten tests from mobile camera photos or scanned PDF files.",
      icon: <FileText size={18} />,
      badge: "Multimodal AI",
      image: "https://images.unsplash.com/photo-1509062522246-3755977927d7?auto=format&fit=crop&w=800&q=80",
    },
    {
      id: "anti-hallucination",
      title: "Anti-Hallucination Guardrails",
      desc: "Zero fabricated justification. Every score is linked to verifiable quotes from course materials.",
      icon: <ShieldCheck size={18} />,
      badge: "100% Grounded",
      image: "https://images.unsplash.com/photo-1451187580459-43490279c0fa?auto=format&fit=crop&w=800&q=80",
    },
    {
      id: "confidence",
      title: "Confidence & Review Routing",
      desc: "Calculates multi-factor confidence and routes ambiguous or flagged papers for priority human review.",
      icon: <Sparkles size={18} />,
      badge: "Human in the Loop",
      image: "https://images.unsplash.com/photo-1454165804606-c3d57bc86b40?auto=format&fit=crop&w=800&q=80",
    },
    {
      id: "feedback",
      title: "Actionable Student Feedback",
      desc: "Generates tailored feedback emphasizing strengths, correcting misconceptions, and guiding study.",
      icon: <GraduationCap size={18} />,
      badge: "Formative Insights",
      image: "https://images.unsplash.com/photo-1523240795612-9a054b0db644?auto=format&fit=crop&w=800&q=80",
    },
  ];

  return (
    <div className="tg-landing">
      {/* 1. FLOATING PILL NAVBAR */}
      <header className="tg-pill-nav">
        <div className="tg-nav-inner">
          <Link to="/" className="tg-nav-brand">
            <span className="tg-brand-symbol">
              <GraduationCap size={18} />
            </span>
            <span className="tg-brand-name">
              Trust<span>Grade</span>
            </span>
          </Link>

          <nav className="tg-nav-links">
            <a href="#about">About Us</a>
            <a href="#capabilities">Capabilities</a>
            <a href="#process">How It Works</a>
            <a href="#showcase">Platform</a>
            <a href="#faculty">For Faculty</a>
          </nav>

          <div className="tg-nav-actions">
            <button className="tg-btn-ghost" onClick={() => navigate("/login")}>
              Sign In
            </button>
            <button className="tg-btn-primary" onClick={() => navigate("/register")}>
              <span>Get Started Free</span>
              <ArrowUpRight size={15} />
            </button>
            <button
              className="tg-mobile-toggle"
              aria-label="Toggle navigation"
              onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
            >
              {mobileMenuOpen ? <X size={20} /> : <Menu size={20} />}
            </button>
          </div>
        </div>

        {mobileMenuOpen && (
          <div className="tg-mobile-drawer">
            <a href="#about" onClick={() => setMobileMenuOpen(false)}>About Us</a>
            <a href="#capabilities" onClick={() => setMobileMenuOpen(false)}>Capabilities</a>
            <a href="#process" onClick={() => setMobileMenuOpen(false)}>How It Works</a>
            <a href="#showcase" onClick={() => setMobileMenuOpen(false)}>Platform</a>
            <a href="#faculty" onClick={() => setMobileMenuOpen(false)}>For Faculty</a>
            <div className="tg-mobile-buttons">
              <button className="tg-btn-ghost" onClick={() => navigate("/login")}>Sign In</button>
              <button className="tg-btn-primary" onClick={() => navigate("/register")}>
                <span>Get Started Free</span>
                <ArrowUpRight size={15} />
              </button>
            </div>
          </div>
        )}
      </header>

      {/* 2. CINEMATIC HERO SECTION (EDITORIAL EDTECH V2) */}
      <section className="tg-hero-wrapper">
        <div className="tg-hero-card">
          <div className="tg-hero-bg-overlay" />
          <div className="tg-hero-grid">
            {/* Left Column: Editorial Academic Content */}
            <div className="tg-hero-left">
              <div className="tg-hero-eyebrow">
                <span className="tg-lime-pip" />
                <span>ACADEMIC INTELLIGENCE PLATFORM</span>
              </div>

              <h1 className="tg-hero-title">
                Every answer<br />
                deserves a<br />
                <em className="tg-hero-serif-fair">fair evaluation<span className="tg-hero-dot">.</span></em>
              </h1>

              <p className="tg-hero-desc">
                Intelligent grading, syllabus-aware assessment and transparent feedback designed to empower educators and students.
              </p>

              <div className="tg-hero-actions">
                <button className="tg-hero-btn-primary" onClick={() => navigate("/register")}>
                  <span>Explore Platform</span>
                  <ArrowUpRight size={15} />
                </button>
                <button className="tg-hero-btn-secondary" onClick={() => navigate("/login")}>
                  <span>For Educators</span>
                </button>
              </div>
            </div>

            {/* Right Column: Realistic Academic Grading Dashboard Preview + 2 Small Floating Cards */}
            <div className="tg-hero-right">
              <div className="tg-hero-board-wrap">
                {/* Floating Card 1: Rubric Evaluation */}
                <div className="tg-hero-float-chip tg-chip-top">
                  <div className="tg-chip-icon">
                    <FileCheck2 size={15} />
                  </div>
                  <div className="tg-chip-text">
                    <strong>Rubric Evaluation</strong>
                    <small>Concept-wise scoring</small>
                  </div>
                  <span className="tg-chip-tag">9.3 / 10</span>
                </div>

                {/* Realistic Academic Grading Dashboard Preview */}
                <div className="tg-hero-preview-board">
                  {/* Top Bar of Dashboard */}
                  <div className="tg-board-header">
                    <div className="tg-board-title-group">
                      <span className="tg-board-badge">CS 302</span>
                      <div>
                        <strong>Algorithms & Data Structures</strong>
                        <small>Assignment 03 · Student: Julian Vance</small>
                      </div>
                    </div>
                    <span className="tg-board-status">
                      <span className="tg-status-dot" /> AI Review Ready
                    </span>
                  </div>

                  {/* Student Answer Sheet Preview */}
                  <div className="tg-board-section">
                    <div className="tg-section-label">STUDENT ANSWER SHEET EXTRACT</div>
                    <div className="tg-answer-preview">
                      <div className="tg-answer-q">Q3: Quicksort Worst-Case Degradation & Mitigations</div>
                      <p className="tg-answer-text">
                        "Quicksort exhibits O(n²) worst-case when partition pivots are unbalanced. Adopting a <mark>randomized pivot selection</mark> guarantees expected O(n log n) runtime..."
                      </p>
                    </div>
                  </div>

                  {/* Rubric-wise Marks & Concept Understanding */}
                  <div className="tg-board-rubric-row">
                    <div className="tg-rubric-mini">
                      <div className="tg-rubric-head">
                        <span>Rubric Criteria</span>
                        <strong className="tg-rubric-total">9.3 / 10</strong>
                      </div>
                      <div className="tg-rubric-bars">
                        <div className="tg-rubric-item">
                          <span>Time Complexity Proof</span>
                          <strong>4.8 / 5.0</strong>
                        </div>
                        <div className="tg-rubric-item">
                          <span>Pivot Randomization Heuristic</span>
                          <strong>4.5 / 5.0</strong>
                        </div>
                      </div>
                    </div>

                    <div className="tg-concept-mini">
                      <span className="tg-section-label">CONCEPT UNDERSTANDING</span>
                      <div className="tg-concept-stat">
                        <strong className="tg-concept-percent">94%</strong>
                        <span className="tg-concept-badge">Mastery</span>
                      </div>
                      <small>Grounded in Lecture 6 & CLRS Sec 7.3</small>
                    </div>
                  </div>

                  {/* AI-Generated Feedback & Confidence Indicator */}
                  <div className="tg-board-footer">
                    <div className="tg-board-feedback">
                      <span className="tg-feedback-label">AI FEEDBACK</span>
                      <p>"Rigorous recurrence derivation. Clear explanation of expected bounds."</p>
                    </div>
                    <div className="tg-confidence-badge">
                      <Sparkles size={12} />
                      <span>Confidence: <strong>98.4%</strong></span>
                    </div>
                  </div>
                </div>

                {/* Floating Card 2: Academic Integrity */}
                <div className="tg-hero-float-chip tg-chip-bottom">
                  <div className="tg-chip-icon">
                    <ShieldCheck size={15} />
                  </div>
                  <div className="tg-chip-text">
                    <strong>Academic Integrity</strong>
                    <small>Similarity analysis</small>
                  </div>
                  <span className="tg-chip-verified">Verified</span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* 3. CAPABILITIES / TRUST PARTNER STRIP */}
      <section className="tg-trust-bar">
        <div className="tg-container">
          <div className="tg-partner-strip">
            <span className="tg-partner-item"><strong>STANFORD</strong> APPLIED AI</span>
            <span className="tg-partner-sep">•</span>
            <span className="tg-partner-item"><strong>OXFORD</strong> CURRICULUM</span>
            <span className="tg-partner-sep">•</span>
            <span className="tg-partner-item"><strong>CAMBRIDGE</strong> DIGITAL ED</span>
            <span className="tg-partner-sep">•</span>
            <span className="tg-partner-item"><strong>BERKELEY</strong> COMPUTING</span>
            <span className="tg-partner-sep">•</span>
            <span className="tg-partner-item"><strong>MIT</strong> INTEGRITY LAB</span>
          </div>
        </div>
      </section>

      {/* 4. ABOUT SECTION (2-COLUMN) */}
      <section className="tg-about-section" id="about">
        <div className="tg-container">
          <div className="tg-about-grid">
            {/* Left Image Card */}
            <div className="tg-about-image-card">
              <img
                src="https://images.unsplash.com/photo-1524178232363-1fb2b075b655?auto=format&fit=crop&w=900&q=80"
                alt="University classroom collaboration"
                className="tg-about-img"
                loading="lazy"
              />
              <div className="tg-about-img-overlay" />
              <div className="tg-about-img-badge">
                <span className="tg-badge-pulse" />
                <span>Active in 140+ Academic Courses</span>
              </div>
              <div className="tg-about-img-footer">
                <span>Verified Source Citations</span>
                <span className="tg-bullet">•</span>
                <span>100% Audit Trail</span>
              </div>
            </div>

            {/* Right Editorial Text */}
            <div className="tg-about-content">
              <span className="tg-section-eyebrow">
                <span className="tg-eyebrow-dot" /> ABOUT TRUSTGRADE
              </span>
              <h2 className="tg-about-headline">
                Assessment should be more than assigning marks. It should <em>elevate learning</em>.
              </h2>
              <p className="tg-about-p">
                TrustGrade started with a clear observation: professors spend countless hours reading repetitive exams, leaving minimal energy for personalized guidance. Standard AI tools fail because they lack institutional course grounding and hallucinate criteria.
              </p>
              <p className="tg-about-p">
                We engineered TrustGrade to fuse custom course syllabi, lecture slides, and faculty-crafted rubrics into an evidence-driven evaluation engine. Every grade suggestion references specific passages—reducing grading fatigue by up to 70% while keeping teachers completely in control.
              </p>
              <div className="tg-about-actions">
                <button className="tg-btn-primary" onClick={() => navigate("/register")}>
                  <span>Explore Capabilities</span>
                  <ArrowUpRight size={15} />
                </button>
                <a href="#process" className="tg-btn-outline">
                  <span>How It Works</span>
                  <ArrowUpRight size={14} />
                </a>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* 5. CAPABILITIES GRID ("OUR SERVICES") */}
      <section className="tg-services-section" id="capabilities">
        <div className="tg-container">
          <div className="tg-services-header">
            <div>
              <span className="tg-section-eyebrow">
                <span className="tg-eyebrow-dot" /> OUR CAPABILITIES
              </span>
              <h2 className="tg-services-headline">
                Everything your <em>faculty needs</em>
              </h2>
            </div>
            <div className="tg-services-header-right">
              <p>
                From raw student PDF ingestion to final published marks—rigorous, evidence-backed evaluation at institutional scale.
              </p>
              <div className="tg-carousel-controls">
                <button
                  className="tg-ctrl-btn"
                  onClick={() => setScrollIndex(Math.max(0, scrollIndex - 1))}
                  aria-label="Previous"
                >
                  <ChevronLeft size={16} />
                </button>
                <button
                  className="tg-ctrl-btn"
                  onClick={() => setScrollIndex(Math.min(capabilities.length - 3, scrollIndex + 1))}
                  aria-label="Next"
                >
                  <ChevronRight size={16} />
                </button>
              </div>
            </div>
          </div>

          <div className="tg-cards-grid">
            {capabilities.map((item) => (
              <div key={item.id} className="tg-feature-card">
                <img src={item.image} alt={item.title} className="tg-card-bg-img" loading="lazy" />
                <div className="tg-card-overlay" />
                <div className="tg-card-top">
                  <span className="tg-card-badge">{item.badge}</span>
                  <span className="tg-card-icon">{item.icon}</span>
                </div>
                <div className="tg-card-body">
                  <h3 className="tg-card-title">{item.title}</h3>
                  <p className="tg-card-desc">{item.desc}</p>
                  <button className="tg-card-pill-btn" onClick={() => navigate("/register")}>
                    <span>Learn More</span>
                    <ArrowUpRight size={13} />
                  </button>
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* 6. HOW IT WORKS / OUR PROCESS */}
      <section className="tg-process-section" id="process">
        <div className="tg-container">
          <div className="tg-process-header">
            <div>
              <span className="tg-section-eyebrow">
                <span className="tg-eyebrow-dot" /> OUR WORKFLOW
              </span>
              <h2 className="tg-process-headline">
                How we evaluate, <em>start to finish</em>
              </h2>
            </div>
            <p className="tg-process-header-sub">
              A transparent, 4-step pipeline that combines high-precision syllabus retrieval with absolute teacher authority.
            </p>
          </div>

          <div className="tg-process-grid">
            {/* Step 01: Left tall card with image */}
            <div className="tg-step-card tg-step-1">
              <span className="tg-step-num">Step 01</span>
              <h3 className="tg-step-title">Course & Rubric Ingestion</h3>
              <p className="tg-step-desc">
                Upload your syllabus, slide decks, and custom rubrics. The AI builds a dedicated course vector index with strict grounding boundaries.
              </p>
              <div className="tg-step-img-box">
                <img
                  src="https://images.unsplash.com/photo-1456513080510-7bf3a84b82f8?auto=format&fit=crop&w=600&q=80"
                  alt="Syllabus and lecture notes"
                  loading="lazy"
                />
                <div className="tg-step-img-tag">
                  <CheckCircle2 size={13} />
                  <span>Private Course Vector Store</span>
                </div>
              </div>
            </div>

            {/* Step 02: Center top card */}
            <div className="tg-step-card tg-step-2">
              <span className="tg-step-num">Step 02</span>
              <h3 className="tg-step-title">Intake Student Submissions</h3>
              <p className="tg-step-desc">
                Students upload typed PDFs or photos of handwritten answer sheets. OCR normalizes text, extracts mathematical notation, and segments questions.
              </p>
              <div className="tg-step-metric-chip">
                <div className="tg-chip-radar">
                  <span className="tg-radar-core" />
                </div>
                <div>
                  <strong>OCR Normalization Engine</strong>
                  <small>Typed PDFs & Handwritten Sheets</small>
                </div>
              </div>
            </div>

            {/* Step 03: Right top card */}
            <div className="tg-step-card tg-step-3">
              <span className="tg-step-num">Step 03</span>
              <h3 className="tg-step-title">Multi-Factor AI Evaluation</h3>
              <p className="tg-step-desc">
                Scores each criterion against the rubric, matches exact source quotes from lecture materials, and calculates a confidence score.
              </p>
              <div className="tg-step-confidence-badge">
                <div className="tg-conf-val">98.4%</div>
                <div>
                  <strong>Confidence Index</strong>
                  <small>High Accuracy · Grounded</small>
                </div>
              </div>
            </div>

            {/* Step 04: Full width bottom card */}
            <div className="tg-step-card tg-step-4-wide">
              <div className="tg-step-4-content">
                <span className="tg-step-num">Step 04 · Faculty Review</span>
                <h3 className="tg-step-title">Teacher Approval & Publication</h3>
                <p className="tg-step-desc">
                  Every evaluation is provisional until reviewed by the professor. Verify marks with single clicks, adjust rubric scores, and publish constructive feedback directly to student dashboards.
                </p>
                <div className="tg-step-4-badges">
                  <span className="tg-badge-tag"><Check size={12} /> 100% Teacher Authority</span>
                  <span className="tg-badge-tag"><Check size={12} /> One-Click Grade Approval</span>
                  <span className="tg-badge-tag"><Check size={12} /> Anti-Hallucination Verified</span>
                </div>
              </div>
              <div className="tg-step-4-graphic">
                <div className="tg-verification-card">
                  <div className="tg-verif-top">
                    <span className="tg-stamp-mark"><CheckCircle2 size={16} /></span>
                    <div>
                      <strong>Evaluation Verified</strong>
                      <small>Prof. Alex Morgan · CS 301</small>
                    </div>
                  </div>
                  <div className="tg-verif-criteria">
                    <div><span>Theoretical Bounds</span><strong>5.0 / 5.0</strong></div>
                    <div><span>Empirical Analysis</span><strong>4.8 / 5.0</strong></div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* 7. AI INTELLIGENCE SHOWCASE (REALISTIC DARK DASHBOARD) */}
      <section className="tg-showcase-section" id="showcase">
        <div className="tg-container">
          <div className="tg-showcase-header">
            <span className="tg-section-eyebrow">
              <span className="tg-eyebrow-dot" /> LIVE PLATFORM INSPECTION
            </span>
            <h2 className="tg-showcase-headline">
              Academic rigor in <em>every single detail</em>
            </h2>
            <p className="tg-showcase-sub">
              Inspect how TrustGrade anchors criteria evaluation in verified lecture citations and provides full faculty oversight before publishing.
            </p>
          </div>

          <div className="tg-showcase-container">
            {/* Top Mock Window Bar */}
            <div className="tg-showcase-topbar">
              <div className="tg-window-dots">
                <span className="tg-dot" />
                <span className="tg-dot" />
                <span className="tg-dot" />
              </div>
              <div className="tg-window-title">
                <span>CS 401: Advanced Algorithms — Midterm Assessment</span>
                <span className="tg-status-pill">Ready for Faculty Approval</span>
              </div>
              <div className="tg-window-user">
                <span className="tg-user-avatar">DR</span>
                <span>Dr. David Rossi</span>
              </div>
            </div>

            {/* Showcase Body */}
            <div className="tg-showcase-body">
              {/* Left Column: Student Answer */}
              <div className="tg-showcase-left">
                <div className="tg-pane-header">
                  <span className="tg-pane-tag">STUDENT SUBMISSION</span>
                  <span className="tg-submission-id">ID: #4092 · Julian Vance</span>
                </div>
                <div className="tg-student-snippet">
                  <h4>Question 2: Quicksort Worst-Case Degradation & Mitigation</h4>
                  <div className="tg-snippet-box">
                    <p>
                      "In worst-case scenarios, Quicksort degrades to <mark className="tg-highlight">O(n²)</mark> when the chosen pivot is consistently the minimum or maximum element in an already sorted or reverse-sorted array. This yields maximally unbalanced partitions containing 0 and n-1 elements respectively."
                    </p>
                    <p>
                      "To mitigate this degradation, we can adopt a <mark className="tg-highlight">randomized pivot selection strategy</mark> or the Median-of-Three heuristic. Randomization guarantees an expected runtime of O(n log n) regardless of the input distribution, effectively eliminating adversarial permutations."
                    </p>
                  </div>
                </div>

                <div className="tg-citation-box">
                  <div className="tg-citation-head">
                    <BookOpen size={13} />
                    <span>Retrieved Course Evidence</span>
                  </div>
                  <p>
                    <strong>Lecture 6, Slide 18:</strong> "Quicksort worst-case recurrence T(n) = T(n-1) + O(n) resolves to O(n²). Mitigated via randomized pivot choosing with uniform probability over [p..r]."
                  </p>
                  <span className="tg-citation-match">● 98.7% Semantic Material Match</span>
                </div>
              </div>

              {/* Right Column: AI Rubric Scoring */}
              <div className="tg-showcase-right">
                <div className="tg-pane-header">
                  <span className="tg-pane-tag">AI CRITERIA BREAKDOWN</span>
                  <span className="tg-score-tag">Score: 9.8 / 10.0</span>
                </div>

                <div className="tg-rubric-cards">
                  <div className="tg-criterion-card">
                    <div className="tg-crit-top">
                      <strong>1. Worst-Case Recurrence Analysis</strong>
                      <span className="tg-crit-score">5.0 / 5.0</span>
                    </div>
                    <p>Correctly identified O(n²) degradation and unbalanced partition depth.</p>
                    <small>Evidence Grounded: Lecture 6 (Slide 18)</small>
                  </div>

                  <div className="tg-criterion-card">
                    <div className="tg-crit-top">
                      <strong>2. Randomized Pivot Mitigation</strong>
                      <span className="tg-crit-score">4.8 / 5.0</span>
                    </div>
                    <p>Accurately explained randomized selection and expected O(n log n) proof.</p>
                    <small>Evidence Grounded: CLRS Textbook, Chapter 7</small>
                  </div>
                </div>

                <div className="tg-confidence-panel">
                  <div className="tg-conf-row">
                    <div>
                      <small>EVALUATION CONFIDENCE</small>
                      <strong>99.2% — High Confidence</strong>
                    </div>
                    <span className="tg-conf-tag">Audit Clean</span>
                  </div>
                  <div className="tg-conf-meter">
                    <div className="tg-conf-fill" style={{ width: "99.2%" }} />
                  </div>
                </div>

                <div className="tg-approval-actions">
                  <button className="tg-btn-approve" onClick={() => navigate("/login")}>
                    <CheckCircle2 size={16} />
                    <span>Approve Grade & Publish</span>
                  </button>
                  <button className="tg-btn-adjust" onClick={() => navigate("/login")}>
                    Adjust Score
                  </button>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* 8. FINAL CALL TO ACTION BANNER */}
      <section className="tg-cta-section" id="faculty">
        <div className="tg-container">
          <div className="tg-cta-banner">
            <div className="tg-cta-glow" />
            <div className="tg-cta-content">
              <span className="tg-section-eyebrow">
                <span className="tg-eyebrow-dot" /> ELEVATE YOUR INSTITUTION
              </span>
              <h2 className="tg-cta-headline">
                Make every evaluation <em>meaningful</em>.
              </h2>
              <p className="tg-cta-sub">
                Join forward-thinking faculty and university departments using TrustGrade to streamline grading while delivering transparent, evidence-based feedback.
              </p>
              <div className="tg-cta-buttons">
                <button className="tg-btn-primary-lg" onClick={() => navigate("/register")}>
                  <span>Get Started for Free</span>
                  <ArrowUpRight size={16} />
                </button>
                <button className="tg-btn-glass-lg" onClick={() => navigate("/login")}>
                  <span>Schedule Faculty Demo</span>
                  <ArrowUpRight size={16} />
                </button>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* 9. FOOTER */}
      <footer className="tg-footer">
        <div className="tg-container">
          <div className="tg-footer-grid">
            {/* Column 1: Brand & Mission */}
            <div className="tg-footer-col tg-footer-brand-col">
              <Link to="/" className="tg-nav-brand">
                <span className="tg-brand-symbol">
                  <GraduationCap size={18} />
                </span>
                <span className="tg-brand-name">
                  Trust<span>Grade</span>
                </span>
              </Link>
              <p className="tg-footer-tagline">
                The intelligent academic assessment platform grounded in course materials, rigorous rubrics, and faculty authority.
              </p>
              <div className="tg-footer-badges">
                <span className="tg-security-pill">FERPA Compliant</span>
                <span className="tg-security-pill">SOC2 Ready</span>
              </div>
            </div>

            {/* Column 2: Platform */}
            <div className="tg-footer-col">
              <strong className="tg-col-title">Platform</strong>
              <ul className="tg-footer-links">
                <li><a href="#capabilities">Automated Rubric Grading</a></li>
                <li><a href="#capabilities">Syllabus Alignment Engine</a></li>
                <li><a href="#capabilities">Handwritten OCR Processing</a></li>
                <li><a href="#capabilities">Anti-Hallucination Guard</a></li>
                <li><a href="#capabilities">Confidence & Review Routing</a></li>
              </ul>
            </div>

            {/* Column 3: Resources */}
            <div className="tg-footer-col">
              <strong className="tg-col-title">Resources</strong>
              <ul className="tg-footer-links">
                <li><a href="#about">Academic Documentation</a></li>
                <li><a href="#about">Pedagogical Research</a></li>
                <li><a href="#showcase">Case Studies</a></li>
                <li><a href="#showcase">Security Architecture</a></li>
                <li><a href="#showcase">Faculty Guidelines</a></li>
              </ul>
            </div>

            {/* Column 4: Contact & Faculty Support */}
            <div className="tg-footer-col">
              <strong className="tg-col-title">Faculty Support</strong>
              <ul className="tg-footer-links">
                <li><span>Institutional Inquiries</span></li>
                <li><strong className="tg-support-phone">+1 (800) 459-7812</strong></li>
                <li><span>support@trustgrade.edu</span></li>
                <li><span>Available Mon - Fri, 8am - 6pm EST</span></li>
              </ul>
            </div>
          </div>

          <div className="tg-footer-bottom">
            <span>© 2026 TrustGrade AI Inc. All rights reserved.</span>
            <div className="tg-bottom-links">
              <a href="#">Privacy Policy</a>
              <a href="#">Terms of Service</a>
              <a href="#">Academic Integrity Pledge</a>
            </div>
          </div>
        </div>
      </footer>
    </div>
  );
}

export function AuthPage({ mode, onAuthenticated }: { mode: "login" | "register"; onAuthenticated: (user: User) => void }) {
  const navigate = useNavigate();
  const submissionInProgress = useRef(false);
  const [role, setRole] = useState<"teacher" | "student">("teacher");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const register = mode === "register";

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (submissionInProgress.current) return;
    setError("");
    setNotice("");
    const form = new FormData(event.currentTarget);
    const email = String(form.get("email") ?? "").trim();
    const password = String(form.get("password") ?? "");
    const name = String(form.get("name") ?? "").trim();

    if (register && !name) { setError("Enter your name to create an account."); return; }
    if (!email.includes("@") || password.length < 6) { setError("Use a valid email and a password of at least 6 characters."); return; }

    submissionInProgress.current = true;
    setLoading(true);
    try {
      if (register) {
        const user = await authService.register(name, email, password, role);
        onAuthenticated(user);
      } else {
        onAuthenticated(await authService.login(email, password));
      }
      navigate("/app");
    } catch (reason) {
      const message = extractErrorMessage(reason, "Authentication failed. Check your credentials and server status.");
      const isEmailRateLimited =
        /email rate limit exceeded/i.test(message) ||
        (typeof reason === "object" && reason !== null && "code" in reason && reason.code === "over_email_send_rate_limit");
      setError(isEmailRateLimited
        ? "Confirmation emails are temporarily rate-limited. Please wait before trying again; you can manually resubmit once the limit clears."
        : message);
    } finally {
      submissionInProgress.current = false;
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
          {notice && <div role="status" className="form-success">{notice}</div>}
          <Button className="full-button" disabled={loading}>
            {loading ? <><span className="button-spinner" />{register ? "Creating account…" : "Signing in…"}</> : <>{register ? "Create account" : "Sign in"}<ArrowRight size={14} /></>}
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
