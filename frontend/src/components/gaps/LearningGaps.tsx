import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { ChevronRight, Lightbulb, Target, TrendingDown, Users } from "lucide-react";
import { Panel } from "../ui";
import { formatMarks } from "../../lib/grades";
import {
  classGaps, collectAttempts, studentGaps, WEAK_PERCENT,
  type QuestionAttempt, type StudentGaps,
} from "../../lib/learningGaps";
import type { Assignment, Course, Submission } from "../../types/models";
import "./learningGaps.css";

/**
 * Learning gaps (weak points) for students and teachers. See lib/learningGaps.ts for how they are
 * worked out. Three views share one vocabulary:
 *  - MyLearningGaps: a student's own weak points (student Overview);
 *  - ClassLearningGaps: a teacher's class-wide weak points and the students who need support;
 *  - StudentGapsBody: one student's weak points, for the teacher (course roster, class panel).
 */

const LIST_LIMIT = 5;
const plural = (count: number, word: string) => `${count} ${word}${count === 1 ? "" : "s"}`;
const truncate = (text: string, length: number) => (text.length > length ? `${text.slice(0, length - 1).trimEnd()}…` : text);

/** The best short reason a question was weak: teacher's note, missed key points, then the AI's tip. */
function weakReason(attempt: QuestionAttempt): string | null {
  if (attempt.teacherComment) return `Teacher: ${attempt.teacherComment}`;
  if (attempt.missing.length) return `Missed: ${attempt.missing.join(", ")}`;
  return attempt.tips[0] ?? null;
}

function ShowMore({ total, open, onToggle }: { total: number; open: boolean; onToggle: () => void }) {
  if (total <= LIST_LIMIT) return null;
  return (
    <button type="button" className="text-button gaps-more" onClick={onToggle}>
      {open ? "Show fewer" : `Show all ${total}`}
    </button>
  );
}

/** One student's weak points. `you` switches the wording between the student and their teacher. */
export function StudentGapsBody({ gaps, you }: { gaps: StudentGaps; you: boolean }) {
  const [allConcepts, setAllConcepts] = useState(false);
  const [allQuestions, setAllQuestions] = useState(false);
  const concepts = allConcepts ? gaps.concepts : gaps.concepts.slice(0, LIST_LIMIT);
  const questions = allQuestions ? gaps.weakQuestions : gaps.weakQuestions.slice(0, LIST_LIMIT);

  if (gaps.questionsGraded === 0) {
    return (
      <p className="analytics-empty">
        {you
          ? "Your weak points appear here once your teacher publishes a grade with per-question marks."
          : "No published grade with per-question marks yet."}
      </p>
    );
  }

  return (
    <div className="gaps-body">
      <div className="gaps-tiles">
        <div>
          <span>Question marks earned</span>
          <strong>{formatMarks(gaps.marksEarned, gaps.marksAvailable)}</strong>
          <small>Across {plural(gaps.questionsGraded, "graded question")}</small>
        </div>
        <div>
          <span>Weak questions</span>
          <strong>{gaps.weakQuestions.length}</strong>
          <small>Under {WEAK_PERCENT}% of the marks</small>
        </div>
        <div>
          <span>Strong questions</span>
          <strong>{gaps.strongQuestions}</strong>
          <small>80% of the marks or more</small>
        </div>
      </div>

      <div className="gaps-columns">
        <section className="gaps-section">
          <h3><Target size={14} /> Key points to revisit</h3>
          {concepts.length ? (
            <ul className="gaps-concepts">
              {concepts.map((concept) => (
                <li key={concept.key}>
                  <strong>{concept.label}</strong>
                  <small>
                    {concept.times > 1 ? `Missed ${concept.times} times` : "Missed once"} · {concept.assignments.join(", ")}
                  </small>
                  {concept.times > 1 && <span className="gaps-chip">Recurring</span>}
                </li>
              ))}
            </ul>
          ) : (
            <p className="gaps-muted">
              {gaps.pendingDetails > 0
                ? you
                  ? "The exact key points you missed appear after each assignment's due date."
                  : "No missed key points recorded yet."
                : gaps.weakQuestions.length
                  ? "No specific key points were recorded; see the questions alongside."
                  : you
                    ? "Nothing to revisit: you covered the key points of every graded question."
                    : "No missed key points recorded."}
            </p>
          )}
          <ShowMore total={gaps.concepts.length} open={allConcepts} onToggle={() => setAllConcepts((v) => !v)} />
        </section>

        <section className="gaps-section">
          <h3><TrendingDown size={14} /> Questions to review</h3>
          {questions.length ? (
            <ul className="gaps-questions">
              {questions.map((attempt) => {
                const reason = weakReason(attempt);
                return (
                  <li key={`${attempt.submissionId}:${attempt.number}`}>
                    <div className="gaps-question-top">
                      <span>
                        <strong>{attempt.assignmentTitle} · Q{attempt.number}</strong>
                        <small title={attempt.questionText}>{truncate(attempt.questionText, 110)}</small>
                      </span>
                      <b className="gaps-score">{formatMarks(attempt.awarded, attempt.max)}</b>
                    </div>
                    {reason && <p>{truncate(reason, 180)}</p>}
                  </li>
                );
              })}
            </ul>
          ) : (
            <p className="gaps-muted">No weak questions: every graded question earned at least {WEAK_PERCENT}% of its marks.</p>
          )}
          <ShowMore total={gaps.weakQuestions.length} open={allQuestions} onToggle={() => setAllQuestions((v) => !v)} />
        </section>
      </div>
    </div>
  );
}

