import { AnimatePresence, motion } from "framer-motion";
import {
  Award, Bell, BookOpen, Check, ChevronDown, ClipboardCheck, FileCheck2, FileText, GraduationCap,
  LayoutDashboard, LogOut, Menu, Search, Settings, ShieldCheck, Sparkles, Upload, X,
} from "lucide-react";
import { createContext, useContext, useEffect, useMemo, useState, type Dispatch, type ReactNode, type SetStateAction } from "react";
import { Link, Navigate, Outlet, Route, Routes, useLocation, useNavigate } from "react-router-dom";
import { cn } from "./lib/utils";
import { Avatar, ToastProvider, useToast } from "./components/ui";
import type { Assignment, Course, CourseMaterial, Submission, User } from "./types/models";
import { assignmentService, courseService, submissionService } from "./services/api";
import { getProfile, signOut } from "./services/auth";
import {
  AssignmentEditor, AssignmentsPage, AssessmentPage, AuthPage, CourseDetailPage, CoursesPage,
  GradingReviewPage, LandingPage, LeaderboardPage, MaterialsPage, NotFoundPage, OCRReviewPage,
  OverviewPage, ResultsPage, SettingsPage, StudentAssignmentsPage, StudentSubmissionPage,
  SubmissionsPage,
} from "./pages";

interface AppState {
  user: User | null;
  setUser: (user: User | null) => void;
  people: User[];
  courses: Course[];
  setCourses: Dispatch<SetStateAction<Course[]>>;
  assignments: Assignment[];
  setAssignments: Dispatch<SetStateAction<Assignment[]>>;
  joinedCourseIds: string[];
  setJoinedCourseIds: Dispatch<SetStateAction<string[]>>;
  submissions: Submission[];
  setSubmissions: Dispatch<SetStateAction<Submission[]>>;
  materials: CourseMaterial[];
  setMaterials: Dispatch<SetStateAction<CourseMaterial[]>>;
  loading: boolean;
  refreshSession: () => Promise<void>;
}

const AppContext = createContext<AppState | null>(null);

export function useAppState() {
  const context = useContext(AppContext);
  if (!context) throw new Error("useAppState must be used inside AppContext.");
  return context;
}

function AppProvider({ children }: { children: ReactNode }) {
  const [user, setUserState] = useState<User | null>(null);
  const [people, setPeople] = useState<User[]>([]);
  const [courseState, setCourses] = useState<Course[]>([]);
  const [assignmentState, setAssignments] = useState<Assignment[]>([]);
  const [joinedCourseIds, setJoinedCourseIds] = useState<string[]>([]);
  const [submissionState, setSubmissions] = useState<Submission[]>([]);
  const [materialState, setMaterials] = useState<CourseMaterial[]>([]);
  const [loading, setLoading] = useState(true);
  const refreshSession = async () => {
    setLoading(true);
    try {
      const profile = await getProfile();
      setUserState(profile);
      const [courses, assignments, submissions] = await Promise.all([
        courseService.getCourses(),
        assignmentService.getAssignments(),
        submissionService.getSubmissions(),
      ]);
      setCourses(courses);
      setAssignments(assignments);
      setJoinedCourseIds(courses.map((course) => course.id));
      setSubmissions(submissions);
      setPeople([]);
      setMaterials([]);
    } catch {
      signOut();
      setUserState(null);
      setCourses([]);
      setAssignments([]);
      setJoinedCourseIds([]);
      setSubmissions([]);
      setPeople([]);
      setMaterials([]);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (sessionStorage.getItem("tg_access_token")) void refreshSession();
    else setLoading(false);
  }, []);

  const setUser = (nextUser: User | null) => {
    if (nextUser) {
      void refreshSession();
    } else {
      signOut();
      setUserState(null);
      setPeople([]);
      setCourses([]);
      setAssignments([]);
      setJoinedCourseIds([]);
      setSubmissions([]);
      setMaterials([]);
    }
  };

  const value = useMemo(
    () => ({
      user,
      setUser,
      people,
      courses: courseState,
      setCourses,
      assignments: assignmentState,
      setAssignments,
      joinedCourseIds,
      setJoinedCourseIds,
      submissions: submissionState,
      setSubmissions,
      materials: materialState,
      setMaterials,
      loading,
      refreshSession,
    }),
    [user, people, courseState, assignmentState, joinedCourseIds, submissionState, materialState, loading]
  );

  return <AppContext.Provider value={value}>{children}</AppContext.Provider>;
}

