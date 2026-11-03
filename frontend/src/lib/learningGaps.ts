import type { Assignment, Submission } from "../types/models";

/**
 * Learning gaps: weak points of one student, or of a whole class, worked out in the browser from the
 * per-question results of *published* grades the app already loads (no extra request, no AI call).
 *
 * Two signals are used:
 *  - marks per question: a question where the student earned under WEAK_PERCENT of the marks is a weak
 *    question;
 *  - the key points the answer missed (``missingPoints``). They come from the teacher's answer key, so
 *    the same key point has the same wording for every student on a question, which lets us count how
 *    often a student (or how many classmates) missed it. Students only receive them after the due date.
 *
 * Questions without per-question marks (teacher-only grades, or AI marks that contradicted the
 * teacher's total and were dropped) are left out.
 */

/** A question scored below this share of its marks is a weak point. Matches the pass mark elsewhere. */
export const WEAK_PERCENT = 60;
/** At or above this share a question counts as a strength. */
export const STRONG_PERCENT = 80;

/** Placeholder "missing" items the grader uses for MCQs and blank answers: not concepts. */
const GENERIC_POINTS = new Set(["correct option", "selection required", "response required"]);

export interface QuestionAttempt {
  submissionId: string;
  studentId: string;
  assignmentId: string;
  assignmentTitle: string;
  courseId: string;
  dueAt: string;
  number: number;
  questionText: string;
  awarded: number;
  max: number;
  /** 0–100 share of the question's marks earned (bonus marks not included). */
  percent: number;
  /** Key points the answer missed, cleaned (generic placeholders removed). */
  missing: string[];
  tips: string[];
  teacherComment: string | null;
  /** True while the key points missed are still withheld from the student (before the due date). */
  detailsPending: boolean;
}

export interface ConceptGap {
  key: string;
  label: string;
  /** How many questions this key point was missed on. */
  times: number;
  /** Assignment titles it was missed in, most recent first. */
  assignments: string[];
  lastDueAt: string;
}

export interface StudentGaps {
  questionsGraded: number;
  /** Share of all question marks earned, 0–100; null when nothing is graded per question. */
  mastery: number | null;
  marksEarned: number;
  marksAvailable: number;
  weakQuestions: QuestionAttempt[];
  strongQuestions: number;
  concepts: ConceptGap[];
  /** Weak questions whose missed key points are not released yet. */
  pendingDetails: number;
}

const cleanPoint = (text: string) => text.replace(/\s+/g, " ").trim().replace(/[.;:,]+$/, "");
const pointKey = (text: string) => cleanPoint(text).toLowerCase();
const round1 = (value: number) => Math.round(value * 10) / 10;
const byRecent = (a: { dueAt: string }, b: { dueAt: string }) => Date.parse(b.dueAt || "0") - Date.parse(a.dueAt || "0");

/** Every question with a published per-question mark, across the given submissions. */
export function collectAttempts(submissions: Submission[], assignments: Assignment[]): QuestionAttempt[] {
  const assignmentById = new Map(assignments.map((a) => [a.id, a]));
  const attempts: QuestionAttempt[] = [];
  for (const submission of submissions) {
    const grading = submission.grading;
    if (submission.state !== "Published" || !grading?.questionResults?.length) continue;
    const assignment = assignmentById.get(submission.assignmentId);
    for (const result of grading.questionResults) {
      if (result.awardedMarks === null || !(result.maxMarks > 0)) continue;
      const percent = Math.max(0, Math.min(100, (result.awardedMarks / result.maxMarks) * 100));
      const missing = (result.missingPoints ?? []).map(cleanPoint).filter((p) => p && !GENERIC_POINTS.has(p.toLowerCase()));
      attempts.push({
        submissionId: submission.id,
        studentId: submission.studentId,
        assignmentId: submission.assignmentId,
        assignmentTitle: assignment?.title ?? "Untitled assignment",
        courseId: assignment?.courseId ?? "",
        dueAt: assignment?.dueAt ?? submission.deadline ?? "",
        number: result.number,
        questionText: result.questionText,
        awarded: result.awardedMarks,
        max: result.maxMarks,
        percent,
        missing: [...new Set(missing)],
        tips: result.areasForImprovement ?? [],
        teacherComment: result.teacherComment,
        detailsPending: percent < 100 && missing.length === 0 && !!grading.missingPointsAvailableAt,
      });
    }
  }
  return attempts;
}

