import { useRef, useState, type Dispatch, type DragEvent, type FormEvent, type SetStateAction } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import {
  Activity, AlertCircle, ArrowDownToLine, ArrowLeft, ArrowRight, Award, BookOpen, CalendarDays,
  Check, CheckCircle2, ChevronLeft, ChevronRight, Clock3, CloudUpload,
  FileCheck2, FileText, Filter, GraduationCap, Info, LayoutDashboard, MoreHorizontal, Plus,
  Search, ShieldCheck, Sparkles, Upload, Users, X,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";
import {
  Area, AreaChart, CartesianGrid, Cell, Pie, PieChart, ResponsiveContainer,
  Tooltip, XAxis, YAxis,
} from "recharts";
import { motion } from "framer-motion";
import * as Dialog from "@radix-ui/react-dialog";
import { authService } from "./services/api";
import { mockService } from "./services/mock-service";
import { assignments, courses, leaderboard, publishedResults, rubrics, submissions as mockSubmissions, users } from "./lib/mock-data";
import { formatDate } from "./lib/utils";
import { useAppState } from "./App";
import { Avatar, Badge, Button, ConfirmDialog, GlassPanel, Panel, StatusBadge, useToast } from "./components/ui";
import type { Assignment, Course, CourseMaterial, Question, Submission, User } from "./types/models";

const demoLabel = <span className="demo-label">DEMO DATA</span>;

function PageHeader({ eyebrow = "TRUSTGRADE WORKSPACE", title, subtitle, action }: { eyebrow?: string; title: string; subtitle: string; action?: React.ReactNode }) {
  return <div className="page-heading"><div><div className="eyebrow">{eyebrow}</div><h1>{title}</h1><p className="page-subtitle">{subtitle}</p></div>{action && <div className="heading-actions">{action}</div>}</div>;
}

function SectionTitle({ title, subtitle, action }: { title: string; subtitle?: string; action?: React.ReactNode }) {
  return <div className="section-heading"><div><h2>{title}</h2>{subtitle && <p>{subtitle}</p>}</div>{action}</div>;
}

function AvatarStack({ ids }: { ids: string[] }) {
  return <div className="avatar-stack">{ids.map((id) => {
    const user = users.find((item) => item.id === id);
    return user && <Avatar key={id} name={user.name} initials={user.initials} />;
  })}<span className="avatar-more">+68</span></div>;
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
        <defs><linearGradient id="sageWash" x1="0" x2="0" y1="0" y2="1"><stop offset="0%" stopColor="#81927f" stopOpacity={0.17} /><stop offset="95%" stopColor="#81927f" stopOpacity={0} /></linearGradient></defs>
        <CartesianGrid vertical={false} stroke="#ecebe5" strokeDasharray="3 5" />
        <XAxis dataKey="week" axisLine={false} tickLine={false} tick={{ fill: "#96978f", fontSize: 10 }} dy={10} />
        <YAxis domain={[60, 100]} ticks={[60, 70, 80, 90, 100]} axisLine={false} tickLine={false} tick={{ fill: "#96978f", fontSize: 9 }} />
        <Tooltip cursor={{ stroke: "#d7d9d1", strokeDasharray: "3 4" }} contentStyle={{ borderRadius: 9, border: "1px solid #eeede8", boxShadow: "0 6px 20px #20231f12", fontSize: 10 }} formatter={(value) => [`${value} / 100`, "Average mark"]} />
        <Area type="monotone" dataKey="average" stroke="#34483b" strokeWidth={2.2} fill="url(#sageWash)" activeDot={{ r: 4, fill: "#fff", stroke: "#34483b", strokeWidth: 2 }} />
      </AreaChart>
    </ResponsiveContainer>
  </div>;
}

const distribution = [{ name: "A", value: 38, fill: "#435b48" }, { name: "B", value: 61, fill: "#657b66" }, { name: "C", value: 74, fill: "#91a18b" }, { name: "D", value: 51, fill: "#becbb9" }, { name: "F", value: 24, fill: "#e1e6dc" }];

function DistributionChart() {
  return <div className="distribution-layout"><div className="donut-wrap"><ResponsiveContainer width="100%" height="100%"><PieChart><Pie data={distribution} dataKey="value" nameKey="name" innerRadius="69%" outerRadius="92%" paddingAngle={3} stroke="none">{distribution.map((item) => <Cell key={item.name} fill={item.fill} />)}</Pie><Tooltip contentStyle={{ borderRadius: 9, border: "1px solid #eeede8", fontSize: 10 }} /></PieChart></ResponsiveContainer><div className="donut-center"><strong>248</strong><span>students</span></div></div><div className="distribution-legend">{distribution.map((item) => <div className="distribution-row" key={item.name}><span className="legend-key" style={{ background: item.fill }} /><span>{item.name}</span><strong>{item.value}</strong></div>)}</div></div>;
}

function StatCard({ title, value, note, change, icon: Icon, featured = false, alert = false }: { title: string; value: string; note: string; change: string; icon: typeof Users; featured?: boolean; alert?: boolean }) {
  return <Panel className={`stat-card ${featured ? "stat-feature" : ""} ${alert ? "stat-alert" : ""}`}><div className="stat-top"><span>{title}</span><span className="stat-icon"><Icon size={16} /></span></div><div className="stat-value-row"><strong>{value}</strong><span className="stat-change">{change}</span></div><div className="stat-foot">{note}</div><svg className="stat-spark" viewBox="0 0 84 30" aria-hidden="true"><polyline points="0,23 12,19 24,20 36,12 48,15 60,7 72,10 84,3" fill="none" stroke="#82927d" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" /></svg></Panel>;
}

function RecentSubmissions({ rows }: { rows: Submission[] }) {
  const { user, assignments: assignmentList, people } = useAppState();
  const navigate = useNavigate();
  const submissionDetails = rows.map((submission) => ({ submission, student: people.find((person) => person.id === submission.studentId), assignment: assignmentList.find((item) => item.id === submission.assignmentId) }));
  return <div className="table-scroll"><table className="data-table"><thead><tr><th>Student</th><th>Assignment</th><th>Submitted</th><th>OCR</th><th>AI grade</th><th>Status</th><th>Action</th></tr></thead><tbody>
    {submissionDetails.map(({ submission, student, assignment }) => <tr key={submission.id}>
      <td><span className="student-name">{student && <Avatar name={student.name} initials={student.initials} />}{student?.name}</span></td>
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
  return <>
    <div className="welcome-row"><div><div className="eyebrow">SATURDAY, OCTOBER 31, 2026</div><h1>Good morning, Alex.</h1><p className="page-subtitle">Your classroom, intelligently organized.</p><div className="welcome-context"><span>12 assignments</span><i /><span>248 students</span><i /><span>18 pending reviews</span></div></div><Button onClick={() => navigate("/app/assignment/new")}><Plus size={16} />Create assignment</Button></div>
    <div className="stat-grid">{[
      { title: "Active courses", value: "8", note: "Across 3 departments", change: "+2 this term", icon: BookOpen, featured: true },
      { title: "Students", value: "248", note: "Across all courses", change: "+12 this month", icon: Users },
      { title: "Pending reviews", value: "18", note: "6 need your attention", change: "3 due today", icon: Clock3, alert: true },
      { title: "Published assignments", value: "24", note: "Feedback shared", change: "+4 this month", icon: CheckCircle2 },
    ].map((item) => <StatCard key={item.title} {...item} />)}</div>
    <div className="dashboard-grid">
      <Panel className="grading-feature"><div className="feature-top"><div className="feature-title"><span className="feature-symbol"><Sparkles size={16} /></span><span><strong>AI Grading Activity</strong><small>A little help with the heavy lifting.</small></span></div><Badge tone="sage"><i className="live-dot" />In progress</Badge></div>
        <h2 className="feature-assignment">Data Structures — Assignment 03</h2><p className="feature-course">CS 204 <i /> Due Oct 31, 11:59 PM</p>
        <div className="progress-row"><span><strong>72 / 96</strong> submissions reviewed</span><span>75%</span></div><div className="progress-track"><span style={{ width: "75%" }} /></div>
        <div className="feature-bottom"><AvatarStack ids={["student-maya", "student-ethan", "student-sofia", "student-noah"]} /><div className="feature-meta"><span><CheckCircle2 size={13} />Avg. confidence 91%</span><span><Clock3 size={13} />24 awaiting review</span></div><Button variant="secondary" size="sm" onClick={() => navigate("/app/grading/sub-maya-ds")}>Continue review<ArrowRight size={14} /></Button></div>
        <span className="feature-watermark"><ShieldCheck size={138} strokeWidth={0.55} /></span>
      </Panel>
      <div className="side-stack"><Panel className="mini-card"><div className="mini-head"><span>Class performance</span><Activity size={15} /></div><strong className="mini-number">84.6 <small>/ 100</small></strong><p>Average across active courses</p><div className="mini-meter"><span style={{ width: "84.6%" }} /></div><span className="mini-foot">↑ 3.2% this term</span></Panel>
        <Panel className="mini-card"><div className="mini-head"><span>Students to check in with</span><Users size={15} /></div><strong className="mini-number">6</strong><p>May benefit from a little support</p><AvatarStack ids={["student-maya", "student-ethan", "student-sofia"]} /></Panel></div>
    </div>
    <div className="analytics-grid"><Panel className="chart-card"><SectionTitle title="Performance trend" subtitle="Average marks across all courses" action={<select className="filter-select"><option>Last 8 weeks</option><option>This term</option></select>} /><div className="chart-total">84.6 <span>↑ 3.2% this term</span></div><TrendChart /></Panel><Panel className="chart-card"><SectionTitle title="Grade distribution" subtitle="248 students · all active courses" action={demoLabel} /><DistributionChart /></Panel></div>
    <div className="lower-grid"><Panel className="deadline-card"><SectionTitle title="Upcoming deadlines" subtitle="A clear view of what’s next" action={<button className="text-button" onClick={() => navigate("/app/assignments")}>View all<ArrowRight size={13} /></button>} /><div className="timeline">
      {[
        ["Operating Systems — Assignment 02", "CS 301 · 31 submissions", "Tomorrow, 11:59 PM", true],
        ["Database Systems — Project 01", "CS 220 · 38 submissions", "Nov 03, 11:59 PM", false],
        ["Data Structures — Quiz 04", "CS 204 · 42 submissions", "Nov 05, 9:00 AM", false],
      ].map(([title, detail, due, urgent]) => <div className={`timeline-item ${urgent ? "urgent" : ""}`} key={title.toString()}><strong>{title}</strong><div><span>{detail}</span><b>{due}</b></div></div>)}
    </div></Panel>
    <Panel className="recent-card"><SectionTitle title="Recent submissions" subtitle="Your latest classroom activity" action={<button className="text-button" onClick={() => navigate("/app/submissions")}>View all<ArrowRight size={13} /></button>} /><RecentSubmissions rows={mockSubmissions.slice(0, 3)} /></Panel></div>
  </>;
}

function StudentOverview() {
  const navigate = useNavigate();
  const { user, courses: courseList, assignments: assignmentList, joinedCourseIds, submissions: studentRows } = useAppState();
  const myCourses = courseList.filter((course) => joinedCourseIds.includes(course.id));
  const myAssignments = assignmentList.filter((assignment) => assignment.state === "Published" && joinedCourseIds.includes(assignment.courseId));
  const published = studentRows.filter((item) => item.studentId === user?.id && item.state === "Published" && item.grading?.teacherApproved);
  const latestPublished = published[0];
  const latestAssignment = latestPublished && assignmentList.find((item) => item.id === latestPublished.assignmentId);
  return <>
    <div className="page-heading"><div><div className="eyebrow">STUDENT WORKSPACE · SATURDAY, OCTOBER 31</div><h1>Welcome back, {user?.name.split(" ")[0] ?? "there"}.</h1><p className="page-subtitle">Stay on top of your coursework. You’re making steady progress.</p></div><Button variant="secondary" onClick={() => navigate("/app/student/assignments")}><Plus size={15} />Join a course</Button></div>
    <Panel className="student-welcome"><div className="student-welcome-copy"><span className="eyebrow">A GOOD WEEK TO KEEP GOING</span><h2>Small steps add up.</h2><p>{latestPublished ? "Your teacher has published feedback. Take a moment to review what went well and what to try next." : "Your coursework and teacher feedback will appear here as your classes get underway."}</p><Button variant="secondary" size="sm" onClick={() => navigate("/app/student/assignments")}>See what’s next<ArrowRight size={14} /></Button></div><div className="student-progress-orb"><span>86.4</span><small>current average</small><svg viewBox="0 0 120 120"><circle cx="60" cy="60" r="52" /><circle className="progress-circle" cx="60" cy="60" r="52" /></svg></div></Panel>
    <div className="student-stat-row"><Panel className="student-stat"><span>Current average</span><strong>86.4</strong><small>↑ 2.8 this month</small></Panel><Panel className="student-stat"><span>Assignments completed</span><strong>12 <small>/ 15</small></strong><small>3 still to come</small></Panel><Panel className="student-stat"><span>Pending feedback</span><strong>2</strong><small>Being reviewed by your teacher</small></Panel></div>
    <div className="student-columns"><div><SectionTitle title="Coming up" subtitle="Plan your next study session" action={<button className="text-button" onClick={() => navigate("/app/student/assignments")}>All assignments<ArrowRight size={13} /></button>} />
      {myAssignments.slice(0, 3).map((assignment) => { const ownSubmission = studentRows.find((item) => item.studentId === user?.id && item.assignmentId === assignment.id); const status = ownSubmission?.state ?? "Not Started"; const destination = status === "Published" ? "/app/results" : assignment.submissionType === "MCQ" ? `/app/student/assessment/${assignment.id}` : `/app/student/submit/${assignment.id}`; return <Panel key={assignment.id} className="student-assignment-card"><span className="course-icon"><FileText size={16} /></span><span className="assignment-card-copy"><strong>{assignment.title}</strong><small>{courseList.find((course) => course.id === assignment.courseId)?.code} · Due {formatDate(assignment.dueAt)}</small></span><StatusBadge status={status} /><Button size="sm" variant="secondary" onClick={() => navigate(destination)}>{status === "Published" ? "View feedback" : "Open"}<ChevronRight size={13} /></Button></Panel>; })}
      <SectionTitle title="Recently published" subtitle="Only teacher-approved results appear here" />
      {latestPublished && latestAssignment && <Panel className="published-result-card"><span className="result-seal"><Check size={16} /></span><span><strong>{latestAssignment.title}</strong><small>{courseList.find((course) => course.id === latestAssignment.courseId)?.name} · Teacher approved</small></span><strong className="result-score">{latestPublished.grading?.suggestedScore} <small>/ {latestAssignment.totalMarks}</small></strong><Button size="sm" variant="secondary" onClick={() => navigate("/app/results")}>View feedback<ChevronRight size={13} /></Button></Panel>}
    </div><aside><SectionTitle title="Your courses" subtitle="This term" /><div className="course-summary-list">{myCourses.slice(0, 3).map((course) => <Panel className="course-summary" key={course.id}><span className="course-summary-icon"><BookOpen size={15} /></span><span><strong>{course.name}</strong><small>{course.code}</small></span><ChevronRight size={15} /></Panel>)}{!myCourses.length && <Panel className="empty-state">Join a course to see your class activity here.</Panel>}</div><Panel className="notice-card"><span className="notice-icon"><Info size={15} /></span><div><strong>New course material</strong><p>Week 07: Trees &amp; Graphs slides are available.</p><span>2 hours ago</span></div></Panel></aside></div>
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
  const navigate = useNavigate();
  const toast = useToast();
  const student = user?.role === "student";
  const visibleCourses = student ? courseList.filter((course) => joinedCourseIds.includes(course.id)) : courseList;
  const filtered = visibleCourses.filter((course) => `${course.name} ${course.code} ${course.instructor}`.toLowerCase().includes(query.toLowerCase()) && (courseFilter !== "Active this week" || course.activity > 60));
  const createCourse = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const name = String(form.get("courseName") ?? "").trim();
    const code = String(form.get("courseCode") ?? "").trim().toUpperCase();
    if (!name || !code) return;
    if (courseList.some((course) => course.code.toLowerCase() === code.toLowerCase())) { toast("A course with this code already exists.", "info"); return; }
    const created: Course = { id: `course-${crypto.randomUUID()}`, name, code, instructor: "Dr. Alex Morgan", students: 0, assignments: 0, activity: 0, average: 0 };
    setCourses((current) => [...current, created]);
    setDialogOpen(false);
    toast(`${name} added to this workspace.`);
  };
  return <><PageHeader title={student ? "My courses" : "Your courses"} subtitle={student ? "The classes you’re enrolled in this term." : "Every class, thoughtfully brought together."} action={student ? <Button onClick={() => navigate("/app/student/assignments")}><Plus size={15} />Join a course</Button> : <Dialog.Root open={dialogOpen} onOpenChange={setDialogOpen}><Dialog.Trigger asChild><Button><Plus size={15} />Create course</Button></Dialog.Trigger><Dialog.Portal><Dialog.Overlay className="modal-backdrop" /><Dialog.Content className="modal" aria-describedby="course-create-description"><div className="modal-head"><Dialog.Title className="modal-title">Create a course</Dialog.Title><Dialog.Close asChild><Button variant="quiet" size="icon" aria-label="Close"><X size={15} /></Button></Dialog.Close></div><Dialog.Description id="course-create-description" className="modal-description">Set up a course workspace for assignments, materials, and student progress.</Dialog.Description><form onSubmit={createCourse}><div className="field-block"><label htmlFor="course-name">Course name</label><input id="course-name" name="courseName" className="field-input" placeholder="e.g. Applied Computing" required /></div><div className="field-block"><label htmlFor="course-code">Course code</label><input id="course-code" name="courseCode" className="field-input" placeholder="e.g. CS 240" required /></div><div className="modal-actions"><Dialog.Close asChild><Button type="button" variant="secondary">Cancel</Button></Dialog.Close><Button type="submit">Create course</Button></div></form></Dialog.Content></Dialog.Portal></Dialog.Root>} />
    <div className="toolbar"><label className="inline-search"><Search size={14} /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search courses..." aria-label="Search courses" /></label><select className="filter-select" aria-label="Term"><option>Spring term 2026</option><option>Fall term 2026</option></select><select className="filter-select" aria-label="Activity filter" value={courseFilter} onChange={(event) => setCourseFilter(event.target.value)}><option>All courses</option><option>Active this week</option></select></div>
    <div className="course-grid">{filtered.length ? filtered.map((course, index) => <motion.div key={course.id} initial={{ opacity: 0, y: 7 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: index * 0.035 }}><Panel className="course-card"><div className={`course-accent accent-${index % 4}`} /><div className="course-card-top"><span className="course-icon"><BookOpen size={18} /></span><Badge>{course.code}</Badge></div><h3>{course.name}</h3><span className="course-instructor">{course.instructor}</span><div className="course-stats"><div><strong>{course.students}</strong><small>Students</small></div><div><strong>{course.assignments}</strong><small>Assignments</small></div><div><strong>{Math.round(course.students * 0.75)}</strong><small>Active this week</small></div></div><div className="course-activity"><span>Course activity</span><span className="activity-meter"><i style={{ width: `${course.activity}%` }} /></span><b>{course.activity}%</b></div><button className="text-button" onClick={() => navigate(`/app/courses/${course.id}`)}>Open course<ArrowRight size={13} /></button></Panel></motion.div>) : <Panel className="empty-state">No courses match “{query}”.</Panel>}</div>
  </>;
}

export function CourseDetailPage({ courses: courseList }: { courses: Course[] }) {
  const { assignments: assignmentList } = useAppState();
  const { courseId } = useParams();
  const navigate = useNavigate();
  const course = courseList.find((item) => item.id === courseId);
  if (!course) return <NotFoundPage />;
  const courseAssignments = assignmentList.filter((item) => item.courseId === course.id);
  return <><PageHeader title={course.name} subtitle={`${course.code} · ${course.instructor} · Spring term 2026`} action={<><Button variant="secondary" onClick={() => navigate("/app/materials")}><FileCheck2 size={15} />Course materials</Button><Button onClick={() => navigate("/app/assignment/new")}><Plus size={15} />Create assignment</Button></>} />
    <div className="metric-strip">{[["Enrolled students", course.students, "Active this term"], ["Assignments", course.assignments, "Across this course"], ["Course activity", `${course.activity}%`, "Active this week"], ["Average mark", `${course.average}`, "↑ 2.4 this term"]].map(([label, value, note]) => <Panel className="metric-card" key={label.toString()}><span>{label}</span><strong>{value}</strong><small>{note}</small></Panel>)}</div>
    <div className="course-detail-grid"><Panel className="recent-card"><SectionTitle title="Course assignments" subtitle="Recent work and grading progress" /><div className="table-scroll"><table className="data-table"><thead><tr><th>Assignment</th><th>Due</th><th>Submissions</th><th>Grading state</th></tr></thead><tbody>{courseAssignments.length ? courseAssignments.map((item) => <tr key={item.id}><td>{item.title}</td><td>{formatDate(item.dueAt)}</td><td>38 / {course.students}</td><td><StatusBadge status={item.state} /></td></tr>) : <tr><td colSpan={4}>No assignments yet.</td></tr>}</tbody></table></div></Panel><Panel className="course-activity-panel"><SectionTitle title="Course activity" subtitle="Recent moments from your classroom" /><div className="timeline"><div className="timeline-item"><strong>New submissions received</strong><span>8 students submitted Assignment 03</span><small>Today, 9:42 AM</small></div><div className="timeline-item"><strong>Course material added</strong><span>Week 07: Trees &amp; Graphs</span><small>Oct 29, 2:18 PM</small></div><div className="timeline-item"><strong>Assignment published</strong><span>Quiz 03 — Traversals</span><small>Oct 25, 10:00 AM</small></div></div></Panel></div>
  </>;
}

export function AssignmentsPage() {
  const navigate = useNavigate();
  const { user, assignments: assignmentList } = useAppState();
  const student = user?.role === "student";
  const items = student ? assignmentList.filter((assignment) => assignment.state === "Published") : assignmentList;
  return <><PageHeader title={student ? "My assignments" : "Assignments"} subtitle={student ? "A clear view of what’s due and what you’ve submitted." : "Thoughtfully set up, clearly tracked, and always teacher-led."} action={!student && <Button onClick={() => navigate("/app/assignment/new")}><Plus size={15} />Create assignment</Button>} />
    <div className="toolbar"><div className="segmented"><button className="segment active">All</button><button className="segment">Upcoming</button><button className="segment">Past</button></div><select className="filter-select"><option>All courses</option>{courses.map((course) => <option key={course.id}>{course.name}</option>)}</select></div>
    <div className="assignment-list">{items.map((assignment, index) => {
      const state = student ? ["In Progress", "Not Started", "Under Review"][index % 3] : assignment.state;
      const route = assignment.submissionType === "MCQ" ? `/app/student/assessment/${assignment.id}` : `/app/student/submit/${assignment.id}`;
      return <Panel className="assignment-list-card" key={assignment.id}><span className="course-icon"><FileText size={17} /></span><div className="assignment-list-main"><strong>{assignment.title}</strong><small>{courses.find((course) => course.id === assignment.courseId)?.code} · {assignment.totalMarks} marks</small></div><div className="assignment-list-meta"><span><CalendarDays size={13} />Due {formatDate(assignment.dueAt)}</span><span>{assignment.submissionType} submission</span></div><StatusBadge status={state} /><Button variant="secondary" size="sm" onClick={() => navigate(student ? route : `/app/submissions`)}>{student ? "Open assignment" : "View submissions"}<ChevronRight size={13} /></Button></Panel>;
    })}</div>
  </>;
}

export function AssignmentEditor({ courses: courseList, assignments: assignmentList, setAssignments }: {
  courses: Course[];
  assignments: Assignment[];
  setAssignments: Dispatch<SetStateAction<Assignment[]>>;
}) {
  const navigate = useNavigate();
  const toast = useToast();
  const { setCourses } = useAppState();
  const [questions, setQuestions] = useState<Question[]>(assignments[0].questions.slice(0, 2).map((item) => ({ ...item })));
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [dueAt, setDueAt] = useState("2026-11-07T23:59");
  const [rubricId, setRubricId] = useState(rubrics[0].id);
  const [difficulty, setDifficulty] = useState("Mixed");
  const [count, setCount] = useState("5");
  const [type, setType] = useState<"Subjective" | "MCQ" | "Mixed">("Mixed");
  const [generating, setGenerating] = useState(false);
  const [generatedQuestionIds, setGeneratedQuestionIds] = useState<string[]>([]);
  const [courseId, setCourseId] = useState(courseList[0]?.id ?? "");
  const total = questions.reduce((sum, item) => sum + item.marks, 0);

  const updateQuestion = (id: string, patch: Partial<Question>) => setQuestions((current) => current.map((item) => item.id === id ? { ...item, ...patch } : item));
  const generate = async () => {
    setGenerating(true);
    try {
      const generated = await mockService.generateQuestions(Number(count), type, difficulty);
      setQuestions((current) => [...current.filter((question) => !generatedQuestionIds.includes(question.id)), ...generated]);
      setGeneratedQuestionIds(generated.map((question) => question.id));
      toast(`${generated.length} draft questions are ready. Review each before publishing.`, "info");
    } finally { setGenerating(false); }
  };
  const saveAssignment = (state: Assignment["state"]) => {
    const cleanTitle = title.trim();
    if (!cleanTitle) { toast("Add an assignment title before saving.", "info"); return; }
    if (!courseId) { toast("Choose a course before saving this assignment.", "info"); return; }
    if (assignmentList.some((item) => item.courseId === courseId && item.title.toLowerCase() === cleanTitle.toLowerCase())) {
      toast("An assignment with this title already exists in the selected course.", "info");
      return;
    }
    const deadline = new Date(dueAt);
    if (Number.isNaN(deadline.valueOf())) { toast("Choose a valid due date before saving.", "info"); return; }
    if (state === "Published" && (!questions.length || questions.some((question) => !question.prompt.trim()) || total <= 0)) {
      toast("Add a question prompt and valid marks before publishing.", "info");
      return;
    }
    const questionTypes = new Set(questions.map((question) => question.type));
    const created: Assignment = {
      id: `assignment-${crypto.randomUUID()}`,
      courseId,
      title: cleanTitle,
      description: description.trim(),
      dueAt: deadline.toISOString(),
      totalMarks: total,
      state,
      submissionType: questionTypes.size > 1 ? "Mixed" : questionTypes.has("MCQ") ? "MCQ" : "PDF",
      rubricId,
      questions: questions.map((question) => ({ ...question, prompt: question.prompt.trim() })),
    };
    setAssignments((current) => [created, ...current]);
    setCourses((current) => current.map((course) => course.id === courseId ? { ...course, assignments: course.assignments + 1 } : course));
    toast(state === "Published" ? "Assignment published in this demo. Students in the course can now see it." : "Assignment draft saved in this demo.", "info");
    navigate("/app/assignments");
  };

  return <><PageHeader title="Create assignment" subtitle="Give your class a clear, thoughtful next step." action={<><Button variant="secondary" onClick={() => saveAssignment("Draft")}><FileText size={15} />Save draft</Button><Button onClick={() => saveAssignment("Published")}><Upload size={15} />Publish assignment</Button></>} />
    <div className="editor-layout"><div className="editor-main"><Panel className="editor-card"><SectionTitle title="Assignment details" /><div className="field-block"><label htmlFor="assignment-title">Assignment title</label><input id="assignment-title" className="field-input" value={title} onChange={(event) => setTitle(event.target.value)} placeholder="e.g. Data Structures — Assignment 04" /></div><div className="field-block"><label htmlFor="assignment-description">Description for students</label><textarea id="assignment-description" className="field-textarea" value={description} onChange={(event) => setDescription(event.target.value)} placeholder="Set the context and let students know what they’ll learn..." /></div></Panel>
      <Panel className="editor-card"><SectionTitle title="Questions" subtitle={`${questions.length} questions · ${total} marks total`} action={<Button variant="secondary" size="sm" onClick={() => setQuestions((current) => [...current].reverse())}><Filter size={13} />Reorder</Button>} />
        <div className="question-list">{questions.map((question, index) => <QuestionEditor key={question.id} question={question} index={index} onChange={(patch) => updateQuestion(question.id, patch)} onDelete={() => setQuestions((current) => current.filter((item) => item.id !== question.id))} onMove={() => setQuestions((current) => { if (!index) return current; const next = [...current]; [next[index - 1], next[index]] = [next[index], next[index - 1]]; return next; })} />)}</div>
        <Button className="add-question-button" variant="secondary" onClick={() => setQuestions((current) => [...current, { id: crypto.randomUUID(), prompt: "", type: "Subjective", marks: 5, expectedAnswer: "" }])}><Plus size={14} />Add a question</Button>
      </Panel></div>
      <aside className="editor-side"><Panel className="ai-panel"><div className="ai-title"><span className="feature-symbol"><Sparkles size={15} /></span><div><strong>Generate with AI</strong><small>A starting point, always yours to review.</small></div></div>
        <div className="field-block"><label>Difficulty</label><div className="difficulty-options">{["Easy", "Medium", "Hard", "Mixed"].map((item) => <button key={item} className={difficulty === item ? "active" : ""} onClick={() => setDifficulty(item)}>{item}</button>)}</div></div>
        <div className="field-block"><label htmlFor="question-count">Question count</label><select id="question-count" className="field-select" value={count} onChange={(event) => setCount(event.target.value)}>{["3", "5", "8", "10"].map((item) => <option key={item} value={item}>{item} questions</option>)}</select></div>
        <div className="field-block"><label htmlFor="question-type">Question type</label><select id="question-type" className="field-select" value={type} onChange={(event) => setType(event.target.value as typeof type)}><option value="Mixed">Mix of subjective &amp; MCQ</option><option value="Subjective">Subjective only</option><option value="MCQ">MCQ only</option></select></div>
        <div className="field-block"><label>Source materials</label><label className="material-check"><input type="checkbox" defaultChecked />Week 07: Trees &amp; Graphs</label><label className="material-check"><input type="checkbox" defaultChecked />Course syllabus</label><label className="material-check"><input type="checkbox" />Grading rubric</label></div>
        <div className="ai-disclaimer"><Info size={13} />Suggestions are generated locally for this prototype. Verify accuracy, fairness, and course fit against the selected material before publishing.</div>
        <Button className="full-button" disabled={generating} onClick={generate}>{generating ? <><span className="button-spinner" />Drafting suggestions…</> : <><Sparkles size={14} />{generatedQuestionIds.length ? "Regenerate suggestions" : "Generate questions"}</>}</Button>
      </Panel>
      <Panel className="editor-card"><SectionTitle title="Assignment settings" /><div className="field-block"><label htmlFor="course-select">Course</label><select id="course-select" className="field-select" value={courseId} onChange={(event) => setCourseId(event.target.value)}>{courseList.map((course) => <option value={course.id} key={course.id}>{course.name} · {course.code}</option>)}</select></div><div className="field-block"><label htmlFor="due-date">Due date</label><input id="due-date" className="field-input" type="datetime-local" value={dueAt} onChange={(event) => setDueAt(event.target.value)} /></div><div className="field-block"><label htmlFor="total-marks">Total marks</label><input id="total-marks" className="field-input" type="number" value={total} readOnly /></div><div className="field-block"><label htmlFor="rubric-select">Rubric</label><select id="rubric-select" className="field-select" value={rubricId} onChange={(event) => setRubricId(event.target.value)}>{rubrics.map((rubric) => <option value={rubric.id} key={rubric.id}>{rubric.name}</option>)}</select></div><div className="publish-toggle"><span><strong>Publishing state</strong><small>Review questions before sharing with students</small></span><StatusBadge status="Draft until published" /></div></Panel></aside></div>
  </>;
}

function QuestionEditor({ question, index, onChange, onDelete, onMove }: { question: Question; index: number; onChange: (patch: Partial<Question>) => void; onDelete: () => void; onMove: () => void }) {
  return <article className="question-card"><div className="question-head"><div className="question-label"><span className="question-number">{index + 1}</span>Question {index + 1}<Badge>{question.type}</Badge></div><div className="question-tools"><button className="icon-button" aria-label="Move question up" onClick={onMove}><ChevronLeft size={14} /></button><button className="icon-button" aria-label="Delete question" onClick={onDelete}><X size={14} /></button></div></div><div className="question-two-col"><div className="field-block"><label>Question prompt</label><textarea className="field-textarea" value={question.prompt} onChange={(event) => onChange({ prompt: event.target.value })} placeholder="Write your question..." /></div><div className="field-block"><label>Type · marks</label><select className="field-select" value={question.type} onChange={(event) => onChange({ type: event.target.value as Question["type"] })}><option>Subjective</option><option>MCQ</option></select><input className="field-input question-mark-input" type="number" min={1} value={question.marks} onChange={(event) => onChange({ marks: Number(event.target.value) })} aria-label={`Marks for question ${index + 1}`} /></div></div><div className="field-block expected-answer"><label>{question.type === "MCQ" ? "Correct answer" : "Expected answer / marking guidance"}</label><textarea className="field-textarea" value={question.expectedAnswer} onChange={(event) => onChange({ expectedAnswer: event.target.value })} placeholder="Provide expected reasoning, not just keywords." /></div>{question.type === "MCQ" && <div className="mcq-options">{(question.options ?? ["Option A", "Option B", "Option C", "Option D"]).map((option, optionIndex) => <label key={optionIndex}><input type="radio" name={`correct-${question.id}`} checked={(question.correctOption ?? 0) === optionIndex} onChange={() => onChange({ correctOption: optionIndex })} /><input value={option} onChange={(event) => onChange({ options: (question.options ?? ["Option A", "Option B", "Option C", "Option D"]).map((item, current) => current === optionIndex ? event.target.value : item) })} aria-label={`Option ${optionIndex + 1}`} /></label>)}</div>}</article>;
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
      if (file.size > 25 * 1024 * 1024) { toast(`${file.name}: file exceeds the 25 MB demo limit.`, "info"); continue; }
      valid.push({ id: crypto.randomUUID(), name: file.name, category: extension?.startsWith("ppt") ? "Lecture slides" : extension === "doc" || extension === "docx" ? "Notes" : "Reference", size: file.size > 1_048_576 ? `${(file.size / 1_048_576).toFixed(1)} MB` : `${Math.max(1, Math.round(file.size / 1024))} KB`, uploadedAt: new Date().toISOString(), state: "Uploading", indexing: "Processing" });
    }
    if (valid.length) { setMaterials((current) => [...valid, ...current]); toast(`${valid.length} file${valid.length === 1 ? "" : "s"} added. Processing is simulated in this demo.`, "info"); }
  };
  const visible = fileList.filter((file) => filter === "All files" || (filter === "Course docs" ? ["Syllabus", "Rulebook", "Rubric"].includes(file.category) : ["Notes", "Reference"].includes(file.category)));
  return <><PageHeader title="Course materials" subtitle="Keep the knowledge behind every assignment in one place." action={<Button onClick={() => inputRef.current?.click()}><Plus size={15} />Add materials</Button>} />
    <div className="toolbar"><div className="toolbar-left"><select className="filter-select"><option>Data Structures · CS 204</option><option>Operating Systems · CS 301</option><option>Database Systems · CS 220</option></select><div className="segmented">{["All files", "Course docs", "Reference"].map((item) => <button className={filter === item ? "segment active" : "segment"} key={item} onClick={() => setFilter(item)}>{item}</button>)}</div></div><span className="demo-label">{fileList.length} FILES · DEMO DATA</span></div>
    <GlassPanel className={`upload-zone ${dragging ? "drag-active" : ""}`} onDragOver={(event: DragEvent<HTMLElement>) => { event.preventDefault(); setDragging(true); }} onDragLeave={() => setDragging(false)} onDrop={(event: DragEvent<HTMLElement>) => { event.preventDefault(); setDragging(false); addFiles(event.dataTransfer.files); }}>
      <input ref={inputRef} className="visually-hidden" type="file" multiple accept=".pdf,.ppt,.pptx,.doc,.docx,.txt" onChange={(event) => { addFiles(event.target.files); event.target.value = ""; }} />
      <span className="upload-icon"><CloudUpload size={20} /></span><strong>Drop your course materials here</strong><p>PDF, PPTX, DOCX, or TXT · Up to 25 MB each</p><Button variant="secondary" size="sm" onClick={() => inputRef.current?.click()}>Browse files</Button><small>Processing and AI indexing statuses below are prototype data.</small>
    </GlassPanel>
    <SectionTitle title="Course library" subtitle="Manage the resources used by students and grading workflows." action={demoLabel} />
    <Panel className="file-list"><div className="file-header"><span>Name</span><span>Category</span><span>Size</span><span>Uploaded</span><span>Processing</span><span>Indexing</span><span /></div>{visible.map((file) => <div className="file-row" key={file.id}><span className="file-name"><span className="file-icon"><FileText size={16} /></span><span><strong>{file.name}</strong><small>{file.id.startsWith("mat") ? "Sample document" : "Local mock upload"}</small></span></span><span>{file.category}</span><span>{file.size}</span><span>{formatDate(file.uploadedAt)}</span><StatusBadge status={file.state} /><StatusBadge status={`Indexing ${file.indexing}`} /><button className="icon-button" aria-label={`Options for ${file.name}`} onClick={() => toast("Material actions are a demo-only interaction.", "info")}><MoreHorizontal size={15} /></button></div>)}</Panel>
  </>;
}

