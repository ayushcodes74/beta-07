import { useNavigate } from "react-router-dom";
import { Button } from "../../components/ui";

export function NotFoundPage() {
  const navigate = useNavigate();
  return (
    <div style={{ padding: "5rem 2rem", textAlign: "center" }}>
      <h2 style={{ fontSize: "24px", color: "#173D2B" }}>Page not found</h2>
      <p style={{ margin: "1rem 0 2rem", color: "#5C6E61" }}>
        The requested page or resource could not be found in this workspace.
      </p>
      <Button variant="secondary" onClick={() => navigate("/app")}>
        Back to Overview
      </Button>
    </div>
  );
}

