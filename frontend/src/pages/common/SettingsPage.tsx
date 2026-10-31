import { useAppState } from "../../App";
import { Badge, Panel } from "../../components/ui";

export function SettingsPage() {
  const { user } = useAppState();

  return (
    <>
      <div className="page-heading">
        <div>
          <div className="eyebrow">PREFERENCES & PROFILE</div>
          <h1>Settings</h1>
          <p className="page-subtitle">Your trusted account profile and academic workspace configuration.</p>
        </div>
      </div>
      <Panel className="editor-card" style={{ maxWidth: "600px" }}>
        <div className="section-heading">
          <div>
            <h2>Account Profile</h2>
            <p>Verified authentication details</p>
          </div>
          <Badge tone="sage">{user?.role === "teacher" ? "Faculty" : "Student"}</Badge>
        </div>
        <div className="field-block">
          <label>Full Name</label>
          <input className="field-input" value={user?.name ?? ""} readOnly />
        </div>
        <div className="field-block">
          <label>Email address</label>
          <input className="field-input" value={user?.email ?? ""} readOnly />
        </div>
        <div className="field-block">
          <label>User Identifier</label>
          <input className="field-input" value={user?.id ?? ""} readOnly />
        </div>
        <div className="field-block">
          <label>Account Role</label>
          <input className="field-input" value={user?.role ?? ""} readOnly />
        </div>
      </Panel>
    </>
  );
}