export function SubmissionsPage({ submissions: rows }: { submissions: Submission[] }) {
  const { user, assignments: assignmentList, people } = useAppState();
  const toast = useToast();
  const [filter, setFilter] = useState("All");
  const [query, setQuery] = useState("");
  const navigate = useNavigate();
  const student = user?.role === "student";
  const studentRows = rows.filter((item) => item.studentId === user?.id);
  const visible = (student ? studentRows : rows).filter((item) => {
    const person = people.find((userItem) => userItem.id === item.studentId)?.name ?? "";
    const matchesText = `${person} ${assignmentList.find((assignment) => assignment.id === item.assignmentId)?.title ?? ""}`.toLowerCase().includes(query.toLowerCase());
    const matchesState = filter === "All" || (filter === "Reviewed" ? ["Under Review", "Graded", "Published"].includes(item.state) : filter === "Pending" ? ["Submitted", "In Progress"].includes(item.state) : filter === "Needs OCR Review" ? ["Needs review", "Low confidence"].includes(item.ocr.state) : filter === "Published" ? item.state === "Published" : filter === "Late" ? item.state === "Late Submission" : item.state === filter);
    return matchesText && matchesState;
  });
  const filters = student ? ["All", "Submitted", "Under Review", "Graded", "Late Submission"] : ["All", "Pending", "Reviewed", "Late", "Needs OCR Review", "Published"];
  return <><PageHeader title={student ? "My submissions" : "Submissions"} subtitle={student ? "Keep track of work you’ve handed in and what’s being reviewed." : "A considered review queue. Late work always gets a human decision."} action={!student && <Button variant="secondary" onClick={() => toast("CSV export is available from the dashboard prototype.", "info")}><ArrowDownToLine size={15} />Export submissions</Button>} />
    {!student && <div className="submission-summary">{([
      { value: "18", label: "Pending review", icon: Clock3 },
      { value: "3", label: "OCR needs a check", icon: Search },
      { value: "4", label: "Late · decision needed", icon: AlertCircle },
      { value: "36", label: "Published this week", icon: CheckCircle2 },
    ] satisfies { value: string; label: string; icon: LucideIcon }[]).map(({ value, label, icon: Icon }) => <Panel className="summary-chip" key={label}><span className="stat-icon"><Icon size={15} /></span><span><strong>{value}</strong><small>{label}</small></span></Panel>)}</div>}
    {!student && <div className="late-note"><AlertCircle size={15} /><span><strong>Late submissions are held for your review.</strong> No automatic zero is applied; accept or reject each submission based on your course policy.</span></div>}
    <div className="toolbar"><div className="segmented">{filters.map((item) => <button className={filter === item ? "segment active" : "segment"} key={item} onClick={() => setFilter(item)}>{item}</button>)}</div><label className="inline-search"><Search size={14} /><input placeholder={student ? "Find an assignment..." : "Find a student..."} value={query} onChange={(event) => setQuery(event.target.value)} /></label></div>
    <SubmissionTable rows={visible} student={student} onReview={(item) => navigate(student ? `/app/student/submit/${item.assignmentId}` : `/app/grading/${item.id}`)} onAccept={(item) => navigate(`/app/grading/${item.id}`)} />
  </>;
}

