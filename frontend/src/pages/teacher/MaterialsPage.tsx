import { useRef, useState, type Dispatch, type DragEvent, type SetStateAction } from "react";
import { CloudUpload, FileText, MoreHorizontal, Plus } from "lucide-react";
import { Badge, Button, GlassPanel, Panel, StatusBadge, useToast } from "../../components/ui";
import { IntegrationNotice } from "../../components/common/IntegrationNotice";
import { formatDate } from "../../lib/utils";
import type { CourseMaterial } from "../../types/models";

export function MaterialsPage({
  materials: fileList,
  setMaterials,
}: {
  materials: CourseMaterial[];
  setMaterials: Dispatch<SetStateAction<CourseMaterial[]>>;
}) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [filter, setFilter] = useState("All files");
  const [dragging, setDragging] = useState(false);
  const toast = useToast();

  const addFiles = (files: FileList | null) => {
    if (!files) return;
    const valid: CourseMaterial[] = [];
    for (const file of Array.from(files)) {
      const extension = file.name.split(".").pop()?.toLowerCase();
      if (!["pdf", "ppt", "pptx", "doc", "docx", "txt"].includes(extension ?? "")) {
        toast(`${file.name}: please select PDF, PPTX, DOCX, or TXT files.`, "info");
        continue;
      }
      if (file.size > 25 * 1024 * 1024) {
        toast(`${file.name}: file exceeds 25 MB limit.`, "info");
        continue;
      }
      valid.push({
        id: crypto.randomUUID(),
        name: file.name,
        category: extension?.startsWith("ppt")
          ? "Lecture slides"
          : extension === "doc" || extension === "docx"
          ? "Notes"
          : "Reference",
        size: `${(file.size / 1024 / 1024).toFixed(1)} MB`,
        uploadedAt: new Date().toISOString(),
        state: "Ready",
        indexing: "Ready",
      });
    }
    if (valid.length) {
      setMaterials((current) => [...valid, ...current]);
      toast(`${valid.length} file(s) staged in workspace.`);
    }
  };

  const visible = fileList.filter(
    (file) =>
      filter === "All files" ||
      (filter === "Course docs"
        ? ["Syllabus", "Rulebook", "Rubric"].includes(file.category)
        : ["Notes", "Reference"].includes(file.category))
  );

  return (
    <>
      <div className="page-heading">
        <div>
          <div className="eyebrow">COURSE REPOSITORY</div>
          <h1>Course materials</h1>
          <p className="page-subtitle">Keep the knowledge behind every assignment in one place for AI grounding.</p>
        </div>
        <div className="heading-actions">
          <Button onClick={() => inputRef.current?.click()}>
            <Plus size={15} />
            Add materials
          </Button>
        </div>
      </div>

      <IntegrationNotice
        title="Material Cloud Storage Status"
        description="Persistent cloud object storage for course materials (POST /api/v1/courses/:id/materials) is pending backend route integration. Files staged below remain accessible in your session."
        endpoint="POST /api/v1/courses/{course_id}/materials"
        tone="info"
      />

      <div className="toolbar">
        <div className="segmented">
          {["All files", "Course docs", "Reference"].map((item) => (
            <button
              className={filter === item ? "segment active" : "segment"}
              key={item}
              onClick={() => setFilter(item)}
            >
              {item}
            </button>
          ))}
        </div>
      </div>

      <GlassPanel
        className={`upload-zone ${dragging ? "drag-active" : ""}`}
        onDragOver={(event: DragEvent<HTMLElement>) => {
          event.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(event: DragEvent<HTMLElement>) => {
          event.preventDefault();
          setDragging(false);
          addFiles(event.dataTransfer.files);
        }}
      >
        <input
          ref={inputRef}
          className="visually-hidden"
          type="file"
          multiple
          accept=".pdf,.ppt,.pptx,.doc,.docx,.txt"
          onChange={(event) => {
            addFiles(event.target.files);
            event.target.value = "";
          }}
        />
        <span className="upload-icon">
          <CloudUpload size={22} />
        </span>
        <strong>Drop syllabus, lecture slides, or readings here</strong>
        <p>PDF, PPTX, DOCX, or TXT · Up to 25 MB per file</p>
        <Button variant="secondary" size="sm" onClick={() => inputRef.current?.click()}>
          Browse files
        </Button>
      </GlassPanel>

      <div className="section-heading" style={{ marginTop: "24px" }}>
        <div>
          <h2>Course repository library</h2>
          <p>Staged documents for syllabus reference</p>
        </div>
      </div>

      <Panel className="file-list">
        <div className="file-header">
          <span>Document Name</span>
          <span>Category</span>
          <span>Size</span>
          <span>Uploaded</span>
          <span>Indexing</span>
          <span />
        </div>
        {visible.map((file) => (
          <div className="file-row" key={file.id}>
            <span className="file-name">
              <span className="file-icon">
                <FileText size={16} />
              </span>
              <span>
                <strong>{file.name}</strong>
              </span>
            </span>
            <span>
              <Badge tone="ink">{file.category}</Badge>
            </span>
            <span>{file.size}</span>
            <span>{formatDate(file.uploadedAt)}</span>
            <StatusBadge status={file.state} />
            <button className="icon-button" aria-label={`Options for ${file.name}`}>
              <MoreHorizontal size={15} />
            </button>
          </div>
        ))}
        {!visible.length && (
          <div className="table-empty" style={{ padding: "2rem", textAlign: "center", color: "#5C6E61" }}>
            No course materials uploaded yet. Drag and drop PDF, PPTX, or DOCX documents above.
          </div>
        )}
      </Panel>
    </>
  );
}

