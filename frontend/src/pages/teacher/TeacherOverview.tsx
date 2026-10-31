import { useNavigate } from "react-router-dom";
import {
  Activity, ArrowRight, BookOpen, CheckCircle2, ChevronRight, FileText,
  Plus, ShieldCheck, Sparkles, Users,
} from "lucide-react";
import {
  Area, AreaChart, Bar, BarChart, CartesianGrid, Cell, ResponsiveContainer,
  Tooltip, XAxis, YAxis,
} from "recharts";
import { useAppState } from "../../App";
import { Avatar, Badge, Button, Panel, StatusBadge } from "../../components/ui";
import { IntegrationNotice } from "../../components/common/IntegrationNotice";
import { formatDate } from "../../lib/utils";
import { isDemoSession } from "../../services/demo-session";
import type { Submission } from "../../types/models";

function TrendChart({ height = 190 }: { height?: number }) {
  const data = [
    { week: "W1", average: 76 },
    { week: "W2", average: 78 },
    { week: "W3", average: 77 },
    { week: "W4", average: 81 },
    { week: "W5", average: 84 },
    { week: "W6", average: 83 },
    { week: "W7", average: 86 },
    { week: "W8", average: 88 },
  ];

  return (
    <div className="chart-area" style={{ height }}>
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={data} margin={{ top: 16, right: 12, bottom: 0, left: -20 }}>
          <defs>
            <linearGradient id="forestWash" x1="0" x2="0" y1="0" y2="1">
              <stop offset="0%" stopColor="#173D2B" stopOpacity={0.25} />
              <stop offset="95%" stopColor="#A8C98A" stopOpacity={0} />
            </linearGradient>
          </defs>
          <CartesianGrid vertical={false} stroke="#E7EBE3" strokeDasharray="3 5" />
          <XAxis dataKey="week" axisLine={false} tickLine={false} tick={{ fill: "#7A8C7F", fontSize: 10 }} dy={10} />
          <YAxis domain={[60, 100]} ticks={[60, 70, 80, 90, 100]} axisLine={false} tickLine={false} tick={{ fill: "#7A8C7F", fontSize: 9 }} />
          <Tooltip
            cursor={{ stroke: "#A8C98A", strokeDasharray: "3 4" }}
            contentStyle={{ borderRadius: 10, border: "1px solid #E7EBE3", boxShadow: "0 6px 20px rgba(16, 42, 32, 0.08)", fontSize: 11 }}
            formatter={(value) => [`${value} / 100`, "Class Average"]}
          />
          <Area
            type="monotone"
            dataKey="average"
            stroke="#173D2B"
            strokeWidth={2.4}
            fill="url(#forestWash)"
            activeDot={{ r: 5, fill: "#C8F169", stroke: "#173D2B", strokeWidth: 2 }}
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}

const distribution = [
  { name: "A", value: 38, fill: "#173D2B" },
  { name: "B", value: 61, fill: "#2D6346" },
  { name: "C", value: 74, fill: "#528F6C" },
  { name: "D", value: 51, fill: "#A8C98A" },
  { name: "F", value: 24, fill: "#D5DDD0" },
];

function DistributionChart() {
  return (
    <div className="distribution-bars">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={distribution} margin={{ top: 10, right: 4, bottom: 0, left: -20 }} barCategoryGap="28%">
          <CartesianGrid vertical={false} stroke="#E7EBE3" strokeDasharray="3 5" />
          <XAxis dataKey="name" axisLine={false} tickLine={false} tick={{ fill: "#7A8C7F", fontSize: 10 }} dy={8} />
          <YAxis axisLine={false} tickLine={false} tick={{ fill: "#7A8C7F", fontSize: 9 }} />
          <Tooltip
            cursor={{ fill: "rgba(200, 241, 105, 0.15)" }}
            contentStyle={{ borderRadius: 10, border: "1px solid #E7EBE3", boxShadow: "0 6px 20px rgba(16, 42, 32, 0.08)", fontSize: 11 }}
            formatter={(value) => [`${value} students`, "Grade"]}
          />
          <Bar dataKey="value" radius={[5, 5, 0, 0]}>
            {distribution.map((item) => (
              <Cell key={item.name} fill={item.fill} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

function StatCard({
  title,
  value,
  note,
  change,
  icon: Icon,
  featured = false,
  alert = false,
}: {
  title: string;
  value: string;
  note: string;
  change: string;
  icon: typeof Users;
  featured?: boolean;
  alert?: boolean;
}) {
  return (
    <Panel className={`stat-card ${featured ? "stat-feature" : ""} ${alert ? "stat-alert" : ""}`}>
      <div className="stat-top">
        <span>{title}</span>
        <span className="stat-icon">
          <Icon size={16} />
        </span>
      </div>
      <div className="stat-value-row">
        <strong>{value}</strong>
        <span className="stat-change">{change}</span>
      </div>
      <div className="stat-foot">{note}</div>
      <svg className="stat-spark" viewBox="0 0 84 30" aria-hidden="true">
        <polyline
          points="0,23 12,19 24,20 36,12 48,15 60,7 72,10 84,3"
          fill="none"
          stroke="#173D2B"
          strokeWidth="1.8"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </svg>
    </Panel>
  );
}

function RecentSubmissions({ rows }: { rows: Submission[] }) {
  const { user, assignments: assignmentList, people } = useAppState();
  const navigate = useNavigate();

  if (!rows.length) {
    return (
      <div className="table-empty" style={{ padding: "1.75rem", textAlign: "center", color: "#5C6E61" }}>
        No student submissions received in this queue yet. Submissions uploaded by students will appear here.
      </div>
    );
  }

  const submissionDetails = rows.map((submission) => ({
    submission,
    student: people.find((person) => person.id === submission.studentId),
    assignment: assignmentList.find((item) => item.id === submission.assignmentId),
  }));

  return (
    <div className="table-scroll">
      <table className="data-table">
        <thead>
          <tr>
            <th>Student</th>
            <th>Assignment</th>
            <th>Submitted</th>
            <th>OCR Status</th>
            <th>Score</th>
            <th>Status</th>
            <th>Action</th>
          </tr>
        </thead>
        <tbody>
          {submissionDetails.map(({ submission, student, assignment }) => (
            <tr key={submission.id}>
              <td>
                <span className="student-name">
                  {student && <Avatar name={student.name} initials={student.initials} />}
                  {student?.name ?? "Student"}
                </span>
              </td>
              <td>{assignment?.title ?? "Assignment"}</td>
              <td>{formatDate(submission.submittedAt)}</td>
              <td>
                <StatusBadge status={submission.ocr.state} />
              </td>
              <td className="score-cell">
                {submission.grading
                  ? `${submission.grading.suggestedScore} / ${assignment?.totalMarks ?? "—"}`
                  : "—"}
              </td>
              <td>
                <StatusBadge status={submission.state} />
              </td>
              <td>
                <button
                  className="text-button"
                  onClick={() =>
                    navigate(
                      user?.role === "teacher"
                        ? `/app/grading/${submission.id}`
                        : `/app/student/submit/${submission.assignmentId}`
                    )
                  }
                >
                  {user?.role === "teacher" ? "Review" : "Open"}
                  <ChevronRight size={13} />
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function TeacherOverview() {
  const navigate = useNavigate();
  const { user, courses: courseList, assignments: assignmentList, submissions } = useAppState();
  const demoSession = isDemoSession();
  const recentSubmissions = [...submissions]
    .sort((a, b) => Date.parse(b.submittedAt) - Date.parse(a.submittedAt))
    .slice(0, 5);
  const activeAssignment = assignmentList.find((item) => item.state === "Published") ?? assignmentList[0];
  const upcomingDeadlines = assignmentList
    .filter((item) => Date.parse(item.dueAt) >= Date.now())
    .sort((a, b) => Date.parse(a.dueAt) - Date.parse(b.dueAt))
    .slice(0, 3);
  const totalStudents = courseList.reduce((acc, c) => acc + (c.students || 0), 0);
  const activeAssignmentSubmissions = activeAssignment
    ? submissions.filter((submission) => submission.assignmentId === activeAssignment.id).length
    : 0;
  const activeCourseStudentCount = courseList.find((course) => course.id === activeAssignment?.courseId)?.students ?? 0;
  const turnoutPercent = activeCourseStudentCount > 0
    ? Math.min(100, (activeAssignmentSubmissions / activeCourseStudentCount) * 100)
    : null;

  return (
    <>
      <div className="welcome-row">
        <div>
          <div className="eyebrow">FACULTY WORKSPACE</div>
          <h1>Good morning, {user?.name.split(" ")[0] ?? "Professor"}.</h1>
          <p className="page-subtitle">Your classroom, intelligently organized and grounded in academic authority.</p>
          <div className="welcome-context">
            <span>{courseList.length} course{courseList.length === 1 ? "" : "s"}</span>
            <i />
            <span>{assignmentList.length} assignment{assignmentList.length === 1 ? "" : "s"}</span>
            <i />
            <span>{submissions.length} submission{submissions.length === 1 ? "" : "s"}</span>
          </div>
        </div>
        <Button onClick={() => navigate("/app/assignment/new")}>
          <Plus size={16} />
          Create assignment
        </Button>
      </div>

      <div className="stat-grid dashboard-stats">
        {[
          {
            title: "Active courses",
            value: String(courseList.length),
            note: demoSession ? "Demo workspace" : "Loaded from backend",
            change: `${courseList.length} registered`,
            icon: BookOpen,
            featured: true,
          },
          {
            title: "Assignments",
            value: String(assignmentList.length),
            note: "Created across courses",
            change: `${assignmentList.filter((a) => a.state === "Published").length} published`,
            icon: FileText,
            alert: assignmentList.length === 0,
          },
          {
            title: "Course enrollments",
            value: String(totalStudents),
            note: "Across course rosters",
            change: "Live roster",
            icon: Users,
          },
          {
            title: "Submissions",
            value: String(submissions.length),
            note: "In submission queue",
            change: "Loaded submission count",
            icon: Activity,
          },
        ].map((item) => (
          <StatCard key={item.title} {...item} />
        ))}
      </div>

      <div className="dashboard-grid">
        <Panel className="grading-feature">
          <div className="feature-top">
            <div className="feature-title">
              <span className="feature-symbol">
                <Sparkles size={16} />
              </span>
              <span>
                <strong>Assignment Velocity</strong>
                <small>Review progress and submission turnout.</small>
              </span>
            </div>
            {activeAssignment && (
              <Badge tone="sage">
                <i className="live-dot" />
                {activeAssignment.state}
              </Badge>
            )}
          </div>
          {activeAssignment ? (
            <>
              <h2 className="feature-assignment">{activeAssignment.title}</h2>
              <p className="feature-course">Due {formatDate(activeAssignment.dueAt)}</p>
              <div className="progress-row">
                <span>
                  <strong>{activeAssignmentSubmissions}</strong> submissions received
                </span>
                <span>{activeAssignment.totalMarks} marks</span>
              </div>
              {turnoutPercent !== null ? (
                <div className="progress-track" aria-label={`${Math.round(turnoutPercent)}% submission turnout`}>
                  <span style={{ width: `${turnoutPercent}%` }} />
                </div>
              ) : (
                <small>Submission turnout is unavailable without an enrolled-student roster.</small>
              )}
              <div className="feature-bottom">
                <div className="feature-meta">
                  <span>
                    <CheckCircle2 size={13} />
                    {activeAssignment.submissionType} format
                  </span>
                </div>
                <Button variant="secondary" size="sm" onClick={() => navigate("/app/submissions")}>
                  View queue
                  <ArrowRight size={14} />
                </Button>
              </div>
            </>
          ) : (
            <div style={{ padding: "2rem 0", color: "#5C6E61" }}>
              <p>No assignments created yet. Set up an assignment to begin receiving student submissions.</p>
              <Button size="sm" onClick={() => navigate("/app/assignment/new")} style={{ marginTop: "1rem" }}>
                <Plus size={14} />
                Create first assignment
              </Button>
            </div>
          )}
          <span className="feature-watermark">
            <ShieldCheck size={138} strokeWidth={0.55} />
          </span>
        </Panel>

        <Panel className="deadline-card dashboard-deadlines">
          <div className="section-heading">
            <div>
              <h2>Upcoming deadlines</h2>
              <p>Assignments scheduled for your classes</p>
            </div>
            <button className="text-button" onClick={() => navigate("/app/assignments")}>
              View all
              <ArrowRight size={13} />
            </button>
          </div>
          <div className="timeline">
            {upcomingDeadlines.length > 0 ? (
              upcomingDeadlines.map((item) => (
                <div className="timeline-item" key={item.id}>
                  <strong>{item.title}</strong>
                  <div>
                    <span>{item.totalMarks} marks · {item.submissionType}</span>
                    <b>Due {formatDate(item.dueAt)}</b>
                  </div>
                </div>
              ))
            ) : (
              <p className="table-empty" style={{ padding: "1rem 0", color: "#5C6E61" }}>
                No deadlines scheduled yet.
              </p>
            )}
          </div>
        </Panel>
      </div>

      {demoSession ? (
        <div className="analytics-grid">
          <Panel className="chart-card">
            <div className="section-heading">
              <div>
                <h2>Demo class performance trend</h2>
                <p>Sample data for interface demonstration only</p>
              </div>
            </div>
            <div className="chart-total">
              84.6 <span>Demo sample</span>
            </div>
            <TrendChart />
          </Panel>
          <Panel className="chart-card">
            <div className="section-heading">
              <div>
                <h2>Demo grade distribution</h2>
                <p>Sample data for interface demonstration only</p>
              </div>
            </div>
            <DistributionChart />
          </Panel>
        </div>
      ) : (
        <IntegrationNotice
          title="Class analytics are not available"
          description="The connected backend does not expose grading statistics or historical performance data. Analytics are omitted rather than estimated."
          tone="info"
        />
      )}

      <Panel className="recent-card dashboard-recent">
        <div className="section-heading">
          <div>
            <h2>Recent submissions</h2>
            <p>Latest student work handed in for assessment</p>
          </div>
          <button className="text-button" onClick={() => navigate("/app/submissions")}>
            View all
            <ArrowRight size={13} />
          </button>
        </div>
        <RecentSubmissions rows={recentSubmissions} />
      </Panel>
    </>
  );
}
