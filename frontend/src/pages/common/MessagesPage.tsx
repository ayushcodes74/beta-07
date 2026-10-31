import { useCallback, useEffect, useMemo, useRef, useState, type FormEvent, type KeyboardEvent } from "react";
import { useSearchParams } from "react-router-dom";
import { ArrowLeft, MessageCircle, Plus, RefreshCw, Send } from "lucide-react";
import { useAppState } from "../../App";
import { Avatar, Button, Panel } from "../../components/ui";
import { cn } from "../../lib/utils";
import { courseService, extractErrorMessage, type EnrolledStudentResponse } from "../../services/api";
import { MAX_MESSAGE_CHARS, messageService, type ChatMessage, type MessageThread } from "../../services/messages";
import "./messages.css";

/** How often the open conversation and the inbox check for new messages (only while the tab is visible). */
const CHAT_POLL_MS = 4_000;
const INBOX_POLL_MS = 15_000;

const initialsOf = (name: string) =>
  name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((word) => word[0]?.toUpperCase())
    .join("") || "?";

function formatWhen(iso: string, withDate = false) {
  const date = new Date(iso);
  const sameDay = date.toDateString() === new Date().toDateString();
  const time = date.toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" });
  if (sameDay) return time;
  const day = date.toLocaleDateString(undefined, { month: "short", day: "numeric" });
  return withDate ? `${day}, ${time}` : day;
}

/** One entry in the conversation list (may not have any messages yet). */
interface Conversation {
  key: string;
  courseId: string;
  studentId: string;
  /** Who the signed-in user is talking to. */
  title: string;
  courseName: string;
  preview: string;
  lastAt: string | null;
  unread: number;
}

const keyOf = (courseId: string, studentId: string) => `${courseId}:${studentId}`;

const visible = () => document.visibilityState === "visible";

