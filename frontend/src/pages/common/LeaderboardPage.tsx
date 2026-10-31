import { Award } from "lucide-react";
import { Panel } from "../../components/ui";
import { IntegrationNotice } from "../../components/common/IntegrationNotice";

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
      {
        <IntegrationNotice
          title="Leaderboard data is not connected"
          description="No published-grades or leaderboard API exists, so TrustGrade has no authorized score data from which to calculate standings."
          endpoint="No leaderboard endpoint is currently available"
          tone="info"
        />
      }
      <Panel className="empty-state" style={{ padding: "3rem", textAlign: "center", color: "#5C6E61" }}>
        <Award size={36} style={{ margin: "0 auto 12px", color: "#173D2B", opacity: 0.8 }} />
        <h3>Leaderboard unavailable</h3>
        <p style={{ marginTop: "8px", fontSize: "11px" }}>
          Standings require stored, teacher-published results from the backend.
        </p>
      </Panel>
    </>
  );
}
