import { useEffect, useState } from "react";
import { Award, Crown, Medal, RefreshCw, Trophy } from "lucide-react";
import { useAppState } from "../../App";
import { Avatar, Badge, Button, Panel } from "../../components/ui";
import { formatDate } from "../../lib/utils";
import { extractErrorMessage, leaderboardService, type CourseLeaderboard, type LeaderboardStanding } from "../../services/api";

const initialsOf = (name: string) =>
  name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((word) => word[0]?.toUpperCase())
    .join("") || "S";

const marks = (value: number) => (Number.isInteger(value) ? String(value) : value.toFixed(1));

const PODIUM_ICONS = [Crown, Trophy, Medal];

export function LeaderboardPage() {
  const { user, courses } = useAppState();
  const student = user?.role === "student";
  const [courseId, setCourseId] = useState<string>(courses[0]?.id ?? "");
  const [board, setBoard] = useState<CourseLeaderboard | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [reload, setReload] = useState(0);

  // Keep a valid selection when the course list loads or changes.
  useEffect(() => {
    if (!courses.some((course) => course.id === courseId)) setCourseId(courses[0]?.id ?? "");
  }, [courses, courseId]);

  useEffect(() => {
    if (!courseId) return;
    let active = true;
    setLoading(true);
    setError("");
    leaderboardService
      .getCourseLeaderboard(courseId)
      .then((result) => active && setBoard(result))
      .catch((reason: unknown) => {
        if (!active) return;
        setBoard(null);
        setError(extractErrorMessage(reason, "Could not load the leaderboard."));
      })
      .finally(() => active && setLoading(false));
    return () => {
      active = false;
    };
  }, [courseId, reload]);

  const hasResults = !!board && board.assignments_counted > 0;
  const me = board?.entries.find((entry) => entry.is_you);
  const podium = hasResults ? board!.entries.filter((entry) => entry.total_score > 0).slice(0, 3) : [];

  return (
    <>
      <div className="page-heading">
        <div>
          <div className="eyebrow">ACADEMIC EXCELLENCE</div>
          <h1>Leaderboard</h1>
          <p className="page-subtitle">
            Course standings by total marks earned. Only grades your teacher has published are counted.
          </p>
        </div>
        {courseId && (
          <div className="heading-actions">
            <Button variant="secondary" disabled={loading} onClick={() => setReload((n) => n + 1)}>
              <RefreshCw size={14} className={loading ? "spin" : undefined} />
              Refresh
            </Button>
          </div>
        )}
      </div>

      {courses.length === 0 ? (
        <Panel className="leaderboard-empty">
          <Award size={34} />
          <h3>No courses yet</h3>
          <p>{student ? "Join a course to see its leaderboard." : "Create a course and publish grades to see standings."}</p>
        </Panel>
      ) : (
        <>
          {courses.length > 1 && (
            <div className="toolbar">
              <div className="segmented leaderboard-courses" role="tablist" aria-label="Course">
                {courses.map((course) => (
                  <button
                    key={course.id}
                    role="tab"
                    aria-selected={course.id === courseId}
                    className={course.id === courseId ? "segment active" : "segment"}
                    onClick={() => setCourseId(course.id)}
                  >
                    {course.name}
                  </button>
                ))}
              </div>
            </div>
          )}

          {error && <p role="alert" className="form-error">{error}</p>}
          {loading && !board && <p role="status" className="leaderboard-loading">Loading standings…</p>}

          {board && !hasResults && (
            <Panel className="leaderboard-empty">
              <Award size={34} />
              <h3>No published grades in {board.course_name} yet</h3>
              <p>
                {student
                  ? "Standings appear once your teacher publishes grades for this course."
                  : "Publish grades from the grading review page and standings will appear here."}
              </p>
            </Panel>
          )}

          {board && hasResults && (
            <>
              {student && me && <YourStanding me={me} board={board} />}

              {podium.length > 0 && (
                <div className="leaderboard-podium">
                  {podium.map((entry, index) => {
                    const Icon = PODIUM_ICONS[Math.min(entry.rank, 3) - 1] ?? Medal;
                    return (
                      <Panel key={entry.student_id} className={`podium-card podium-${Math.min(entry.rank, 3)}${entry.is_you ? " is-you" : ""}`}>
                        <span className="podium-icon"><Icon size={18} /></span>
                        <Avatar name={entry.name} initials={initialsOf(entry.name)} />
                        <strong>{entry.name}{entry.is_you && " (you)"}</strong>
                        <span className="podium-score">
                          {marks(entry.total_score)} <small>/ {marks(board.total_possible)}</small>
                        </span>
                        <Badge tone={index === 0 ? "sage" : "neutral"}>#{entry.rank}</Badge>
                      </Panel>
                    );
                  })}
                </div>
              )}

              <Panel className="leaderboard-panel">
                <div className="section-heading">
                  <div>
                    <h2>{board.course_name}</h2>
                    <p>
                      {board.entries.length} student{board.entries.length === 1 ? "" : "s"} · {board.assignments_counted}{" "}
                      graded assignment{board.assignments_counted === 1 ? "" : "s"} · {marks(board.total_possible)} marks available
                    </p>
                  </div>
                </div>
                <div className="table-scroll">
                  <table className="data-table leaderboard-table">
                    <thead>
                      <tr>
                        <th>Rank</th>
                        <th>Student</th>
                        <th>Total marks</th>
                        <th>Share of marks</th>
                        <th>Graded</th>
                        <th>Last result</th>
                      </tr>
                    </thead>
                    <tbody>
                      {board.entries.map((entry) => (
                        <tr key={entry.student_id} className={entry.is_you ? "leaderboard-you" : undefined}>
                          <td className="leaderboard-rank">#{entry.rank}</td>
                          <td>
                            <span className="student-name">
                              <Avatar name={entry.name} initials={initialsOf(entry.name)} />
                              {entry.name}
                              {entry.is_you && <Badge tone="sage">You</Badge>}
                            </span>
                          </td>
                          <td className="score-cell">
                            {marks(entry.total_score)} / {marks(board.total_possible)}
                          </td>
                          <td>
                            <div className="leaderboard-bar" aria-label={`${entry.percentage ?? 0}% of available marks`}>
                              <span style={{ width: `${Math.min(100, entry.percentage ?? 0)}%` }} />
                            </div>
                            <small className="leaderboard-pct">{entry.percentage ?? 0}%</small>
                          </td>
                          <td>
                            {entry.assignments_graded} / {board.assignments_counted}
                          </td>
                          <td>{entry.last_published_at ? formatDate(entry.last_published_at) : "—"}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                <p className="leaderboard-footnote">
                  Ranked by total marks from published grades. Students with equal totals share a rank. Assignments
                  without any published grade are not counted yet.
                </p>
              </Panel>
            </>
          )}
        </>
      )}
    </>
  );
}

function YourStanding({ me, board }: { me: LeaderboardStanding; board: CourseLeaderboard }) {
  return (
    <Panel className="leaderboard-you-card">
      <div>
        <small>Your rank</small>
        <strong>#{me.rank}</strong>
        <span>of {board.entries.length}</span>
      </div>
      <div>
        <small>Total marks</small>
        <strong>{marks(me.total_score)}</strong>
        <span>of {marks(board.total_possible)}</span>
      </div>
      <div>
        <small>Share of marks</small>
        <strong>{me.percentage ?? 0}%</strong>
        <span>across graded work</span>
      </div>
      <div>
        <small>Graded assignments</small>
        <strong>{me.assignments_graded}</strong>
        <span>of {board.assignments_counted}</span>
      </div>
    </Panel>
  );
}
