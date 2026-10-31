import { AlertCircle, Info, Sparkles } from "lucide-react";

interface IntegrationNoticeProps {
  title: string;
  description: string;
  endpoint?: string;
  tone?: "info" | "warning" | "ai";
}

export function IntegrationNotice({
  title,
  description,
  endpoint,
  tone = "info",
}: IntegrationNoticeProps) {
  const Icon = tone === "ai" ? Sparkles : tone === "warning" ? AlertCircle : Info;

  return (
    <div className={`integration-notice-card ${tone === "warning" ? "warning-notice" : ""}`}>
      <span className="integration-notice-icon">
        <Icon size={17} />
      </span>
      <div className="integration-notice-content">
        <h4>{title}</h4>
        <p>{description}</p>
        {endpoint && (
          <p style={{ marginTop: "4px", fontSize: "9px", opacity: 0.75, fontFamily: "monospace" }}>
            Backend route: {endpoint}
          </p>
        )}
      </div>
    </div>
  );
}