function SubmissionTable({ rows, student, onReview, onAccept }: { rows: Submission[]; student: boolean; onReview: (item: Submission) => void; onAccept: (item: Submission) => void }) {
  const toast = useToast();
  const { setSubmissions, assignments: assignmentList, people } = useAppState();
  const person = (item: Submission) => people.find((user) => user.id === item.studentId);
  const assignment = (item: Submission) => assignmentList.find((entry) => entry.id === item.assignmentId);
  const decide = (item: Submission, accepted: boolean) => {
    setSubmissions((current) => current.map((entry) => entry.id === item.id ? { ...entry, state: accepted ? "Submitted" : "Late Submission" } : entry));
    toast(accepted ? "Late work accepted for grading. No automatic penalty was applied." : "Submission returned for a teacher decision; no automatic zero was assigned.", "info");
  };
  return <Panel className="table-card"><div className="table-scroll"><table className="data-table"><thead><tr>{student ? <><th>Assignment</th><th>Submitted</th><th>Due</th><th>Timing</th><th>OCR</th><th>Grading</th><th /></> : <><th>Student</th><th>Assignment</th><th>Submitted</th><th>Deadline</th><th>Timing</th><th>OCR</th><th>Grading</th><th>Action</th></>}</tr></thead><tbody>
    {rows.map((item) => <tr key={item.id}>{student ? <><td><strong>{assignment(item)?.title}</strong></td><td>{formatDate(item.submittedAt)}</td><td>{formatDate(item.deadline)}</td><td><StatusBadge status={item.state === "Late Submission" ? "Late" : "On time"} /></td><td><StatusBadge status={item.ocr.state} /></td><td><StatusBadge status={item.state} /></td><td><Button size="sm" variant="secondary" onClick={() => onReview(item)}>View<ChevronRight size={13} /></Button></td></> : <>
      <td><span className="student-name">{person(item) && <Avatar name={person(item)!.name} initials={person(item)!.initials} />}{person(item)?.name}</span></td><td>{assignment(item)?.title}</td><td>{formatDate(item.submittedAt)}</td><td>{formatDate(item.deadline)}</td><td><StatusBadge status={item.state === "Late Submission" ? "Late" : "On time"} /></td><td><StatusBadge status={item.ocr.state} /></td><td><StatusBadge status={item.state} /></td>
      <td>{item.state === "Late Submission" ? <span className="late-actions"><button className="text-button" onClick={() => decide(item, true)}>Accept</button><button className="text-button reject-text" onClick={() => decide(item, false)}>Reject</button><button className="text-button" onClick={() => onAccept(item)}>Review</button></span> : <button className="text-button" onClick={() => onReview(item)}>Review<ChevronRight size={13} /></button>}</td>
    </>}</tr>)}
    {!rows.length && <tr><td className="table-empty" colSpan={student ? 7 : 8}>No submissions match this view.</td></tr>}
  </tbody></table></div></Panel>;
}