const teacherNavigation = [
  {
    title: "Workspace",
    items: [
      { label: "Overview", to: "/app", icon: LayoutDashboard },
      { label: "Courses", to: "/app/courses", icon: BookOpen },
      { label: "Assignments", to: "/app/assignments", icon: FileText },
      { label: "Submissions", to: "/app/submissions", icon: Upload },
      { label: "AI Grading", to: "/app/grading/review", icon: Sparkles },
    ],
  },
  {
    title: "Resources",
    items: [
      { label: "Course materials", to: "/app/materials", icon: FileCheck2 },
      { label: "OCR review", to: "/app/ocr/review", icon: Search },
      { label: "Results", to: "/app/results", icon: ClipboardCheck },
      { label: "Leaderboard", to: "/app/leaderboard", icon: Award },
    ],
  },
];

const studentNavigation = [
  {
    title: "My learning",
    items: [
      { label: "Overview", to: "/app", icon: LayoutDashboard },
      { label: "My courses", to: "/app/courses", icon: BookOpen },
      { label: "Assignments", to: "/app/student/assignments", icon: FileText },
      { label: "My submissions", to: "/app/submissions", icon: Upload },
      { label: "My results", to: "/app/results", icon: ClipboardCheck },
      { label: "Leaderboard", to: "/app/leaderboard", icon: Award },
    ],
  },
];

