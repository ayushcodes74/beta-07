import * as Dialog from "@radix-ui/react-dialog";
import { X } from "lucide-react";
import { useEffect, useMemo, useRef, useState, type KeyboardEvent } from "react";
import { useAppState } from "../../App";
import { Button } from "../../components/ui";
import { commonTotal, formatMarks, marksAvailable, percentToMarks, scorePercent } from "../../lib/grades";
import { formatDate } from "../../lib/utils";

/**
 * One assignment on the x-axis: the student's published score and the class average, stored as
 * 0–100 so assignments with different totals share the chart, and shown in marks out of `outOf`.
 */
export interface PerformancePoint {
  id: string;
  title: string;
  dueAt: string;
  student: number | null;
  classAverage: number | null;
  outOf: number;
}

/**
 * The student's published score on each assignment of the course, oldest due date first, next to
 * the class average. Assignments nobody has a published grade for yet are left out.
 */
function usePerformance(courseId: string, studentId: string): PerformancePoint[] {
  const { assignments, submissions } = useAppState();
  return useMemo(() => {
    const courseAssignments = assignments
      .filter((assignment) => assignment.courseId === courseId)
      .sort((a, b) => Date.parse(a.dueAt) - Date.parse(b.dueAt));
    return courseAssignments.flatMap((assignment) => {
      const graded = submissions
        .filter((submission) => submission.assignmentId === assignment.id)
        .map((submission) => ({ submission, percent: scorePercent(submission, assignment) }))
        .filter((item): item is { submission: typeof item.submission; percent: number } => item.percent !== null);
      if (!graded.length) return [];
      // A student can resubmit; the most recent published one is their grade.
      const own = graded
        .filter((item) => item.submission.studentId === studentId)
        .sort((a, b) => Date.parse(b.submission.submittedAt) - Date.parse(a.submission.submittedAt))[0];
      return [{
        id: assignment.id,
        title: assignment.title,
        dueAt: assignment.dueAt,
        student: own ? own.percent : null,
        classAverage: graded.reduce((sum, item) => sum + item.percent, 0) / graded.length,
        outOf: commonTotal(graded.map((item) => marksAvailable(item.submission, assignment))) ?? assignment.totalMarks,
      }];
    });
  }, [assignments, submissions, courseId, studentId]);
}

/** Tracks an element's rendered width so the SVG draws at true pixel size (crisp text and lines). */
function useWidth<T extends HTMLElement>() {
  const ref = useRef<T>(null);
  const [width, setWidth] = useState(0);
  useEffect(() => {
    const element = ref.current;
    if (!element) return;
    const observer = new ResizeObserver(([entry]) => setWidth(Math.floor(entry.contentRect.width)));
    observer.observe(element);
    return () => observer.disconnect();
  }, []);
  return [ref, width] as const;
}

const HEIGHT = 250;
const MARGIN = { top: 14, right: 46, bottom: 42, left: 40 };
const TICKS = [0, 25, 50, 75, 100]; // % of the scale; labelled in marks (0, 5, 10, 15, 20 out of 20)
export const STUDENT_COLOR = "#2E7D4F"; // validated series hue (shared with Class analytics)
const AVERAGE_COLOR = "#A3AFA6"; // de-emphasised reference line

const truncate = (text: string, max: number) => (text.length > max ? `${text.slice(0, Math.max(1, max - 1))}…` : text);

/** Line path through the points that have a value; a missing grade breaks the line instead of bridging it. */
function linePath(values: (number | null)[], x: (i: number) => number, y: (v: number) => number) {
  let path = "";
  let drawing = false;
  values.forEach((value, index) => {
    if (value === null) {
      drawing = false;
      return;
    }
    path += `${drawing ? "L" : "M"}${x(index).toFixed(1)},${y(value).toFixed(1)}`;
    drawing = true;
  });
  return path;
}

/** A point's score in its own assignment's marks, e.g. "10.3 / 20". */
export const pointMarks = (percent: number, point: PerformancePoint) => formatMarks(percentToMarks(percent, point.outOf), point.outOf);

/**
 * Line chart of one student's marks by assignment, plus the class average where `classAverage` is
 * set (the student's own view has no class data, so that line and tooltip row are simply absent).
 */