/** One student's weak questions and the key points they keep missing. */
export function studentGaps(attempts: QuestionAttempt[]): StudentGaps {
  const totalMax = attempts.reduce((sum, a) => sum + a.max, 0);
  const totalAwarded = attempts.reduce((sum, a) => sum + Math.min(a.awarded, a.max), 0);
  const weakQuestions = attempts
    .filter((a) => a.percent < WEAK_PERCENT)
    .sort((a, b) => a.percent - b.percent || byRecent(a, b) || a.number - b.number);

  const concepts = new Map<string, ConceptGap>();
  for (const attempt of [...attempts].sort(byRecent)) {
    for (const point of attempt.missing) {
      const key = pointKey(point);
      const entry = concepts.get(key) ?? { key, label: point, times: 0, assignments: [], lastDueAt: attempt.dueAt };
      entry.times += 1;
      if (!entry.assignments.includes(attempt.assignmentTitle)) entry.assignments.push(attempt.assignmentTitle);
      concepts.set(key, entry);
    }
  }

  return {
    questionsGraded: attempts.length,
    mastery: totalMax > 0 ? (totalAwarded / totalMax) * 100 : null,
    marksEarned: totalAwarded,
    marksAvailable: totalMax,
    weakQuestions,
    strongQuestions: attempts.filter((a) => a.percent >= STRONG_PERCENT).length,
    // Recurring gaps first (missed on several questions), then the most recent.
    concepts: [...concepts.values()].sort((a, b) => b.times - a.times || Date.parse(b.lastDueAt || "0") - Date.parse(a.lastDueAt || "0")),
    pendingDetails: weakQuestions.filter((a) => a.detailsPending).length,
  };
}

export interface QuestionStat {
  key: string;
  assignmentId: string;
  assignmentTitle: string;
  dueAt: string;
  number: number;
  questionText: string;
  max: number;
  students: number;
  /** Class average on this question, 0–100. */
  average: number;
  /** Students who scored under WEAK_PERCENT. */
  struggling: number;
  /** Key points missed on this question, by how many students. */
  topMissing: { label: string; students: number }[];
}

export interface ClassConcept {
  key: string;
  label: string;
  /** Distinct students who missed this key point. */
  students: number;
  /** Distinct students graded on the questions that call for it. */
  outOf: number;
  share: number;
  questions: { assignmentTitle: string; number: number }[];
}

export interface StudentSupport {
  studentId: string;
  mastery: number;
  marksEarned: number;
  marksAvailable: number;
  questionsGraded: number;
  weakQuestions: number;
  topConcepts: string[];
}

export interface ClassGaps {
  students: number;
  questionsGraded: number;
  /** Class-wide share of question marks earned, 0–100. */
  mastery: number | null;
  hardQuestions: QuestionStat[];
  concepts: ClassConcept[];
  needSupport: StudentSupport[];
}