function ApplicationShell() {
  const { user, setUser, loading, submissions } = useAppState();
  const navigate = useNavigate();
  const location = useLocation();
  const toast = useToast();
  const [mobileOpen, setMobileOpen] = useState(false);
  const [searchOpen, setSearchOpen] = useState(false);
  const [notificationsOpen, setNotificationsOpen] = useState(false);

  if (loading) {
    return (
      <div style={{ display: "flex", height: "100vh", alignItems: "center", justifyContent: "center", flexDirection: "column", gap: "1rem" }}>
        <span className="button-spinner" style={{ width: 24, height: 24 }} />
        <span style={{ fontSize: "0.9rem", color: "var(--color-text-muted, #71717a)" }}>Loading workspace…</span>
      </div>
    );
  }

  if (!user) return <Navigate to="/login" replace state={{ from: location.pathname }} />;

  const isStudent = user.role === "student";
  const rawNavigation = isStudent ? studentNavigation : teacherNavigation;
  // Dynamic submission count badge if real submissions exist
  const navigation = rawNavigation.map((group) => ({
    ...group,
    items: group.items.map((item) => ({
      ...item,
      count: item.label === "Submissions" && submissions.length > 0 ? String(submissions.length) : undefined,
    })),
  }));

  const pageName = location.pathname.endsWith("/app")
    ? "Overview"
    : location.pathname.split("/").filter(Boolean).at(-1)?.replace(/-/g, " ") ?? "Overview";
  const title = pageName.split(" ").map((word) => word[0]?.toUpperCase() + word.slice(1)).join(" ");

  const { courses: courseList } = useAppState();
  const search = (value: string) => {
    if (!value.trim()) return;
    const query = value.toLowerCase();
    const course = courseList.find((item) => `${item.name} ${item.code}`.toLowerCase().includes(query));
    if (course) navigate(`/app/courses/${course.id}`);
    else if (isStudent) navigate("/app/student/assignments");
    else navigate("/app/submissions");
    setSearchOpen(false);
  };

  const logout = async () => {
    setUser(null);
    navigate("/login");
    toast("Signed out.", "info");
  };

  return (
    <div className="app-shell">
      {mobileOpen && <button className="mobile-scrim" aria-label="Close navigation" onClick={() => setMobileOpen(false)} />}
      <aside className={cn("sidebar", mobileOpen && "sidebar-open")}>
        <Link to="/app" className="brand">
          <span className="brand-mark"><Check size={19} strokeWidth={2.2} /></span>
          <span className="brand-word">Trust<span>Grade</span></span>
        </Link>
        <button
          className="workspace-switch"
          onClick={() => toast(`Role: ${isStudent ? "Student" : "Faculty"}. Managed by your account profile.`, "info")}
        >
          <span className="workspace-icon"><GraduationCap size={16} /></span>
          <span className="workspace-copy">
            <strong>{isStudent ? "Student workspace" : "Faculty workspace"}</strong>
            <small>Current workspace</small>
          </span>
          <ChevronDown size={14} />
        </button>
        <nav className="sidebar-nav" aria-label="Main navigation">
          {navigation.map((group) => (
            <div className="nav-group" key={group.title}>
              <div className="nav-label">{group.title}</div>
              {group.items.map(({ label, to, icon: Icon, count }) => {
                const active = location.pathname === to || (to !== "/app" && location.pathname.startsWith(to));
                return (
                  <Link
                    key={to}
                    to={to}
                    onClick={() => setMobileOpen(false)}
                    className={cn("nav-link", active && "active")}
                  >
                    <Icon size={16} strokeWidth={1.8} />
                    <span>{label}</span>
                    {count && <span className="nav-count">{count}</span>}
                  </Link>
                );
              })}
            </div>
          ))}
        </nav>
        <div className="sidebar-bottom">
          {!isStudent && (
            <Link to="/app/settings" className={cn("nav-link", location.pathname.includes("settings") && "active")}>
              <Settings size={16} />
              <span>Settings</span>
            </Link>
          )}
          <div className="sidebar-profile">
            <Avatar name={user.name} initials={user.initials} className="avatar-profile" />
            <span className="profile-copy">
              <strong>{user.name}</strong>
              <small>{isStudent ? "Student" : "Instructor"}</small>
            </span>
            <button className="icon-button profile-logout" aria-label="Log out" onClick={() => void logout()}>
              <LogOut size={15} />
            </button>
          </div>
        </div>
      </aside>
      <div className="main-shell">
        <header className="topbar">
          <div className="breadcrumbs">
            <button className="icon-button mobile-menu-button" onClick={() => setMobileOpen(true)} aria-label="Open navigation">
              <Menu size={18} />
            </button>
            <span>TrustGrade</span><span className="crumb-separator">/</span><strong>{title}</strong>
          </div>
          <div className="topbar-actions">
            {searchOpen ? (
              <form
                className="search-box search-open"
                onSubmit={(event) => {
                  event.preventDefault();
                  search(new FormData(event.currentTarget).get("query")?.toString() ?? "");
                }}
              >
                <Search size={15} />
                <input autoFocus name="query" placeholder="Search courses, assignments..." aria-label="Search courses and assignments" />
                <button className="icon-button" type="button" onClick={() => setSearchOpen(false)} aria-label="Close search">
                  <X size={14} />
                </button>
              </form>
            ) : (
              <>
                <form
                  className="search-box desktop-search"
                  onSubmit={(event) => {
                    event.preventDefault();
                    search(new FormData(event.currentTarget).get("query")?.toString() ?? "");
                  }}
                >
                  <Search size={15} />
                  <input name="query" placeholder="Search courses, assignments..." aria-label="Search courses and assignments" />
                </form>
                <button className="icon-button search-trigger mobile-search-trigger" aria-label="Search" onClick={() => setSearchOpen(true)}>
                  <Search size={17} />
                </button>
              </>
            )}
            <span className="topbar-divider" />
            <div className="notification-wrap">
              <button
                className="icon-button notification-button"
                aria-label="Notifications"
                onClick={() => setNotificationsOpen((open) => !open)}
              >
                <Bell size={17} />
              </button>
              {notificationsOpen && (
                <div className="notification-popover glass-panel">
                  <strong>Notifications</strong>
                  <p>
                    <b>Workspace connected</b>
                    <span>{user.name} · {user.role === "teacher" ? "Faculty" : "Student"}</span>
                  </p>
                </div>
              )}
            </div>
            <Avatar name={user.name} initials={user.initials} className="avatar-top" />
          </div>
        </header>
        <div className="route-stage">
          <AnimatePresence mode="wait" initial={false}>
            <motion.main
              key={location.pathname}
              className="page-content"
              initial={{ opacity: 0, y: 5 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -3 }}
              transition={{ duration: 0.18 }}
            >
              <Outlet />
            </motion.main>
          </AnimatePresence>
        </div>
        <footer className="app-footnote">
          <ShieldCheck size={13} />
          <span>AI assists. Teachers decide. Students understand.</span>
          <span className="workspace-status-label" style={{ opacity: 0.8 }}>Signed in workspace</span>
        </footer>
      </div>
    </div>
  );
}

