import { useState, type Dispatch, type DragEvent, type SetStateAction } from "react";
import { Link, useParams } from "react-router-dom";
import { ArrowLeft, CalendarDays, Check, CloudUpload, FileCheck2, ShieldCheck, Upload } from "lucide-react";
import { useAppState } from "../../App";
import { Button, ConfirmDialog, GlassPanel, Panel, StatusBadge, useToast } from "../../components/ui";
import { extractErrorMessage, submissionService } from "../../services/api";
import { formatDate } from "../../lib/utils";
import { canReplaceSubmission, type Submission } from "../../types/models";

export function StudentSubmissionPage({
  submissions: studentRows,
  setSubmissions,
}: {
  submissions: Submission[];
  setSubmissions: Dispatch<SetStateAction<Submission[]>>;
}) {
  const { user, courses: courseList, assignments: assignmentList } = useAppState();
  const { assignmentId } = useParams();
  const assignment = assignmentList.find((item) => item.id === assignmentId);
  const course = assignment ? courseList.find((item) => item.id === assignment.courseId) : undefined;
  const existing = studentRows.find((item) => item.studentId === user?.id && item.assignmentId === assignmentId);
  // Replacing is allowed until grading starts; the backend enforces the same rule.
  const replacing = Boolean(existing) && canReplaceSubmission(existing!);
  const locked = Boolean(existing) && !replacing;
  const [file, setFile] = useState<File | null>(null);
  const [drag, setDrag] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [submittedItem, setSubmittedItem] = useState<Submission | null>(null);
  const toast = useToast();

  if (!assignment) {
    return (
      <div style={{ padding: "4rem", textAlign: "center" }}>
        <h2>Assignment not found</h2>
        <p style={{ margin: "1rem 0", color: "#5C6E61" }}>The requested assignment could not be found.</p>
        <Link to="/app/student/assignments">
          <Button variant="secondary">Back to Assignments</Button>
        </Link>
      </div>
    );
  }

  const chooseFile = (candidate?: File) => {
    if (!candidate) return;
    if (candidate.type !== "application/pdf" && !candidate.name.toLowerCase().endsWith(".pdf")) {
      toast("Please select a valid PDF file.", "info");
      return;
    }
    if (candidate.size > 20 * 1024 * 1024) {
      toast("File exceeds the 20 MB size limit.", "info");
      return;
    }
    setFile(candidate);
  };

  const submit = async () => {
    if (!file) {
      toast("Choose a PDF document before submitting.", "info");
      return;
    }
    setSubmitting(true);
    try {
      const created = await submissionService.submitPdf(assignment.id, file);
      // A replacement keeps the same submission id, so swap it in rather than adding a duplicate.
      setSubmissions((current) => [
        created,
        ...current.filter(
          (item) => item.id !== created.id && !(item.studentId === created.studentId && item.assignmentId === created.assignmentId)
        ),
      ]);
      setSubmittedItem(created);
      setFile(null);
      toast(replacing ? "Submission replaced and queued for OCR processing." : "PDF uploaded successfully and queued for OCR processing!");
    } catch (err) {
      toast(extractErrorMessage(err, "Failed to submit PDF. Please verify your connection."), "info");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <>
      <div className="page-heading">
        <div>
          <div className="eyebrow">STUDENT HAND-IN</div>
          <h1>Submit assignment</h1>
          <p className="page-subtitle">
            {assignment.title} · {course?.name ?? "Course"} ({course?.code ?? "CS"})
          </p>
        </div>
        <div className="heading-actions">
          <Link to="/app/student/assignments">
            <Button variant="secondary">
              <ArrowLeft size={14} />
              All assignments
            </Button>
          </Link>
        </div>
      </div>

      <div className="student-submit-layout">
        <div>
          <Panel className="instruction-panel">
            <div className="assignment-state-line">
              <StatusBadge status={existing ? existing.state : "Not Started"} />
              <span>
                <CalendarDays size={13} />
                Due {formatDate(assignment.dueAt)}
              </span>
            </div>
            <h2>Submission instructions</h2>
            <p>{assignment.description || "Submit your completed solutions in PDF format for multimodal OCR review."}</p>
            <ul>
              <li>Submit a single PDF containing all answer sheets and scratch work.</li>
              <li>Ensure handwriting, figures, and mathematical notations are clearly lit and legible.</li>
              <li>Submissions are timestamped; a late-submission policy is not configured in the backend.</li>
            </ul>
            <div className="assignment-instruction-footer">
              <span>{assignment.totalMarks} marks total</span>
            </div>
          </Panel>

          <div className="section-heading" style={{ marginTop: "20px" }}>
            <div>
              <h2>Your submission document</h2>
              <p>Accepted format: PDF · Up to 20 MB</p>
            </div>
          </div>

          <GlassPanel
            className={`student-dropzone ${drag ? "drag-active" : ""} ${file ? "file-selected" : ""}`}
            onDragOver={(event: DragEvent<HTMLElement>) => {
              event.preventDefault();
              setDrag(true);
            }}
            onDragLeave={() => setDrag(false)}
            onDrop={(event: DragEvent<HTMLElement>) => {
              event.preventDefault();
              setDrag(false);
              chooseFile(event.dataTransfer.files[0]);
            }}
          >
            <input
              type="file"
              accept=".pdf,application/pdf"
              id="student-pdf"
              className="visually-hidden"
              onChange={(event) => chooseFile(event.target.files?.[0])}
            />
            {file ? (
              <>
                <span className="file-icon-large">
                  <FileCheck2 size={24} style={{ color: "#173D2B" }} />
                </span>
                <strong>{file.name}</strong>
                <p>{(file.size / 1024 / 1024).toFixed(2)} MB · Ready to submit</p>
                <button className="text-button" type="button" onClick={() => setFile(null)}>
                  Choose another file
                </button>
              </>
            ) : (
              <>
                <span className="upload-icon">
                  <CloudUpload size={24} style={{ color: "#173D2B" }} />
                </span>
                <strong>Drop your PDF here</strong>
                <p>or click to browse from your device.</p>
                <Button
                  type="button"
                  variant="secondary"
                  size="sm"
                  onClick={() => document.getElementById("student-pdf")?.click()}
                >
                  Choose PDF
                </Button>
              </>
            )}
          </GlassPanel>

          <div className="submit-actions" style={{ marginTop: "16px" }}>
            <span style={{ fontSize: "10px", color: "#5C6E61", display: "inline-flex", alignItems: "center", gap: "6px" }}>
              <ShieldCheck size={14} style={{ color: "#173D2B" }} />
              {locked
                ? "Your submission is being reviewed, so it can no longer be replaced."
                : replacing
                  ? "You can replace your submission until your teacher starts reviewing it."
                  : "The backend will record your submission and return its submission ID."}
            </span>
            <ConfirmDialog
              trigger={
                <Button disabled={!file || submitting || locked}>
                  <Upload size={14} />
                  {locked
                    ? "Under review"
                    : submitting
                      ? "Uploading…"
                      : replacing
                        ? "Replace submission"
                        : "Submit PDF"}
                </Button>
              }
              title={replacing ? "Replace your submission?" : "Submit your assignment?"}
              description={
                replacing
                  ? `This will replace your previous PDF with ${file?.name ?? "your new PDF"} for ${assignment.title}. Only the new file will be graded.`
                  : `This will submit ${file?.name ?? "your PDF"} for evaluation in ${assignment.title}.`
              }
              confirmLabel={replacing ? "Replace submission" : "Confirm submission"}
              onConfirm={submit}
            />
          </div>
        </div>

        <aside className="submission-side">
          <Panel className="side-detail-card">
            <div className="section-heading">
              <div>
                <h2>Assignment details</h2>
              </div>
            </div>
            <dl>
              <div>
                <dt>Deadline</dt>
                <dd>{formatDate(assignment.dueAt)}</dd>
              </div>
              <div>
                <dt>Maximum marks</dt>
                <dd>{assignment.totalMarks} marks</dd>
              </div>
              <div>
                <dt>Submission format</dt>
                <dd>PDF document</dd>
              </div>
              <div>
                <dt>Current status</dt>
                <dd>
                  <StatusBadge status={existing ? existing.state : "Not Started"} />
                </dd>
              </div>
            </dl>
          </Panel>
        </aside>
      </div>

      {submittedItem && (
        <div className="modal-backdrop">
          <div className="receipt-modal">
            <span className="receipt-check">
              <Check size={22} />
            </span>
            <span className="eyebrow">SUBMISSION RECEIPT</span>
            <h2>All handed in.</h2>
            <p>Your work has been submitted to the FastAPI backend and queued for OCR processing.</p>
            <div className="receipt-line">
              <span>Assignment</span>
              <strong>{assignment.title}</strong>
            </div>
            <div className="receipt-line">
              <span>Submission ID</span>
              <code style={{ fontSize: "0.8rem", color: "#173D2B" }}>{submittedItem.id}</code>
            </div>
            <div className="receipt-line">
              <span>File Name</span>
              <strong>{submittedItem.fileName || file?.name}</strong>
            </div>
            <div className="receipt-line">
              <span>OCR Status</span>
              <StatusBadge status={submittedItem.ocr.state} />
            </div>
            <Button className="full-button" onClick={() => setSubmittedItem(null)}>
              Done
            </Button>
          </div>
        </div>
      )}
    </>
  );
}
