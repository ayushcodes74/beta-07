import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { ArrowLeft, Search } from "lucide-react";
import { Badge, Button, Panel, StatusBadge } from "../../components/ui";
import { IntegrationNotice } from "../../components/common/IntegrationNotice";
import { formatDate } from "../../lib/utils";
import { extractErrorMessage, submissionService, type BackendOCRDocumentResult, type BackendOCRProcessingStatus } from "../../services/api";
import { isDemoSession } from "../../services/demo-session";
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
  const demoSession = isDemoSession();
  const [document, setDocument] = useState<BackendOCRDocumentResult | null>(null);
  const [processing, setProcessing] = useState<BackendOCRProcessingStatus | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [retry, setRetry] = useState(0);

  useEffect(() => {
    if (!submission) return;
    if (demoSession) {
      setDocument(null);
      setProcessing(null);
      setError("");
      setLoading(false);
      return;
    }

    let active = true;
    setLoading(true);
    setError("");
    setDocument(null);
    setProcessing(null);
    submissionService
      .getOcrResult(submission.id)
      .then((result) => {
        if (!active) return;
        if ("pages" in result) setDocument(result);
        else setProcessing(result);
      })
      .catch((reason: unknown) => {
        if (active) setError(extractErrorMessage(reason, "Could not load OCR results."));
      })
      .finally(() => {
        if (active) setLoading(false);
      });

    return () => {
      active = false;
    };
  }, [demoSession, retry, submission?.id]);

  return (
    <>
      <div className="page-heading">
        <div>
          <div className="eyebrow">MULTIMODAL OCR PIPELINE</div>
          <h1>OCR Extraction Review</h1>
          <p className="page-subtitle">Review extracted text, region confidence, page order, and warnings from the OCR service.</p>
        </div>
        <div className="heading-actions">
          <Button variant="secondary" onClick={() => navigate("/app/submissions")}>
            <ArrowLeft size={14} />
            Back to queue
          </Button>
          {submission && !demoSession && (
            <Button variant="secondary" disabled={loading} onClick={() => setRetry((value) => value + 1)}>
              {loading ? "Refreshing…" : "Refresh OCR"}
            </Button>
          )}
        </div>
      </div>

      {submission ? (
        <div style={{ display: "grid", gap: "16px" }}>
          {demoSession && (
            <IntegrationNotice
              title="Demo OCR content"
              description="This sample extraction is for demonstration only; it is not the OCR result for a real submission."
              tone="info"
            />
          )}
          {error && <p role="alert" className="form-error">{error}</p>}
          {loading && <p role="status">Loading OCR result…</p>}
          {processing && (
            <Panel style={{ padding: "20px" }}>
              <h2>OCR processing</h2>
              <p>{processing.message}</p>
              <p>Stage: {processing.stage} · {processing.progress}%</p>
            </Panel>
          )}
          <Panel style={{ padding: "20px" }}>
            <div className="section-heading">
              <div>
                <h2>Submission Document Analysis</h2>
                <p>Submitted {formatDate(submission.submittedAt)} · File: {submission.fileName || "PDF submission"}</p>
              </div>
              <StatusBadge status={document?.status ?? submission.ocr.state} />
            </div>

            {demoSession ? (
              <>
                {submission.ocr.confidence !== null && (
                  <div style={{ margin: "14px 0" }}>
                    <Badge tone="sage">Sample confidence: {Math.round(submission.ocr.confidence * 100)}%</Badge>
                  </div>
                )}
                <h4 style={{ margin: "16px 0 8px", fontSize: "12px" }}>Demo extracted text:</h4>
                <div className="ocr-box">{submission.ocr.extractedText || "No demo OCR text recorded."}</div>
              </>
            ) : document ? (
              <>
                <p>
                  Processed {document.processing_summary.processed_pages} of {document.processing_summary.total_pages} pages
                  {document.processing_summary.failed_pages > 0 &&
                    ` · ${document.processing_summary.failed_pages} failed`}
                </p>
                {document.warnings.map((warning, index) => <p role="status" key={`warning-${index}`}>{warning}</p>)}
                {document.errors.map((message, index) => <p role="alert" key={`error-${index}`}>{message}</p>)}
                {document.pages.map((page) => (
                  <section key={`${document.job_id}-${page.page_number}`} style={{ marginTop: "18px" }}>
                    <h3 style={{ fontSize: "14px" }}>Page {page.page_number} · {page.status}</h3>
                    {page.warnings.map((warning, index) => (
                      <p role="status" key={`page-${page.page_number}-${index}`}>{warning}</p>
                    ))}
                    <div className="ocr-box">{page.full_text || "No text extracted for this page."}</div>
                    {page.text_blocks.map((block) => (
                      <div key={block.block_id} style={{ borderBottom: "1px solid #E7EBE3", padding: "10px 0" }}>
                        <div style={{ display: "flex", gap: "8px", flexWrap: "wrap" }}>
                          <Badge tone="ink">Region {block.sequence} · {block.type}</Badge>
                          {block.confidence !== null && (
                            <Badge tone={block.confidence < 0.6 ? "gold" : "sage"}>
                              Confidence {Math.round(block.confidence * 100)}%
                            </Badge>
                          )}
                          <small>
                            Box ({block.bounding_box.x1}, {block.bounding_box.y1})–({block.bounding_box.x2},{" "}
                            {block.bounding_box.y2})
                          </small>
                        </div>
                        <p>{block.text || "Unreadable or empty region."}</p>
                        {block.warnings.map((warning, index) => (
                          <p role="status" key={`${block.block_id}-${index}`}>{warning}</p>
                        ))}
                      </div>
                    ))}
                    {page.math_blocks.map((block, index) => (
                      <div key={`${page.page_number}-math-${index}`}>
                        <p>Math region: {block.recognized_text || block.latex || "Unreadable"}</p>
                        {block.confidence !== null && <small>Confidence {Math.round(block.confidence * 100)}%</small>}
                        {block.requires_manual_review && <p role="status">Requires teacher review.</p>}
                      </div>
                    ))}
                  </section>
                ))}
                {!document.pages.length && <p>No page-level OCR output was returned.</p>}
              </>
            ) : !loading && !processing && !error ? (
              <div className="ocr-box">No OCR result is available yet. Use Refresh OCR to check again.</div>
            ) : null}
          </Panel>
        </div>
      ) : (
        <Panel className="empty-state" style={{ padding: "3rem", textAlign: "center", color: "#5C6E61" }}>
          <Search size={32} style={{ margin: "0 auto 12px", opacity: 0.6 }} />
          <h3>No submission selected for OCR review</h3>
          <p style={{ margin: "8px 0 16px" }}>
            Select a submission from the queue to inspect OCR results and confidence scores.
          </p>
          <Button variant="secondary" onClick={() => navigate("/app/submissions")}>
            View submissions queue
          </Button>
        </Panel>
      )}
    </>
  );
}
