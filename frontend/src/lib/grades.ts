import type { Assignment, Submission } from "../types/models";

/**
 * A published grade as a percentage of the marks available (0–100), or null when the submission
 * has no published grade or the maximum is unknown. Unpublished AI suggestions never count.
 */
export function scorePercent(submission: Submission, assignment: Assignment | undefined): number | null {
  const grading = submission.grading;
  if (submission.state !== "Published" || !grading) return null;
  const questionMax = (grading.questionResults ?? []).reduce((sum, q) => sum + (q.maxMarks || 0), 0);
  const max = grading.maxScore || questionMax || assignment?.totalMarks || 0;
  if (max <= 0) return null;
  return Math.max(0, Math.min(100, (grading.suggestedScore / max) * 100));
}

export const formatPercent = (value: number) => `${Math.round(value)}%`;
