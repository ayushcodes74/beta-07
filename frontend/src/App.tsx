import { AnimatePresence, motion } from "framer-motion";
import {
  Award, Bell, BookOpen, Check, ChevronDown, ClipboardCheck, FileCheck2, FileText, GraduationCap,
  LayoutDashboard, LogOut, Menu, Search, Settings, ShieldCheck, Sparkles, Upload, X,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { createContext, useContext, useMemo, useState, type Dispatch, type ReactNode, type SetStateAction } from "react";
import { Link, Navigate, Outlet, Route, Routes, useLocation, useNavigate } from "react-router-dom";
import { assignments as initialAssignments, courses as initialCourses, materials, submissions, users } from "./lib/mock-data";
import { cn } from "./lib/utils";
import { Avatar, ToastProvider, useToast } from "./components/ui";
import type { Assignment, Course, CourseMaterial, Submission, User } from "./types/models";
import { authService } from "./services/api";
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
}

const AppContext = createContext<AppState | null>(null);

function loadDemoUser(): User | null {
  if (import.meta.env.VITE_USE_API_AUTH === "true") return null;
  const id = sessionStorage.getItem("trustgrade-user");
  if (!id) return null;
  const knownUser = users.find((item) => item.id === id);
  if (knownUser) return knownUser;
  const name = sessionStorage.getItem("trustgrade-user-name");
  const email = sessionStorage.getItem("trustgrade-user-email");
  const role = sessionStorage.getItem("trustgrade-user-role");
  const initials = sessionStorage.getItem("trustgrade-user-initials");
  if (!name || !email || !initials || (role !== "teacher" && role !== "student")) return null;
  return { id, name, email, role, initials };
}

export function useAppState() {
  const context = useContext(AppContext);
  if (!context) throw new Error("useAppState must be used inside AppContext.");
  return context;
}

function AppProvider({ children }: { children: ReactNode }) {
  const [user, setUserState] = useState<User | null>(loadDemoUser);
  const [people, setPeople] = useState(users);
  const [courseState, setCourses] = useState(initialCourses);
  const [assignmentState, setAssignments] = useState(initialAssignments);
  const [joinedCourseIds, setJoinedCourseIds] = useState(["cs204"]);
  const [submissionState, setSubmissions] = useState(submissions);
  const [materialState, setMaterials] = useState(materials);
  const setUser = (nextUser: User | null) => {
    if (nextUser) setPeople((current) => current.some((person) => person.id === nextUser.id) ? current : [...current, nextUser]);
    if (nextUser && import.meta.env.VITE_USE_API_AUTH !== "true") {
      sessionStorage.setItem("trustgrade-user", nextUser.id);
      sessionStorage.setItem("trustgrade-user-name", nextUser.name);
      sessionStorage.setItem("trustgrade-user-email", nextUser.email);
      sessionStorage.setItem("trustgrade-user-role", nextUser.role);
      sessionStorage.setItem("trustgrade-user-initials", nextUser.initials);
    } else {
      for (const key of ["trustgrade-user", "trustgrade-user-name", "trustgrade-user-email", "trustgrade-user-role", "trustgrade-user-initials"]) sessionStorage.removeItem(key);
    }
    setUserState(nextUser);
  };
  const value = useMemo(() => ({ user, setUser, people, courses: courseState, setCourses, assignments: assignmentState, setAssignments, joinedCourseIds, setJoinedCourseIds, submissions: submissionState, setSubmissions, materials: materialState, setMaterials }), [user, people, courseState, assignmentState, joinedCourseIds, submissionState, materialState]);
  return <AppContext.Provider value={value}>{children}</AppContext.Provider>;
}

const teacherNavigation = [
  { title: "Workspace", items: [
    { label: "Overview", to: "/app", icon: LayoutDashboard },
    { label: "Courses", to: "/app/courses", icon: BookOpen },
    { label: "Assignments", to: "/app/assignments", icon: FileText },
    { label: "Submissions", to: "/app/submissions", icon: Upload, count: "18" },
    { label: "AI Grading", to: "/app/grading/sub-maya-ds", icon: Sparkles },
  ] },
  { title: "Resources", items: [
    { label: "Course materials", to: "/app/materials", icon: FileCheck2 },
    { label: "OCR review", to: "/app/ocr/sub-maya-ds", icon: Search, count: "3" },
    { label: "Results", to: "/app/results", icon: ClipboardCheck },
    { label: "Leaderboard", to: "/app/leaderboard", icon: Award },
  ] },
];

const studentNavigation = [
  { title: "My learning", items: [
    { label: "Overview", to: "/app", icon: LayoutDashboard },
    { label: "My courses", to: "/app/courses", icon: BookOpen },
    { label: "Assignments", to: "/app/student/assignments", icon: FileText },
    { label: "My submissions", to: "/app/submissions", icon: Upload },
    { label: "My results", to: "/app/results", icon: ClipboardCheck },
    { label: "Leaderboard", to: "/app/leaderboard", icon: Award },
  ] },
];

