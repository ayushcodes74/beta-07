import {
  Award, BookOpen, Check, ChevronDown, ClipboardCheck, Clock, FileText, GraduationCap,
  LayoutDashboard, LogOut, Menu, MessageCircle, MessageSquareWarning, ScanText, Search, Settings, ShieldAlert, ShieldCheck,
  Sparkles, Upload,
} from "lucide-react";
import { createContext, Suspense, useContext, useEffect, useMemo, useState, type Dispatch, type ReactNode, type SetStateAction } from "react";
import { Link, Navigate, Outlet, Route, Routes, useLocation, useNavigate } from "react-router-dom";
import { cn } from "./lib/utils";
import { Avatar, ToastProvider, useToast } from "./components/ui";
import type { Assignment, Course, Submission, User } from "./types/models";
import { assignmentService, courseService, extractErrorMessage, submissionService } from "./services/api";
import { getProfile, signOut } from "./services/auth";
import { NamePrompt } from "./components/common/NamePrompt";
import { NotificationBell } from "./components/common/NotificationBell";
import { useUnreadMessages } from "./components/common/useUnreadMessages";
import { HeaderSearch } from "./components/common/HeaderSearch";
import { useSubmissionStatusSync } from "./lib/useSubmissionStatusSync";
import {
  AssignmentEditor, AssignmentsPage, AssessmentPage, AuthPage, CourseDetailPage, CoursesPage,
  GradingReviewPage, LandingPage, LateSubmissionsPage, LeaderboardPage, MessagesPage, NotFoundPage, OCRReviewPage,
  OverviewPage, ResultsPage, ReviewQueuePage, SettingsPage, StudentAssignmentsPage, StudentSubmissionPage,
  SubmissionsPage, prefetchAppPages,
} from "./pages";

/** Shown for the moment a page's code is downloading (first visit only). */
function PageLoading() {
  return (
    <div className="page-loading" role="status" aria-live="polite">
      <span className="page-loading-bar" />
      <span className="sr-only">Loading page…</span>
    </div>
  );
}

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
  loading: boolean;
  /** Loads the signed-in workspace. Resolves to an error message on failure, or null on success. */
  refreshSession: () => Promise<string | null>;
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
  const [loading, setLoading] = useState(true);
  const refreshSession = async (): Promise<string | null> => {
    setLoading(true);
    try {
      // All four requests start together (the lists don't depend on the profile: the backend reads the
      // user from the token), saving a full round trip before the workspace appears.
      const workspace = Promise.all([
        courseService.getCourses(),
        assignmentService.getAssignments(),
        submissionService.getSubmissions(),
      ]);
      workspace.catch(() => undefined); // handled below; avoids an unhandled rejection if the profile fails first
      const profile = await getProfile();
      setUserState(profile);
      prefetchAppPages(profile.role);
      const [courses, assignments, submissions] = await workspace;
      setCourses(courses);
      setAssignments(assignments);
      setJoinedCourseIds(courses.map((course) => course.id));
      setSubmissions(submissions);
      setPeople([]);
      return null;
    } catch (reason) {
      signOut();
      setUserState(null);
      setCourses([]);
      setAssignments([]);
      setJoinedCourseIds([]);
      setSubmissions([]);
      setPeople([]);
      return `Signed in, but your workspace could not be loaded: ${extractErrorMessage(reason, "unknown error")}`;
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
      loading,
      refreshSession,
    }),
    [user, people, courseState, assignmentState, joinedCourseIds, submissionState, loading]
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
      { label: "Messages", to: "/app/messages", icon: MessageCircle },
    ],
  },
  {
    // Manual review: all three link to the Review queue page, one tab each.
    title: "Review",
    items: [
      { label: "OCR review", to: "/app/reviews?tab=ocr", icon: ScanText },
      { label: "Low trust score", to: "/app/reviews?tab=trust", icon: ShieldAlert },
      { label: "Student requests", to: "/app/reviews?tab=requests", icon: MessageSquareWarning },
      { label: "Late submissions", to: "/app/late-submissions", icon: Clock },
    ],
  },
  {
    title: "Resources",
    items: [
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
      { label: "Messages", to: "/app/messages", icon: MessageCircle },
    ],
  },
];

