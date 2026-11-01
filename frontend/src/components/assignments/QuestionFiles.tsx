import { useCallback, useEffect, useRef, useState, type ChangeEvent } from "react";
import { FileText, ImageIcon, Paperclip, X } from "lucide-react";
import {
  ATTACHMENT_ACCEPT,
  ATTACHMENT_TYPES,
  MAX_ATTACHMENTS_PER_QUESTION,
  MAX_ATTACHMENT_BYTES,
  attachmentService,
  formatBytes,
  isImage,
  type QuestionAttachment,
} from "../../services/attachments";

// ==========================================================================================
// Student view: the files under a question
// ==========================================================================================

/** Pictures inline (click to open full size), PDFs as a link. */
export function QuestionFileGallery({ files }: { files: QuestionAttachment[] }) {
  if (!files.length) return null;
  return (
    <div className="qfile-gallery">
      {files.map((file) =>
        isImage(file.content_type) && file.url ? (
          <a key={file.id} className="qfile-image" href={file.url} target="_blank" rel="noopener noreferrer">
            <img src={file.url} alt={file.filename} loading="lazy" />
            <span>{file.filename}</span>
          </a>
        ) : (
          <a
            key={file.id}
            className="qfile-chip"
            href={file.url ?? undefined}
            target="_blank"
            rel="noopener noreferrer"
            aria-disabled={!file.url}
          >
            <FileText size={14} aria-hidden="true" />
            <span>{file.filename}</span>
            <small>{file.url ? `Open · ${formatBytes(file.size_bytes)}` : "Unavailable"}</small>
          </a>
        )
      )}
    </div>
  );
}

/** Loads an assignment's files once and groups them by question number. Fails quietly. */
export function useAssignmentFiles(assignmentId: string | undefined) {
  const [byQuestion, setByQuestion] = useState<Record<number, QuestionAttachment[]>>({});
  useEffect(() => {
    if (!assignmentId) return;
    let active = true;
    attachmentService
      .list(assignmentId)
      .then((files) => {
        if (!active) return;
        const grouped: Record<number, QuestionAttachment[]> = {};
        for (const file of files) (grouped[file.question_number] ??= []).push(file);
        setByQuestion(grouped);
      })
      .catch(() => undefined); // attachments not set up yet / unavailable: questions still show
    return () => {
      active = false;
    };
  }, [assignmentId]);
  return byQuestion;
}

// ==========================================================================================
// Teacher editor: pick files per question; they are uploaded / moved / removed on save
// ==========================================================================================

interface SavedFile {
  file: QuestionAttachment;
  /** Local id of the question it belongs to in the editor (null = its question was not found). */
  questionKey: string | null;
  removed: boolean;
}

export interface QuestionFilesState {
  saved: (questionKey: string) => QuestionAttachment[];
  staged: (questionKey: string) => File[];
  add: (questionKey: string, files: File[]) => string | null;
  removeSaved: (attachmentId: string) => void;
  removeStaged: (questionKey: string, index: number) => void;
  /** Apply the editor's changes after the assignment is saved. Resolves to the number of failures. */
  sync: (assignmentId: string, questionKeys: string[]) => Promise<number>;
}

/**
 * `questionKeys`: the editor's question ids in order. `ready`: the editor has finished loading the
 * assignment being edited (its question ids are final), so saved files can be matched to questions.
 */
