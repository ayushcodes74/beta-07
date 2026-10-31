import axios, { AxiosError } from "axios";
import { getSupabaseClient } from "./supabase";
import type {
  Assignment,
  Course,
  OCRResult,
  Question,
  Submission,
  SubmissionState,
  User,
} from "../types/models";

// Base API Axios instance
export const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || "http://localhost:8000/api/v1",
  timeout: 20000,
  headers: { "Content-Type": "application/json" },
});

// Request interceptor: attach Supabase access token as Bearer
api.interceptors.request.use(async (config) => {
  try {
    const client = getSupabaseClient();
    const { data: { session } } = await client.auth.getSession();
    if (session?.access_token) {
      config.headers.Authorization = `Bearer ${session.access_token}`;
    }
  } catch (err) {
    // Supabase client may not be initialized if env variables are missing
    console.warn("Supabase auth session unavailable for request:", err);
  }
  return config;
});

// Response interceptor: handle 401s and attempt session refresh
api.interceptors.response.use(
  (response) => response,
  async (error: AxiosError) => {
    if (error.response?.status === 401) {
      try {
        const client = getSupabaseClient();
        const { data: { session } } = await client.auth.refreshSession();
        if (session?.access_token && error.config && !(error.config as any)._retry) {
          (error.config as any)._retry = true;
          error.config.headers.Authorization = `Bearer ${session.access_token}`;
          return api(error.config);
        }
      } catch (refreshErr) {
        console.warn("Session refresh failed:", refreshErr);
      }
    }
    return Promise.reject(error);
  }
);

// --------------------------------------------------------------------------
// Backend Response DTOs
// --------------------------------------------------------------------------

export interface BackendUserResponse {
  id: string;
  email: string;
  role: "teacher" | "student";
}

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
    courseId: defaultCourseId,
    title: b.title,
    description: b.instructions || "",
    dueAt: b.due_at,
    totalMarks: Number(b.total_marks),
    state: b.status === "published" ? "Published" : "Draft",
    submissionType,
    questions,
    rubricId: "rubric-ds-code",
  };
}

export function toBackendAssignmentCreate(a: {
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
  else if (b.status === "ocr_completed") state = "Under Review";
  else if (b.status === "ocr_failed") state = "Needs Review" as any;

  let ocrState: OCRResult["state"] = "Verified";
  if (b.status === "ocr_queued" || b.status === "ocr_processing") ocrState = "Needs review";
  else if (b.status === "ocr_degraded") ocrState = "Low confidence";
  else if (b.status === "ocr_failed") ocrState = "Needs review";

  return {
    id: b.submission_id,
    studentId: b.student_id,
    assignmentId: b.assignment_id,
    submittedAt: b.created_at,
    deadline: b.created_at,
    state,
    ocr: {
      confidence: b.ocr_progress ? b.ocr_progress / 100 : 0.85,
      state: ocrState,
      extractedText: b.ocr_stage ? `OCR stage: ${b.ocr_stage} (${b.ocr_progress}%)` : "Processing...",
      warnings: b.warnings ?? [],
      expressions: [],
    },
    answer: "PDF submission received.",
    fileName: fileName || "submission.pdf",
  };
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

async function getTrustedProfile() {
  const client = getSupabaseClient();
  const { data: { session } } = await client.auth.getSession();
  if (!session?.access_token) {
    throw new Error("Sign-in completed without an access token. Please sign in again.");
  }
  const response = await api.get<BackendUserResponse>("/auth/me", {
    headers: { Authorization: `Bearer ${session.access_token}` },
  });
  return {
    ...response.data,
    name:
      session.user.user_metadata?.name ??
      session.user.email?.split("@")[0] ??
      "TrustGrade user",
  };
}

export const authService = {
  async getSession() {
    const client = getSupabaseClient();
    const { data: { session }, error } = await client.auth.getSession();
    if (error || !session) return null;
    return session;
  },

  async getCurrentUser(): Promise<User | null> {
    try {
      const client = getSupabaseClient();
      const { data: { session }, error } = await client.auth.getSession();
      if (error || !session?.access_token) return null;
      const profile = await getTrustedProfile();
      return {
        id: profile.id,
        name: profile.name,
        email: profile.email,
        role: profile.role,
        initials:
          profile.name
            .split(/\s+/)
            .map((part: string) => part[0])
            .slice(0, 2)
            .join("")
            .toUpperCase() || "TG",
      };
    } catch {
      return null;
    }
  },

  async login(email: string, password: string): Promise<User> {
    const client = getSupabaseClient();
    const { error } = await client.auth.signInWithPassword({ email, password });
    if (error) throw error;
    try {
      const profile = await getTrustedProfile();
      return {
        id: profile.id,
        name: profile.name,
        email: profile.email,
        role: profile.role,
        initials:
          profile.name
            .split(/\s+/)
            .map((part: string) => part[0])
            .slice(0, 2)
            .join("")
            .toUpperCase() || "TG",
      };
    } catch (err) {
      await client.auth.signOut();
      throw err;
    }
  },

  async register(name: string, email: string, password: string, role: "teacher" | "student"): Promise<User> {
    const client = getSupabaseClient();
    const { data, error } = await client.auth.signUp({
      email,
      password,
      options: { data: { name, role } },
    });
    if (error) throw error;
    if (!data.session) {
      throw new Error(
        "Check your email to confirm your account, then sign in. Role access is confirmed from your trusted profile."
      );
    }
    const profile = await getTrustedProfile();
    return {
      id: profile.id,
      name: profile.name,
      email: profile.email,
      role: profile.role,
      initials:
        profile.name
          .split(/\s+/)
          .map((part: string) => part[0])
          .slice(0, 2)
          .join("")
          .toUpperCase() || "TG",
    };
  },

  async logout(): Promise<void> {
    const client = getSupabaseClient();
    const { error } = await client.auth.signOut();
    if (error) throw error;
  },
};

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

  async removeStudent(courseId: string, studentId: string): Promise<void> {
    await api.delete(`/courses/${courseId}/enrollments/${studentId}`);
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
  async submitPdf(assignmentId: string, file: File): Promise<Submission> {
    const formData = new FormData();
    formData.append("file", file, file.name);
    const response = await api.post<BackendSubmissionStatus>(
      `/assignments/${assignmentId}/submissions`,
      formData,
      {
        headers: { "Content-Type": "multipart/form-data" },
      }
    );
    return adaptSubmissionStatus(response.data, file.name);
  },

  async getStatus(submissionId: string): Promise<BackendSubmissionStatus> {
    const response = await api.get<BackendSubmissionStatus>(`/submissions/${submissionId}/status`);
    return response.data;
  },

  async getOcrResult(submissionId: string) {
    const response = await api.get(`/submissions/${submissionId}/ocr-result`);
    return response.data;
  },

  async cancelOcrJob(submissionId: string) {
    const response = await api.delete(`/submissions/${submissionId}/ocr-job`);
    return response.data;
  },
};
