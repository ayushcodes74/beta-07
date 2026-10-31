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

- `VITE_USE_API_AUTH=true` to use Supabase Auth instead of the local demo sign-in.
- `VITE_SUPABASE_URL` and `VITE_SUPABASE_ANON_KEY` for the public Supabase client configuration.
- `VITE_API_BASE_URL` for the FastAPI API base URL.

The frontend does not contain service-role keys or other server secrets. With real authentication enabled, the application obtains the user's role from the trusted `/api/v1/auth/me` profile endpoint; it does not use a client-selected role as authorization.

AI question generation, OCR, file handling, grading, and course workflows are demonstration experiences unless connected to their backend services. The FastAPI backend is in `backend/`.

### Submission integrity comparison

The authenticated FastAPI endpoint `GET /api/v1/submissions` lists only the student's own submissions or submissions for assignments owned by the teacher. The teacher-facing endpoint `GET /api/v1/submissions/{submission_id}/integrity` compares recognized passages only against other submissions visible under the caller's Supabase/RLS context for that same assignment. Evidence includes OCR page/region references, token-sequence similarity, and low-confidence OCR regions. Known printed OCR regions are excluded to avoid matching repeated question prompts; question-level answer alignment is not available in the current OCR contract. A match is a teacher-review signal, never an automatic misconduct decision; no internet-wide search is performed.

The endpoint reads completed OCR results on request and does not persist comparisons or teacher decisions. No database migration or new environment variable is required. The AI Engine contains a separate SentenceTransformer/RAG abstraction for course materials, but no configured submission embedding index or backend integration; semantic/vector similarity is therefore reported as unavailable rather than using its deterministic test embedder. The API and review UI expose handwriting-style analysis as unavailable with no score: this repository has no validated writer-verification model or labeled validation set. No separate writer-sample ingestion is enabled; student submissions must not be repurposed as labeled identity samples without an explicit consent and retention policy. The existing OCR output does include ordered regions, page coordinates, and optional confidence; low-confidence text is surfaced unchanged for review.

Before enabling handwriting-style scores, collect consented, labeled same-writer/different-writer samples across different text, layouts, instruments, and image conditions. Keep writers disjoint between training and validation, report false-positive/false-negative rates and precision/recall at a predeclared operating threshold, and evaluate image-quality subgroups. Until those checks pass, handwriting evidence must remain unavailable rather than receive an invented score.

Run the focused backend checks from the repository root:

```powershell
.\venv\Scripts\python.exe -m pytest backend\tests\test_plagiarism.py backend\tests\test_ocr_integration.py
```