/** The class's weakest questions, the key points most students miss, and who needs support. */
export function classGaps(attempts: QuestionAttempt[]): ClassGaps {
  // Per question (assignment + number).
  const questions = new Map<string, { attempts: QuestionAttempt[] }>();
  for (const attempt of attempts) {
    const key = `${attempt.assignmentId}:${attempt.number}`;
    const entry = questions.get(key) ?? { attempts: [] };
    entry.attempts.push(attempt);
    questions.set(key, entry);
  }

  const stats: QuestionStat[] = [];
  // Key point -> the questions it was missed on, and which students missed it.
  const conceptMisses = new Map<string, { label: string; questionKeys: Set<string>; students: Set<string> }>();
  for (const [key, { attempts: rows }] of questions) {
    const first = rows[0];
    const students = new Set(rows.map((r) => r.studentId));
    const missingBy = new Map<string, { label: string; students: Set<string> }>();
    for (const row of rows) {
      for (const point of row.missing) {
        const pkey = pointKey(point);
        const local = missingBy.get(pkey) ?? { label: point, students: new Set<string>() };
        local.students.add(row.studentId);
        missingBy.set(pkey, local);
        const global = conceptMisses.get(pkey) ?? { label: point, questionKeys: new Set<string>(), students: new Set<string>() };
        global.questionKeys.add(key);
        global.students.add(row.studentId);
        conceptMisses.set(pkey, global);
      }
    }
    stats.push({
      key,
      assignmentId: first.assignmentId,
      assignmentTitle: first.assignmentTitle,
      dueAt: first.dueAt,
      number: first.number,
      questionText: first.questionText,
      max: first.max,
      students: students.size,
      average: rows.reduce((sum, r) => sum + r.percent, 0) / rows.length,
      struggling: new Set(rows.filter((r) => r.percent < WEAK_PERCENT).map((r) => r.studentId)).size,
      topMissing: [...missingBy.values()]
        .map((m) => ({ label: m.label, students: m.students.size }))
        .sort((a, b) => b.students - a.students)
        .slice(0, 3),
    });
  }

  const statByKey = new Map(stats.map((s) => [s.key, s]));
  const concepts: ClassConcept[] = [...conceptMisses.entries()].map(([key, entry]) => {
    const graded = new Set<string>();
    for (const qkey of entry.questionKeys) for (const row of questions.get(qkey)!.attempts) graded.add(row.studentId);
    return {
      key,
      label: entry.label,
      students: entry.students.size,
      outOf: graded.size,
      share: graded.size ? (entry.students.size / graded.size) * 100 : 0,
      questions: [...entry.questionKeys]
        .map((qkey) => statByKey.get(qkey)!)
        .sort(byRecent)
        .map((s) => ({ assignmentTitle: s.assignmentTitle, number: s.number })),
    };
  });
  concepts.sort((a, b) => b.students - a.students || b.share - a.share || a.label.localeCompare(b.label));

  // Per student.
  const byStudent = new Map<string, QuestionAttempt[]>();
  for (const attempt of attempts) byStudent.set(attempt.studentId, [...(byStudent.get(attempt.studentId) ?? []), attempt]);
  const needSupport: StudentSupport[] = [];
  for (const [studentId, rows] of byStudent) {
    const gaps = studentGaps(rows);
    if (gaps.mastery === null || gaps.mastery >= WEAK_PERCENT) continue;
    needSupport.push({
      studentId,
      mastery: round1(gaps.mastery),
      marksEarned: gaps.marksEarned,
      marksAvailable: gaps.marksAvailable,
      questionsGraded: gaps.questionsGraded,
      weakQuestions: gaps.weakQuestions.length,
      topConcepts: gaps.concepts.slice(0, 3).map((c) => c.label),
    });
  }
  needSupport.sort((a, b) => a.mastery - b.mastery || b.weakQuestions - a.weakQuestions);

  const totalMax = attempts.reduce((sum, a) => sum + a.max, 0);
  const totalAwarded = attempts.reduce((sum, a) => sum + Math.min(a.awarded, a.max), 0);
  return {
    students: byStudent.size,
    questionsGraded: attempts.length,
    mastery: totalMax > 0 ? (totalAwarded / totalMax) * 100 : null,
    hardQuestions: stats
      .filter((s) => s.average < WEAK_PERCENT)
      .sort((a, b) => a.average - b.average || b.students - a.students),
    concepts,
    needSupport,
  };
}
