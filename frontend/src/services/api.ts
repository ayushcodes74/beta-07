import axios from "axios";
import type {
  Assignment,
  Course,
  LateDecision,
  OCRResult,
  Question,
  Submission,
  SubmissionState,
} from "../types/models";

// Base API Axios instance
export const api = axios.create({
  // Relative by default so the Vite dev proxy (vite.config.ts) forwards /api to FastAPI on the same origin,
  // avoiding a cross-origin preflight the backend does not handle. Set VITE_API_BASE_URL to override.
  baseURL: import.meta.env.VITE_API_BASE_URL || "/api/v1",
  timeout: 20000,
  headers: { "Content-Type": "application/json" },
});

api.interceptors.request.use((config) => {
  const token = sessionStorage.getItem("tg_access_token");
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

// --------------------------------------------------------------------------
// Backend Response DTOs
// --------------------------------------------------------------------------

export interface BackendCourse {
  id: string;
  teacher_id?: string;
  name: string;
  description?: string | null;
  created_at?: string;
  code?: string;
  instructor?: string;
  students?: number;
  assignments?: number;
  activity?: number;
  average?: number;
}

export interface BackendMcqOption {
  id: string;
  text: string;
}

export interface BackendQuestion {
  position?: number;
  type: "mcq" | "subjective";
  text: string;
  marks: number | string;
  options?: BackendMcqOption[];
  correct_option_id?: string;
  expected_answer?: string | null;
  instructions?: string | null;
}

export interface BackendAssignment {
  id: string;
  teacher_id?: string;
  course_id?: string | null;
  title: string;
  instructions?: string | null;
  due_at: string;
  total_marks: number | string;
  status?: "draft" | "published";
  questions?: BackendQuestion[];
}

export interface BackendSubmissionStatus {
  submission_id: string;
  assignment_id: string;
  student_id: string;
  status: string;
  ocr_job_id?: string | null;
  ocr_stage?: string | null;
  ocr_progress?: number;
  warnings?: string[];
  error_message?: string | null;
  created_at: string;
  updated_at: string;
  submitted_at?: string | null;
  late_status?: LateDecision | null;
  late_penalty_percent?: number | null;
  late_decision_note?: string | null;
  late_decided_at?: string | null;
}

export interface BackendOCRTextBlock {
  block_id: string;
  sequence: number;
  type: string;
  text: string;
  confidence: number | null;
  bounding_box: { x1: number; y1: number; x2: number; y2: number };
  warnings: string[];
}

export interface BackendOCRPage {
  page_number: number;
  status: string;
  full_text: string;
  text_blocks: BackendOCRTextBlock[];
  warnings: string[];
  math_blocks: Array<{
    recognized_text: string;
    latex: string;
    confidence: number | null;
    requires_manual_review: boolean;
    warnings: string[];
  }>;
}

export interface BackendOCRDocumentResult {
  job_id: string;
  submission_id: string;
  status: string;
  warnings: string[];
  errors: string[];
  processing_summary: {
    total_pages: number;
    processed_pages: number;
    failed_pages: number;
  };
  pages: BackendOCRPage[];
}

export interface BackendQuestionGradeSuggestion {
  number: number;
  question_text: string;
  question_type: string;
  max_marks: number;
  awarded_marks: number;
  explanation: string;
  strengths: string[];
  areas_for_improvement: string[];
  matched_concepts: string[];
  missing_concepts: string[];
  confidence: number | null;
  review_required: boolean;
  review_reasons: string[];
  /** How many earlier teacher corrections of this question the AI was given. */
  teacher_corrections_used?: number;
}

/** A teacher's correction of the AI's grading of one question; reused by future AI checks. */
export interface BackendGradingCorrection {
  question_number: number;
  question_text: string;
  max_marks: number;
  ai_marks: number | null;
  ai_explanation: string;
  teacher_marks: number;
  note: string;
  teacher_id: string | null;
  created_at: string | null;
}

export interface BackendGradingSuggestion {
  submission_id: string;
  assignment_id: string;
  total_awarded_marks: number;
  total_max_marks: number;
  percentage: number;
  overall_feedback: string;
  review_required: boolean;
  review_reasons: string[];
  questions: BackendQuestionGradeSuggestion[];
  ocr_confidence: number | null;
  graded_at: string;
  saved: boolean;
  status: string;
  teacher_corrections?: BackendGradingCorrection[];
}

export interface BackendPublishedGrade {
  submission_id: string;
  final_score: number;
  max_score: number | null;
  final_feedback: string;
  status: string;
  reviewed_at: string | null;
  published_at: string | null;
  late_penalty_percent?: number | null;
  score_before_late_penalty?: number | null;
  questions?: BackendPublishedQuestion[];
  solutions_available_at?: string | null;
}

export interface BackendPublishedQuestion {
  number: number;
  question_text: string;
  awarded_marks: number | null;
  max_marks: number;
  explanation: string;
  strengths: string[];
  areas_for_improvement: string[];
  teacher_comment: string | null;
  expected_solution?: string | null;
}

/** Attach a published grade to a submission so result views can render it. */
export function withPublishedGrade(submission: Submission, grade: BackendPublishedGrade): Submission {
  return {
    ...submission,
    state: "Published",
    backendStatus: "published",
    grading: {
      suggestedScore: grade.final_score,
      confidence: 1,
      reasoning: grade.final_feedback,
      rubric: [],
      feedback: { id: grade.submission_id, comment: grade.final_feedback, deductions: [], courseReferences: [] },
      teacherApproved: true,
      questionResults: (grade.questions ?? []).map((q) => ({
        number: q.number,
        questionText: q.question_text,
        awardedMarks: q.awarded_marks,
        maxMarks: q.max_marks,
        explanation: q.explanation,
        strengths: q.strengths ?? [],
        areasForImprovement: q.areas_for_improvement ?? [],
        teacherComment: q.teacher_comment,
        expectedSolution: q.expected_solution ?? null,
      })),
      solutionsAvailableAt: grade.solutions_available_at ?? null,
    },
  };
}

export interface BackendOCRProcessingStatus {
  job_id: string;
  status: string;
  stage: string;
  progress: number;
  message: string;
}

export interface BackendOCRRegionReference {
  page_number: number;
  region_id: string | null;
  bounding_box: { x1: number; y1: number; x2: number; y2: number } | null;
  confidence: number | null;
  original_text: string;
}

export interface BackendIntegrityEvidence {
  submission_id: string;
  answer_id: string;
  source_submission_id: string;
  source_answer_id: string;
  source_type: "same_assignment_submission";
  source_reference: string;
  current_passage: string;
  source_passage: string;
  exact_match_score: number;
  semantic_similarity_score: number | null;
  current_regions: BackendOCRRegionReference[];
  source_regions: BackendOCRRegionReference[];
  method: "normalized_token_sequence";
  ocr_uncertain: boolean;
  context_note: string | null;
  detected_at: string;
}

export interface BackendHandwritingSample {
  page_number: number;
  text: string;
  /** PNG data URL of the handwritten line */
  image: string;
}

export interface BackendHandwritingFlag {
  label: string;
  page_numbers: number[];
  compared_with: string;
  difference_score: number;
  p_value: number | null;
  samples: BackendHandwritingSample[];
  reference_samples: BackendHandwritingSample[];
}

export interface BackendIntegrityReport {
  submission_id: string;
  review_status: "processing" | "needs_teacher_review" | "no_matches";
  comparison_scope: "same_assignment";
  comparisons_completed: number;
  comparisons_skipped: number;
  comparison_complete: boolean;
  exact_matching: "normalized_token_sequence";
  semantic_similarity: "unavailable";
  /** Teacher-only, unvalidated within-submission handwriting consistency check. Never shown to students. */
  handwriting_analysis: {
    status: "unavailable" | "processing" | "insufficient_handwriting" | "consistent" | "possible_different_handwriting";
    method: string | null;
    validated: false;
    calibrated_score: null;
    model_name: null;
    model_version: string | null;
    reason: string | null;
    threshold: number | null;
    lines_analyzed: number | null;
    flagged: BackendHandwritingFlag[];
    segments: {
      label: string;
      kind: string;
      page_numbers: number[];
      line_count: number;
      difference_score: number | null;
      p_value: number | null;
      flagged: boolean;
    }[];
    limitations: string | null;
  };
  ocr_quality: {
    mean_confidence: number | null;
    low_confidence_regions: BackendOCRRegionReference[];
    unreadable_pages: number[];
    missing_pages: number[];
  };
  evidence: BackendIntegrityEvidence[];
  notes: string[];
}

export interface EnrolledStudentResponse {
  student_id: string;
  name: string | null;
  email: string | null;
  status: string;
  enrolled_at: string;
}

// --------------------------------------------------------------------------
// Adapters: Backend DTOs -> Frontend Domain Models
// --------------------------------------------------------------------------

export function adaptCourse(b: BackendCourse): Course {
  return {
    id: b.id,
    name: b.name,
    code: b.code || "CRS",
    instructor: b.instructor || "Faculty",
    students: b.students ?? 0,
    assignments: b.assignments ?? 0,
    activity: b.activity ?? 0,
    average: b.average ?? 0,
  };
}

export function adaptAssignment(b: BackendAssignment, defaultCourseId: string = ""): Assignment {
  const questions: Question[] = (b.questions || []).map((q, idx) => {
    const isMcq = q.type === "mcq";
    const options = isMcq && q.options ? q.options.map((opt) => opt.text) : undefined;
    let correctOption: number | undefined;
    if (isMcq && q.options && q.correct_option_id) {
      const foundIdx = q.options.findIndex((opt) => opt.id === q.correct_option_id);
      correctOption = foundIdx >= 0 ? foundIdx : 0;
    }
    return {
      id: `q-${idx + 1}`,
      prompt: q.text,
      type: isMcq ? "MCQ" : "Subjective",
      marks: Number(q.marks),
      expectedAnswer: q.expected_answer || "",
      options,
      correctOption,
    };
  });

  const questionTypes = new Set(questions.map((q) => q.type));
  const submissionType: "PDF" | "MCQ" | "Mixed" =
    questionTypes.size > 1 ? "Mixed" : questionTypes.has("MCQ") ? "MCQ" : "PDF";

  return {
    id: b.id,
    courseId: b.course_id || defaultCourseId,
    title: b.title,
    description: b.instructions || "",
    dueAt: b.due_at,
    totalMarks: Number(b.total_marks),
    // Student responses (AssignmentStudentResponse) omit `status`: the API only ever returns
    // published assignments to students. Teacher responses always include it.
    state: (b.status ?? "published") === "published" ? "Published" : "Draft",
    submissionType,
    questions,
    rubricId: "rubric-ds-code",
  };
}

export function toBackendAssignmentCreate(a: {
  courseId?: string;
  title: string;
  description?: string;
  dueAt: string;
  totalMarks: number;
  questions: Question[];
}) {
  const backendQuestions = a.questions.map((q) => {
    if (q.type === "MCQ") {
      const rawOptions = q.options && q.options.length >= 2 ? q.options : ["Option A", "Option B"];
      const opts = rawOptions.map((text, oIdx) => ({
        id: String.fromCharCode(65 + oIdx),
        text: text.trim() || `Option ${String.fromCharCode(65 + oIdx)}`,
      }));
      const correctIdx = Math.min(Math.max(0, q.correctOption ?? 0), opts.length - 1);
      return {
        type: "mcq" as const,
        text: q.prompt.trim() || "Multiple Choice Question",
        marks: Number(q.marks) || 1,
        options: opts,
        correct_option_id: opts[correctIdx].id,
      };
    } else {
      return {
        type: "subjective" as const,
        text: q.prompt.trim() || "Subjective Question",
        marks: Number(q.marks) || 1,
        instructions: null,
        expected_answer: q.expectedAnswer ? q.expectedAnswer.trim() : null,
      };
    }
  });

  const dueDateTime = new Date(a.dueAt);
  const validDueAt = Number.isNaN(dueDateTime.getTime())
    ? new Date(Date.now() + 7 * 24 * 3600 * 1000).toISOString()
    : dueDateTime.toISOString();

  return {
    course_id: a.courseId || null,
    title: a.title.trim(),
    instructions: a.description ? a.description.trim() : null,
    due_at: validDueAt,
    total_marks: Number(a.totalMarks) || 1,
    questions: backendQuestions,
  };
}

export function adaptSubmissionStatus(b: BackendSubmissionStatus, fileName?: string): Submission {
  let state: SubmissionState = "Submitted";
  if (b.status === "submitted" || b.status === "ocr_queued") state = "Submitted";
  else if (b.status === "ocr_processing") state = "In Progress";
  else if (b.status.startsWith("ocr_completed") || ["ocr_failed", "ocr_degraded", "ocr_cancelled", "under_review"].includes(b.status)) state = "Under Review";
  else if (b.status === "graded") state = "Graded";
  else if (b.status === "published") state = "Published";

  let ocrState: OCRResult["state"] = "Needs review";
  if (b.status === "ocr_queued" || b.status === "ocr_processing") ocrState = "Needs review";
  else if (b.status === "ocr_degraded") ocrState = "Low confidence";
  else if (b.status === "ocr_failed") ocrState = "Needs review";

  return {
    id: b.submission_id,
    studentId: b.student_id,
    assignmentId: b.assignment_id,
    submittedAt: b.submitted_at || b.created_at,
    deadline: b.created_at,
    state,
    ocr: {
      confidence: null,
      state: ocrState,
      extractedText: "",
      warnings: b.warnings ?? [],
      expressions: [],
    },
    answer: "",
    fileName: fileName || "submission.pdf",
    backendStatus: b.status,
    late: b.late_status
      ? {
          status: b.late_status,
          penaltyPercent: b.late_penalty_percent ?? null,
          note: b.late_decision_note ?? null,
          decidedAt: b.late_decided_at ?? null,
        }
      : undefined,
  };
}

/** Final score after a late-submission deduction (mirrors the backend's late_adjusted_score). */
export function lateAdjustedScore(score: number, penaltyPercent: number | null | undefined): number {
  if (!penaltyPercent) return Math.round(score * 100) / 100;
  return Math.round(score * (1 - penaltyPercent / 100) * 100) / 100;
}

export function extractErrorMessage(error: unknown, fallback: string = "An error occurred."): string {
  if (axios.isAxiosError(error)) {
    const detail = error.response?.data?.detail;
    if (typeof detail === "string") return detail;
    if (detail && typeof detail === "object" && "message" in detail) {
      return String(detail.message);
    }
    if (error.response?.data?.message) return String(error.response.data.message);
    if (error.message) return error.message;
  }
  if (error instanceof Error) return error.message;
  return fallback;
}

// --------------------------------------------------------------------------
// Centralized Services
// --------------------------------------------------------------------------

export const courseService = {
  async getCourses(): Promise<Course[]> {
    const response = await api.get<BackendCourse[]>("/courses");
    return (response.data || []).map(adaptCourse);
  },

  async getCourse(id: string): Promise<Course> {
    const response = await api.get<BackendCourse>(`/courses/${id}`);
    return adaptCourse(response.data);
  },

  async createCourse(payload: { name: string; description?: string }): Promise<Course> {
    const response = await api.post<BackendCourse>("/courses", payload);
    return adaptCourse(response.data);
  },

  async getStudents(courseId: string): Promise<EnrolledStudentResponse[]> {
    const response = await api.get<EnrolledStudentResponse[]>(`/courses/${courseId}/students`);
    return response.data || [];
  },

  async enrollStudent(courseId: string, studentId: string) {
    const response = await api.post(`/courses/${courseId}/enrollments`, { student_id: studentId });
    return response.data;
  },

  async enrollStudentByEmail(courseId: string, email: string) {
    const response = await api.post(`/courses/${courseId}/enrollments/by-email`, { email: email.trim() });
    return response.data;
  },

  async removeStudent(courseId: string, studentId: string): Promise<void> {
    await api.delete(`/courses/${courseId}/enrollments/${studentId}`);
  },
};

// AI-assisted drafting (POST /assignments/generate-ai). Suggestions only; nothing is saved.
export interface AssignmentGenerationRequest {
  topic: string;
  instructions?: string;
  questionCount: number;
  questionFormat: "mixed" | "subjective" | "mcq";
  difficulty: "easy" | "medium" | "hard" | "mixed";
  totalMarks: number;
  /** Course material attached in the editor (extracted file text + pasted notes). Not stored. */
  courseMaterial?: string;
  /** Syllabus and/or rulebook: questions stay within its scope and follow its rules. Not stored. */
  syllabus?: string;
}

/** Must match MAX_SYLLABUS_CHARS in backend/app/schemas/ai_generation.py. */
export const MAX_SYLLABUS_CHARS = 50_000;

/** Must match MAX_MATERIAL_CHARS in backend/app/services/course_material_service.py. */
export const MAX_COURSE_MATERIAL_CHARS = 100_000;

export interface ExtractedCourseMaterial {
  filename: string;
  text: string;
  characters: number;
  truncated: boolean;
  pages: number | null;
}

interface BackendGeneratedQuestion {
  type: "mcq" | "subjective";
  text: string;
  marks: number;
  expected_answer: string;
  options?: string[] | null;
  correct_option_index?: number | null;
}

interface BackendGeneratedDraft {
  title: string;
  instructions?: string | null;
  questions: BackendGeneratedQuestion[];
  grounded_in_course_materials: boolean;
}

export interface GeneratedAssignmentDraft {
  title: string;
  instructions: string;
  questions: Question[];
  groundedInCourseMaterials: boolean;
}

// Generation makes several sequential LLM calls; allow well beyond the default 20s timeout.
const AI_GENERATION_TIMEOUT_MS = 240_000;

export const aiAssignmentService = {
  /** Upload a course-material file (PDF/DOCX/PPTX/TXT) and get its text back. Nothing is stored. */
  async extractCourseMaterial(file: File): Promise<ExtractedCourseMaterial> {
    const formData = new FormData();
    formData.append("file", file);
    const response = await api.post<ExtractedCourseMaterial>("/assignments/materials/extract", formData, {
      headers: { "Content-Type": "multipart/form-data" },
      timeout: 120_000,
    });
    return response.data;
  },

  async generateDraft(request: AssignmentGenerationRequest): Promise<GeneratedAssignmentDraft> {
    const response = await api.post<BackendGeneratedDraft>(
      "/assignments/generate-ai",
      {
        topic: request.topic,
        instructions: request.instructions || undefined,
        question_count: request.questionCount,
        question_format: request.questionFormat,
        difficulty: request.difficulty,
        total_marks: request.totalMarks,
        course_material: request.courseMaterial?.trim() || undefined,
        syllabus: request.syllabus?.trim() || undefined,
      },
      { timeout: AI_GENERATION_TIMEOUT_MS }
    );
    return {
      title: response.data.title,
      instructions: response.data.instructions ?? "",
      groundedInCourseMaterials: response.data.grounded_in_course_materials,
      questions: response.data.questions.map((q) => ({
        id: crypto.randomUUID(),
        prompt: q.text,
        type: q.type === "mcq" ? "MCQ" : "Subjective",
        marks: q.marks,
        expectedAnswer: q.expected_answer,
        ...(q.type === "mcq" && q.options
          ? { options: q.options, correctOption: q.correct_option_index ?? 0 }
          : {}),
      })),
    };
  },
};

export const assignmentService = {
  async getAssignments(): Promise<Assignment[]> {
    const response = await api.get<BackendAssignment[]>("/assignments");
    return (response.data || []).map((item) => adaptAssignment(item));
  },

  async getAssignment(id: string): Promise<Assignment> {
    const response = await api.get<BackendAssignment>(`/assignments/${id}`);
    return adaptAssignment(response.data);
  },

  async createAssignment(assignment: {
    courseId?: string;
    title: string;
    description?: string;
    dueAt: string;
    totalMarks: number;
    questions: Question[];
  }): Promise<Assignment> {
    const payload = toBackendAssignmentCreate(assignment);
    const response = await api.post<BackendAssignment>("/assignments", payload);
    return adaptAssignment(response.data);
  },

  /**
   * Edit an existing assignment (draft or published). Course cannot be changed. Pass
   * `dueAt` only when it changed: the API rejects past deadlines, so re-sending an
   * already-passed due date would block edits to an overdue assignment.
   */
  async updateAssignment(
    id: string,
    assignment: {
      title: string;
      description?: string;
      dueAt?: string;
      totalMarks: number;
      questions: Question[];
    }
  ): Promise<Assignment> {
    const full = toBackendAssignmentCreate({ ...assignment, dueAt: assignment.dueAt ?? "" });
    const payload: Record<string, unknown> = {
      title: full.title,
      instructions: full.instructions,
      total_marks: full.total_marks,
      questions: full.questions,
    };
    if (assignment.dueAt) payload.due_at = full.due_at;
    const response = await api.patch<BackendAssignment>(`/assignments/${id}`, payload);
    return adaptAssignment(response.data);
  },

  async publishAssignment(id: string): Promise<Assignment> {
    const response = await api.post<BackendAssignment>(`/assignments/${id}/publish`);
    return adaptAssignment(response.data);
  },

  async unpublishAssignment(id: string): Promise<Assignment> {
    const response = await api.post<BackendAssignment>(`/assignments/${id}/unpublish`);
    return adaptAssignment(response.data);
  },

  async deleteAssignment(id: string): Promise<void> {
    await api.delete(`/assignments/${id}`);
  },
};

export const submissionService = {
  async getSubmissions(): Promise<Submission[]> {
    // Published grades live in grading_results: fetch them all in ONE request, in parallel with the
    // submission list (previously one /result request per published submission, after the list).
    const [response, grades] = await Promise.all([
      api.get<BackendSubmissionStatus[]>("/submissions"),
      submissionService.getPublishedResults().catch(() => [] as BackendPublishedGrade[]),
    ]);
    const bySubmission = new Map(grades.map((grade) => [grade.submission_id, grade]));
    return (response.data || []).map((item) => {
      const row = adaptSubmissionStatus(item);
      const grade = row.backendStatus === "published" ? bySubmission.get(row.id) : undefined;
      return grade ? withPublishedGrade(row, grade) : row;
    });
  },

  /** Every published grade the caller may see (student: own; teacher: own assignments). */
  async getPublishedResults(): Promise<BackendPublishedGrade[]> {
    const response = await api.get<BackendPublishedGrade[]>("/results");
    return response.data || [];
  },

  async submitPdf(assignmentId: string, file: File): Promise<Submission> {
    const formData = new FormData();
    formData.append("file", file, file.name);
    const response = await api.post<BackendSubmissionStatus>(
      `/assignments/${assignmentId}/submissions`,
      formData,
      {
        headers: { "Content-Type": "multipart/form-data" },
        // Uploading up to 20 MB and handing it to the OCR engine (which renders every page)
        // can exceed the default 20s on a busy machine; the backend saves it regardless.
        timeout: 120_000,
      }
    );
    return adaptSubmissionStatus(response.data, file.name);
  },

  async getStatus(submissionId: string): Promise<BackendSubmissionStatus> {
    const response = await api.get<BackendSubmissionStatus>(`/submissions/${submissionId}/status`);
    return response.data;
  },

  async getOcrResult(
    submissionId: string
  ): Promise<BackendOCRDocumentResult | BackendOCRProcessingStatus> {
    const response = await api.get<BackendOCRDocumentResult | BackendOCRProcessingStatus>(
      `/submissions/${submissionId}/ocr-result`
    );
    return response.data;
  },

  async getIntegrity(submissionId: string): Promise<BackendIntegrityReport> {
    const response = await api.get<BackendIntegrityReport>(`/submissions/${submissionId}/integrity`);
    return response.data;
  },

  /** Teacher: AI answer check of the OCR text against the answer keys (one LLM call per question). */
  async checkAnswers(submissionId: string): Promise<BackendGradingSuggestion> {
    const response = await api.post<BackendGradingSuggestion>(`/submissions/${submissionId}/grade`, undefined, {
      timeout: AI_GENERATION_TIMEOUT_MS,
    });
    return response.data;
  },

  /** Teacher: last stored AI answer check, or null if none has been run yet. */
  async getAnswerCheck(submissionId: string): Promise<BackendGradingSuggestion | null> {
    try {
      const response = await api.get<BackendGradingSuggestion>(`/submissions/${submissionId}/grading`);
      return response.data;
    } catch (error) {
      if (axios.isAxiosError(error) && error.response?.status === 404) return null;
      throw error;
    }
  },

  /** Teacher: replace this submission's corrections of the AI check (empty list removes them). */
  async saveCorrections(
    submissionId: string,
    corrections: { question_number: number; teacher_marks: number; note: string }[]
  ): Promise<BackendGradingCorrection[]> {
    const response = await api.put<BackendGradingCorrection[]>(`/submissions/${submissionId}/grading/corrections`, {
      corrections,
    });
    return response.data;
  },

  /** Teacher: approve the final score/feedback and publish it to the student. */
  async publishGrade(
    submissionId: string,
    finalScore: number,
    finalFeedback: string,
    showSolutions = true
  ): Promise<BackendPublishedGrade> {
    const response = await api.post<BackendPublishedGrade>(`/submissions/${submissionId}/grading/publish`, {
      final_score: finalScore,
      final_feedback: finalFeedback,
      show_solutions: showSolutions,
    });
    return response.data;
  },

  /**
   * Owning teacher rules on a late submission. `accepted` deducts `penaltyPercent` (50 = half marks)
   * from the final score when the grade is published; `rejected` blocks publishing; `pending` undoes.
   */
  async decideLateSubmission(
    submissionId: string,
    decision: LateDecision,
    penaltyPercent = 0,
    note = ""
  ): Promise<Submission> {
    const response = await api.post<BackendSubmissionStatus>(`/submissions/${submissionId}/late-decision`, {
      decision,
      penalty_percent: penaltyPercent,
      note,
    });
    return adaptSubmissionStatus(response.data);
  },

  /** Student (own) or owning teacher: the published grade, or null if not published yet. */
  async getPublishedResult(submissionId: string): Promise<BackendPublishedGrade | null> {
    try {
      const response = await api.get<BackendPublishedGrade>(`/submissions/${submissionId}/result`);
      return response.data;
    } catch (error) {
      if (axios.isAxiosError(error) && error.response?.status === 404) return null;
      throw error;
    }
  },

  async cancelOcrJob(submissionId: string) {
    const response = await api.delete(`/submissions/${submissionId}/ocr-job`);
    return response.data;
  },
};

// --------------------------------------------------------------------------
// Review queue (teacher) and review requests (student re-evaluation)
// --------------------------------------------------------------------------

export type ReviewRequestStatus = "open" | "resolved" | "dismissed";

export interface ReviewRequest {
  id: string;
  submission_id: string;
  student_id: string;
  reason: string;
  status: ReviewRequestStatus;
  teacher_response: string | null;
  resolved_by: string | null;
  resolved_at: string | null;
  created_at: string;
  updated_at: string;
}

export type ReviewCategory = "ocr" | "low_trust" | "student_request";

export interface ReviewQueueItem {
  category: ReviewCategory;
  submission_id: string;
  assignment_id: string;
  student_id: string;
  submission_status: string;
  submitted_at: string;
  reasons: string[];
  /** Mean OCR text-block confidence, 0-1. */
  ocr_confidence: number | null;
  /** AI answer-check confidence, 0-1. */
  trust_score: number | null;
  ai_score: number | null;
  final_score: number | null;
  max_score: number | null;
  grading_status: string | null;
  review_request: ReviewRequest | null;
}

export interface ReviewQueue {
  ocr: ReviewQueueItem[];
  low_trust: ReviewQueueItem[];
  student_requests: ReviewQueueItem[];
  thresholds: { ocr_confidence: number; trust_score: number };
  /** Parts of the queue that could not be checked (e.g. OCR engine offline). */
  notes: string[];
}

export const reviewService = {
  /** Teacher: everything that needs manual review, grouped into OCR / low trust / student requests. */
  async getQueue(): Promise<ReviewQueue> {
    // Checks OCR results for every unpublished submission, so allow longer than the default.
    const response = await api.get<ReviewQueue>("/reviews/queue", { timeout: 60_000 });
    return response.data;
  },

  /** Student: own requests. Teacher: requests on own assignments. */
  async listRequests(): Promise<ReviewRequest[]> {
    const response = await api.get<ReviewRequest[]>("/review-requests");
    return response.data || [];
  },

  /** Student: flag a published grade for teacher review. */
  async requestReview(submissionId: string, reason: string): Promise<ReviewRequest> {
    const response = await api.post<ReviewRequest>(`/submissions/${submissionId}/review-requests`, {
      reason: reason.trim(),
    });
    return response.data;
  },

  /** Teacher: close a student's request with an optional reply the student can read. */
  async resolveRequest(
    requestId: string,
    status: "resolved" | "dismissed",
    teacherResponse?: string
  ): Promise<ReviewRequest> {
    const response = await api.patch<ReviewRequest>(`/review-requests/${requestId}`, {
      status,
      teacher_response: teacherResponse?.trim() || null,
    });
    return response.data;
  },
};

// --------------------------------------------------------------------------
// Course leaderboard (GET /courses/{id}/leaderboard): total marks from published grades
// --------------------------------------------------------------------------

export interface LeaderboardStanding {
  /** Ties share a rank (1, 2, 2, 4). */
  rank: number;
  student_id: string;
  name: string;
  total_score: number;
  /** total_score / total_possible * 100; null while nothing is published. */
  percentage: number | null;
  assignments_graded: number;
  last_published_at: string | null;
  /** The signed-in student's own row. */
  is_you: boolean;
}

export interface CourseLeaderboard {
  course_id: string;
  course_name: string;
  total_possible: number;
  assignments_counted: number;
  entries: LeaderboardStanding[];
}

export const leaderboardService = {
  async getCourseLeaderboard(courseId: string): Promise<CourseLeaderboard> {
    const response = await api.get<CourseLeaderboard>(`/courses/${courseId}/leaderboard`);
    return response.data;
  },
};
