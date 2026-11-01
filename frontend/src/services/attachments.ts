import { api } from "./api";

// --------------------------------------------------------------------------
// Files attached to assignment questions (backend/app/api/v1/endpoints/attachments.py)
// --------------------------------------------------------------------------

export interface QuestionAttachment {
  id: string;
  assignment_id: string;
  /** 1-based question the file belongs to. */
  question_number: number;
  filename: string;
  content_type: "application/pdf" | "image/png" | "image/jpeg" | "image/webp" | string;
  size_bytes: number;
  /** Short-lived signed URL (about 15 minutes); null if it could not be created. */
  url: string | null;
  /** Text extraction for AI grading. */
  extraction_status: "pending" | "ready" | "no_text" | "failed";
  /** Teacher only: start of the text the AI will see for this file. */
  text_preview: string | null;
  created_at: string;
}

export const ATTACHMENT_TYPES = ["application/pdf", "image/png", "image/jpeg", "image/webp"];
export const ATTACHMENT_ACCEPT = ".pdf,.png,.jpg,.jpeg,.webp,application/pdf,image/png,image/jpeg,image/webp";
export const MAX_ATTACHMENT_BYTES = 10 * 1024 * 1024;
export const MAX_ATTACHMENTS_PER_QUESTION = 5;

export const isImage = (contentType: string) => contentType.startsWith("image/");

export function formatBytes(bytes: number) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export const attachmentService = {
  async list(assignmentId: string): Promise<QuestionAttachment[]> {
    const response = await api.get<QuestionAttachment[]>(`/assignments/${assignmentId}/attachments`);
    return response.data || [];
  },

  async upload(assignmentId: string, questionNumber: number, file: File): Promise<QuestionAttachment> {
    const form = new FormData();
    form.append("file", file, file.name);
    const response = await api.post<QuestionAttachment>(
      `/assignments/${assignmentId}/questions/${questionNumber}/attachments`,
      form,
      { headers: { "Content-Type": "multipart/form-data" }, timeout: 120_000 }
    );
    return response.data;
  },

  async move(assignmentId: string, attachmentId: string, questionNumber: number): Promise<void> {
    await api.patch(`/assignments/${assignmentId}/attachments/${attachmentId}`, { question_number: questionNumber });
  },

  async remove(assignmentId: string, attachmentId: string): Promise<void> {
    await api.delete(`/assignments/${assignmentId}/attachments/${attachmentId}`);
  },
};
