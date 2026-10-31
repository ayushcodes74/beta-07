import { lazy } from "react";
import { useAppState } from "./App";

// Public entry pages load with the main bundle: they are the first thing a visitor sees, and they
// render outside the app shell's <Suspense> boundary.
export { LandingPage } from "./pages/common/LandingPage";
export { NotFoundPage } from "./pages/common/NotFoundPage";
export { AuthPage } from "./pages/common/AuthPage";

// Every page inside the signed-in app is its own chunk, downloaded the first time it is opened
// (and prefetched after sign-in, see prefetchAppPages). The app shell wraps them in <Suspense>.
const pageLoaders = {
  LeaderboardPage: () => import("./pages/common/LeaderboardPage").then((m) => ({ default: m.LeaderboardPage })),
  SettingsPage: () => import("./pages/common/SettingsPage").then((m) => ({ default: m.SettingsPage })),
  CoursesPage: () => import("./pages/teacher/CoursesPage").then((m) => ({ default: m.CoursesPage })),
  CourseDetailPage: () => import("./pages/teacher/CourseDetailPage").then((m) => ({ default: m.CourseDetailPage })),
  AssignmentsPage: () => import("./pages/teacher/AssignmentsPage").then((m) => ({ default: m.AssignmentsPage })),
  AssignmentEditor: () => import("./pages/teacher/AssignmentEditor").then((m) => ({ default: m.AssignmentEditor })),
  LateSubmissionsPage: () =>
    import("./pages/teacher/LateSubmissionsPage").then((m) => ({ default: m.LateSubmissionsPage })),
  SubmissionsPage: () => import("./pages/teacher/SubmissionsPage").then((m) => ({ default: m.SubmissionsPage })),
  GradingReviewPage: () => import("./pages/teacher/GradingReviewPage").then((m) => ({ default: m.GradingReviewPage })),
  OCRReviewPage: () => import("./pages/teacher/OCRReviewPage").then((m) => ({ default: m.OCRReviewPage })),
  ReviewQueuePage: () => import("./pages/teacher/ReviewQueuePage").then((m) => ({ default: m.ReviewQueuePage })),
  TeacherOverview: () => import("./pages/teacher/TeacherOverview").then((m) => ({ default: m.TeacherOverview })),
  StudentAssignmentsPage: () =>
    import("./pages/student/StudentAssignmentsPage").then((m) => ({ default: m.StudentAssignmentsPage })),
  StudentSubmissionPage: () =>
    import("./pages/student/StudentSubmissionPage").then((m) => ({ default: m.StudentSubmissionPage })),
  AssessmentPage: () => import("./pages/student/AssessmentPage").then((m) => ({ default: m.AssessmentPage })),
  ResultsPage: () => import("./pages/student/ResultsPage").then((m) => ({ default: m.ResultsPage })),
  StudentOverview: () => import("./pages/student/StudentOverview").then((m) => ({ default: m.StudentOverview })),
};

export const LeaderboardPage = lazy(pageLoaders.LeaderboardPage);
export const SettingsPage = lazy(pageLoaders.SettingsPage);
export const CoursesPage = lazy(pageLoaders.CoursesPage);
export const CourseDetailPage = lazy(pageLoaders.CourseDetailPage);
export const AssignmentsPage = lazy(pageLoaders.AssignmentsPage);
export const AssignmentEditor = lazy(pageLoaders.AssignmentEditor);
export const LateSubmissionsPage = lazy(pageLoaders.LateSubmissionsPage);
export const SubmissionsPage = lazy(pageLoaders.SubmissionsPage);
export const GradingReviewPage = lazy(pageLoaders.GradingReviewPage);
export const OCRReviewPage = lazy(pageLoaders.OCRReviewPage);
export const ReviewQueuePage = lazy(pageLoaders.ReviewQueuePage);
export const StudentAssignmentsPage = lazy(pageLoaders.StudentAssignmentsPage);
export const StudentSubmissionPage = lazy(pageLoaders.StudentSubmissionPage);
export const AssessmentPage = lazy(pageLoaders.AssessmentPage);
export const ResultsPage = lazy(pageLoaders.ResultsPage);
const TeacherOverview = lazy(pageLoaders.TeacherOverview);
const StudentOverview = lazy(pageLoaders.StudentOverview);

const teacherPages = [
  "TeacherOverview", "CoursesPage", "CourseDetailPage", "AssignmentsPage", "AssignmentEditor", "SubmissionsPage",
  "GradingReviewPage", "OCRReviewPage", "ReviewQueuePage", "LateSubmissionsPage", "ResultsPage", "LeaderboardPage",
  "SettingsPage",
] as const;
const studentPages = [
  "StudentOverview", "StudentAssignmentsPage", "StudentSubmissionPage", "AssessmentPage", "ResultsPage",
  "LeaderboardPage", "SettingsPage",
] as const;

let prefetched = false;

/** After sign-in, quietly download the role's other pages while the browser is idle, so later
 *  navigation is instant without making the first screen wait for them. */
export function prefetchAppPages(role: "teacher" | "student") {
  if (prefetched) return;
  prefetched = true;
  const names = role === "student" ? studentPages : teacherPages;
  const run = () => names.forEach((name) => void pageLoaders[name]().catch(() => undefined));
  const idle = (window as Window & { requestIdleCallback?: (cb: () => void) => number }).requestIdleCallback;
  if (idle) idle(run);
  else window.setTimeout(run, 1500);
}

export function OverviewPage() {
  const { user } = useAppState();
  return user?.role === "student" ? <StudentOverview /> : <TeacherOverview />;
}