export function PerformanceLineChart({
  points,
  studentName,
  scale,
  ariaLabel,
}: {
  points: PerformancePoint[];
  studentName: string;
  scale: number;
  ariaLabel?: string;
}) {
  const [ref, width] = useWidth<HTMLDivElement>();
  const [active, setActive] = useState<number | null>(null);
  const plotWidth = Math.max(0, width - MARGIN.left - MARGIN.right);
  const plotHeight = HEIGHT - MARGIN.top - MARGIN.bottom;
  const count = points.length;
  const slot = count > 1 ? plotWidth / (count - 1) : plotWidth;
  const x = (index: number) => MARGIN.left + (count > 1 ? index * slot : plotWidth / 2);
  const y = (value: number) => MARGIN.top + plotHeight - (value / 100) * plotHeight;

  // Label every assignment when there is room, otherwise every n-th (the tooltip and table have all).
  const labelEvery = Math.max(1, Math.ceil(56 / Math.max(slot, 1)));
  const labelChars = Math.max(4, Math.floor(Math.min(slot * labelEvery, 140) / 6.4));
  let lastStudentIndex = -1;
  points.forEach((point, index) => {
    if (point.student !== null) lastStudentIndex = index;
  });

  const onKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    if (!count) return;
    if (event.key === "ArrowRight") setActive((current) => Math.min(count - 1, (current ?? -1) + 1));
    else if (event.key === "ArrowLeft") setActive((current) => Math.max(0, (current ?? count) - 1));
    else if (event.key === "Escape") setActive(null);
    else return;
    event.preventDefault();
  };

  const activePoint = active === null ? null : points[active];
  // The tooltip sits beside the crosshair (never on top of the lines it describes), flipping to the
  // left of it on the right half of the chart.
  const flip = active !== null && x(active) > width / 2;
  const tooltipStyle = active === null ? undefined : flip
    ? { right: width - x(active) + 12 }
    : { left: x(active) + 12 };

  return (
    <div
      ref={ref}
      className="perf-chart"
      tabIndex={0}
      role="img"
      aria-label={`${ariaLabel ?? `${studentName}'s marks by assignment`}, out of ${scale}. Use the arrow keys to read each assignment.`}
      onKeyDown={onKeyDown}
      onBlur={() => setActive(null)}
      onMouseLeave={() => setActive(null)}
    >
      {width > 0 && (
        <svg width={width} height={HEIGHT} aria-hidden="true">
          {TICKS.map((tick) => (
            <g key={tick}>
              <line x1={MARGIN.left} x2={MARGIN.left + plotWidth} y1={y(tick)} y2={y(tick)} className={tick === 0 ? "perf-baseline" : "perf-grid"} />
              <text x={MARGIN.left - 8} y={y(tick)} dy="0.32em" textAnchor="end" className="perf-tick">{formatMarks(percentToMarks(tick, scale))}</text>
            </g>
          ))}
          {points.map((point, index) =>
            index % labelEvery === 0 || index === count - 1 ? (
              <text key={point.id} x={x(index)} y={MARGIN.top + plotHeight + 20} textAnchor="middle" className="perf-tick perf-xlabel">
                {truncate(point.title, labelChars)}
              </text>
            ) : null,
          )}

          {active !== null && (
            <line x1={x(active)} x2={x(active)} y1={MARGIN.top} y2={MARGIN.top + plotHeight} className="perf-crosshair" />
          )}

          <path d={linePath(points.map((p) => p.classAverage), x, y)} fill="none" stroke={AVERAGE_COLOR} strokeWidth={2} strokeLinejoin="round" strokeLinecap="round" />
          <path d={linePath(points.map((p) => p.student), x, y)} fill="none" stroke={STUDENT_COLOR} strokeWidth={2} strokeLinejoin="round" strokeLinecap="round" />

          {points.map((point, index) => (
            <g key={point.id}>
              {point.classAverage !== null && (
                <circle cx={x(index)} cy={y(point.classAverage)} r={active === index ? 5 : 4} fill={AVERAGE_COLOR} stroke="#FFFFFF" strokeWidth={2} />
              )}
              {point.student !== null && (
                <circle cx={x(index)} cy={y(point.student)} r={active === index ? 5.5 : 4.5} fill={STUDENT_COLOR} stroke="#FFFFFF" strokeWidth={2} />
              )}
            </g>
          ))}

          {/* Direct label on the student's latest score only. */}
          {lastStudentIndex >= 0 && points[lastStudentIndex].student !== null && (
            <text x={x(lastStudentIndex) + 10} y={y(points[lastStudentIndex].student!)} dy="0.32em" className="perf-end-label">
              {formatMarks(percentToMarks(points[lastStudentIndex].student!, scale))}
            </text>
          )}

          {/* Hit areas: one full-height column per assignment, wider than the marks. */}
          {points.map((point, index) => (
            <rect
              key={point.id}
              x={x(index) - Math.max(slot, 24) / 2}
              y={MARGIN.top}
              width={Math.max(slot, 24)}
              height={plotHeight}
              fill="transparent"
              onMouseEnter={() => setActive(index)}
            />
          ))}
        </svg>
      )}

      {activePoint && (
        <div className="perf-tooltip" style={tooltipStyle} role="presentation">
          <strong>{activePoint.title}</strong>
          <small>Due {formatDate(activePoint.dueAt)}</small>
          <span>
            <i style={{ background: STUDENT_COLOR }} />
            {studentName}
            <b>{activePoint.student === null ? "No grade" : pointMarks(activePoint.student, activePoint)}</b>
          </span>
          {activePoint.classAverage !== null && (
            <span>
              <i style={{ background: AVERAGE_COLOR }} />
              Class average
              <b>{pointMarks(activePoint.classAverage, activePoint)}</b>
            </span>
          )}
        </div>
      )}
    </div>
  );
}

