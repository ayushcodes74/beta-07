import { useMemo } from "react";
import { Panel } from "../../components/ui";
import type { Assignment, Submission } from "../../types/models";
import { commonTotal, formatMarks, marksAvailable, percentToMarks, scorePercent } from "../../lib/grades";

/**
 * Class analytics for the teacher overview, computed in the browser from the submissions and
 * published grades the app already loads (no extra request). Only *published* grades count toward
 * scores: AI suggestions the teacher hasn't approved yet are shown as a pipeline stage, never averaged.
 *
 * Scores are shown in marks (e.g. "12.5 / 20"), not percentages. Class-wide figures use the total
 * most assignments are marked out of; a grade from an assignment with a different total is scaled
 * to it, and the panel says so.
 *
 * Plain HTML/CSS bars (no chart library) keep the overview page light.
 */

/** Grade bands by share of the marks available; labelled in marks out of the class total. */
const BANDS = [
  { grade: "A", min: 90 },
  { grade: "B", min: 80 },
  { grade: "C", min: 70 },
  { grade: "D", min: 60 },
  { grade: "F", min: -Infinity },
] as const;
const PASS_PERCENT = 60;

/** Grading pipeline, in order. Colors are a validated lightÃƒÂ¢Ã¢â‚¬Â Ã¢â‚¬â„¢dark ordinal ramp (see styles.css). */
const STAGES = [
  { key: "awaiting", label: "Awaiting grading", hint: "Submitted, reading the answer sheet or in review" },
  { key: "approval", label: "AI graded, needs approval", hint: "Waiting for you to approve and publish" },
  { key: "published", label: "Published", hint: "Final grade visible to the student" },
] as const;
type StageKey = (typeof STAGES)[number]["key"];

function stageOf(submission: Submission): StageKey | null {
  if (submission.state === "Published") return "published";
  // Late work the teacher turned down is never graded, so it isn't part of the pipeline.
  if (submission.state === "Rejected" || submission.late?.status === "rejected") return null;
  // AI-checked, awaiting approval (the list marks these "Graded" from grading_results).
  if (submission.state === "Graded") return "approval";
  return "awaiting";
}

const median = (values: number[]) => {
  const sorted = [...values].sort((a, b) => a - b);
  const mid = Math.floor(sorted.length / 2);
  return sorted.length % 2 ? sorted[mid] : (sorted[mid - 1] + sorted[mid]) / 2;
};