export function GradingReviewPage({ submissions: rows, setSubmissions }: { submissions: Submission[]; setSubmissions: Dispatch<SetStateAction<Submission[]>> }) {
  const { assignments: assignmentList, people } = useAppState();
  const { submissionId } = useParams();
  const navigate = useNavigate();
  const toast = useToast();
  const submission = rows.find((item) => item.id === submissionId) ?? rows[0];
  const student = submission && people.find((item) => item.id === submission.studentId);
  const assignment = submission && assignmentList.find((item) => item.id === submission.assignmentId);
  const [scores, setScores] = useState([3, 2, 1.5, 1]);
  const [feedback, setFeedback] = useState(submission?.grading?.feedback.comment ?? "");
  const [question, setQuestion] = useState(0);
  if (!submission || !student || !assignment) return <NotFoundPage />;
  const total = scores.reduce((sum, value) => sum + value, 0);
  const questionCount = assignment.questions.length;
  const maximum = 10;

  const approve = () => {
    setSubmissions((current) => current.map((item) => item.id === submission.id ? { ...item, state: "Published", grading: { ...(item.grading ?? { suggestedScore: total, confidence: 0.91, reasoning: "", rubric: rubrics[0].criteria, feedback: { id: crypto.randomUUID(), comment: feedback, deductions: [], courseReferences: ["Lecture 04 — Trees", "Course Notes — Binary Search Trees"] }, teacherApproved: true }), suggestedScore: total, teacherApproved: true, feedback: { ...(item.grading?.feedback ?? { id: crypto.randomUUID(), deductions: [], courseReferences: [] }), comment: feedback } } } : item));
    toast("Grade approved and feedback published in the demo.");
    navigate("/app/submissions");
  };
  const selectQuestion = (next: number) => setQuestion(Math.max(0, Math.min(questionCount - 1, next)));

  return <><PageHeader title="AI grading review" subtitle="A second set of eyes. The final grade is always your call." action={<div className="review-pagination"><button className="icon-button" aria-label="Previous question" onClick={() => selectQuestion(question - 1)}><ChevronLeft size={15} /></button><span>Question {question + 1} of {questionCount}</span><button className="icon-button" aria-label="Next question" onClick={() => selectQuestion(question + 1)}><ChevronRight size={15} /></button></div>} />
    <div className="review-breadcrumb"><span>{courses.find((item) => item.id === assignment.courseId)?.name}</span><ChevronRight size={12} /><span>{assignment.title}</span><ChevronRight size={12} /><strong>{student.name}</strong>{submission.state === "Late Submission" && <StatusBadge status="Late · decision needed" />}</div>
    <div className="review-workspace"><div className="review-left"><Panel className="review-panel document-panel"><div className="review-panel-head"><span className="submission-person"><Avatar name={student.name} initials={student.initials} /><span><strong>{student.name}</strong><small>{formatDate(submission.submittedAt)} · {submission.state === "Late Submission" ? "Late · decision needed" : "On time"} · {submission.fileName}</small></span></span><Button variant="secondary" size="sm" onClick={() => toast("PDF preview is represented with sample text in this demo.", "info")}><ArrowDownToLine size={13} />Original PDF</Button></div>
      <div className="document-frame"><div className="document-meta"><span>{submission.fileName ?? "submission.pdf"}</span><span>Page 1 of 4</span></div><div className="paper-preview"><div className="paper-university">TRUSTGRADE · STUDENT SUBMISSION</div><h3>{assignment.questions[question]?.prompt}</h3><div className="ocr-caption">EXTRACTED TEXT · <span>{submission.ocr.state}</span></div><p>{question === 0 ? <>{submission.answer.slice(0, 168)} <mark>rotation</mark> {submission.answer.slice(168)}</> : submission.ocr.extractedText}</p><p className="paper-placeholder">[Handwritten diagram detected in original PDF]</p></div></div>
      <div className="document-footer"><div className="page-thumbnails"><button className="page-thumb active">01</button><button className="page-thumb">02</button><button className="page-thumb">03</button><button className="page-thumb">04</button></div><div className="question-tabs">{assignment.questions.map((item, index) => <button key={item.id} className={question === index ? "question-tab active" : "question-tab"} onClick={() => selectQuestion(index)}>Q{index + 1}<small>{item.marks} pts</small></button>)}</div></div>
    </Panel>
    <Panel className="ocr-extract-panel"><div className="review-panel-head"><span><strong>OCR transcription</strong><small>Source text is a reading aid. Check the original when uncertain.</small></span><StatusBadge status={submission.ocr.state} /></div><div className="ocr-text">{submission.ocr.extractedText}</div><div className="ocr-confidence"><span>OCR confidence</span><strong>{Math.round(submission.ocr.confidence * 100)}%</strong><span className="confidence-track"><i style={{ width: `${submission.ocr.confidence * 100}%` }} /></span></div>{submission.ocr.warnings.map((warning) => <div className="ocr-warning" key={warning}><AlertCircle size={14} />{warning}</div>)}</Panel>
    </div>
    <aside className="review-right"><Panel className="ai-analysis-panel"><div className="ai-analysis-head"><span className="feature-symbol"><Sparkles size={15} /></span><div><strong>AI suggested grade</strong><small>Based on selected rubric and available evidence</small></div></div><div className="ai-vs-teacher"><ShieldCheck size={15} /><span>AI suggestion <b>≠</b> final grade</span><span>Teacher decides</span></div><div className="suggested-score"><span>Suggested score</span><strong>7.5 <small>/ 10</small></strong><Badge tone="sage">High confidence · 91%</Badge></div><div className="confidence-track confidence-large"><i style={{ width: "91%" }} /></div>
      <div className="rubric-heading">RUBRIC BREAKDOWN <button className="text-button" onClick={() => toast("Rubric criteria can be edited in assignment settings.", "info")}>Edit rubric</button></div>
      {[["Concept accuracy", "Core concepts are correct.", 4], ["Method", "Method is sound; example lacks detail.", 3], ["Explanation", "Reasoning is clear and supported.", 2], ["Presentation", "Terminology and organization.", 1]].map(([label, detail, max], index) => <div className="rubric-row" key={label.toString()}><span><strong>{label}</strong><small>{detail}</small></span><input aria-label={`${label} score`} type="number" min="0" max={Number(max)} step="0.5" value={scores[index]} onChange={(event) => setScores((current) => current.map((score, item) => item === index ? Number(event.target.value) : score))} /><span className="rubric-max">/ {max}</span></div>)}
      <div className="grade-total"><span>Teacher-edited total</span><strong>{total.toFixed(1)} <small>/ {maximum}</small></strong></div></Panel>
      <Panel className="reasoning-panel"><SectionTitle title="Why this was suggested" subtitle="Reasoning is reviewable—not a final decision." /><p>{submission.grading?.reasoning ?? "Course-grounded grading suggestions are unavailable for this submission. Review the rubric and evidence manually."}</p><div className="evidence-heading">COURSE EVIDENCE</div>{["Lecture 04 — Trees", "Course Notes — Binary Search Trees"].map((reference) => <button className="evidence-link" key={reference} onClick={() => toast("Course evidence preview is sample data.", "info")}><FileText size={13} />{reference}<ChevronRight size={13} /></button>)}<p className="evidence-caveat">Evidence is sample prototype content. If course references are unavailable, verify the answer manually.</p></Panel>
      <Panel className="feedback-panel"><SectionTitle title="Feedback for student" subtitle="Editable before publication." /><textarea className="field-textarea feedback-edit" value={feedback} onChange={(event) => setFeedback(event.target.value)} /><div className="review-actions"><Button variant="secondary" onClick={() => toast("Submission remains in your review queue.", "info")}>Return for review</Button><Button onClick={approve}><Check size={14} />Approve &amp; publish</Button></div><small className="approval-note">Only approved feedback is visible to the student.</small></Panel>
    </aside></div>
  </>;
}

