export type UserRole = "teacher" | "student";
export type ProcessingState = "Uploading" | "Processing" | "Ready" | "Needs Review" | "Failed";
export type SubmissionState = "Not Started" | "In Progress" | "Submitted" | "Under Review" | "Graded" | "Late Submission" | "Rejected" | "Published";

export interface User {
  id: string;
  name: string;
  email: string;
  role: UserRole;
  initials: string;
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

export interface CourseMaterial {
  id: string;
  name: string;
  category: "Syllabus" | "Rulebook" | "Lecture slides" | "Notes" | "PDF" | "Reference" | "Rubric";
  size: string;
  uploadedAt: string;
  state: ProcessingState;
  indexing: ProcessingState;
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

export interface GradingResult {
  suggestedScore: number;
  confidence: number;
  reasoning: string;
  rubric: RubricCriterion[];
  feedback: Feedback;
  teacherApproved: boolean;
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
}

/** Students may replace a submission until grading starts (matches the backend and DB policy). */
export function canReplaceSubmission(submission: Pick<Submission, "backendStatus">): boolean {
  const status = submission.backendStatus ?? "submitted";
  return status === "submitted" || status === "late_pending" || status.startsWith("ocr_");
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