function ApplicationShell() {
  const { user, setUser, people } = useAppState();
  const navigate = useNavigate();
  const location = useLocation();
  const toast = useToast();
  const [mobileOpen, setMobileOpen] = useState(false);
  const [searchOpen, setSearchOpen] = useState(false);
  const [notificationsOpen, setNotificationsOpen] = useState(false);
  if (!user) return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  const isStudent = user.role === "student";
  const navigation: { title: string; items: { label: string; to: string; icon: LucideIcon; count?: string }[] }[] = isStudent ? studentNavigation : teacherNavigation;
  const pageName = location.pathname.endsWith("/app") ? "Overview" : location.pathname.split("/").filter(Boolean).at(-1)?.replace(/-/g, " ") ?? "Overview";
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
    try {
      if (import.meta.env.VITE_USE_API_AUTH === "true") await authService.logout();
      setUser(null);
      navigate("/");
    } catch (reason) {
      toast(reason instanceof Error ? `Could not sign out: ${reason.message}` : "Could not sign out. Please try again.", "info");
    }
  };

  return <div className="app-shell">
    {mobileOpen && <button className="mobile-scrim" aria-label="Close navigation" onClick={() => setMobileOpen(false)} />}
    <aside className={cn("sidebar", mobileOpen && "sidebar-open")}>
      <Link to="/app" className="brand"><span className="brand-mark"><Check size={19} strokeWidth={2.2} /></span><span className="brand-word">Trust<span>Grade</span></span></Link>
      <button className="workspace-switch" onClick={() => setUser(people.find((person) => person.role !== user.role) ?? users[0])}>
        <span className="workspace-icon"><GraduationCap size={16} /></span>
        <span className="workspace-copy"><strong>{isStudent ? "Student workspace" : "Faculty workspace"}</strong><small>Spring term · 2026</small></span><ChevronDown size={14} />
      </button>
      <nav className="sidebar-nav" aria-label="Main navigation">
        {navigation.map((group) => <div className="nav-group" key={group.title}>
          <div className="nav-label">{group.title}</div>
          {group.items.map(({ label, to, icon: Icon, count }) => {
            const active = location.pathname === to || (to !== "/app" && location.pathname.startsWith(to));
            return <Link key={to} to={to} onClick={() => setMobileOpen(false)} className={cn("nav-link", active && "active")}>
              <Icon size={16} strokeWidth={1.8} /><span>{label}</span>{count && <span className="nav-count">{count}</span>}
            </Link>;
          })}
        </div>)}
      </nav>
      <div className="sidebar-bottom">
        {!isStudent && <Link to="/app/settings" className={cn("nav-link", location.pathname.includes("settings") && "active")}><Settings size={16} /><span>Settings</span></Link>}
        <div className="sidebar-profile">
          <Avatar name={user.name} initials={user.initials} className="avatar-profile" />
          <span className="profile-copy"><strong>{user.name}</strong><small>{isStudent ? "Student" : "Instructor"}</small></span>
          <button className="icon-button profile-logout" aria-label="Log out" onClick={() => void logout()}><LogOut size={15} /></button>
        </div>
      </div>
    </aside>
    <div className="main-shell">
      <header className="topbar">
        <div className="breadcrumbs">
          <button className="icon-button mobile-menu-button" onClick={() => setMobileOpen(true)} aria-label="Open navigation"><Menu size={18} /></button>
          <span>TrustGrade</span><span className="crumb-separator">/</span><strong>{title}</strong>
        </div>
        <div className="topbar-actions">
          {searchOpen ? <form className="search-box search-open" onSubmit={(event) => { event.preventDefault(); search(new FormData(event.currentTarget).get("query")?.toString() ?? ""); }}>
            <Search size={15} /><input autoFocus name="query" placeholder="Search courses, assignments..." aria-label="Search courses and assignments" /><button className="icon-button" type="button" onClick={() => setSearchOpen(false)} aria-label="Close search"><X size={14} /></button>
          </form> : <button className="icon-button search-trigger" aria-label="Search" onClick={() => setSearchOpen(true)}><Search size={17} /></button>}
          <span className="topbar-divider" />
          <div className="notification-wrap"><button className="icon-button notification-button" aria-label="Notifications" onClick={() => setNotificationsOpen((open) => !open)}><span className="notification-dot" /><Bell size={17} /></button>
            {notificationsOpen && <div className="notification-popover glass-panel"><strong>Notifications</strong><p><b>3 submissions need OCR review</b><span>Check handwritten pages before grading.</span></p><p><b>Assignment due tomorrow</b><span>Operating Systems — Assignment 02.</span></p></div>}
          </div>
          <Avatar name={user.name} initials={user.initials} className="avatar-top" />
        </div>
      </header>
      <div className="route-stage">
        <AnimatePresence mode="wait" initial={false}>
          <motion.main key={location.pathname} className="page-content" initial={{ opacity: 0, y: 5 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -3 }} transition={{ duration: 0.18 }}>
            <Outlet />
          </motion.main>
        </AnimatePresence>
      </div>
      <footer className="app-footnote"><ShieldCheck size={13} /><span>AI assists. Teachers decide. Students understand.</span><span className="demo-label">DEMO DATA</span></footer>
    </div>
  </div>;
}

function SessionRoute({ children }: { children: ReactNode }) {
  const { user } = useAppState();
  return user ? <>{children}</> : <Navigate to="/login" replace />;
}

function AppRoutes() {
  const { user, setUser, courses: courseState, setCourses, assignments: assignmentState, setAssignments, joinedCourseIds, setJoinedCourseIds, submissions: submissionState, setSubmissions, materials: materialState, setMaterials } = useAppState();
  return <Routes>
    <Route path="/" element={<LandingPage />} />
    <Route path="/login" element={user ? <Navigate to="/app" replace /> : <AuthPage mode="login" onAuthenticated={setUser} />} />
    <Route path="/register" element={user ? <Navigate to="/app" replace /> : <AuthPage mode="register" onAuthenticated={setUser} />} />
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
  </Routes>;
}

export function App() {
  return <ToastProvider><AppProvider><AppRoutes /></AppProvider></ToastProvider>;
}