export function OCRReviewPage({ submissions: rows, setSubmissions }: { submissions: Submission[]; setSubmissions: Dispatch<SetStateAction<Submission[]>> }) {
  const { assignments: assignmentList, people } = useAppState();
  const { submissionId } = useParams();
  const toast = useToast();
  const submission = rows.find((item) => item.id === submissionId) ?? rows.find((item) => item.ocr.state === "Needs review" || item.ocr.state === "Low confidence") ?? rows[0];
  const person = submission && people.find((item) => item.id === submission.studentId);
  const assignment = submission && assignmentList.find((item) => item.id === submission.assignmentId);
  const [text, setText] = useState(submission?.ocr.extractedText ?? "");
  if (!submission || !person || !assignment) return <NotFoundPage />;
  const verify = () => {
    setSubmissions((current) => current.map((item) => item.id === submission.id ? { ...item, ocr: { ...item.ocr, state: "Verified", confidence: Math.max(item.ocr.confidence, 0.95), extractedText: text, warnings: [] } } : item));
    toast("OCR text verified by teacher. It has not been graded automatically.");
  };
  return <><PageHeader title="OCR review" subtitle="Verify uncertain text before it reaches the grading workflow." action={<Button variant="secondary" onClick={() => toast("OCR retry is simulated in this demo.", "info")}><Activity size={14} />Retry OCR</Button>} />
    <div className="late-note"><AlertCircle size={15} /><span>OCR is a reading aid, not a source of truth. OCR failure does not equal zero marks. Confirm the original student submission whenever text is uncertain.</span></div>
    <div className="ocr-workspace"><Panel className="review-panel"><div className="submission-person"><Avatar name={person.name} initials={person.initials} /><span><strong>{person.name}</strong><small>{assignment.title} · Submitted {formatDate(submission.submittedAt)}</small></span></div><div className="document-frame ocr-document"><div className="document-meta"><span>{submission.fileName}</span><span>Page 2 of 4</span></div><div className="paper-preview"><div className="paper-university">ORIGINAL DOCUMENT · PAGE IMAGE PLACEHOLDER</div><h3>Question response</h3><p>{submission.answer}</p><div className="math-detected"><span>DETECTED MATHEMATICAL EXPRESSION</span><code>{submission.ocr.expressions.join(" · ") || "No expressions detected"}</code></div></div></div></Panel>
      <Panel className="review-panel"><div className="review-panel-head"><span><strong>Extracted text</strong><small>Correct transcription errors before verification.</small></span><StatusBadge status={submission.ocr.state} /></div><div className="confidence-summary"><span>OCR confidence</span><strong>{Math.round(submission.ocr.confidence * 100)}%</strong><span className="confidence-track"><i style={{ width: `${submission.ocr.confidence * 100}%` }} /></span></div><textarea className="field-textarea ocr-edit" value={text} onChange={(event) => setText(event.target.value)} aria-label="Correct OCR text" />{submission.ocr.warnings.map((warning) => <div className="ocr-warning" key={warning}><AlertCircle size={14} />{warning}</div>)}<div className="ocr-actions"><Button variant="secondary" onClick={() => setText(submission.ocr.extractedText)}>Reset correction</Button><Button onClick={verify}><Check size={14} />Verify transcription</Button></div></Panel></div>
  </>;
}

