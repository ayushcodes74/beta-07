import { useMemo } from "react";
import { Panel } from "../../components/ui";
import type { Assignment, Submission } from "../../types/models";
import { formatPercent, scorePercent } from "../../lib/grades";

/**
 * Class analytics for the teacher overview, computed in the browser from the submissions and
 * published grades the app already loads (no extra request). Only *published* grades count toward
 * scores: AI suggestions the teacher hasn't approved yet are shown as a pipeline stage, never averaged.
 *
 * Plain HTML/CSS bars (no chart library) keep the overview page light.
 */

const BANDS = [
  { grade: "A", min: 90, range: "90–100%" },
  { grade: "B", min: 80, range: "80–89%" },
  { grade: "C", min: 70, range: "70–79%" },
  { grade: "D", min: 60, range: "60–69%" },
  { grade: "F", min: -Infinity, range: "below 60%" },
] as const;

/** Grading pipeline, in order. Colors are a validated light→dark ordinal ramp (see styles.css). */
const STAGES = [
  { key: "awaiting", label: "Awaiting grading", hint: "Submitted, reading the answer sheet or in review" },
  { key: "approval", label: "AI graded, needs approval", hint: "Waiting for you to approve and publish" },
  { key: "published", label: "Published", hint: "Final grade visible to the student" },
] as const;
type StageKey = (typeof STAGES)[number]["key"];

function stageOf(submission: Submission): StageKey | null {
  if (submission.state === "Published") return "published";
  if (submission.state === "Graded") return "approval";
  if (submission.state === "Rejected") return null; // turned down (e.g. rejected late work): not in the pipeline
  return "awaiting";
}

const fmtPct = formatPercent;
const median = (values: number[]) => {
  const sorted = [...values].sort((a, b) => a - b);
  const mid = Math.floor(sorted.length / 2);
  return sorted.length % 2 ? sorted[mid] : (sorted[mid - 1] + sorted[mid]) / 2;
};

export function ClassAnalytics({ submissions, assignments }: { submissions: Submission[]; assignments: Assignment[] }) {
  const stats = useMemo(() => {
    const assignmentById = new Map(assignments.map((a) => [a.id, a]));
    const scored: { submission: Submission; percent: number }[] = [];
    const stageCounts: Record<StageKey, number> = { awaiting: 0, approval: 0, published: 0 };
    for (const submission of submissions) {
      const stage = stageOf(submission);
      if (stage) stageCounts[stage] += 1;
      const percent = scorePercent(submission, assignmentById.get(submission.assignmentId));
      if (percent !== null) scored.push({ submission, percent });
    }
    const percents = scored.map((item) => item.percent);

    const distribution = BANDS.map((band, index) => ({
      ...band,
      count: percents.filter((p) => p >= band.min && (index === 0 || p < BANDS[index - 1].min)).length,
    }));

    // Average per assignment, most recently due first (the ones a teacher is thinking about).
    const byAssignment = new Map<string, number[]>();
    for (const { submission, percent } of scored) {
      byAssignment.set(submission.assignmentId, [...(byAssignment.get(submission.assignmentId) ?? []), percent]);
    }
    const perAssignment = [...byAssignment.entries()]
      .map(([id, values]) => ({
        id,
        title: assignmentById.get(id)?.title ?? "Untitled assignment",
        dueAt: assignmentById.get(id)?.dueAt ?? "",
        graded: values.length,
        average: values.reduce((sum, v) => sum + v, 0) / values.length,
      }))
      .sort((a, b) => Date.parse(b.dueAt || "0") - Date.parse(a.dueAt || "0"))
      .slice(0, 6);

    return {
      count: percents.length,
      average: percents.length ? percents.reduce((sum, v) => sum + v, 0) / percents.length : null,
      median: percents.length ? median(percents) : null,
      passRate: percents.length ? (percents.filter((p) => p >= 60).length / percents.length) * 100 : null,
      distribution,
      perAssignment,
      stageCounts,
      inPipeline: stageCounts.awaiting + stageCounts.approval + stageCounts.published,
    };
  }, [submissions, assignments]);

  const maxBand = Math.max(1, ...stats.distribution.map((band) => band.count));

  return (
    <Panel className="analytics-card">
      <div className="section-heading">
        <div>
          <h2>Class analytics</h2>
          <p>Calculated from published grades across your courses</p>
        </div>
      </div>

      {stats.inPipeline === 0 ? (
        <p className="analytics-empty">Analytics appear here once students start submitting work.</p>
      ) : (
        <>
          <div className="analytics-tiles">
            <div className="analytics-tile">
              <span>Class average</span>
              <strong>{stats.average === null ? "—" : fmtPct(stats.average)}</strong>
              <small>
                {stats.count ? `${stats.count} published grade${stats.count === 1 ? "" : "s"}` : "No grades published yet"}
              </small>
            </div>
            <div className="analytics-tile">
              <span>Median score</span>
              <strong>{stats.median === null ? "—" : fmtPct(stats.median)}</strong>
              <small>Half the class scored at or above this</small>
            </div>
            <div className="analytics-tile">
              <span>Pass rate</span>
              <strong>{stats.passRate === null ? "—" : fmtPct(stats.passRate)}</strong>
              <small>Scored 60% or more</small>
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
                    title={`${stage.label}: ${value} (${fmtPct(share)})`}
                  >
                    {/* Only print the share when the block is wide enough to hold it. */}
                    {share >= 12 && <b>{fmtPct(share)}</b>}
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
                  <small>Students per grade band</small>
                </div>
                <div className="column-chart" role="list">
                  {stats.distribution.map((band) => (
                    <div
                      className="column-slot"
                      role="listitem"
                      key={band.grade}
                      tabIndex={0}
                      aria-label={`Grade ${band.grade} (${band.range}): ${band.count}`}
                      title={`Grade ${band.grade} (${band.range}): ${band.count} student${band.count === 1 ? "" : "s"}`}
                    >
                      <span className="column-value">{band.count}</span>
                      <span className="column-track">
                        <span className="column-bar" style={{ height: `${(band.count / maxBand) * 100}%` }} />
                      </span>
                      <span className="column-label">{band.grade}</span>
                    </div>
                  ))}
                </div>
                <small className="analytics-note">A 90%+ · B 80–89 · C 70–79 · D 60–69 · F below 60</small>
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
                      aria-label={`${row.title}: average ${fmtPct(row.average)} from ${row.graded} graded`}
                      title={`${row.title}: average ${fmtPct(row.average)} (${row.graded} graded)`}
                    >
                      <span className="bar-row-label">
                        <strong>{row.title}</strong>
                        <small>{row.graded} graded</small>
                      </span>
                      <span className="bar-row-track">
                        <span className="bar-row-fill" style={{ width: `${row.average}%` }} />
                        <span className="bar-row-value">{fmtPct(row.average)}</span>
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
              <thead><tr><th scope="col">Grade</th><th scope="col">Range</th><th scope="col">Students</th></tr></thead>
              <tbody>
                {stats.distribution.map((band) => (
                  <tr key={band.grade}><td>{band.grade}</td><td>{band.range}</td><td>{band.count}</td></tr>
                ))}
              </tbody>
            </table>
            <table>
              <caption>Average by assignment</caption>
              <thead><tr><th scope="col">Assignment</th><th scope="col">Graded</th><th scope="col">Average</th></tr></thead>
              <tbody>
                {stats.perAssignment.map((row) => (
                  <tr key={row.id}><td>{row.title}</td><td>{row.graded}</td><td>{fmtPct(row.average)}</td></tr>
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