/** Student Overview: the signed-in student's own weak points across their published grades. */
export function MyLearningGaps({
  studentId,
  submissions,
  assignments,
}: {
  studentId: string;
  submissions: Submission[];
  assignments: Assignment[];
}) {
  const navigate = useNavigate();
  const gaps = useMemo(
    () => studentGaps(collectAttempts(submissions.filter((s) => s.studentId === studentId), assignments)),
    [studentId, submissions, assignments],
  );
  return (
    <Panel className="analytics-card gaps-card">
      <div className="section-heading">
        <div>
          <h2>Your learning gaps</h2>
          <p>Where you lost marks in teacher-approved grades, and the key points worth revising</p>
        </div>
        {gaps.questionsGraded > 0 && (
          <button className="text-button" onClick={() => navigate("/app/results")}>
            Full feedback
            <ChevronRight size={13} />
          </button>
        )}
      </div>
      <StudentGapsBody gaps={gaps} you />
      {gaps.weakQuestions.length > 0 && (
        <p className="gaps-hint">
          <Lightbulb size={13} /> Start with the recurring key points: they cost you marks on more than one question.
          Unsure about one? Message your teacher.
        </p>
      )}
    </Panel>
  );
}

/** Teacher: one student's weak points within one course (or all the teacher's courses). */
export function StudentGapsForTeacher({
  studentId,
  courseId,
  submissions,
  assignments,
}: {
  studentId: string;
  courseId?: string;
  submissions: Submission[];
  assignments: Assignment[];
}) {
  const gaps = useMemo(() => {
    const scoped = courseId ? assignments.filter((a) => a.courseId === courseId) : assignments;
    return studentGaps(collectAttempts(submissions.filter((s) => s.studentId === studentId), scoped));
  }, [studentId, courseId, submissions, assignments]);
  return <StudentGapsBody gaps={gaps} you={false} />;
}