export function StudentAssignmentsPage({ courses: courseList, joinedCourseIds, setJoinedCourseIds, submissions: studentRows }: {
  courses: Course[];
  joinedCourseIds: string[];
  setJoinedCourseIds: Dispatch<SetStateAction<string[]>>;
  submissions: Submission[];
}) {
  const { user, assignments: assignmentList } = useAppState();
  const navigate = useNavigate();
  const toast = useToast();
  const [dialogOpen, setDialogOpen] = useState(false);
  const joined = courseList.filter((course) => joinedCourseIds.includes(course.id));
  const visibleAssignments = assignmentList.filter((item) => item.state === "Published" && joinedCourseIds.includes(item.courseId));
  const joinCourse = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const code = String(form.get("inviteCode") ?? "").trim().toUpperCase();
    const course = courseList.find((item) => item.code.toUpperCase() === code);
    if (!course) { toast("That course code wasn’t found. Check it with your instructor.", "info"); return; }
    if (joinedCourseIds.includes(course.id)) { toast(`You’re already enrolled in ${course.name}.`, "info"); return; }
    setJoinedCourseIds((current) => [...current, course.id]);
    setDialogOpen(false);
    toast(`You joined ${course.name}.`);
  };
  return <><PageHeader title="My assignments" subtitle="A calm, clear view of what’s due and what you’ve completed." action={<Dialog.Root open={dialogOpen} onOpenChange={setDialogOpen}><Dialog.Trigger asChild><Button variant="secondary"><Plus size={15} />Join a course</Button></Dialog.Trigger><Dialog.Portal><Dialog.Overlay className="modal-backdrop" /><Dialog.Content className="modal" aria-describedby="join-course-description"><div className="modal-head"><Dialog.Title className="modal-title">Join a course</Dialog.Title><Dialog.Close asChild><Button variant="quiet" size="icon" aria-label="Close"><X size={15} /></Button></Dialog.Close></div><Dialog.Description id="join-course-description" className="modal-description">Enter the course code shared by your instructor. This demo accepts the sample course codes shown below.</Dialog.Description><form onSubmit={joinCourse}><div className="field-block"><label htmlFor="course-invite-code">Course code</label><input id="course-invite-code" name="inviteCode" className="field-input" placeholder="e.g. CS 301" required /></div><p className="modal-description">Available demo codes: {courseList.map((course) => course.code).join(", ")}.</p><div className="modal-actions"><Dialog.Close asChild><Button type="button" variant="secondary">Cancel</Button></Dialog.Close><Button type="submit">Join course</Button></div></form></Dialog.Content></Dialog.Portal></Dialog.Root>} />
    {joined.length > 0 && <div className="course-summary-list">{joined.map((course) => <Panel className="course-summary" key={course.id}><span className="course-summary-icon"><BookOpen size={15} /></span><span><strong>{course.name}</strong><small>{course.code}</small></span><ChevronRight size={15} /></Panel>)}</div>}
    <div className="student-assignment-list">{visibleAssignments.map((item) => {
      const submission = studentRows.find((row) => row.studentId === user?.id && row.assignmentId === item.id);
      const status = submission?.state ?? "Not Started";
      const actionLabel = status === "Published" ? "View feedback" : item.submissionType === "MCQ" ? submission ? "View submission" : "Start assessment" : submission ? "View submission" : "Open assignment";
      return <Panel className="student-assignment-row" key={item.id}><span className="student-assignment-icon"><FileText size={17} /></span><span className="assignment-row-copy"><strong>{item.title}</strong><small>{courseList.find((course) => course.id === item.courseId)?.name} · {item.totalMarks} marks</small></span><span className="assignment-row-due"><CalendarDays size={13} />Due {formatDate(item.dueAt)}</span><StatusBadge status={status} /><Button size="sm" variant="secondary" onClick={() => navigate(status === "Published" ? "/app/results" : item.submissionType === "MCQ" ? `/app/student/assessment/${item.id}` : `/app/student/submit/${item.id}`)}>{actionLabel}<ChevronRight size={13} /></Button></Panel>;
    })}{!visibleAssignments.length && <Panel className="empty-state">You haven’t joined a course yet. Use a course code from your instructor to get started.</Panel>}</div>
  </>;
}

export function StudentSubmissionPage({ submissions: studentRows, setSubmissions }: { submissions: Submission[]; setSubmissions: Dispatch<SetStateAction<Submission[]>> }) {
  const { user, courses: courseList, assignments: assignmentList } = useAppState();
  const { assignmentId } = useParams();
  const assignment = assignmentList.find((item) => item.id === assignmentId) ?? assignments[0];
  const course = courseList.find((item) => item.id === assignment.courseId) ?? courses.find((item) => item.id === assignment.courseId)!;
  const existing = studentRows.find((item) => item.studentId === user?.id && item.assignmentId === assignment.id);
  const [file, setFile] = useState<File | null>(null);
  const [drag, setDrag] = useState(false);
  const [progress, setProgress] = useState(0);
  const [receipt, setReceipt] = useState(false);
  const toast = useToast();
  const chooseFile = (candidate?: File) => {
    if (!candidate) return;
    if (candidate.type !== "application/pdf" && !candidate.name.toLowerCase().endsWith(".pdf")) { toast("Please choose a PDF file.", "info"); return; }
    if (candidate.size > 25 * 1024 * 1024) { toast("This file exceeds the 25 MB demo limit.", "info"); return; }
    setFile(candidate);
  };
  const submit = () => {
    if (!file) { toast("Choose a PDF before submitting.", "info"); return; }
    setProgress(12);
    const timer = window.setInterval(() => setProgress((current) => {
      if (current >= 100) {
        window.clearInterval(timer);
        const submittedAt = new Date();
        const deadline = new Date(assignment.dueAt);
        setSubmissions((currentRows) => [...currentRows, {
          id: `sub-${crypto.randomUUID()}`,
          studentId: user?.id ?? "",
          assignmentId: assignment.id,
          submittedAt: submittedAt.toISOString(),
          deadline: assignment.dueAt,
          state: submittedAt > deadline ? "Late Submission" : "Submitted",
          ocr: { confidence: 0, state: "Needs review", extractedText: "OCR processing is not connected in this demo.", warnings: ["Verify the original PDF before grading."], expressions: [] },
          answer: "PDF submission received. OCR processing is not connected in this demo.",
          fileName: file.name,
        }]);
        setReceipt(true);
        return 100;
      }
      return Math.min(current + 22, 100);
    }), 160);
  };
  return <><PageHeader title="Submit assignment" subtitle={`${assignment.title} · ${course.code}`} action={<Link className="back-link" to="/app/student/assignments"><ArrowLeft size={14} />All assignments</Link>} />
    <div className="student-submit-layout"><div><Panel className="instruction-panel"><div className="assignment-state-line"><StatusBadge status={existing?.state ?? "Not Started"} /><span><CalendarDays size={13} />Due {formatDate(assignment.dueAt)} at 11:59 PM</span></div><h2>Before you submit</h2><p>{assignment.description}</p><ul><li>Submit one PDF containing your complete written responses.</li><li>Include your name and course code on the first page.</li><li>Late work is still received for teacher review; no automatic zero is applied.</li></ul><div className="assignment-instruction-footer"><span><BookOpen size={14} />Course materials may be used for reference.</span><span>{assignment.totalMarks} marks total</span></div></Panel>
      <SectionTitle title="Your submission" subtitle="Accepted format: PDF · Up to 25 MB" />
      <GlassPanel className={`student-dropzone ${drag ? "drag-active" : ""} ${file ? "file-selected" : ""}`} onDragOver={(event: DragEvent<HTMLElement>) => { event.preventDefault(); setDrag(true); }} onDragLeave={() => setDrag(false)} onDrop={(event: DragEvent<HTMLElement>) => { event.preventDefault(); setDrag(false); chooseFile(event.dataTransfer.files[0]); }}>
        <input type="file" accept=".pdf,application/pdf" id="student-pdf" className="visually-hidden" onChange={(event) => chooseFile(event.target.files?.[0])} />
        {file ? <><span className="file-icon-large"><FileCheck2 size={21} /></span><strong>{file.name}</strong><p>{(file.size / 1024 / 1024).toFixed(2)} MB · Ready to submit</p><button className="text-button" onClick={() => setFile(null)}>Choose another file</button></> : <><span className="upload-icon"><CloudUpload size={21} /></span><strong>Drop your PDF here</strong><p>or browse from your device. Your file stays in this demo session.</p><Button variant="secondary" size="sm" onClick={() => document.getElementById("student-pdf")?.click()}>Choose PDF</Button></>}
      </GlassPanel>
      {progress > 0 && <div className="upload-progress"><div><span>{receipt ? "Submitted" : "Uploading your work"}</span><strong>{progress}%</strong></div><div className="progress-track"><span style={{ width: `${progress}%` }} /></div></div>}
      <div className="submit-actions"><span><ShieldCheck size={14} />You’ll receive a submission receipt.</span><ConfirmDialog trigger={<Button disabled={!file || receipt || Boolean(existing)}><Upload size={14} />{existing ? "Already submitted" : "Submit PDF"}</Button>} title="Submit your assignment?" description={`This will submit ${file?.name ?? "your PDF"} for ${assignment.title}. You’ll receive a receipt and can track grading status.`} confirmLabel="Confirm submission" onConfirm={submit} /></div>
    </div><aside className="submission-side"><Panel className="side-detail-card"><SectionTitle title="Assignment details" /><dl><div><dt>Course</dt><dd>{course.name}</dd></div><div><dt>Deadline</dt><dd>{formatDate(assignment.dueAt)} · 11:59 PM</dd></div><div><dt>Maximum marks</dt><dd>{assignment.totalMarks}</dd></div><div><dt>Submission type</dt><dd>PDF document</dd></div><div><dt>Grading status</dt><dd><StatusBadge status={receipt ? "Submitted" : existing?.state ?? "Not Started"} /></dd></div></dl></Panel><Panel className="privacy-note"><ShieldCheck size={17} /><strong>Your work is in good hands.</strong><p>Your teacher reviews all grading suggestions before marks or feedback are published.</p></Panel></aside></div>
    {receipt && <div className="modal-backdrop"><div className="receipt-modal"><span className="receipt-check"><Check size={22} /></span><span className="eyebrow">SUBMISSION RECEIPT</span><h2>All handed in.</h2><p>Your work has been added to the grading queue. We’ll let you know when feedback is ready.</p><div className="receipt-line"><span>Assignment</span><strong>{assignment.title}</strong></div><div className="receipt-line"><span>Submitted</span><strong>Just now · demo receipt</strong></div><div className="receipt-line"><span>File</span><strong>{file?.name}</strong></div><Button className="full-button" onClick={() => { setReceipt(false); setProgress(0); setFile(null); }}>Done</Button></div></div>}
  </>;
}