/** Query-string links (Review queue tabs) match on path + tab; the first tab is the default. */
function isNavItemActive(to: string, pathname: string, search: string) {
  const [path, query] = to.split("?");
  if (!query) return pathname === path || (path !== "/app" && pathname.startsWith(path));
  if (pathname !== path) return false;
  const tab = new URLSearchParams(query).get("tab");
  const current = new URLSearchParams(search).get("tab") ?? "ocr";
  return tab === current;
}

function WorkspaceLoading() {
  return (
    <div style={{ display: "flex", height: "100vh", alignItems: "center", justifyContent: "center", flexDirection: "column", gap: "1rem" }}>
      <span className="button-spinner" style={{ width: 24, height: 24 }} />
      <span style={{ fontSize: "0.9rem", color: "var(--color-text-muted, #71717a)" }}>Loading workspace…</span>
    </div>
  );
}

/** Route segments that are record ids (UUIDs, numeric ids), not page names. */
const isIdSegment = (segment: string) => /\d/.test(segment) && segment.length >= 6;
const pageTitles: Record<string, string> = {
  app: "Overview",
  reviews: "Review queue",
  grading: "AI grading review",
  ocr: "OCR review",
  new: "New assignment",
  edit: "Edit assignment",
  submit: "Submit assignment",
  assessment: "Assessment",
};

function pageTitle(pathname: string) {
  const segment = pathname.split("/").filter(Boolean).reverse().find((part) => !isIdSegment(part)) ?? "app";
  if (pageTitles[segment]) return pageTitles[segment];
  return segment.split("-").filter(Boolean).map((word) => word[0].toUpperCase() + word.slice(1)).join(" ");
}

function ApplicationShell() {
  const {
    user, setUser, submissions, refreshSession,
    setCourses, setAssignments, setJoinedCourseIds, setSubmissions,
  } = useAppState();
  const navigate = useNavigate();
  const location = useLocation();
  const toast = useToast();
  const [mobileOpen, setMobileOpen] = useState(false);
  const [searchOpen, setSearchOpen] = useState(false);

  // A new notification usually means a new/changed assignment, submission or grade: reload those lists
  // quietly so the dashboard (and the notification's link) shows the latest data without a page refresh.
  const reloadWorkspace = () => {
    Promise.all([courseService.getCourses(), assignmentService.getAssignments(), submissionService.getSubmissions()])
      .then(([courses, assignments, items]) => {
        setCourses(courses);
        setAssignments(assignments);
        setJoinedCourseIds(courses.map((course) => course.id));
        setSubmissions(items);
      })
      .catch(() => undefined);
  };
  const unreadMessages = useUnreadMessages(!!user);
  // Lists otherwise keep showing "In Progress" after OCR has finished (see the hook).
  useSubmissionStatusSync(submissions, setSubmissions, !!user);

  if (!user) return <Navigate to="/login" replace state={{ from: location.pathname }} />;

  const isStudent = user.role === "student";
  const rawNavigation = isStudent ? studentNavigation : teacherNavigation;
  // Dynamic count badges: all submissions, and late submissions still awaiting a decision.
  const pendingLate = submissions.filter((item) => item.late?.status === "pending").length;
  const navCount = (label: string) => {
    if (label === "Submissions" && submissions.length > 0) return String(submissions.length);
    if (label === "Late submissions" && pendingLate > 0) return String(pendingLate);
    if (label === "Messages" && unreadMessages > 0) return String(unreadMessages);
    return undefined;
  };
  const navigation = rawNavigation.map((group) => ({
    ...group,
    items: group.items.map((item) => ({ ...item, count: navCount(item.label) })),
  }));

  const title = pageTitle(location.pathname);

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
                const active = isNavItemActive(to, location.pathname, location.search);
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
              <HeaderSearch className="search-open" autoFocus onClose={() => setSearchOpen(false)} />
            ) : (
              <>
                <HeaderSearch className="desktop-search" />
                <button className="icon-button search-trigger mobile-search-trigger" aria-label="Search" onClick={() => setSearchOpen(true)}>
                  <Search size={17} />
                </button>
              </>
            )}
            <span className="topbar-divider" />
            <NotificationBell onNew={reloadWorkspace} />
            <Avatar name={user.name} initials={user.initials} className="avatar-top" />
          </div>
        </header>
        <div className="route-stage">
          {/* Students only: their name is what teachers and the course leaderboard show. */}
          {isStudent && user.needsName && <NamePrompt suggestion={user.name} onSaved={refreshSession} />}
          {/* The new page renders immediately with a short CSS fade-in. (A framer-motion
              AnimatePresence in "wait" mode held every navigation until the old page had faded out.) */}
          <main key={location.pathname} className="page-content page-enter">
            <Suspense fallback={<PageLoading />}>
              <Outlet />
            </Suspense>
          </main>
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
  // Only the first load blocks the screen. Later refreshes (e.g. after saving a display name) keep the
  // shell mounted, so the current page and its unsaved state aren't thrown away.
  if (loading && !user) return <WorkspaceLoading />;
  return user ? <>{children}</> : <Navigate to="/login" replace />;
}

