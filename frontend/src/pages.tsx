import { useAppState } from "./App";
import { TeacherOverview } from "./pages/teacher/TeacherOverview";
import { StudentOverview } from "./pages/student/StudentOverview";

export { LandingPage } from "./pages/common/LandingPage";
export { AuthPage } from "./pages/common/AuthPage";
export { RoleSelectionPage } from "./pages/common/RoleSelectionPage";
export { LeaderboardPage } from "./pages/common/LeaderboardPage";
export { SettingsPage } from "./pages/common/SettingsPage";
export { NotFoundPage } from "./pages/common/NotFoundPage";

export { CoursesPage } from "./pages/teacher/CoursesPage";
export { CourseDetailPage } from "./pages/teacher/CourseDetailPage";
export { AssignmentsPage } from "./pages/teacher/AssignmentsPage";
export { AssignmentEditor } from "./pages/teacher/AssignmentEditor";
export { SubmissionsPage } from "./pages/teacher/SubmissionsPage";
export { GradingReviewPage } from "./pages/teacher/GradingReviewPage";
export { OCRReviewPage } from "./pages/teacher/OCRReviewPage";
export { MaterialsPage } from "./pages/teacher/MaterialsPage";

export { StudentAssignmentsPage } from "./pages/student/StudentAssignmentsPage";
export { StudentSubmissionPage } from "./pages/student/StudentSubmissionPage";
export { AssessmentPage } from "./pages/student/AssessmentPage";
export { ResultsPage } from "./pages/student/ResultsPage";

export function OverviewPage() {
  const { user } = useAppState();
  return user?.role === "student" ? <StudentOverview /> : <TeacherOverview />;
}
