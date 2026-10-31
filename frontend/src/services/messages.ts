import { api } from "./api";

// --------------------------------------------------------------------------
// Student <-> teacher chat (backend/app/api/v1/endpoints/messages.py)
// One private conversation per (course, student) with that course's teacher.
// --------------------------------------------------------------------------

export interface ChatMessage {
  id: string;
  course_id: string;
  student_id: string;
  sender_id: string;
  body: string;
  read_at: string | null;
  /** ISO timestamp from the server; pass it back unchanged as `after` when polling. */
  created_at: string;
  is_mine: boolean;
}

export interface MessageThread {
  course_id: string;
  course_name: string;
  student_id: string;
  student_name: string;
  teacher_id: string;
  teacher_name: string;
  last_message: string;
  last_message_is_mine: boolean;
  last_message_at: string;
  unread_count: number;
}

/** Fired after messages are read or sent, so the sidebar unread badge refreshes right away. */
export const MESSAGES_CHANGED_EVENT = "tg:messages-changed";
const notifyChanged = () => window.dispatchEvent(new Event(MESSAGES_CHANGED_EVENT));

export const MAX_MESSAGE_CHARS = 4000;

export const messageService = {
  /** The signed-in user's conversations, newest first. */
  async listThreads(): Promise<MessageThread[]> {
    const response = await api.get<MessageThread[]>("/messages/threads");
    return response.data || [];
  },

  /** One conversation, oldest first. Teachers pass the student's id; `after` fetches only newer messages. */
  async getMessages(courseId: string, studentId?: string, after?: string): Promise<ChatMessage[]> {
    const params: Record<string, string> = {};
    if (studentId) params.student_id = studentId;
    if (after) params.after = after;
    const response = await api.get<ChatMessage[]>(`/courses/${courseId}/messages`, { params });
    return response.data || [];
  },

  async send(courseId: string, body: string, studentId?: string): Promise<ChatMessage> {
    const response = await api.post<ChatMessage>(`/courses/${courseId}/messages`, {
      body: body.trim(),
      student_id: studentId ?? null,
    });
    notifyChanged();
    return response.data;
  },

  async markRead(courseId: string, studentId?: string): Promise<number> {
    const response = await api.post<{ updated: number }>(`/courses/${courseId}/messages/read`, {
      student_id: studentId ?? null,
    });
    if (response.data.updated > 0) notifyChanged();
    return response.data.updated;
  },
};
