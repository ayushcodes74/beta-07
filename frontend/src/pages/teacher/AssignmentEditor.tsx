import { useEffect, useRef, useState, type Dispatch, type DragEvent, type SetStateAction } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";
import { ChevronLeft, FileText, Paperclip, Plus, Save, Sparkles, Upload, X } from "lucide-react";
import { useAppState } from "../../App";
import { IntegrationNotice } from "../../components/common/IntegrationNotice";
import {
  MAX_COURSE_MATERIAL_CHARS,
  aiAssignmentService,
  assignmentService,
  extractErrorMessage,
  type ExtractedCourseMaterial,
} from "../../services/api";
import { Badge, Button, Panel, StatusBadge, useToast } from "../../components/ui";
import type { Assignment, Course, Question } from "../../types/models";

function QuestionEditor({
  question,
  index,
  onChange,
  onDelete,
  onMove,
}: {
  question: Question;
  index: number;
  onChange: (patch: Partial<Question>) => void;
  onDelete: () => void;
  onMove: () => void;
}) {
  return (
    <article className="question-card">
      <div className="question-head">
        <div className="question-label">
          <span className="question-number">{index + 1}</span>
          Question {index + 1}
          <Badge tone="sage">{question.type}</Badge>
        </div>
        <div className="question-tools">
          <button className="icon-button" aria-label="Move question up" onClick={onMove}>
            <ChevronLeft size={14} />
          </button>
          <button className="icon-button" aria-label="Delete question" onClick={onDelete}>
            <X size={14} />
          </button>
        </div>
      </div>
      <div className="question-two-col">
        <div className="field-block">
          <label>Question prompt</label>
          <textarea
            className="field-textarea"
            value={question.prompt}
            onChange={(event) => onChange({ prompt: event.target.value })}
            placeholder="Write your question..."
          />
        </div>
        <div className="field-block">
          <label>Type · marks</label>
          <select
            className="field-select"
            value={question.type}
            onChange={(event) => onChange({ type: event.target.value as Question["type"] })}
          >
            <option value="Subjective">Subjective</option>
            <option value="MCQ">MCQ</option>
          </select>
          <input
            className="field-input question-mark-input"
            type="number"
            min={1}
            value={question.marks}
            onChange={(event) => onChange({ marks: Number(event.target.value) })}
            aria-label={`Marks for question ${index + 1}`}
          />
        </div>
      </div>
      <div className="field-block expected-answer">
        <label>
          {question.type === "MCQ" ? "Correct answer" : "Expected answer / marking guidance"}
        </label>
        <textarea
          className="field-textarea"
          value={question.expectedAnswer}
          onChange={(event) => onChange({ expectedAnswer: event.target.value })}
          placeholder="Provide expected reasoning, rubrics guidelines, and key concepts."
        />
      </div>
      {question.type === "MCQ" && (
        <div className="mcq-options">
          {(question.options ?? ["Option A", "Option B", "Option C", "Option D"]).map((option, optionIndex) => (
            <label key={optionIndex}>
              <input
                type="radio"
                name={`correct-${question.id}`}
                checked={(question.correctOption ?? 0) === optionIndex}
                onChange={() => onChange({ correctOption: optionIndex })}
              />
              <input
                value={option}
                onChange={(event) =>
                  onChange({
                    options: (question.options ?? ["Option A", "Option B", "Option C", "Option D"]).map(
                      (item, current) => (current === optionIndex ? event.target.value : item)
                    ),
                  })
                }
                aria-label={`Option ${optionIndex + 1}`}
              />
            </label>
          ))}
        </div>
      )}
    </article>
  );
}

const MATERIAL_EXTENSIONS = ["pdf", "docx", "pptx", "txt", "md"];
const MAX_MATERIAL_FILE_BYTES = 25 * 1024 * 1024;

type AttachedMaterial = ExtractedCourseMaterial & { id: string };

/** Combine attached files and pasted notes into the single text block sent to the AI. */
function combineCourseMaterial(materials: AttachedMaterial[], pastedNotes: string): string {
  const parts = materials.map((m) => `### Source: ${m.filename}\n${m.text}`);
  if (pastedNotes.trim()) parts.push(`### Teacher notes\n${pastedNotes.trim()}`);
  return parts.join("\n\n");
}