/** Teacher Overview: the class's weak points and which students need support. */
export function ClassLearningGaps({
  submissions,
  assignments,
  courses,
  names,
}: {
  submissions: Submission[];
  assignments: Assignment[];
  courses: Course[];
  names: Record<string, { name: string }>;
}) {
  const [courseId, setCourseId] = useState("");
  const [allConcepts, setAllConcepts] = useState(false);
  const [allQuestions, setAllQuestions] = useState(false);
  const [allStudents, setAllStudents] = useState(false);
  const [openStudent, setOpenStudent] = useState<string | null>(null);

  const attempts = useMemo(() => collectAttempts(submissions, assignments), [submissions, assignments]);
  const coursesWithData = useMemo(() => {
    const ids = new Set(attempts.map((a) => a.courseId));
    return courses.filter((c) => ids.has(c.id));
  }, [attempts, courses]);
  const scoped = useMemo(
    () => (courseId ? attempts.filter((a) => a.courseId === courseId) : attempts),
    [attempts, courseId],
  );
  const gaps = useMemo(() => classGaps(scoped), [scoped]);
  const scopedAssignments = courseId ? assignments.filter((a) => a.courseId === courseId) : assignments;

  const concepts = allConcepts ? gaps.concepts : gaps.concepts.slice(0, LIST_LIMIT);
  const questions = allQuestions ? gaps.hardQuestions : gaps.hardQuestions.slice(0, LIST_LIMIT);
  const students = allStudents ? gaps.needSupport : gaps.needSupport.slice(0, LIST_LIMIT);
  const nameOf = (id: string) => names[id]?.name ?? "Student";
  const top = gaps.concepts[0];

  return (
    <Panel className="analytics-card gaps-card">
      <div className="section-heading">
        <div>
          <h2>Class learning gaps</h2>
          <p>Weak points across your students, from the per-question marks of published grades</p>
        </div>
        {coursesWithData.length > 1 && (
          <label className="gaps-filter">
            <span className="sr-only">Course</span>
            <select value={courseId} onChange={(event) => setCourseId(event.target.value)}>
              <option value="">All courses</option>
              {coursesWithData.map((course) => (
                <option key={course.id} value={course.id}>{course.code ? `${course.code} · ${course.name}` : course.name}</option>
              ))}
            </select>
          </label>
        )}
      </div>

      {gaps.questionsGraded === 0 ? (
        <p className="analytics-empty">Learning gaps appear here once you publish grades with per-question marks.</p>
      ) : (
        <>
          <div className="gaps-tiles">
            <div>
              <span>Students who need support</span>
              <strong>{gaps.needSupport.length} <small>of {gaps.students}</small></strong>
              <small>Earned under {WEAK_PERCENT}% of their question marks</small>
            </div>
            <div>
              <span>Hard questions</span>
              <strong>{gaps.hardQuestions.length}</strong>
              <small>Class average under {WEAK_PERCENT}% of the marks</small>
            </div>
            <div>
              <span>Most-missed key point</span>
              <strong className="gaps-tile-text" title={top?.label}>{top ? truncate(top.label, 40) : "—"}</strong>
              <small>{top ? `Missed by ${top.students} of ${top.outOf} students` : "None recorded yet"}</small>
            </div>
          </div>

          <div className="gaps-columns">
            <section className="gaps-section">
              <h3><Target size={14} /> Key points the class is missing</h3>
              {concepts.length ? (
                <ul className="gaps-bars">
                  {concepts.map((concept) => (
                    <li
                      key={concept.key}
                      tabIndex={0}
                      aria-label={`${concept.label}: missed by ${concept.students} of ${concept.outOf} students`}
                    >
                      <div className="gaps-bar-label">
                        <strong title={concept.label}>{concept.label}</strong>
                        <small>
                          {concept.questions.slice(0, 2).map((q) => `${q.assignmentTitle} Q${q.number}`).join(", ")}
                          {concept.questions.length > 2 && ` +${concept.questions.length - 2} more`}
                        </small>
                      </div>
                      <div className="gaps-bar-track">
                        <span className="gaps-bar-fill" style={{ width: `${Math.max(3, concept.share)}%` }} />
                        <b>{concept.students} / {concept.outOf}</b>
                      </div>
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="gaps-muted">No missed key points recorded for these grades yet.</p>
              )}
              <ShowMore total={gaps.concepts.length} open={allConcepts} onToggle={() => setAllConcepts((v) => !v)} />
            </section>

            <section className="gaps-section">
              <h3><TrendingDown size={14} /> Questions the class found hard</h3>
              {questions.length ? (
                <ul className="gaps-questions">
                  {questions.map((q) => (
                    <li key={q.key}>
                      <div className="gaps-question-top">
                        <span>
                          <strong>{q.assignmentTitle} · Q{q.number}</strong>
                          <small title={q.questionText}>{truncate(q.questionText, 110)}</small>
                        </span>
                        <b className="gaps-score" title="Class average">
                          avg {formatMarks((q.average / 100) * q.max, q.max)}
                        </b>
                      </div>
                      <p>
                        {q.struggling} of {plural(q.students, "student")} under {WEAK_PERCENT}%
                        {q.topMissing.length > 0 && ` · most missed: ${q.topMissing.map((m) => `${m.label} (${m.students})`).join(", ")}`}
                      </p>
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="gaps-muted">No question has a class average under {WEAK_PERCENT}% of its marks.</p>
              )}
              <ShowMore total={gaps.hardQuestions.length} open={allQuestions} onToggle={() => setAllQuestions((v) => !v)} />
            </section>
          </div>

          <section className="gaps-section gaps-support">
            <h3><Users size={14} /> Students who need support</h3>
            {students.length ? (
              <ul className="gaps-students">
                {students.map((s) => {
                  const open = openStudent === s.studentId;
                  return (
                    <li key={s.studentId} className={open ? "open" : undefined}>
                      <button
                        type="button"
                        className="gaps-student-row"
                        aria-expanded={open}
                        onClick={() => setOpenStudent(open ? null : s.studentId)}
                      >
                        <span>
                          <strong>{nameOf(s.studentId)}</strong>
                          <small>
                            {plural(s.weakQuestions, "weak question")} of {s.questionsGraded}
                            {s.topConcepts.length > 0 && ` · missing: ${s.topConcepts.join(", ")}`}
                          </small>
                        </span>
                        <b className="gaps-score">{formatMarks(s.marksEarned, s.marksAvailable)}</b>
                        <ChevronRight size={14} className="gaps-chevron" />
                      </button>
                      {open && (
                        <div className="gaps-student-detail">
                          <StudentGapsForTeacher
                            studentId={s.studentId}
                            courseId={courseId || undefined}
                            submissions={submissions}
                            assignments={scopedAssignments}
                          />
                        </div>
                      )}
                    </li>
                  );
                })}
              </ul>
            ) : (
              <p className="gaps-muted">Every student earned at least {WEAK_PERCENT}% of their question marks.</p>
            )}
            <ShowMore total={gaps.needSupport.length} open={allStudents} onToggle={() => setAllStudents((v) => !v)} />
          </section>
          <small className="analytics-note">
            Only published grades count. Students see their own weak points
            on their Overview; missed key points are shown to them after each due date.
          </small>
        </>
      )}
    </Panel>
  );
}