export function AssessmentPage({ submissions: studentRows, setSubmissions }: { submissions: Submission[]; setSubmissions: Dispatch<SetStateAction<Submission[]>> }) {
  const { user, assignments: assignmentList } = useAppState();
  const navigate = useNavigate();
  const { assignmentId } = useParams();
  const assignment = assignmentList.find((item) => item.id === assignmentId) ?? assignments[0];
  const existing = studentRows.find((item) => item.studentId === user?.id && item.assignmentId === assignment.id);
  const [index, setIndex] = useState(0);
  const [answers, setAnswers] = useState<Record<string, number>>({});
  const [submitted, setSubmitted] = useState(false);
  const current = assignment.questions[index];
  const answered = Object.keys(answers).length;
  const alreadySubmitted = Boolean(existing && !submitted);
  const submitAssessment = () => {
    if (existing || !user) return;
    const score = assignment.questions.reduce((total, question) => total + (answers[question.id] === question.correctOption ? question.marks : 0), 0);
    setSubmissions((currentRows) => [...currentRows, {
      id: `sub-${crypto.randomUUID()}`,
      studentId: user.id,
      assignmentId: assignment.id,
      submittedAt: new Date().toISOString(),
      deadline: assignment.dueAt,
      state: new Date() > new Date(assignment.dueAt) ? "Late Submission" : "Under Review",
      ocr: { confidence: 1, state: "Verified", extractedText: "MCQ response; OCR is not needed.", warnings: [], expressions: [] },
      grading: {
        suggestedScore: score,
        confidence: 1,
        reasoning: "MCQ responses were compared with the teacher-authored answer key. This score is a suggestion and requires teacher approval.",
        rubric: [],
        feedback: { id: `feedback-${crypto.randomUUID()}`, comment: "Your answers are recorded and awaiting teacher review.", deductions: [], courseReferences: [] },
        teacherApproved: false,
      },
      answer: assignment.questions.map((question) => `${question.prompt}: ${question.options?.[answers[question.id] ?? -1] ?? "Unanswered"}`).join("\n"),
    }]);
  };
  return <><PageHeader eyebrow={`${courses.find((item) => item.id === assignment.courseId)?.code} · DISTRACTION-FREE ASSESSMENT`} title={assignment.title} subtitle="Take your time. Your answers are saved in this session." action={<Badge tone="gold"><Clock3 size={12} />Time remaining · 24:58</Badge>} />
    <div className="assessment-layout"><Panel className="assessment-card"><div className="assessment-progress"><span>Question {index + 1} <small>of {assignment.questions.length}</small></span><span>{answered} answered</span><div className="progress-track"><span style={{ width: `${(answered / assignment.questions.length) * 100}%` }} /></div></div>
      <div className="assessment-question"><span className="eyebrow">QUESTION {String(index + 1).padStart(2, "0")} · {current.type.toUpperCase()}</span><h2>{current.prompt}</h2><span className="question-points">{current.marks} marks</span>
        {(current.options ?? []).map((option, optionIndex) => <button key={option} className={`assessment-option ${answers[current.id] === optionIndex ? "selected" : ""}`} onClick={() => setAnswers((prev) => ({ ...prev, [current.id]: optionIndex }))}><span className="option-letter">{String.fromCharCode(65 + optionIndex)}</span><span>{option}</span>{answers[current.id] === optionIndex && <Check size={15} />}</button>)}
      </div>
      <div className="assessment-bottom"><Button variant="secondary" disabled={!index} onClick={() => setIndex((value) => value - 1)}><ChevronLeft size={14} />Previous</Button><div className="assessment-dots">{assignment.questions.map((question, itemIndex) => <button key={question.id} aria-label={`Question ${itemIndex + 1}`} className={`${index === itemIndex ? "active" : ""} ${answers[question.id] !== undefined ? "answered" : ""}`} onClick={() => setIndex(itemIndex)} />)}</div>{index < assignment.questions.length - 1 ? <Button onClick={() => setIndex((value) => value + 1)}>Next question<ChevronRight size={14} /></Button> : <ConfirmDialog trigger={<Button disabled={Boolean(existing)}>{existing ? "Already submitted" : <>Review &amp; submit<Check size={14} /></>}</Button>} title="Submit your answers?" description={`${answered} of ${assignment.questions.length} questions answered. Your responses will be submitted for teacher review.`} confirmLabel="Submit assessment" onConfirm={() => { submitAssessment(); setSubmitted(true); }} />}</div>
    </Panel><Panel className="assessment-aside"><SectionTitle title="Question navigator" subtitle="Select a question to jump to it." />{assignment.questions.map((question, itemIndex) => <button key={question.id} className={`question-nav-item ${index === itemIndex ? "active" : ""}`} onClick={() => setIndex(itemIndex)}><span>{String(itemIndex + 1).padStart(2, "0")}</span><span>Question {itemIndex + 1}<small>{question.marks} marks</small></span>{answers[question.id] !== undefined && <CheckCircle2 size={14} />}</button>)}<div className="assessment-help"><ShieldCheck size={15} /><span>Your teacher reviews submitted work before sharing a grade.</span></div></Panel></div>
    {(submitted || existing) && <div className="modal-backdrop"><div className="receipt-modal"><span className="receipt-check"><Check size={22} /></span><span className="eyebrow">ASSESSMENT {alreadySubmitted ? "ALREADY SUBMITTED" : "SUBMITTED"}</span><h2>{alreadySubmitted ? "Your work is in review." : "Nice work."}</h2><p>{alreadySubmitted ? "You’ve already submitted this assessment. Your teacher reviews the suggested score before publishing feedback." : "Your answers are with your teacher for review. We’ll let you know when feedback is published."}</p><Button className="full-button" onClick={() => navigate("/app/student/assignments")}>Back to coursework</Button></div></div>}
  </>;
}

export function ResultsPage({ submissions: rows }: { submissions: Submission[] }) {
  const { user, assignments: assignmentList } = useAppState();
  const student = user?.role === "student";
  const approved = rows
    .filter((item) => item.studentId === user?.id && item.state === "Published" && item.grading?.teacherApproved)
    .map((item) => ({
      item,
      assignment: assignmentList.find((assignment) => assignment.id === item.assignmentId),
      result: publishedResults.find((result) => result.submissionId === item.id),
    }));
  return <><PageHeader title={student ? "My results" : "Results & performance"} subtitle={student ? "Clear feedback from your teacher, with the reasoning behind every mark." : "A thoughtful picture of learning across your courses."} action={!student && <Button variant="secondary"><ArrowDownToLine size={14} />Export results</Button>} />
    {student ? <div className="published-results">{approved.map(({ item, assignment, result }) => {
      if (!assignment || !item.grading) return null;
      const feedback = result?.feedback ?? item.grading.feedback;
      const course = courses.find((entry) => entry.id === assignment.courseId);
      return <Panel className="published-result-detail" key={item.id}>
        <div className="published-result-head"><span><span className="eyebrow">TEACHER APPROVED</span><h2>{assignment.title}</h2><p>{course?.name ?? "Course"} · Published {formatDate(result?.publishedAt ?? item.submittedAt)}</p></span><div className="published-score">{result?.score ?? item.grading.suggestedScore}<small> / {result?.maximum ?? assignment.totalMarks}</small></div></div>
        <div className="result-trust-label"><ShieldCheck size={14} />Teacher Approved<span>Published grades only · No AI-only suggestions</span></div>
        {result && <><SectionTitle title="Question breakdown" />{result.questionBreakdown.map((line) => <div className="breakdown-row" key={line.question}><span><strong>{line.question}</strong><small>{line.reason}</small></span><b>{line.earned} / {line.maximum}</b></div>)}</>}
        <SectionTitle title="Teacher feedback" /><p className="teacher-feedback">{feedback.comment}</p>{feedback.deductions.map((deduction) => <div className="deduction-note" key={deduction.criterion}><strong>{deduction.criterion} · −{deduction.marks}</strong><span>{deduction.reason}</span></div>)}
        {feedback.courseReferences.length > 0 && <><SectionTitle title="Course references" />{feedback.courseReferences.map((reference) => <span className="evidence-chip" key={reference}><BookOpen size={13} />{reference}</span>)}</>}
      </Panel>;
    })}{!approved.length && <Panel className="empty-state">No teacher-approved results have been published for your account yet. Grades and AI suggestions remain private until your teacher approves them.</Panel>}</div>
      : <><div className="metric-strip">{[["Class average","84.6","↑ 3.2% this term"],["Submissions graded","86%","207 of 240 submitted"],["Feedback published","164","↑ 18 this week"],["At-risk students","6","Across 3 courses"]].map(([label,value,note]) => <Panel className="metric-card" key={label}><span>{label}</span><strong>{value}</strong><small>{note}</small></Panel>)}</div><div className="analytics-grid"><Panel className="chart-card"><SectionTitle title="Performance trend" subtitle="Average marks across all courses" /><div className="chart-total">84.6 <span>↑ 3.2% this term</span></div><TrendChart height={240} /></Panel><Panel className="chart-card"><SectionTitle title="Grade distribution" subtitle="248 students · all active courses" /><DistributionChart /></Panel></div><Panel className="recent-card"><SectionTitle title="Recent published results" subtitle="Only teacher-approved marks are included." /><RecentSubmissions rows={rows.filter((item) => item.state === "Published")} /></Panel></>}
  </>;
}

export function LeaderboardPage() {
  const { user } = useAppState();
  return <><PageHeader title="Leaderboard" subtitle="Celebrate steady effort and progress across the class." action={<select className="filter-select"><option>Data Structures · CS 204</option><option>All courses</option></select>} /><div className="late-note"><Award size={15} /><span>Only published, teacher-approved grades affect this leaderboard. It celebrates progress—not perfection.</span></div><Panel className="table-card"><div className="table-scroll"><table className="data-table leaderboard-table"><thead><tr><th>Rank</th><th>Student</th><th>Course</th><th>Score</th><th>Assignments completed</th><th>Trend</th></tr></thead><tbody>{leaderboard.map((entry) => { const person = users.find((item) => item.id === entry.studentId)!; return <tr key={entry.studentId}><td><span className={`leader-rank rank-${entry.rank}`}>{entry.rank}</span></td><td><span className="student-name"><Avatar name={person.name} initials={person.initials} />{person.name}{person.id === user?.id && <Badge tone="sage">You</Badge>}</span></td><td>Data Structures</td><td className="score-cell">{entry.score}%</td><td>{entry.assignmentsCompleted} / 15</td><td className={entry.trend === "Needs support" ? "trend-support" : "trend-up"}>{entry.trend === "Improving" ? "↗ " : ""}{entry.trend}</td></tr>; })}</tbody></table></div></Panel></>;
}