/** ISO timestamp -> value for an <input type="datetime-local"> in the browser's timezone. */
function toLocalInputValue(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.valueOf())) return "";
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

export function AssignmentEditor({
  courses: courseList,
  setAssignments,
}: {
  courses: Course[];
  assignments: Assignment[];
  setAssignments: Dispatch<SetStateAction<Assignment[]>>;
}) {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const { assignmentId } = useParams();
  const { submissions } = useAppState();
  const toast = useToast();
  // Edit mode: the assignment being edited (draft or published), once loaded.
  const [editing, setEditing] = useState<Assignment | null>(null);
  const [loadingExisting, setLoadingExisting] = useState(Boolean(assignmentId));
  const [originalDueAt, setOriginalDueAt] = useState("");
  const [questions, setQuestions] = useState<Question[]>([
    { id: crypto.randomUUID(), prompt: "", type: "Subjective", marks: 5, expectedAnswer: "" },
  ]);
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [dueAt, setDueAt] = useState("2026-11-15T23:59");
  const [difficulty, setDifficulty] = useState("Mixed");
  const [count, setCount] = useState("3");
  const [type, setType] = useState<"Subjective" | "MCQ" | "Mixed">("Mixed");
  const [topic, setTopic] = useState("");
  const [aiTotalMarks, setAiTotalMarks] = useState("20");
  const [generating, setGenerating] = useState(false);
  const [saving, setSaving] = useState(false);
  const [courseId, setCourseId] = useState(searchParams.get("courseId") ?? courseList[0]?.id ?? "");
  // Course material is attached here, while creating the assignment, and only used for AI drafting.
  const [materials, setMaterials] = useState<AttachedMaterial[]>([]);
  const [pastedNotes, setPastedNotes] = useState("");
  const [extractingCount, setExtractingCount] = useState(0);
  const [dragging, setDragging] = useState(false);
  const materialInputRef = useRef<HTMLInputElement>(null);
  const total = questions.reduce((sum, item) => sum + item.marks, 0);
  const courseMaterial = combineCourseMaterial(materials, pastedNotes);
  const materialChars = courseMaterial.length;
  const materialTooLong = materialChars > MAX_COURSE_MATERIAL_CHARS;
  const submissionCount = editing ? submissions.filter((s) => s.assignmentId === editing.id).length : 0;

  useEffect(() => {
    if (!assignmentId) return;
    let cancelled = false;
    setLoadingExisting(true);
    assignmentService
      .getAssignment(assignmentId)
      .then((existing) => {
        if (cancelled) return;
        const localDue = toLocalInputValue(existing.dueAt);
        setEditing(existing);
        setTitle(existing.title);
        setDescription(existing.description);
        setDueAt(localDue);
        setOriginalDueAt(localDue);
        setCourseId(existing.courseId);
        setQuestions(existing.questions.map((q) => ({ ...q, id: crypto.randomUUID() })));
      })
      .catch((err) => {
        if (cancelled) return;
        toast(extractErrorMessage(err, "Could not load this assignment."), "info");
        navigate("/app/assignments");
      })
      .finally(() => {
        if (!cancelled) setLoadingExisting(false);
      });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [assignmentId]);

  const updateQuestion = (id: string, patch: Partial<Question>) =>
    setQuestions((current) => current.map((item) => (item.id === id ? { ...item, ...patch } : item)));

  const attachMaterials = async (files: FileList | null) => {
    if (!files?.length) return;
    for (const file of Array.from(files)) {
      const extension = file.name.split(".").pop()?.toLowerCase() ?? "";
      if (!MATERIAL_EXTENSIONS.includes(extension)) {
        toast(`${file.name}: attach a PDF, DOCX, PPTX or TXT file.`, "info");
        continue;
      }
      if (file.size > MAX_MATERIAL_FILE_BYTES) {
        toast(`${file.name}: file exceeds the 25 MB limit.`, "info");
        continue;
      }
      setExtractingCount((n) => n + 1);
      try {
        const extracted = await aiAssignmentService.extractCourseMaterial(file);
        setMaterials((current) => [...current, { ...extracted, id: crypto.randomUUID() }]);
        if (extracted.truncated) {
          toast(`${file.name} is very long; only the first ${MAX_COURSE_MATERIAL_CHARS.toLocaleString()} characters are used.`, "info");
        }
      } catch (err) {
        toast(`${file.name}: ${extractErrorMessage(err, "could not read this file.")}`, "info");
      } finally {
        setExtractingCount((n) => n - 1);
      }
    }
  };

  const handleAiGenerateClick = async () => {
    // With material attached, fall back to the first file's name so a topic isn't mandatory.
    const materialTopic = materials[0]?.filename.replace(/\.[^.]+$/, "") ?? "";
    const aiTopic = (topic.trim() || title.trim() || materialTopic).slice(0, 300);
    const questionCount = Number(count);
    const targetMarks = Math.floor(Number(aiTotalMarks));
    if (aiTopic.length < 3) {
      toast("Enter a topic (or an assignment title) for the AI to write questions about.", "info");
      return;
    }
    if (!Number.isFinite(targetMarks) || targetMarks < questionCount) {
      toast(`Total marks must be a whole number of at least ${questionCount} (one per question).`, "info");
      return;
    }
    if (extractingCount > 0) {
      toast("Wait for the attached course material to finish reading.", "info");
      return;
    }
    if (materialTooLong) {
      toast(
        `Course material is too long (${materialChars.toLocaleString()} / ${MAX_COURSE_MATERIAL_CHARS.toLocaleString()} characters). Remove a file or shorten the pasted notes.`,
        "info"
      );
      return;
    }

    setGenerating(true);
    try {
      const draft = await aiAssignmentService.generateDraft({
        topic: aiTopic,
        instructions: description.trim() || undefined,
        questionCount,
        questionFormat: type.toLowerCase() as "mixed" | "subjective" | "mcq",
        difficulty: difficulty.toLowerCase() as "easy" | "medium" | "hard" | "mixed",
        totalMarks: targetMarks,
        courseMaterial: courseMaterial || undefined,
      });
      // Replace the editor's blank starter question(s); otherwise append to the teacher's work.
      const editorIsBlank = questions.every((q) => !q.prompt.trim() && !q.expectedAnswer.trim());
      setQuestions((current) => (editorIsBlank ? draft.questions : [...current, ...draft.questions]));
      if (!title.trim()) setTitle(draft.title);
      if (!description.trim() && draft.instructions) setDescription(draft.instructions);
      toast(
        `Added ${draft.questions.length} AI-drafted question${draft.questions.length === 1 ? "" : "s"}. ` +
          (draft.groundedInCourseMaterials
            ? "They are based on your attached course material. Review them before saving."
            : "They are based on the topic only (no course material attached), so review them carefully before saving.")
      );
    } catch (err) {
      toast(extractErrorMessage(err, "AI generation failed. Try again."), "info");
    } finally {
      setGenerating(false);
    }
  };

  const saveAssignment = async (state: Assignment["state"]) => {
    const cleanTitle = title.trim();
    if (!cleanTitle) {
      toast("Add an assignment title before saving.", "info");
      return;
    }
    // Students only see published assignments from courses they're enrolled in, so an
    // assignment without a course would be invisible to every student.
    const selectedCourseId = courseId || courseList[0]?.id;
    if (!editing && !selectedCourseId) {
      toast("Create a course first (Courses page) and enroll your students; assignments must belong to a course.", "info");
      return;
    }
    if (!questions.length || questions.some((q) => !q.prompt.trim()) || total <= 0) {
      toast("Add question prompts and valid marks before saving.", "info");
      return;
    }
    const deadline = new Date(dueAt);
    if (Number.isNaN(deadline.valueOf())) {
      toast("Choose a valid due date before saving.", "info");
      return;
    }

    setSaving(true);
    if (editing) {
      try {
        let saved = await assignmentService.updateAssignment(editing.id, {
          title: cleanTitle,
          description: description.trim(),
          // Only send the deadline if it changed, so overdue assignments stay editable.
          dueAt: dueAt !== originalDueAt ? deadline.toISOString() : undefined,
          totalMarks: total,
          questions: questions.map((q) => ({ ...q, prompt: q.prompt.trim() })),
        });
        if (state === "Published" && saved.state !== "Published") {
          saved = await assignmentService.publishAssignment(saved.id);
        }
        setAssignments((current) => current.map((item) => (item.id === saved.id ? saved : item)));
        toast(
          editing.state === "Published"
            ? "Changes saved. Students now see the updated assignment."
            : state === "Published"
            ? "Assignment updated and published to students."
            : "Draft updated."
        );
        navigate("/app/assignments");
      } catch (err) {
        toast(extractErrorMessage(err, "Could not save changes. Check all fields and try again."), "info");
      } finally {
        setSaving(false);
      }
      return;
    }
    try {
      let created = await assignmentService.createAssignment({
        courseId: selectedCourseId,
        title: cleanTitle,
        description: description.trim(),
        dueAt: deadline.toISOString(),
        totalMarks: total,
        questions: questions.map((q) => ({ ...q, prompt: q.prompt.trim() })),
      });

      if (state === "Published") {
        created = await assignmentService.publishAssignment(created.id);
      }
      setAssignments((current) => [created, ...current]);
      toast(
        state === "Published"
          ? "Assignment created and published to students successfully!"
          : "Assignment draft saved successfully."
      );
      navigate("/app/assignments");
    } catch (err) {
      toast(extractErrorMessage(err, "Could not save assignment. Check all fields and try again."), "info");
    } finally {
      setSaving(false);
    }
  };

  if (loadingExisting) {
    return (
      <Panel className="empty-state" style={{ padding: "3rem 1.5rem", textAlign: "center", color: "#5C6E61" }}>
        <span className="button-spinner" /> Loading assignment…
      </Panel>
    );
  }

  const editingPublished = editing?.state === "Published";

  return (
    <>
      <div className="page-heading">
        <div>
          <div className="eyebrow">{editing ? "ASSIGNMENT EDITOR" : "ASSIGNMENT CREATION CONSOLE"}</div>
          <h1>
            {editing ? "Edit assignment" : "Create assignment"}{" "}
            {editing && <StatusBadge status={editing.state} />}
          </h1>
          <p className="page-subtitle">
            {editingPublished
              ? "This assignment is live. Changes to details, due date and questions apply to students as soon as you save."
              : editing
              ? "Update this draft, then save it or publish it to students."
              : "Give your class a clear, thoughtful next step with structured questions and rubrics."}
          </p>
        </div>
        <div className="heading-actions">
          {editing && (
            <Button variant="secondary" disabled={saving} onClick={() => navigate("/app/assignments")}>
              Cancel
            </Button>
          )}
          {editingPublished ? (
            <Button disabled={saving} onClick={() => saveAssignment("Published")}>
              <Save size={15} />
              Save changes
            </Button>
          ) : (
            <>
              <Button variant="secondary" disabled={saving} onClick={() => saveAssignment("Draft")}>
                <FileText size={15} />
                Save draft
              </Button>
              <Button disabled={saving} onClick={() => saveAssignment("Published")}>
                <Upload size={15} />
                {editing ? "Save & publish" : "Publish assignment"}
              </Button>
            </>
          )}
        </div>
      </div>

      {submissionCount > 0 && (
        <IntegrationNotice
          tone="warning"
          title={`${submissionCount} submission${submissionCount === 1 ? " has" : "s have"} already been made`}
          description={
            "Edits apply to everyone, including students who already submitted. Their existing answers are kept, " +
            "so prefer editing a question over removing it — removing a question students have answered is refused."
          }
        />
      )}

      <div className="editor-layout">
        <div className="editor-main">
          <Panel className="editor-card">
            <div className="section-heading">
              <div>
                <h2>Assignment details</h2>
                <p>Basic information displayed to students</p>
              </div>
            </div>
            <div className="field-block">
              <label htmlFor="assignment-title">Assignment title</label>
              <input
                id="assignment-title"
                className="field-input"
                value={title}
                onChange={(event) => setTitle(event.target.value)}
                placeholder="e.g. Algorithms & Complexity — Problem Set 03"
              />
            </div>
            <div className="field-block">
              <label htmlFor="assignment-description">Description & instructions for students</label>
              <textarea
                id="assignment-description"
                className="field-textarea"
                value={description}
                onChange={(event) => setDescription(event.target.value)}
                placeholder="Set the context and let students know the topics covered, permitted resources, and expectations..."
              />
            </div>
          </Panel>

          <Panel className="editor-card">
            <div className="section-heading">
              <div>
                <h2>Questions</h2>
                <p>{`${questions.length} questions · ${total} marks total`}</p>
              </div>
            </div>
            <div className="question-list">
              {questions.map((question, index) => (
                <QuestionEditor
                  key={question.id}
                  question={question}
                  index={index}
                  onChange={(patch) => updateQuestion(question.id, patch)}
                  onDelete={() => setQuestions((current) => current.filter((item) => item.id !== question.id))}
                  onMove={() =>
                    setQuestions((current) => {
                      if (!index) return current;
                      const next = [...current];
                      [next[index - 1], next[index]] = [next[index], next[index - 1]];
                      return next;
                    })
                  }
                />
              ))}
            </div>
            <Button
              className="add-question-button"
              variant="secondary"
              onClick={() =>
                setQuestions((current) => [
                  ...current,
                  { id: crypto.randomUUID(), prompt: "", type: "Subjective", marks: 5, expectedAnswer: "" },
                ])
              }
            >
              <Plus size={14} />
              Add a question
            </Button>
          </Panel>
        </div>

        <aside className="editor-side">
          <Panel className="ai-panel">
            <div className="ai-title">
              <span className="feature-symbol">
                <Sparkles size={15} />
              </span>
              <div>
                <strong>Generate with AI</strong>
                <small>Assisted drafting engine</small>
              </div>
            </div>

            <p className="modal-description">
              Drafts questions, model answers and rubrics with AI. Attach the course material for this
              assignment so questions are based on it; without it, questions come from the topic alone.
              Nothing is saved until you save the assignment.
            </p>

            <div className="field-block">
              <label>Course material</label>
              <div
                className={`material-drop ${dragging ? "drag-active" : ""}`}
                onDragOver={(event: DragEvent<HTMLDivElement>) => {
                  event.preventDefault();
                  setDragging(true);
                }}
                onDragLeave={() => setDragging(false)}
                onDrop={(event: DragEvent<HTMLDivElement>) => {
                  event.preventDefault();
                  setDragging(false);
                  void attachMaterials(event.dataTransfer.files);
                }}
              >
                <input
                  ref={materialInputRef}
                  className="visually-hidden"
                  type="file"
                  multiple
                  accept=".pdf,.docx,.pptx,.txt,.md"
                  onChange={(event) => {
                    void attachMaterials(event.target.files);
                    event.target.value = "";
                  }}
                />
                <Button
                  variant="secondary"
                  size="sm"
                  disabled={generating}
                  onClick={() => materialInputRef.current?.click()}
                >
                  <Paperclip size={13} />
                  Attach notes, slides or readings
                </Button>
                <small>PDF, DOCX, PPTX or TXT · up to 25 MB each · or drop files here</small>
              </div>

              {(materials.length > 0 || extractingCount > 0) && (
                <ul className="material-list">
                  {materials.map((material) => (
                    <li className="material-item" key={material.id}>
                      <span className="file-icon">
                        <FileText size={14} />
                      </span>
                      <span className="material-meta">
                        <strong title={material.filename}>{material.filename}</strong>
                        <small>
                          {material.characters.toLocaleString()} characters
                          {material.pages ? ` · ${material.pages} page${material.pages === 1 ? "" : "s"}` : ""}
                          {material.truncated ? " · truncated" : ""}
                        </small>
                      </span>
                      <button
                        className="icon-button"
                        aria-label={`Remove ${material.filename}`}
                        disabled={generating}
                        onClick={() => setMaterials((current) => current.filter((m) => m.id !== material.id))}
                      >
                        <X size={13} />
                      </button>
                    </li>
                  ))}
                  {extractingCount > 0 && (
                    <li className="material-item material-loading">
                      <span className="button-spinner" />
                      Reading {extractingCount} file{extractingCount === 1 ? "" : "s"}…
                    </li>
                  )}
                </ul>
              )}

              <textarea
                id="ai-material-notes"
                className="field-textarea material-notes"
                value={pastedNotes}
                onChange={(event) => setPastedNotes(event.target.value)}
                placeholder="…or paste course notes / key points here (optional)"
                aria-label="Paste course material"
              />
              {materialChars > 0 && (
                <small className={`material-count ${materialTooLong ? "over-limit" : ""}`}>
                  {materialChars.toLocaleString()} / {MAX_COURSE_MATERIAL_CHARS.toLocaleString()} characters
                  {materialTooLong ? " — too long, remove a file or shorten the notes" : ""}
                </small>
              )}
            </div>

            <div className="field-block">
              <label htmlFor="ai-topic">Topic</label>
              <input
                id="ai-topic"
                className="field-input"
                value={topic}
                onChange={(event) => setTopic(event.target.value)}
                placeholder={title.trim() || "e.g. Newton's laws of motion"}
                maxLength={300}
              />
            </div>

            <div className="field-block">
              <label>Target difficulty</label>
              <div className="difficulty-options">
                {["Easy", "Medium", "Hard", "Mixed"].map((item) => (
                  <button
                    key={item}
                    type="button"
                    className={difficulty === item ? "active" : ""}
                    onClick={() => setDifficulty(item)}
                  >
                    {item}
                  </button>
                ))}
              </div>
            </div>
            <div className="field-block">
              <label htmlFor="question-count">Question count</label>
              <select
                id="question-count"
                className="field-select"
                value={count}
                onChange={(event) => setCount(event.target.value)}
              >
                {["3", "5", "8"].map((item) => (
                  <option key={item} value={item}>
                    {item} questions
                  </option>
                ))}
              </select>
            </div>
            <div className="field-block">
              <label htmlFor="question-type">Question format</label>
              <select
                id="question-type"
                className="field-select"
                value={type}
                onChange={(event) => setType(event.target.value as typeof type)}
              >
                <option value="Mixed">Mix of subjective & MCQ</option>
                <option value="Subjective">Subjective only</option>
                <option value="MCQ">MCQ only</option>
              </select>
            </div>
            <div className="field-block">
              <label htmlFor="ai-total-marks">Total marks to distribute</label>
              <input
                id="ai-total-marks"
                className="field-input"
                type="number"
                min={1}
                step={1}
                value={aiTotalMarks}
                onChange={(event) => setAiTotalMarks(event.target.value)}
              />
            </div>
            <Button
              className="full-button"
              variant="secondary"
              disabled={generating || saving || extractingCount > 0}
              onClick={() => void handleAiGenerateClick()}
            >
              {generating ? (
                <>
                  <span className="button-spinner" />
                  Generating… (up to a minute)
                </>
              ) : (
                "Generate question prompts"
              )}
            </Button>
          </Panel>

          <Panel className="editor-card">
            <div className="section-heading">
              <div>
                <h2>Assignment settings</h2>
              </div>
            </div>
            <div className="field-block">
              <label htmlFor="course-select">Course</label>
              <select
                id="course-select"
                className="field-select"
                value={courseId || courseList[0]?.id || ""}
                onChange={(event) => setCourseId(event.target.value)}
                disabled={Boolean(editing)}
                title={editing ? "An assignment's course can't be changed after it is created." : undefined}
              >
                {courseList.map((course) => (
                  <option value={course.id} key={course.id}>
                    {course.name} · {course.code}
                  </option>
                ))}
                {!courseList.length && <option value="">No courses created yet</option>}
              </select>
            </div>
            <div className="field-block">
              <label htmlFor="due-date">Due date</label>
              <input
                id="due-date"
                className="field-input"
                type="datetime-local"
                value={dueAt}
                onChange={(event) => setDueAt(event.target.value)}
              />
            </div>
            <div className="field-block">
              <label htmlFor="total-marks">Total marks</label>
              <input
                id="total-marks"
                className="field-input"
                type="number"
                value={total}
                readOnly
              />
            </div>
            <p className="modal-description">
              Rubric templates are not persisted by the current assignment API. Question marks and teacher-provided
              expected answers are stored with the assignment.
            </p>
          </Panel>
        </aside>
      </div>
    </>
  );
}
