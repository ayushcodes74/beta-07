import { useNavigate, useParams } from "react-router-dom";
import { ArrowLeft, Search } from "lucide-react";
import { Badge, Button, Panel, StatusBadge } from "../../components/ui";
import { formatDate } from "../../lib/utils";
import type { Submission } from "../../types/models";

export function OCRReviewPage({
  submissions: rows,
}: {
  submissions: Submission[];
  setSubmissions: (subs: Submission[]) => void;
}) {
  const { submissionId } = useParams();
  const navigate = useNavigate();
  const submission = rows.find((item) => item.id === submissionId);

  return (
    <>
      <div className="page-heading">
        <div>
          <div className="eyebrow">MULTIMODAL OCR PIPELINE</div>
          <h1>OCR Extraction Review</h1>
          <p className="page-subtitle">Inspect handwriting recognition accuracy, confidence scoring, and formulas.</p>
        </div>
        <div className="heading-actions">
          <Button variant="secondary" onClick={() => navigate("/app/submissions")}>
            <ArrowLeft size={14} />
            Back to queue
          </Button>
        </div>
      </div>

      {submission ? (
        <div style={{ display: "grid", gap: "16px" }}>
          <Panel style={{ padding: "20px" }}>
            <div className="section-heading">
              <div>
                <h2>Submission Document Analysis</h2>
                <p>Submitted {formatDate(submission.submittedAt)} · File: {submission.fileName || "scanned_doc.pdf"}</p>
              </div>
              <StatusBadge status={submission.ocr.state} />
            </div>

            <div style={{ display: "flex", gap: "10px", margin: "14px 0" }}>
              <Badge tone="sage">Confidence: {Math.round((submission.ocr.confidence || 0.95) * 100)}%</Badge>
              <Badge tone="ink">Status: {submission.ocr.state}</Badge>
            </div>

            <h4 style={{ margin: "16px 0 8px", fontSize: "12px" }}>Raw Text Extracted from PDF:</h4>
            <div className="ocr-box">
              {submission.ocr.extractedText || "No extracted text recorded."}
            </div>

            {submission.ocr.warnings && submission.ocr.warnings.length > 0 && (
              <div style={{ marginTop: "14px" }}>
                <strong style={{ fontSize: "11px", color: "#7A5F1E" }}>OCR Warnings:</strong>
                <ul>
                  {submission.ocr.warnings.map((w, i) => (
                    <li key={i} style={{ fontSize: "10px", color: "#7A5F1E" }}>
                      {w}
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </Panel>
        </div>
      ) : (
        <Panel className="empty-state" style={{ padding: "3rem", textAlign: "center", color: "#5C6E61" }}>
          <Search size={32} style={{ margin: "0 auto 12px", opacity: 0.6 }} />
          <h3>No submission selected for OCR review</h3>
          <p style={{ margin: "8px 0 16px" }}>
            Select any submission from the queue to inspect its OCR recognition output and confidence scores.
          </p>
          <Button variant="secondary" onClick={() => navigate("/app/submissions")}>
            View submissions queue
          </Button>
        </Panel>
      )}
    </>
  );
}