export function ClassAnalytics({ submissions, assignments }: { submissions: Submission[]; assignments: Assignment[] }) {
  const stats = useMemo(() => {
    const assignmentById = new Map(assignments.map((a) => [a.id, a]));
    const scored: { submission: Submission; percent: number; outOf: number }[] = [];
    const stageCounts: Record<StageKey, number> = { awaiting: 0, approval: 0, published: 0 };
    for (const submission of submissions) {
      const stage = stageOf(submission);
      if (stage) stageCounts[stage] += 1;
      const assignment = assignmentById.get(submission.assignmentId);
      const percent = scorePercent(submission, assignment);
      if (percent !== null) scored.push({ submission, percent, outOf: marksAvailable(submission, assignment) });
    }
    const percents = scored.map((item) => item.percent);
    // Class-wide figures are in marks out of the total most grades use (e.g. 20).
    const outOf = commonTotal(scored.map((item) => item.outOf));
    const scaled = outOf !== null && scored.some((item) => item.outOf !== outOf);

    const distribution = BANDS.map((band, index) => ({
      ...band,
      count: percents.filter((p) => p >= band.min && (index === 0 || p < BANDS[index - 1].min)).length,
    }));

    // Average per assignment, most recently due first (the ones a teacher is thinking about).
    const byAssignment = new Map<string, { percents: number[]; totals: number[] }>();
    for (const { submission, percent, outOf: total } of scored) {
      const entry = byAssignment.get(submission.assignmentId) ?? { percents: [], totals: [] };
      entry.percents.push(percent);
      entry.totals.push(total);
      byAssignment.set(submission.assignmentId, entry);
    }
    const perAssignment = [...byAssignment.entries()]
      .map(([id, entry]) => ({
        id,
        title: assignmentById.get(id)?.title ?? "Untitled assignment",
        dueAt: assignmentById.get(id)?.dueAt ?? "",
        graded: entry.percents.length,
        average: entry.percents.reduce((sum, v) => sum + v, 0) / entry.percents.length,
        outOf: commonTotal(entry.totals) ?? 0,
      }))
      .sort((a, b) => Date.parse(b.dueAt || "0") - Date.parse(a.dueAt || "0"))
      .slice(0, 6);

    return {
      count: percents.length,
      outOf,
      scaled,
      average: percents.length ? percents.reduce((sum, v) => sum + v, 0) / percents.length : null,
      median: percents.length ? median(percents) : null,
      passed: percents.filter((p) => p >= PASS_PERCENT).length,
      distribution,
      perAssignment,
      stageCounts,
      inPipeline: stageCounts.awaiting + stageCounts.approval + stageCounts.published,
    };
  }, [submissions, assignments]);

  const maxBand = Math.max(1, ...stats.distribution.map((band) => band.count));
  // Only read when a grade exists, so `outOf` is set.
  const total = stats.outOf ?? 0;
  const inMarks = (percent: number) => formatMarks(percentToMarks(percent, total), total);
  const threshold = (percent: number) => formatMarks(percentToMarks(percent, total));
  const bandRange = (index: number) => {
    const band = BANDS[index];
    if (index === 0) return `${threshold(band.min)} or more`;
    if (band.min === -Infinity) return `under ${threshold(BANDS[index - 1].min)}`;
    return `${threshold(band.min)} to under ${threshold(BANDS[index - 1].min)}`;
  };
  const bandKey = BANDS.map((band, index) =>
    band.min === -Infinity ? `${band.grade} under ${threshold(BANDS[index - 1].min)}` : `${band.grade} ${threshold(band.min)}+`,
  ).join(" Ãƒâ€šÃ‚Â· ");

  return (
    <Panel className="analytics-card">
      <div className="section-heading">
        <div>
          <h2>Class analytics</h2>
          <p>
            Calculated from published grades across your courses
            {stats.count > 0 && `, in marks out of ${total}`}
            {stats.scaled && `. Grades from assignments with a different total are scaled to ${total}.`}
          </p>
        </div>
      </div>

      {stats.inPipeline === 0 ? (
        <p className="analytics-empty">Analytics appear here once students start submitting work.</p>
      ) : (
        <>
          <div className="analytics-tiles">
            <div className="analytics-tile">
              <span>Class average</span>
              <strong>{stats.average === null ? "—" : inMarks(stats.average)}</strong>
              <small>
                {stats.count ? `${stats.count} published grade${stats.count === 1 ? "" : "s"}` : "No grades published yet"}
              </small>
            </div>
            <div className="analytics-tile">
              <span>Median score</span>
              <strong>{stats.median === null ? "—" : inMarks(stats.median)}</strong>
              <small>Half of published grades are at or above this</small>
            </div>
            <div className="analytics-tile">
              <span>Passed</span>
              <strong>{stats.count ? `${stats.passed} of ${stats.count}` : "—"}</strong>
              <small>{stats.count ? `Scored ${threshold(PASS_PERCENT)} / ${total} or more` : "No grades published yet"}</small>
            </div>
            <div className="analytics-tile">
              <span>Needs your approval</span>
              <strong>{stats.stageCounts.approval}</strong>
              <small>AI-graded, not yet published</small>
            </div>
          </div>

          <div className="analytics-block">
            <div className="analytics-block-head">
              <h3>Grading progress</h3>
              <small>{stats.inPipeline} submission{stats.inPipeline === 1 ? "" : "s"}</small>
            </div>
            <div
              className="segmented-bar"
              role="img"
              aria-label={STAGES.map((s) => `${s.label}: ${stats.stageCounts[s.key]}`).join(", ")}
            >
              {STAGES.map((stage) => {
                const value = stats.stageCounts[stage.key];
                if (!value) return null;
                const share = (value / stats.inPipeline) * 100;
                return (
                  <span
                    key={stage.key}
                    className={`segment segment-${stage.key}`}
                    style={{ flexGrow: value }}
                    title={`${stage.label}: ${value} of ${stats.inPipeline} submissions`}
                  >
                    {/* Only print the count when the block is wide enough to hold it. */}
                    {share >= 12 && <b>{value}</b>}
                  </span>
                );
              })}
            </div>
            <ul className="analytics-legend">
              {STAGES.map((stage) => (
                <li key={stage.key} title={stage.hint}>
                  <i className={`swatch segment-${stage.key}`} aria-hidden="true" />
                  {stage.label} <span>{stats.stageCounts[stage.key]}</span>
                </li>
              ))}
            </ul>
          </div>

          {stats.count === 0 ? (
            <p className="analytics-empty">Score charts appear after you publish the first grade.</p>
          ) : (
            <div className="analytics-charts">
              <div className="analytics-block">
                <div className="analytics-block-head">
                  <h3>Grade distribution</h3>
                  <small>Published grades per band</small>
                </div>
                <div className="column-chart" role="list">
                  {stats.distribution.map((band, index) => (
                    <div
                      className="column-slot"
                      role="listitem"
                      key={band.grade}
                      tabIndex={0}
                      aria-label={`Grade ${band.grade} (${bandRange(index)} out of ${total}): ${band.count}`}
                      title={`Grade ${band.grade} (${bandRange(index)} out of ${total}): ${band.count} grade${band.count === 1 ? "" : "s"}`}
                    >
                      <span className="column-value">{band.count}</span>
                      <span className="column-track">
                        <span className="column-bar" style={{ height: `${(band.count / maxBand) * 100}%` }} />
                      </span>
                      <span className="column-label">{band.grade}</span>
                    </div>
                  ))}
                </div>
                <small className="analytics-note">Out of {total} Ãƒâ€šÃ‚Â· {bandKey}</small>
              </div>

              <div className="analytics-block">
                <div className="analytics-block-head">
                  <h3>Average by assignment</h3>
                  <small>Most recently due</small>
                </div>
                <div className="bar-list">
                  {stats.perAssignment.map((row) => (
                    <div
                      className="bar-row"
                      key={row.id}
                      tabIndex={0}
                      aria-label={`${row.title}: average ${formatMarks(percentToMarks(row.average, row.outOf), row.outOf)} from ${row.graded} graded`}
                      title={`${row.title}: average ${formatMarks(percentToMarks(row.average, row.outOf), row.outOf)} (${row.graded} graded)`}
                    >
                      <span className="bar-row-label">
                        <strong>{row.title}</strong>
                        <small>{row.graded} graded</small>
                      </span>
                      <span className="bar-row-track">
                        <span className="bar-row-fill" style={{ width: `${row.average}%` }} />
                        <span className="bar-row-value">{formatMarks(percentToMarks(row.average, row.outOf), row.outOf)}</span>
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          )}

          <details className="analytics-table">
            <summary>Show as table</summary>
            <table>
              <caption>Grade distribution</caption>
              <thead><tr><th scope="col">Grade</th><th scope="col">Marks (out of {total})</th><th scope="col">Grades</th></tr></thead>
              <tbody>
                {stats.distribution.map((band, index) => (
                  <tr key={band.grade}><td>{band.grade}</td><td>{bandRange(index)}</td><td>{band.count}</td></tr>
                ))}
              </tbody>
            </table>
            <table>
              <caption>Average by assignment</caption>
              <thead><tr><th scope="col">Assignment</th><th scope="col">Graded</th><th scope="col">Average</th></tr></thead>
              <tbody>
                {stats.perAssignment.map((row) => (
                  <tr key={row.id}><td>{row.title}</td><td>{row.graded}</td><td>{formatMarks(percentToMarks(row.average, row.outOf), row.outOf)}</td></tr>
                ))}
              </tbody>
            </table>
            <table>
              <caption>Grading progress</caption>
              <thead><tr><th scope="col">Stage</th><th scope="col">Submissions</th></tr></thead>
              <tbody>
                {STAGES.map((stage) => (
                  <tr key={stage.key}><td>{stage.label}</td><td>{stats.stageCounts[stage.key]}</td></tr>
                ))}
              </tbody>
            </table>
          </details>
        </>
      )}
    </Panel>
  );
}