export function useQuestionFiles(assignmentId: string | undefined, questionKeys: string[], ready: boolean): QuestionFilesState {
  const [saved, setSaved] = useState<SavedFile[]>([]);
  const [staged, setStaged] = useState<Record<string, File[]>>({});
  const [loaded, setLoaded] = useState<QuestionAttachment[] | null>(assignmentId ? null : []);
  const bound = useRef(false);

  useEffect(() => {
    if (!assignmentId) return;
    let active = true;
    attachmentService
      .list(assignmentId)
      .then((files) => active && setLoaded(files))
      .catch(() => active && setLoaded([]));
    return () => {
      active = false;
    };
  }, [assignmentId]);

  // Match saved files to the editor's questions once both are known (by question position).
  useEffect(() => {
    if (bound.current || !ready || loaded === null) return;
    bound.current = true;
    setSaved(loaded.map((file) => ({ file, questionKey: questionKeys[file.question_number - 1] ?? null, removed: false })));
  }, [ready, loaded, questionKeys]);

  const countFor = (key: string) =>
    saved.filter((s) => s.questionKey === key && !s.removed).length + (staged[key]?.length ?? 0);

  const add = (key: string, files: File[]): string | null => {
    for (const file of files) {
      if (!ATTACHMENT_TYPES.includes(file.type)) return `${file.name}: attach a PDF or a picture (PNG, JPG, WEBP).`;
      if (file.size > MAX_ATTACHMENT_BYTES) return `${file.name} is larger than 10 MB.`;
    }
    if (countFor(key) + files.length > MAX_ATTACHMENTS_PER_QUESTION) {
      return `A question can have at most ${MAX_ATTACHMENTS_PER_QUESTION} files.`;
    }
    setStaged((current) => ({ ...current, [key]: [...(current[key] ?? []), ...files] }));
    return null;
  };

  const sync = useCallback(
    async (id: string, keys: string[]): Promise<number> => {
      let failed = 0;
      const numberOf = (key: string | null) => (key ? keys.indexOf(key) + 1 : 0);
      for (const item of saved) {
        const number = numberOf(item.questionKey);
        try {
          if (item.removed || number === 0) {
            await attachmentService.remove(id, item.file.id); // removed, or its question was deleted
          } else if (number !== item.file.question_number) {
            await attachmentService.move(id, item.file.id, number);
          }
        } catch {
          failed += 1;
        }
      }
      for (const [key, files] of Object.entries(staged)) {
        const number = numberOf(key);
        if (number === 0) continue; // the question was deleted before saving
        for (const file of files) {
          try {
            await attachmentService.upload(id, number, file);
          } catch {
            failed += 1;
          }
        }
      }
      return failed;
    },
    [saved, staged]
  );

  return {
    saved: (key) => saved.filter((s) => s.questionKey === key && !s.removed).map((s) => s.file),
    staged: (key) => staged[key] ?? [],
    add,
    removeSaved: (attachmentId) =>
      setSaved((current) => current.map((s) => (s.file.id === attachmentId ? { ...s, removed: true } : s))),
    removeStaged: (key, index) =>
      setStaged((current) => ({ ...current, [key]: (current[key] ?? []).filter((_, i) => i !== index) })),
    sync,
  };
}

const EXTRACTION_LABEL: Record<QuestionAttachment["extraction_status"], string> = {
  pending: "Reading text…",
  ready: "Text read for AI grading",
  no_text: "No readable text (shown to students only)",
  failed: "Text could not be read (shown to students only)",
};

/** The "Attach files" field inside one question card of the assignment editor. */
export function QuestionFilesField({ questionKey, files }: { questionKey: string; files: QuestionFilesState }) {
  const [error, setError] = useState("");
  const input = useRef<HTMLInputElement>(null);
  const saved = files.saved(questionKey);
  const staged = files.staged(questionKey);

  const onPick = (event: ChangeEvent<HTMLInputElement>) => {
    const picked = Array.from(event.target.files ?? []);
    event.target.value = "";
    if (picked.length) setError(files.add(questionKey, picked) ?? "");
  };

  return (
    <div className="qfile-field">
      <div className="qfile-field-head">
        <button type="button" className="text-button" onClick={() => input.current?.click()}>
          <Paperclip size={13} aria-hidden="true" /> Attach picture or PDF
        </button>
        <small>Shown to students under this question; its text is read for AI grading.</small>
        <input ref={input} type="file" accept={ATTACHMENT_ACCEPT} multiple hidden onChange={onPick} />
      </div>
      {(saved.length > 0 || staged.length > 0) && (
        <ul className="qfile-list">
          {saved.map((file) => (
            <li key={file.id}>
              {isImage(file.content_type) ? <ImageIcon size={13} /> : <FileText size={13} />}
              {file.url ? (
                <a href={file.url} target="_blank" rel="noopener noreferrer">{file.filename}</a>
              ) : (
                <span>{file.filename}</span>
              )}
              <small title={file.text_preview ?? undefined}>{EXTRACTION_LABEL[file.extraction_status]}</small>
              <button type="button" className="icon-button" aria-label={`Remove ${file.filename}`} onClick={() => files.removeSaved(file.id)}>
                <X size={12} />
              </button>
            </li>
          ))}
          {staged.map((file, index) => (
            <li key={`${file.name}-${index}`} className="qfile-staged">
              {file.type.startsWith("image/") ? <ImageIcon size={13} /> : <FileText size={13} />}
              <span>{file.name}</span>
              <small>{formatBytes(file.size)} · uploads when you save</small>
              <button type="button" className="icon-button" aria-label={`Remove ${file.name}`} onClick={() => files.removeStaged(questionKey, index)}>
                <X size={12} />
              </button>
            </li>
          ))}
        </ul>
      )}
      {error && <p className="qfile-error" role="alert">{error}</p>}
    </div>
  );
}