export function SettingsPage() {
  const [enabled, setEnabled] = useState(true);
  const toast = useToast();
  return <><PageHeader title="Settings" subtitle="Make TrustGrade work the way your classroom works." /><div className="settings-layout"><Panel className="settings-nav">{["Profile","Notifications","Grading preferences","Accessibility","Security"].map((item,index) => <button key={item} className={index === 0 ? "active" : ""}>{item}</button>)}</Panel><Panel className="settings-content"><SectionTitle title="Profile & workspace" subtitle="Manage your personal information and workspace defaults." /><div className="settings-row"><span><strong>Display name</strong><small>Shown to students and collaborators</small></span><input className="field-input" defaultValue="Alex Morgan" /></div><div className="settings-row"><span><strong>Email address</strong><small>Used for account notifications</small></span><input className="field-input" defaultValue="alex.morgan@university.edu" /></div><div className="settings-row"><span><strong>Default workspace</strong><small>Choose the first screen you see</small></span><select className="field-select"><option>Faculty workspace</option><option>Student workspace</option></select></div><div className="settings-row"><span><strong>Review notifications</strong><small>Get a note when submissions need attention</small></span><button role="switch" aria-checked={enabled} className={`switch ${enabled ? "on" : ""}`} onClick={() => setEnabled((value) => !value)} /></div><div className="settings-save"><Button onClick={() => toast("Your preferences were saved in this demo.", "info")}>Save changes</Button></div></Panel></div></>;
}

export function LandingPage() {
  const navigate = useNavigate();
  const steps = [
    ["01", "Bring your course context", "Syllabi, rubrics, and teaching materials inform review."],
    ["02", "Review with useful assistance", "OCR and rubric-grounded suggestions surface evidence—not verdicts."],
    ["03", "Publish with confidence", "Teachers approve marks and feedback before students can see them."],
  ];
  return <div className="landing-page">
    <header className="landing-nav">
      <Link to="/" className="brand"><span className="brand-mark"><Check size={19} /></span><span className="brand-word">Trust<span>Grade</span></span></Link>
      <nav><a href="#how-it-works">How it works</a><a href="#trust">Our approach</a></nav>
      <div><Button variant="quiet" onClick={() => navigate("/login")}>Sign in</Button><Button onClick={() => navigate("/register")}>Create account<ArrowRight size={14} /></Button></div>
    </header>
    <main className="landing-hero">
      <div className="landing-copy">
        <span className="landing-kicker"><span className="kicker-line" />A more thoughtful way to grade</span>
        <h1>Grading, with<br /><em>intelligence.</em></h1>
        <p>TrustGrade combines course-grounded AI evaluation with human review to make academic grading faster, clearer, and more trustworthy.</p>
        <div className="landing-actions"><Button onClick={() => navigate("/login")}>Explore TrustGrade<ArrowRight size={15} /></Button><a href="#how-it-works">See how it works<ChevronRight size={14} /></a></div>
        <div className="landing-trust"><span><ShieldCheck size={15} />Human-approved, always</span><span><BookOpen size={15} />Grounded in your course</span></div>
      </div>
      <div className="product-stage">
        <div className="product-window">
          <div className="product-window-top"><span className="brand-mark mini-brand"><Check size={12} /></span><strong>TrustGrade</strong><span className="window-caption">FACULTY WORKSPACE</span><span className="window-avatar">AM</span></div>
          <div className="product-window-body">
            <div className="product-sidebar"><span className="sidebar-mark active"><LayoutDashboard size={14} /></span><span className="sidebar-mark"><BookOpen size={14} /></span><span className="sidebar-mark"><FileText size={14} /></span><span className="sidebar-mark"><Sparkles size={14} /></span></div>
            <div className="product-dashboard">
              <span className="eyebrow">SATURDAY, OCTOBER 31, 2026</span><strong className="product-greeting">Good morning, Alex.</strong>
              <div className="product-stat-row"><span><small>ACTIVE COURSES</small><b>8</b></span><span><small>STUDENTS</small><b>248</b></span><span><small>TO REVIEW</small><b>18</b></span></div>
              <div className="product-grade-card"><span className="feature-symbol"><Sparkles size={12} /></span><span><small>AI GRADING ACTIVITY</small><b>Data Structures — Assignment 03</b><span className="product-progress"><i /></span><small>72 / 96 submissions reviewed</small></span><Badge tone="sage">In progress</Badge></div>
              <div className="product-chart-row"><span className="product-chart"><small>PERFORMANCE TREND</small><svg viewBox="0 0 180 48"><path d="M2 39 C24 34 31 35 48 30S70 35 88 23 119 27 134 16 160 19 178 6" fill="none" stroke="#34483b" strokeWidth="2" /><path d="M2 39 C24 34 31 35 48 30S70 35 88 23 119 27 134 16 160 19 178 6L178 48H2Z" fill="#81927f" fillOpacity=".08" /></svg></span><span className="product-confidence"><CheckCircle2 size={15} /><span><small>TEACHER IN CONTROL</small><b>Every grade reviewed</b></span></span></div>
            </div>
          </div>
        </div>
        <div className="product-float"><span className="float-check"><Check size={14} /></span><span><b>Clear, evidence-based feedback</b><small>Teacher-approved before it’s shared.</small></span></div>
      </div>
    </main>
    <section className="landing-proof" id="trust"><span>BUILT AROUND A SIMPLE PROMISE</span><strong>AI assists. Teachers decide. Students understand.</strong><p>Transparent evidence. Human judgment. Feedback that helps students move forward.</p></section>
    <section className="landing-how" id="how-it-works"><SectionTitle title="Thoughtful by design." subtitle="The right support at every step of the grading journey." />{steps.map(([number, title, copy]) => <article key={number}><span>{number}</span><strong>{title}</strong><p>{copy}</p></article>)}</section>
    <footer className="landing-footer"><Link to="/" className="brand"><span className="brand-mark"><Check size={17} /></span><span className="brand-word">Trust<span>Grade</span></span></Link><span>Thoughtful grading. Clearer learning.</span><Button variant="secondary" size="sm" onClick={() => navigate("/register")}>Get started<ArrowRight size={13} /></Button></footer>
  </div>;
}

export function AuthPage({ mode, onAuthenticated }: { mode: "login" | "register"; onAuthenticated: (user: User) => void }) {
  const navigate = useNavigate();
  const toast = useToast();
  const [role, setRole] = useState<"teacher" | "student">("teacher");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const register = mode === "register";
  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setError("");
    const form = new FormData(event.currentTarget);
    const email = String(form.get("email") ?? "");
    const password = String(form.get("password") ?? "");
    const name = String(form.get("name") ?? "").trim();
    if (register && !name) { setError("Enter your name to create an account."); return; }
    if (!email.includes("@") || password.length < 6) { setError("Use a valid email and a password of at least 6 characters."); return; }
    setLoading(true);
    try {
      if (import.meta.env.VITE_USE_API_AUTH === "true") {
        const profile = register ? await authService.register(name, email, password, role) : await authService.login(email, password);
        onAuthenticated({
          id: profile.id,
          name: profile.name,
          email: profile.email,
          role: profile.role,
          initials: profile.name.split(/\s+/).map((part) => part[0]).slice(0, 2).join("").toUpperCase(),
        });
      } else {
        const existing = users.find((item) => item.role === role) ?? users[0];
        onAuthenticated(register ? { id: `demo-${crypto.randomUUID()}`, name, email, role, initials: name.split(/\s+/).map((part) => part[0]).slice(0, 2).join("").toUpperCase() } : existing);
        toast(register ? "Demo account created for this session." : "Welcome to the TrustGrade demo workspace.", "info");
      }
      navigate("/app");
    } catch (reason) {
      const message = reason instanceof Error ? reason.message : "Sign-in failed. Check your connection and try again.";
      setError(message);
    } finally { setLoading(false); }
  };
  return <div className="auth-page"><div className="auth-backdrop" /><Link to="/" className="brand auth-brand"><span className="brand-mark"><Check size={19} /></span><span className="brand-word">Trust<span>Grade</span></span></Link><div className="auth-layout"><section className="auth-story"><span className="eyebrow">A MORE THOUGHTFUL CLASSROOM</span><h1>Clarity for your work.<br /><em>Confidence in every grade.</em></h1><p>Course-grounded assistance that respects the people at the heart of learning.</p><div className="auth-promise"><ShieldCheck size={18} /><span><strong>AI assists. Teachers decide.</strong><small>Human judgment is always the last word.</small></span></div></section><Panel className="auth-card"><span className="eyebrow">{register ? "YOUR CLASSROOM, IN GOOD HANDS" : "WELCOME BACK"}</span><h2>{register ? "Create your account" : "Welcome back"}</h2><p>{register ? "Join a calmer, clearer way to teach and learn." : "Sign in to your TrustGrade workspace."}</p><form onSubmit={submit}>
      {register && <div className="field-block"><label htmlFor="name">Your name</label><input className="field-input" id="name" name="name" autoComplete="name" placeholder="Alex Morgan" required /></div>}
      <div className="field-block"><label htmlFor="email">Email address</label><input className="field-input" id="email" name="email" type="email" autoComplete="email" placeholder="you@university.edu" required /></div>
      <div className="field-block"><div className="field-label-row"><label htmlFor="password">Password</label>{!register && <button type="button" className="text-button" onClick={() => toast("Password recovery requires the configured Supabase Auth service.", "info")}>Forgot password?</button>}</div><input className="field-input" id="password" name="password" type="password" autoComplete={register ? "new-password" : "current-password"} minLength={6} placeholder="At least 6 characters" required /></div>
      {(register || import.meta.env.VITE_USE_API_AUTH !== "true") && <div className="field-block"><label>{register ? "Choose your workspace" : "Preview workspace"}</label><div className="role-picker">{(["teacher", "student"] as const).map((value) => <button type="button" key={value} className={role === value ? "active" : ""} onClick={() => setRole(value)}><span>{value === "teacher" ? <GraduationCap size={16} /> : <BookOpen size={16} />}</span>{value === "teacher" ? "Teacher" : "Student"}{role === value && <Check size={13} />}</button>)}</div></div>}
      {!register && <label className="remember-check"><input type="checkbox" defaultChecked />Keep me signed in</label>}
      {error && <div role="alert" className="form-error"><AlertCircle size={14} />{error}</div>}
      <Button className="full-button" disabled={loading}>{loading ? <><span className="button-spinner" />Signing in…</> : <>{register ? "Create account" : "Sign in"}<ArrowRight size={14} /></>}</Button>
    </form><div className="auth-switch">{register ? "Already have an account?" : "New to TrustGrade?"} <Link to={register ? "/login" : "/register"}>{register ? "Sign in" : "Create account"}</Link></div><div className="auth-demo-note"><Info size={13} />Prototype sign-in uses a local demo workspace. Configure Supabase Auth before handling real credentials.</div></Panel></div><footer className="auth-footer"><span>© 2026 TrustGrade</span><span>AI assists. Teachers decide. Students understand.</span></footer></div>;
}

export function NotFoundPage() {
  return <div className="not-found"><span className="eyebrow">404 · THIS PAGE ISN’T HERE</span><h1>A small detour.</h1><p>That page may have moved. Your work is still right where you left it.</p><Link className="button button-primary" to="/app"><ArrowLeft size={14} />Back to TrustGrade</Link></div>;
}