/** A difference between two 0–100 scores, in marks out of `outOf`: "+1.5 marks". */
function signedMarks(percentDiff: number, outOf: number) {
  const value = Math.round(percentToMarks(percentDiff, outOf) * 10) / 10;
  return `${value > 0 ? "+" : value < 0 ? "−" : "±"}${formatMarks(Math.abs(value))} mark${Math.abs(value) === 1 ? "" : "s"}`;
}

export function StudentPerformanceDialog({
  courseId,
  student,
  onClose,
}: {
  courseId: string;
  student: { id: string; name: string } | null;
  onClose: () => void;
}) {
  return (
    <Dialog.Root open={student !== null} onOpenChange={(open) => !open && onClose()}>
      <Dialog.Portal>
        <Dialog.Overlay className="modal-backdrop" />
        <Dialog.Content className="modal performance-modal" aria-describedby={undefined}>
          {student && <PerformanceBody courseId={courseId} student={student} />}
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}

function PerformanceBody({ courseId, student }: { courseId: string; student: { id: string; name: string } }) {
  const points = usePerformance(courseId, student.id);
  const graded = points.filter((point) => point.student !== null) as (PerformancePoint & { student: number })[];
  const average = graded.length ? graded.reduce((sum, point) => sum + point.student, 0) / graded.length : null;
  const latest = graded.at(-1) ?? null;
  const previous = graded.at(-2) ?? null;
  const vsClass = graded.length
    ? graded.reduce((sum, point) => sum + (point.student - (point.classAverage ?? point.student)), 0) / graded.length
    : null;
  // The chart and course-wide figures are in marks out of the total most assignments use (e.g. 20).
  const scale = commonTotal(points.map((point) => point.outOf)) ?? 0;
  const scaled = points.some((point) => point.outOf !== scale);

  return (
    <>
      <div className="modal-head">
        <div>
          <Dialog.Title className="modal-title">{student.name}</Dialog.Title>
          <p className="perf-subtitle">
            Marks on each assignment in this course{points.length > 0 && ` (out of ${scale})`}, from published grades
            {scaled && `. Assignments with a different total are scaled to ${scale} on the chart.`}
          </p>
        </div>
        <Dialog.Close asChild>
          <Button variant="quiet" size="icon" aria-label="Close">
            <X size={16} />
          </Button>
        </Dialog.Close>
      </div>

      {!points.length ? (
        <p className="perf-empty">No grades have been published for this course yet.</p>
      ) : (
        <>
          <div className="perf-tiles">
            <div>
              <span>Average</span>
              <strong>{average === null ? "—" : formatMarks(percentToMarks(average, scale), scale)}</strong>
              <small>{graded.length} of {points.length} assignment{points.length === 1 ? "" : "s"} graded</small>
            </div>
            <div>
              <span>Latest</span>
              <strong>{latest ? pointMarks(latest.student, latest) : "—"}</strong>
              <small>{latest && previous ? `${signedMarks(latest.student - previous.student, scale)} vs previous` : latest ? truncate(latest.title, 28) : "No grade yet"}</small>
            </div>
            <div>
              <span>Vs class average</span>
              <strong>{vsClass === null ? "—" : signedMarks(vsClass, scale)}</strong>
              <small>Average gap on the same assignments</small>
            </div>
          </div>

          {graded.length === 0 && <p className="perf-empty">This student has no published grades yet; the grey line is the class average.</p>}

          <ul className="perf-legend">
            <li><i style={{ background: STUDENT_COLOR }} />{student.name}</li>
            <li><i style={{ background: AVERAGE_COLOR }} />Class average</li>
          </ul>
          <PerformanceLineChart points={points} studentName={student.name} scale={scale} />

          <details className="analytics-table">
            <summary>Show as table</summary>
            <table>
              <thead>
                <tr><th scope="col">Assignment</th><th scope="col">Due</th><th scope="col">Score</th><th scope="col">Class average</th></tr>
              </thead>
              <tbody>
                {points.map((point) => (
                  <tr key={point.id}>
                    <td>{point.title}</td>
                    <td>{formatDate(point.dueAt)}</td>
                    <td>{point.student === null ? "No grade" : pointMarks(point.student, point)}</td>
                    <td>{point.classAverage === null ? "—" : pointMarks(point.classAverage, point)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </details>
        </>
      )}
    </>
  );
}