/** Layout route: pages for one role only. The other role is sent to its own Overview instead of
 *  seeing a page whose actions the backend would reject (403). */
function RoleRoute({ role }: { role: User["role"] }) {
  const { user } = useAppState();
  return user?.role === role ? <Outlet /> : <Navigate to="/app" replace />;
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
  } = useAppState();

  return (
    <Routes>
      <Route path="/" element={<LandingPage />} />
      <Route path="/login" element={<AuthPage />} />
      <Route path="/register" element={<AuthPage register />} />
      <Route path="/app" element={<SessionRoute><ApplicationShell /></SessionRoute>}>
        <Route index element={<OverviewPage />} />
        <Route path="courses" element={<CoursesPage courses={courseState} setCourses={setCourses} />} />
        {/* Both roles */}
        <Route path="submissions" element={<SubmissionsPage submissions={submissionState} />} />
        <Route path="results" element={<ResultsPage submissions={submissionState} />} />
        <Route path="leaderboard" element={<LeaderboardPage />} />
        <Route path="messages" element={<MessagesPage />} />
        <Route path="settings" element={<SettingsPage />} />
        {/* Teachers only */}
        <Route element={<RoleRoute role="teacher" />}>
          <Route path="courses/:courseId" element={<CourseDetailPage courses={courseState} />} />
          {/* Course material is now attached while creating an assignment; keep old links working. */}
          <Route path="materials" element={<Navigate to="/app/assignment/new" replace />} />
          <Route path="assignments" element={<AssignmentsPage />} />
          <Route path="assignment/new" element={<AssignmentEditor courses={courseState} assignments={assignmentState} setAssignments={setAssignments} />} />
          <Route path="assignment/:assignmentId/edit" element={<AssignmentEditor courses={courseState} assignments={assignmentState} setAssignments={setAssignments} />} />
          <Route path="grading/:submissionId" element={<GradingReviewPage submissions={submissionState} setSubmissions={setSubmissions} />} />
          <Route path="reviews" element={<ReviewQueuePage />} />
          <Route path="late-submissions" element={<LateSubmissionsPage />} />
          {/* The old "OCR review" sidebar link pointed here; it is now a Review queue tab. */}
          <Route path="ocr/review" element={<Navigate to="/app/reviews?tab=ocr" replace />} />
          <Route path="ocr/:submissionId" element={<OCRReviewPage submissions={submissionState} setSubmissions={setSubmissions} />} />
        </Route>
        {/* Students only */}
        <Route element={<RoleRoute role="student" />}>
          <Route path="student/assignments" element={<StudentAssignmentsPage courses={courseState} joinedCourseIds={joinedCourseIds} setJoinedCourseIds={setJoinedCourseIds} submissions={submissionState} />} />
          <Route path="student/submit/:assignmentId" element={<StudentSubmissionPage submissions={submissionState} setSubmissions={setSubmissions} />} />
          <Route path="student/assessment/:assignmentId" element={<AssessmentPage submissions={submissionState} setSubmissions={setSubmissions} />} />
        </Route>
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