export function MessagesPage() {
  const { user, courses } = useAppState();
  const isStudent = user?.role === "student";
  const [params, setParams] = useSearchParams();
  const selectedCourse = params.get("course") ?? "";
  // Students always use their own conversation; teachers pick the student.
  const selectedStudent = isStudent ? user?.id ?? "" : params.get("student") ?? "";
  const selectedKey = selectedCourse && selectedStudent ? keyOf(selectedCourse, selectedStudent) : "";

  const [threads, setThreads] = useState<MessageThread[]>([]);
  const [inboxError, setInboxError] = useState("");
  const [inboxLoading, setInboxLoading] = useState(true);

  // Teacher "new message" picker.
  const [composing, setComposing] = useState(false);
  const [pickCourse, setPickCourse] = useState("");
  const [roster, setRoster] = useState<EnrolledStudentResponse[]>([]);
  const [rosterLoading, setRosterLoading] = useState(false);
  const [rosterNames, setRosterNames] = useState<Record<string, string>>({});

  const loadThreads = useCallback(async () => {
    try {
      setThreads(await messageService.listThreads());
      setInboxError("");
    } catch (reason) {
      setInboxError(extractErrorMessage(reason, "Could not load your conversations."));
    } finally {
      setInboxLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadThreads();
    const timer = window.setInterval(() => visible() && void loadThreads(), INBOX_POLL_MS);
    return () => window.clearInterval(timer);
  }, [loadThreads]);

  useEffect(() => {
    if (!composing || !pickCourse) {
      setRoster([]);
      return;
    }
    let active = true;
    setRosterLoading(true);
    courseService
      .getStudents(pickCourse)
      .then((students) => {
        if (!active) return;
        setRoster(students);
        setRosterNames((names) => ({
          ...names,
          ...Object.fromEntries(students.map((s) => [keyOf(pickCourse, s.student_id), s.name || s.email || "Student"])),
        }));
      })
      .catch(() => active && setRoster([]))
      .finally(() => active && setRosterLoading(false));
    return () => {
      active = false;
    };
  }, [composing, pickCourse]);

  // Teacher deep link (e.g. "Message" on the course roster) to a conversation with no messages yet:
  // look the student's name up from the course roster.
  const needsRosterName =
    !isStudent && !!selectedKey && !inboxLoading && !rosterNames[selectedKey] &&
    !threads.some((t) => keyOf(t.course_id, t.student_id) === selectedKey);
  useEffect(() => {
    if (!needsRosterName) return;
    let active = true;
    courseService
      .getStudents(selectedCourse)
      .then((students) => {
        if (!active) return;
        setRosterNames((names) => ({
          ...names,
          ...Object.fromEntries(students.map((s) => [keyOf(selectedCourse, s.student_id), s.name || s.email || "Student"])),
        }));
      })
      .catch(() => undefined);
    return () => {
      active = false;
    };
  }, [needsRosterName, selectedCourse]);

  const conversations = useMemo<Conversation[]>(() => {
    const fromThreads = threads.map<Conversation>((t) => ({
      key: keyOf(t.course_id, t.student_id),
      courseId: t.course_id,
      studentId: t.student_id,
      title: isStudent ? t.teacher_name : t.student_name,
      courseName: t.course_name,
      preview: `${t.last_message_is_mine ? "You: " : ""}${t.last_message}`,
      lastAt: t.last_message_at,
      unread: t.unread_count,
    }));
    const known = new Set(fromThreads.map((c) => c.key));
    const extra: Conversation[] = [];
    if (isStudent && user) {
      // Every enrolled course is a conversation with its teacher, even before the first message.
      for (const course of courses) {
        const key = keyOf(course.id, user.id);
        if (known.has(key)) continue;
        known.add(key);
        extra.push({
          key, courseId: course.id, studentId: user.id, title: course.instructor || "Your teacher",
          courseName: course.name, preview: "No messages yet", lastAt: null, unread: 0,
        });
      }
    }
    if (!isStudent && selectedKey && !known.has(selectedKey)) {
      // A new conversation the teacher just opened from the picker or a deep link.
      extra.push({
        key: selectedKey, courseId: selectedCourse, studentId: selectedStudent,
        title: rosterNames[selectedKey] ?? "Student",
        courseName: courses.find((c) => c.id === selectedCourse)?.name ?? "Course",
        preview: "No messages yet", lastAt: null, unread: 0,
      });
    }
    return [...fromThreads, ...extra];
  }, [threads, courses, isStudent, user, selectedKey, selectedCourse, selectedStudent, rosterNames]);

  const selected = conversations.find((c) => c.key === selectedKey) ?? null;
  const totalUnread = conversations.reduce((sum, c) => sum + c.unread, 0);

  const open = (courseId: string, studentId: string) => {
    const next: Record<string, string> = { course: courseId };
    if (!isStudent) next.student = studentId;
    setParams(next);
    setComposing(false);
  };

  const clearUnread = useCallback((courseId: string, studentId: string) => {
    setThreads((list) =>
      list.map((t) => (t.course_id === courseId && t.student_id === studentId ? { ...t, unread_count: 0 } : t))
    );
  }, []);

  const onSent = useCallback(
    (message: ChatMessage) => {
      setThreads((list) => {
        const index = list.findIndex((t) => t.course_id === message.course_id && t.student_id === message.student_id);
        if (index === -1) {
          void loadThreads(); // first message in this conversation: fetch names etc. from the server
          return list;
        }
        const updated = { ...list[index], last_message: message.body, last_message_is_mine: true, last_message_at: message.created_at };
        return [updated, ...list.filter((_, i) => i !== index)];
      });
    },
    [loadThreads]
  );

  return (
    <>
      <div className="page-heading">
        <div>
          <div className="eyebrow">{isStudent ? "ASK YOUR TEACHER" : "STUDENT CONVERSATIONS"}</div>
          <h1>Messages</h1>
          <p className="page-subtitle">
            {isStudent
              ? "Private conversations with the teacher of each of your courses."
              : "Private conversations with the students in your courses."}
            {totalUnread > 0 && ` ${totalUnread} unread.`}
          </p>
        </div>
        <div className="heading-actions">
          <Button variant="secondary" onClick={() => void loadThreads()}>
            <RefreshCw size={14} />
            Refresh
          </Button>
          {!isStudent && courses.length > 0 && (
            <Button
              onClick={() => {
                setComposing((value) => !value);
                setPickCourse((current) => current || courses[0]?.id || "");
              }}
            >
              <Plus size={14} />
              New message
            </Button>
          )}
        </div>
      </div>

      {courses.length === 0 && conversations.length === 0 ? (
        <Panel className="chat-empty">
          <MessageCircle size={34} />
          <h3>No conversations yet</h3>
          <p>{isStudent ? "Join a course to message its teacher." : "Create a course and enroll students to message them."}</p>
        </Panel>
      ) : (
        <div className={cn("chat-layout", selected && "chat-has-selection")}>
          <Panel className="chat-inbox">
            {composing && (
              <div className="chat-picker">
                <label>
                  <span>Course</span>
                  <select className="field-select" value={pickCourse} onChange={(e) => setPickCourse(e.target.value)}>
                    {courses.map((course) => (
                      <option key={course.id} value={course.id}>{course.name}</option>
                    ))}
                  </select>
                </label>
                {rosterLoading ? (
                  <p className="chat-muted">Loading students…</p>
                ) : roster.length === 0 ? (
                  <p className="chat-muted">No students are enrolled in this course yet.</p>
                ) : (
                  <ul className="chat-picker-list">
                    {roster.map((student) => (
                      <li key={student.student_id}>
                        <button type="button" onClick={() => open(pickCourse, student.student_id)}>
                          <strong>{student.name || "Student"}</strong>
                          {student.email && <small>{student.email}</small>}
                        </button>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            )}
            {inboxError && <p className="chat-error" role="alert">{inboxError}</p>}
            {inboxLoading && conversations.length === 0 ? (
              <p className="chat-muted chat-inbox-note">Loading conversations…</p>
            ) : conversations.length === 0 ? (
              <p className="chat-muted chat-inbox-note">
                No conversations yet. Use “New message” to write to a student.
              </p>
            ) : (
              <ul className="chat-threads" aria-label="Conversations">
                {conversations.map((c) => (
                  <li key={c.key}>
                    <button
                      type="button"
                      className={cn("chat-thread", c.key === selectedKey && "active", c.unread > 0 && "unread")}
                      onClick={() => open(c.courseId, c.studentId)}
                      aria-current={c.key === selectedKey ? "true" : undefined}
                    >
                      <Avatar name={c.title} initials={initialsOf(c.title)} className="chat-avatar" />
                      <span className="chat-thread-copy">
                        <span className="chat-thread-top">
                          <strong>{c.title}</strong>
                          {c.lastAt && <time dateTime={c.lastAt}>{formatWhen(c.lastAt)}</time>}
                        </span>
                        <small className="chat-thread-course">{c.courseName}</small>
                        <span className="chat-thread-preview">{c.preview}</span>
                      </span>
                      {c.unread > 0 && <span className="chat-unread" aria-label={`${c.unread} unread`}>{c.unread}</span>}
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </Panel>

          {selected ? (
            <ChatPane
              key={selected.key}
              conversation={selected}
              studentIdParam={isStudent ? undefined : selected.studentId}
              onBack={() => setParams({})}
              onRead={() => clearUnread(selected.courseId, selected.studentId)}
              onSent={onSent}
            />
          ) : (
            <Panel className="chat-pane chat-pane-empty">
              <MessageCircle size={30} />
              <p>Select a conversation to start chatting.</p>
            </Panel>
          )}
        </div>
      )}
    </>
  );
}

function ChatPane({
  conversation,
  studentIdParam,
  onBack,
  onRead,
  onSent,
}: {
  conversation: Conversation;
  /** Teachers address a student's conversation by id; students omit it. */
  studentIdParam?: string;
  onBack: () => void;
  onRead: () => void;
  onSent: (message: ChatMessage) => void;
}) {
  const { courseId } = conversation;
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [draft, setDraft] = useState("");
  const [sending, setSending] = useState(false);
  const [sendError, setSendError] = useState("");
  const scroller = useRef<HTMLDivElement>(null);
  const stickToBottom = useRef(true);
  const lastAt = useRef<string | undefined>(undefined);

  const merge = useCallback((incoming: ChatMessage[]) => {
    if (incoming.length === 0) return;
    setMessages((current) => {
      const seen = new Set(current.map((m) => m.id));
      const added = incoming.filter((m) => !seen.has(m.id));
      if (added.length === 0) return current;
      // Compare as times, not strings: the server may omit zero fractional seconds.
      const next = [...current, ...added].sort((a, b) => Date.parse(a.created_at) - Date.parse(b.created_at));
      lastAt.current = next[next.length - 1].created_at;
      return next;
    });
  }, []);

  // Initial load, then poll for newer messages while the tab is visible.
  useEffect(() => {
    let active = true;
    const fetchNew = async (initial: boolean) => {
      try {
        const rows = await messageService.getMessages(courseId, studentIdParam, initial ? undefined : lastAt.current);
        if (!active) return;
        merge(rows);
        setError("");
      } catch (reason) {
        if (active && initial) setError(extractErrorMessage(reason, "Could not load this conversation."));
      } finally {
        if (active && initial) setLoading(false);
      }
    };
    void fetchNew(true);
    const timer = window.setInterval(() => visible() && void fetchNew(false), CHAT_POLL_MS);
    return () => {
      active = false;
      window.clearInterval(timer);
    };
  }, [courseId, studentIdParam, merge]);

  // Mark incoming messages as read once they are on screen.
  const hasUnreadIncoming = messages.some((m) => !m.is_mine && !m.read_at);
  useEffect(() => {
    if (!hasUnreadIncoming || !visible()) return;
    const readAt = new Date().toISOString();
    messageService
      .markRead(courseId, studentIdParam)
      .then(() => {
        setMessages((current) => current.map((m) => (!m.is_mine && !m.read_at ? { ...m, read_at: readAt } : m)));
        onRead();
      })
      .catch(() => undefined); // retried on the next new message
  }, [hasUnreadIncoming, courseId, studentIdParam, onRead]);

  // Keep the newest message in view unless the user has scrolled up to read history.
  useEffect(() => {
    const el = scroller.current;
    if (el && stickToBottom.current) el.scrollTop = el.scrollHeight;
  }, [messages]);

  const send = async (event?: FormEvent) => {
    event?.preventDefault();
    const body = draft.trim();
    if (!body || sending) return;
    setSending(true);
    setSendError("");
    try {
      const message = await messageService.send(courseId, body, studentIdParam);
      stickToBottom.current = true;
      merge([message]);
      setDraft("");
      onSent(message);
    } catch (reason) {
      setSendError(extractErrorMessage(reason, "Your message could not be sent."));
    } finally {
      setSending(false);
    }
  };

  const onKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
      event.preventDefault();
      void send();
    }
  };

  return (
    <Panel className="chat-pane">
      <header className="chat-pane-header">
        <button type="button" className="icon-button chat-back" onClick={onBack} aria-label="Back to conversations">
          <ArrowLeft size={16} />
        </button>
        <Avatar name={conversation.title} initials={initialsOf(conversation.title)} className="chat-avatar" />
        <div>
          <strong>{conversation.title}</strong>
          <small>{conversation.courseName}</small>
        </div>
      </header>

      <div
        className="chat-messages"
        ref={scroller}
        role="log"
        aria-live="polite"
        aria-label={`Conversation with ${conversation.title}`}
        onScroll={(event) => {
          const el = event.currentTarget;
          stickToBottom.current = el.scrollHeight - el.scrollTop - el.clientHeight < 60;
        }}
      >
        {loading ? (
          <p className="chat-muted chat-center">Loading messages…</p>
        ) : error ? (
          <p className="chat-error chat-center" role="alert">{error}</p>
        ) : messages.length === 0 ? (
          <p className="chat-muted chat-center">No messages yet. Say hello 👋</p>
        ) : (
          messages.map((message, index) => {
            const previous = messages[index - 1];
            const newDay = !previous || new Date(previous.created_at).toDateString() !== new Date(message.created_at).toDateString();
            return (
              <div key={message.id} className="chat-row-wrap">
                {newDay && (
                  <div className="chat-day">
                    {new Date(message.created_at).toLocaleDateString(undefined, { weekday: "short", month: "short", day: "numeric" })}
                  </div>
                )}
                <div className={cn("chat-row", message.is_mine ? "mine" : "theirs")}>
                  <div className="chat-bubble">
                    <p>{message.body}</p>
                    <time dateTime={message.created_at}>
                      {formatWhen(message.created_at, true)}
                      {message.is_mine && message.read_at && " · Seen"}
                    </time>
                  </div>
                </div>
              </div>
            );
          })
        )}
      </div>

      <form className="chat-composer" onSubmit={(event) => void send(event)}>
        <textarea
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          onKeyDown={onKeyDown}
          placeholder={`Message ${conversation.title}…`}
          aria-label="Message"
          rows={2}
          maxLength={MAX_MESSAGE_CHARS}
          disabled={!!error}
        />
        <Button type="submit" disabled={sending || !draft.trim() || !!error} aria-label="Send message">
          <Send size={15} />
          {sending ? "Sending…" : "Send"}
        </Button>
        {sendError && <span className="chat-error chat-send-error" role="alert">{sendError}</span>}
      </form>
    </Panel>
  );
}
