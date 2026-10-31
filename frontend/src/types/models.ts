export type UserRole = "teacher" | "student";
export type ProcessingState = "Uploading" | "Processing" | "Ready" | "Needs Review" | "Failed";
export type SubmissionState = "Not Started" | "In Progress" | "Submitted" | "Under Review" | "Graded" | "Late Submission" | "Rejected" | "Published";

export interface User {
  id: string;
  name: string;
  email: string;
  role: UserRole;
  initials: string;
  /** True until the user has saved a display name (profiles.display_name is empty). */
  needsName?: boolean;
}

export interface Course {
  id: string;
  name: string;
  code: string;
  instructor: string;
  students: number;
  assignments: number;
  activity: number;
  average: number;
}

export interface Question {
  id: string;
  prompt: string;
  type: "Subjective" | "MCQ";
  marks: number;
  expectedAnswer: string;
  options?: string[];
  correctOption?: number;
}

export interface RubricCriterion {
  id: string;
  name: string;
  description: string;
  score: number;
  maximum: number;
}

export interface Rubric {
  id: string;
  name: string;
  criteria: RubricCriterion[];
}

export interface Assignment {
  id: string;
  courseId: string;
  title: string;
  description: string;
  dueAt: string;
  totalMarks: number;
  state: "Draft" | "Published" | "Closed";
  submissionType: "PDF" | "MCQ" | "Mixed";
  questions: Question[];
  rubricId: string;
}

export interface OCRResult {
  confidence: number | null;
  state: "High confidence" | "Needs review" | "Low confidence" | "Verified";
  extractedText: string;
  warnings: string[];
  expressions: string[];
}

export interface Feedback {
  id: string;
  comment: string;
  deductions: { criterion: string; reason: string; marks: number }[];
  courseReferences: string[];
}

/** Why one question got its mark, as published to the student. */
export interface QuestionResult {
  number: number;
  questionText: string;
  /** null when the grade has no per-question marks (teacher-only grade). */
  awardedMarks: number | null;
  maxMarks: number;
  explanation: string;
  strengths: string[];
  areasForImprovement: string[];
  /** Set when the teacher changed the AI's mark for this question. */
  teacherComment: string | null;
  /** The teacher's expected answer, once released to students. */
  expectedSolution: string | null;
}

export interface GradingResult {
  suggestedScore: number;
  confidence: number;
  reasoning: string;
  rubric: RubricCriterion[];
  feedback: Feedback;
  teacherApproved: boolean;
  questionResults?: QuestionResult[];
  /** While expected solutions are still withheld from the student: when they will appear. */
  solutionsAvailableAt?: string | null;
}

export interface Submission {
  id: string;
  studentId: string;
  assignmentId: string;
  submittedAt: string;
  deadline: string;
  state: SubmissionState;
  ocr: OCRResult;
  grading?: GradingResult;
  answer: string;
  fileName?: string;
  /** Raw backend status, e.g. "ocr_processing", "submitted", "under_review", "graded". */
  backendStatus?: string;
  /** Present only when the work was handed in after the due date. */
  late?: LateSubmissionInfo;
}

export type LateDecision = "pending" | "accepted" | "rejected";

export interface LateSubmissionInfo {
  status: LateDecision;
  /** Accepted late work: % deducted from the final score when the grade is published. */
  penaltyPercent: number | null;
  note: string | null;
  decidedAt: string | null;
}

/**
 * Students may replace a submission until grading starts, and not once the teacher has ruled on
 * a late hand-in (matches the backend and DB trigger).
 */
export function canReplaceSubmission(submission: Pick<Submission, "backendStatus" | "late">): boolean {
  if (submission.late && submission.late.status !== "pending") return false;
  const status = submission.backendStatus ?? "submitted";
  return status === "submitted" || status === "late_pending" || status.startsWith("ocr_");
}

/** Student-facing wording for a late submission's state. */
export function describeLate(late: LateSubmissionInfo): string {
  if (late.status === "pending") return "Handed in late · awaiting your teacher's decision";
  if (late.status === "rejected") return "Handed in late · not accepted by your teacher";
  return late.penaltyPercent
    ? `Handed in late · accepted with a ${late.penaltyPercent}% mark deduction`
    : "Handed in late · accepted for full marks";
}

export interface PublishedResult {
  id: string;
  submissionId: string;
  publishedAt: string;
  score: number;
  maximum: number;
  feedback: Feedback;
  questionBreakdown: { question: string; earned: number; maximum: number; reason: string }[];
}

export interface LeaderboardEntry {
  rank: number;
  studentId: string;
  score: number;
  assignmentsCompleted: number;
  trend: "Improving" | "Steady" | "Needs support";
}
