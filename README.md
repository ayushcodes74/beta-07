# TrustGrade

TrustGrade is a teacher-led academic grading workspace for assignments, course materials, student submissions, OCR verification, AI-assisted grading, and teacher-approved feedback.

## Frontend

The React, TypeScript, and Vite application lives in `frontend/`.

```powershell
cd frontend
npm install
npm run dev
```

Create a production build with `npm run build`, or run `npm run typecheck` to check TypeScript without bundling. The local demo supports teacher and student previews; select a workspace on the sign-in screen. Demo changes are held in memory for the current session.

### Authentication and API configuration

Copy `frontend/.env.example` to `frontend/.env` and configure:

- `VITE_DEMO_MODE=true` only when intentionally using the isolated sample/demo workspace. Leave it `false` for connected accounts.
- `VITE_SUPABASE_URL` and `VITE_SUPABASE_ANON_KEY` for the public Supabase client configuration.
- `VITE_API_BASE_URL` for the FastAPI API base URL.

The frontend does not contain service-role keys or other server secrets. Connected accounts use Supabase Auth and obtain their role from the trusted `/api/v1/auth/me` profile endpoint; a client-selected role is never authorization.

The connected API currently supports course and assignment records, PDF submissions, OCR status/results, and same-assignment integrity comparisons. Assignment creation accepts an optional `course_id`; the backend verifies the course belongs to the creating teacher before storing it. The API derives display codes from course names and does not persist custom course codes.

Course-material upload/indexing, student invite-code enrollment, MCQ answer submission, grade review/publication, results, leaderboard, corrected OCR persistence, and teacher integrity-decision audit endpoints are not implemented. Their connected-mode UI is disabled or shows an explicit limitation instead of recording local-only success. Interactive sample content and simulated grades are restricted to active demo sessions. The FastAPI backend is in `backend/`.

### Submission integrity comparison

The authenticated FastAPI endpoint `GET /api/v1/submissions` lists only the student's own submissions or submissions for assignments owned by the teacher. The teacher-facing endpoint `GET /api/v1/submissions/{submission_id}/integrity` compares recognized passages only against other submissions visible under the caller's Supabase/RLS context for that same assignment. Evidence includes OCR page/region references, token-sequence similarity, and low-confidence OCR regions. Known printed OCR regions are excluded to avoid matching repeated question prompts; question-level answer alignment is not available in the current OCR contract. A match is a teacher-review signal, never an automatic misconduct decision; no internet-wide search is performed.

The endpoint reads completed OCR results on request and does not persist comparisons or teacher decisions. No database migration or new environment variable is required. The AI Engine contains a separate SentenceTransformer/RAG abstraction for course materials, but no configured submission embedding index or backend integration; semantic/vector similarity is therefore reported as unavailable rather than using its deterministic test embedder. Handwriting: a **within-submission** consistency check is enabled as a **teacher-only review signal** (`handwriting_analysis` in the integrity report; computed by the OCR service at `GET /api/v1/ocr/handwriting/{job_id}`). It compares handwriting style (stroke direction, thickness, letter size/spacing, texture) of each answer and each page against the rest of the same submission and flags a part only if the difference is large (effect size >= 0.9) and unlikely by chance (permutation p < 0.01), with at least 6 handwritten lines per part; otherwise it reports `insufficient_handwriting`. It never compares different students or a student's earlier submissions, is never shown to students, never blocks publishing, and is labeled "possible different handwriting - needs teacher review", not a finding. It is an **unvalidated heuristic** (no trained writer-verification model): pens, paper, scanning and writing speed also change style. No separate writer-sample ingestion is enabled; student submissions must not be repurposed as labeled identity samples without an explicit consent and retention policy. The existing OCR output does include ordered regions, page coordinates, and optional confidence; low-confidence text is surfaced unchanged for review.

Before relying on the handwriting check (or extending it beyond teacher review), collect consented, labeled same-writer/different-writer samples across different text, layouts, instruments, and image conditions. Keep writers disjoint between calibration and validation, report false-positive/false-negative rates at the operating threshold, and evaluate image-quality subgroups. `ocr-engine/scripts/evaluate_handwriting_consistency.py` runs the check on single-writer OCR jobs (false positives) and on pages spliced in from another writer (detection); at the time of writing it was only checked on 2 distinct writers (0 false positives, 2/2 spliced pages detected), which is not a validation.

Run the focused backend checks from the repository root:

```powershell
.\venv\Scripts\python.exe -m pytest backend\tests\test_plagiarism.py backend\tests\test_ocr_integration.py
```
