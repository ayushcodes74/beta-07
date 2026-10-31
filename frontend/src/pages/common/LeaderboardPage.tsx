import { Award } from "lucide-react";
import { Panel } from "../../components/ui";

export function LeaderboardPage() {
  return (
    <>
      <div className="page-heading">
        <div>
          <div className="eyebrow">ACADEMIC EXCELLENCE</div>
          <h1>Leaderboard & Effort Insights</h1>
          <p className="page-subtitle">Celebrate steady effort, consistency, and progress across course cohorts.</p>
        </div>
      </div>
      <Panel className="empty-state" style={{ padding: "3rem", textAlign: "center", color: "#5C6E61" }}>
        <Award size={36} style={{ margin: "0 auto 12px", color: "#173D2B", opacity: 0.8 }} />
        <h3>Cohort recognition is warming up</h3>
        <p style={{ marginTop: "8px", fontSize: "11px" }}>
          Leaderboard standings appear once assignment evaluations are reviewed and published by course faculty.
        </p>
      </Panel>
    </>
  );
}

