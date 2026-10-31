import { useState, type Dispatch, type SetStateAction } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { ChevronLeft, FileText, Plus, Sparkles, Upload, X } from "lucide-react";
import { aiAssignmentService, assignmentService, extractErrorMessage } from "../../services/api";
import { Badge, Button, Panel, useToast } from "../../components/ui";
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
  const toast = useToast();
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
  const total = questions.reduce((sum, item) => sum + item.marks, 0);

  const updateQuestion = (id: string, patch: Partial<Question>) =>
    setQuestions((current) => current.map((item) => (item.id === id ? { ...item, ...patch } : item)));

  const handleAiGenerateClick = async () => {
    const aiTopic = (topic.trim() || title.trim());
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

    setGenerating(true);
    try {
      const draft = await aiAssignmentService.generateDraft({
        topic: aiTopic,
        instructions: description.trim() || undefined,
        questionCount,
        questionFormat: type.toLowerCase() as "mixed" | "subjective" | "mcq",
        difficulty: difficulty.toLowerCase() as "easy" | "medium" | "hard" | "mixed",
        totalMarks: targetMarks,
      });
      // Replace the editor's blank starter question(s); otherwise append to the teacher's work.
      const editorIsBlank = questions.every((q) => !q.prompt.trim() && !q.expectedAnswer.trim());
      setQuestions((current) => (editorIsBlank ? draft.questions : [...current, ...draft.questions]));
      if (!title.trim()) setTitle(draft.title);
      if (!description.trim() && draft.instructions) setDescription(draft.instructions);
      toast(
        `Added ${draft.questions.length} AI-drafted question${draft.questions.length === 1 ? "" : "s"}. ` +
          (draft.groundedInCourseMaterials
            ? "Review them before saving."
            : "They are based on the topic only (no course materials), so review them carefully before saving.")
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
    if (!selectedCourseId) {
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

  return (
    <>
      <div className="page-heading">
        <div>
          <div className="eyebrow">ASSIGNMENT CREATION CONSOLE</div>
          <h1>Create assignment</h1>
          <p className="page-subtitle">Give your class a clear, thoughtful next step with structured questions and rubrics.</p>
        </div>
        <div className="heading-actions">
          <Button variant="secondary" disabled={saving} onClick={() => saveAssignment("Draft")}>
            <FileText size={15} />
            Save draft
          </Button>
          <Button disabled={saving} onClick={() => saveAssignment("Published")}>
            <Upload size={15} />
            Publish assignment
          </Button>
        </div>
      </div>

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
              Drafts questions, model answers and rubrics with AI. Nothing is saved until you save the
              assignment. Course materials aren't used yet, so questions come from the topic alone.
            </p>

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
              disabled={generating || saving}
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
