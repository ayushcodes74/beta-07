import { useMemo, useState } from "react";
import { useAppState } from "../../App";
import { Panel } from "../../components/ui";
import { commonTotal, formatMarks, marksAvailable, percentToMarks, scorePercent } from "../../lib/grades";
import { formatDate } from "../../lib/utils";
import type { Submission } from "../../types/models";
import { PerformanceLineChart, pointMarks, STUDENT_COLOR, type PerformancePoint } from "../teacher/StudentPerformance";

/**
 * Student "My results": a line graph of the student's own published marks on each assignment,
 * oldest due date first. Students only receive their own grades, so there is no class-average line.
 * Unpublished AI suggestions never appear.
 */
export function MyProgressChart({ submissions }: { submissions: Submission[] }) {
  const { user, assignments, courses } = useAppState();
  const [courseId, setCourseId] = useState("all");

  const allPoints = useMemo(() => {
    const assignmentById = new Map(assignments.map((assignment) => [assignment.id, assignment]));
    // A student can resubmit; the most recent published submission is their grade.
    const latest = new Map<string, Submission>();
    for (const submission of submissions) {
      if (submission.studentId !== user?.id || submission.state !== "Published") continue;
      const current = latest.get(submission.assignmentId);
      if (!current || Date.parse(submission.submittedAt) > Date.parse(current.submittedAt)) latest.set(submission.assignmentId, submission);
    }
    return [...latest.values()]
      .flatMap((submission) => {
        const assignment = assignmentById.get(submission.assignmentId);
        const percent = scorePercent(submission, assignment);
        if (percent === null) return [];
        const point: PerformancePoint & { courseId: string } = {
          id: submission.assignmentId,
          title: assignment?.title ?? "Assignment",
          dueAt: assignment?.dueAt ?? submission.submittedAt,
          student: percent,
          classAverage: null,
          outOf: marksAvailable(submission, assignment),
          courseId: assignment?.courseId ?? "",
        };
        return [point];
      })
      .sort((a, b) => Date.parse(a.dueAt) - Date.parse(b.dueAt));
  }, [assignments, submissions, user?.id]);

  const courseOptions = courses.filter((course) => allPoints.some((point) => point.courseId === course.id));
  const points = courseId === "all" ? allPoints : allPoints.filter((point) => point.courseId === courseId);
  if (!allPoints.length) return null;

  // Chart and summary are in marks out of the total most assignments use (e.g. 20).
  const scale = commonTotal(points.map((point) => point.outOf)) ?? 0;
  const scaled = points.some((point) => point.outOf !== scale);
  const scores = points.map((point) => point.student as number);
  const average = scores.length ? scores.reduce((sum, value) => sum + value, 0) / scores.length : null;
  const latest = points.at(-1) ?? null;
  const previous = points.at(-2) ?? null;
  const best = points.length ? points.reduce((top, point) => ((point.student as number) > (top.student as number) ? point : top)) : null;
  const change = latest && previous ? percentToMarks((latest.student as number) - (previous.student as number), scale) : null;
  const signed = (value: number) => {
    const rounded = Math.round(value * 10) / 10;
    return `${rounded > 0 ? "+" : rounded < 0 ? "ÃƒÂ¢Ã‹â€ Ã¢â‚¬â„¢" : "Ãƒâ€šÃ‚Â±"}${formatMarks(Math.abs(rounded))} mark${Math.abs(rounded) === 1 ? "" : "s"}`;
  };

  return (
    <Panel className="my-progress-card" style={{ padding: "20px 22px" }}>
      <div className="section-heading" style={{ alignItems: "flex-start", gap: 12, flexWrap: "wrap" }}>
        <div>
          <h2>Your marks over time</h2>
          <p>
            Each teacher-approved grade, oldest due date first{scale > 0 && ` (out of ${scale})`}
            {scaled && `. Assignments with a different total are scaled to ${scale} on the graph.`}
          </p>
        </div>
        {courseOptions.length > 1 && (
          <select
            className="field-select"
            aria-label="Show marks for course"
            value={courseId}
            onChange={(event) => setCourseId(event.target.value)}
            style={{ width: "auto", minWidth: 180 }}
          >
            <option value="all">All courses</option>
            {courseOptions.map((course) => (
              <option key={course.id} value={course.id}>{course.name}</option>
            ))}
          </select>
        )}
      </div>

      <div className="perf-tiles">
        <div>
          <span>Average</span>
          <strong style={{ whiteSpace: "nowrap" }}>{average === null ? "—" : formatMarks(percentToMarks(average, scale), scale)}</strong>
          <small>{points.length} graded assignment{points.length === 1 ? "" : "s"}</small>
        </div>
        <div>
          <span>Latest</span>
          <strong style={{ whiteSpace: "nowrap" }}>{latest ? pointMarks(latest.student as number, latest) : "—"}</strong>
          <small>{change !== null ? `${signed(change)} vs previous` : latest?.title ?? ""}</small>
        </div>
        <div>
          <span>Best</span>
          <strong style={{ whiteSpace: "nowrap" }}>{best ? pointMarks(best.student as number, best) : "—"}</strong>
          <small>{best?.title ?? ""}</small>
        </div>
      </div>

      {points.length === 1 && (
        <p className="perf-empty">The line appears once a second grade is published.</p>
      )}
      <ul className="perf-legend">
        <li><i style={{ background: STUDENT_COLOR }} />Your marks</li>
      </ul>
      <PerformanceLineChart points={points} studentName="Your marks" ariaLabel="Your marks by assignment" scale={scale} />

      <details className="analytics-table">
        <summary>Show as table</summary>
        <table>
          <thead>
            <tr><th scope="col">Assignment</th><th scope="col">Due</th><th scope="col">Marks</th></tr>
          </thead>
          <tbody>
            {points.map((point) => (
              <tr key={point.id}>
                <td>{point.title}</td>
                <td>{formatDate(point.dueAt)}</td>
                <td>{pointMarks(point.student as number, point)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </details>
    </Panel>
  );
}