function SessionRoute({ children }: { children: ReactNode }) {
  const { user, loading } = useAppState();
  if (loading) return null;
  return user ? <>{children}</> : <Navigate to="/login" replace />;
}

function AppRoutes() {
  const {
    courses: courseState,
    setCourses,
    assignments: assignmentState,
    setAssignments,
    joinedCourseIds,
    setJoinedCourseIds,
    submissions: submissionState,
    setSubmissions,
    materials: materialState,
    setMaterials,
  } = useAppState();

  return (
    <Routes>
      <Route path="/" element={<LandingPage />} />
      <Route path="/login" element={<AuthPage />} />
      <Route path="/register" element={<AuthPage register />} />
      <Route path="/app" element={<SessionRoute><ApplicationShell /></SessionRoute>}>
        <Route index element={<OverviewPage />} />
        <Route path="courses" element={<CoursesPage courses={courseState} setCourses={setCourses} />} />
        <Route path="courses/:courseId" element={<CourseDetailPage courses={courseState} />} />
        <Route path="materials" element={<MaterialsPage materials={materialState} setMaterials={setMaterials} />} />
        <Route path="assignments" element={<AssignmentsPage />} />
        <Route path="assignment/new" element={<AssignmentEditor courses={courseState} assignments={assignmentState} setAssignments={setAssignments} />} />
        <Route path="submissions" element={<SubmissionsPage submissions={submissionState} />} />
        <Route path="grading/:submissionId" element={<GradingReviewPage submissions={submissionState} setSubmissions={setSubmissions} />} />
        <Route path="ocr/:submissionId" element={<OCRReviewPage submissions={submissionState} setSubmissions={setSubmissions} />} />
        <Route path="results" element={<ResultsPage submissions={submissionState} />} />
        <Route path="leaderboard" element={<LeaderboardPage />} />
        <Route path="settings" element={<SettingsPage />} />
        <Route path="student/assignments" element={<StudentAssignmentsPage courses={courseState} joinedCourseIds={joinedCourseIds} setJoinedCourseIds={setJoinedCourseIds} submissions={submissionState} />} />
        <Route path="student/submit/:assignmentId" element={<StudentSubmissionPage submissions={submissionState} setSubmissions={setSubmissions} />} />
        <Route path="student/assessment/:assignmentId" element={<AssessmentPage submissions={submissionState} setSubmissions={setSubmissions} />} />
        <Route path="*" element={<NotFoundPage />} />
      </Route>
      <Route path="*" element={<NotFoundPage />} />
    </Routes>
  );
}

export function App() {
  return (
    <ToastProvider>
      <AppProvider>
        <AppRoutes />
      </AppProvider>
    </ToastProvider>
  );
}
