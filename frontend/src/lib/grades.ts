import type { Assignment, Submission } from "../types/models";

/**
 * The marks a submission is graded out of: the grade's own maximum, else the sum of its question
 * marks, else the assignment total. 0 when none of these is known.
 */
export function marksAvailable(submission: Submission, assignment: Assignment | undefined): number {
  const grading = submission.grading;
  const questionMax = (grading?.questionResults ?? []).reduce((sum, q) => sum + (q.maxMarks || 0), 0);
  return grading?.maxScore || questionMax || assignment?.totalMarks || 0;
}

/**
 * A published grade as a percentage of the marks available (0–100), or null when the submission
 * has no published grade or the maximum is unknown. Unpublished AI suggestions never count.
 * Charts use it to place scores from assignments with different totals on one scale; show marks
 * to people (see formatMarks).
 */
export function scorePercent(submission: Submission, assignment: Assignment | undefined): number | null {
  const grading = submission.grading;
  if (submission.state !== "Published" || !grading) return null;
  const max = marksAvailable(submission, assignment);
  if (max <= 0) return null;
  return Math.max(0, Math.min(100, (grading.suggestedScore / max) * 100));
}

/**
 * The total most grades are marked out of (e.g. 20), used as a chart's scale. Ties go to the larger
 * total; null when there are no totals.
 */
export function commonTotal(totals: number[]): number | null {
  const counts = new Map<number, number>();
  for (const total of totals) if (total > 0) counts.set(total, (counts.get(total) ?? 0) + 1);
  let best: number | null = null;
  for (const [total, count] of counts) {
    const bestCount = best === null ? 0 : counts.get(best)!;
    if (count > bestCount || (count === bestCount && total > best!)) best = total;
  }
  return best;
}

/** A 0–100 percentage expressed in marks out of `outOf`. */
export const percentToMarks = (percent: number, outOf: number) => (percent / 100) * outOf;

/** Marks to one decimal place without a trailing ".0": "10.3", or "10.3 / 20" when given a total. */
export function formatMarks(value: number, outOf?: number): string {
  const marks = String(Math.round(value * 10) / 10);
  return outOf === undefined ? marks : `${marks} / ${String(Math.round(outOf * 10) / 10)}`;
}

export const formatPercent = (value: number) => `${Math.round(value)}%`;
