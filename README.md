# GradeX

GradeX is a teacher-led grading workspace for handwritten and typed assignments. Students upload their answer
sheets as PDFs; GradeX reads them with OCR, checks the answers against the teacher's answer keys with AI, flags
anything that needs a human look (unclear OCR, low-confidence grades, possible copying), and lets the teacher
review, correct and publish the final grade.

**AI assists. Teachers decide. Students understand.** Nothing is ever published to a student without a teacher.

---

## Features

**Teachers**
- Courses and rosters (enroll students by email), assignments with subjective and multiple-choice questions,
  due dates and late-submission decisions (accept with a penalty, or reject).
- AI-drafted questions from course notes or a syllabus, and course materials (PDF, DOCX, PPTX, TXT; scans via OCR)
  indexed as grading evidence.
- **Question attachments**: pictures or PDFs attached to individual questions are shown to students and used for
  grading (their OCR text, and the pictures themselves for a multimodal model).
- **Automatic AI answer check** of every submission once its OCR has finished (while a teacher is signed in),
  with per-question marks, explanations and confidence. Teacher corrections are remembered and reused for later
  submissions of the same question.
- **Alternative methods**: when a student solves a question with a valid method the course did not teach, the
  teacher sees web sources describing it (TinyFish search) and can award bonus marks.
- **Review queue**: OCR problems, low-trust AI grades, student re-evaluation requests and **possible copying** in one place.
- Class analytics, leaderboard, notifications and private messaging with students.

**Students**
- See each assignment's questions (with attached figures), upload a PDF answer sheet (or take an online MCQ test).
- See published grades with per-question feedback, request a review of a grade, message the course teacher.

**Integrity checks** (teacher-only review signals, never automatic penalties)
- Same PDF file handed in by two students (SHA-256 fingerprint; works even when OCR read nothing).
- (Nearly) the same answers in different files (OCR text comparison, question text excluded).
- Matching passages between submissions of the same assignment.
- Possible different handwriting within one submission (see [Handwriting check](#handwriting-check)).

---

## Architecture

| Service | Folder | Port | Role |
|---|---|---|---|
| Frontend | `frontend/` | 5173 | React + TypeScript + Vite. Dev server proxies `/api` to the backend. |
| Backend API | `backend/` | 8000 | FastAPI. Verifies Supabase access tokens, enforces roles, orchestrates OCR and AI. |
| OCR engine | `ocr-engine/` | 8001 | PDF → page images → text (OCR.space cloud OCR, optional Gemini vision reader, local PaddleOCR fallback), handwriting analysis. |
| AI Engine | `ai-engine/` | 8002 | Answer checking, question generation, course-material RAG. LLM fallback chain over OpenRouter and Gemini. |
| Database / Auth / Files | Supabase | — | Postgres with row-level security, Supabase Auth, Supabase Storage (`assignment-files` bucket). |

Sign-up and sign-in happen in the browser directly against Supabase Auth. The backend never issues tokens: it
verifies the Supabase access token on every request and reads the user's role from the `profiles` table. All
database and storage access runs under the **user's own token**, so row-level security decides what each user can
see; the service-role key is not used for ordinary operations.

More detail: [`ai-engine/README.md`](ai-engine/README.md), [`ai-engine/INTEGRATION.md`](ai-engine/INTEGRATION.md),
[`ocr-engine/README.md`](ocr-engine/README.md).

---

## Running locally

### 1. Prerequisites

- Node.js 20+ and Python 3.12 or newer (3.13 recommended: PaddleOCR, the local OCR fallback, has no wheels for 3.14).
- A Supabase project, an [OCR.space](https://ocr.space/ocrapi) API key, and at least one LLM key
  ([Gemini](https://aistudio.google.com/apikey) and/or [OpenRouter](https://openrouter.ai)).

> The checked-in `venv/` folder was created on another machine and does not work elsewhere. Create your own
> virtual environment (below).

### 2. Database (Supabase SQL Editor)

Run each file in `backend/` once, in phase order (each runs in one transaction and checks itself at the end):

| File | Adds |
|---|---|
| `phase2a_rls_remediation.sql`, `phase2a_rls_recursion_fix.sql` | Hardened RLS policies and the `private.*` helper functions |
| `phase2b_enrollment_by_email.sql` | Enroll students by email, course roster with names |
| `phase2c_ocr_jobs_policies.sql` | OCR job access rules |
| `phase3a_review_requests.sql` | Student grade-review requests |
| `phase3b_late_submissions.sql`, `phase3b_course_leaderboard.sql` | Late-submission decisions, course leaderboard |
| `phase3c_course_messages.sql` | Student ↔ teacher messaging |
| `phase3d_notifications.sql` | Notifications |
| `phase3e_assignment_attachments.sql` | Question attachments: private storage bucket, table and policies |

Features whose migration has not been applied return a clear "apply phaseX.sql" message instead of failing silently.

### 3. Configuration

Create a `.env` in each service folder. Never commit real keys; the frontend must only ever contain public values.

| File | Required | Optional (defaults are sensible) |
|---|---|---|
| `frontend/.env` | `VITE_SUPABASE_URL`, `VITE_SUPABASE_ANON_KEY` | `VITE_API_BASE_URL` (default `/api/v1` through the dev proxy) |
| `backend/.env` | `SUPABASE_URL`, `SUPABASE_KEY` (anon key), JWT verification (`SUPABASE_JWT_VERIFICATION_METHOD`, `SUPABASE_JWKS_URL` or `SUPABASE_JWT_SECRET`, `SUPABASE_JWT_ISSUER`, `SUPABASE_JWT_AUDIENCE`) | `OCR_SERVICE_URL` (8001), `AI_SERVICE_URL` (8002), `TINYFISH_API_KEY` (alternative-method web sources), `GRADING_FULL_MARKS_AT`, `REVIEW_OCR_CONFIDENCE_THRESHOLD`, `REVIEW_TRUST_THRESHOLD`, `METHOD_BONUS_*` |
| `ocr-engine/.env` | `OCR_SPACE_API_KEY` | `OCR_VISION_API_KEY` (or `GEMINI_API_KEY`) to enable the Gemini vision reader for math (LaTeX), tables and diagrams, `OCR_VISION_MODEL`, `OCR_VISION_FALLBACK_MODELS`, `OCR_SPACE_ENGINE` (default 3) |
| `ai-engine/.env` | `GEMINI_API_KEY` and/or `OPENROUTER_API_KEY` | `LLM_PROVIDER_ORDER`, `GEMINI_MODEL`, `GEMINI_FALLBACK_MODELS`, `OPENROUTER_MODEL`, `OPENROUTER_FALLBACK_MODELS`, timeouts/retries (see `ai-engine/.env.example`) |

Each service reads its `.env` **only at startup**: restart it after changing a key.

### 4. Install and start

```powershell
# Python services (one shared environment is fine for local development)
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt -r ocr-engine\requirements.txt -r ai-engine\requirements.txt

# Three terminals, one per service:
cd backend;    ..\.venv\Scripts\python.exe -m uvicorn app.main:app       --host 127.0.0.1 --port 8000
cd ocr-engine; ..\.venv\Scripts\python.exe -m uvicorn app.api.app:app    --host 127.0.0.1 --port 8001
cd ai-engine;  ..\.venv\Scripts\python.exe -m uvicorn app.server:app     --host 127.0.0.1 --port 8002

# Frontend
cd frontend
npm install
npm run dev        # http://localhost:5173
```

Health checks: `http://127.0.0.1:8000/health`, `:8001/health` (shows which OCR engines are loaded) and
`:8002/health` (shows the LLM provider chain). If the app says *"workspace could not be loaded … status code 500"*,
the backend is usually not running: the Vite proxy reports a stopped backend as a 500.

---

## How grading works

1. A teacher creates a course, enrolls students and publishes an assignment (questions, answer keys, optional
   attachments per question).
2. A student uploads a PDF. The OCR engine renders each page and reads it (Gemini vision reader if configured,
   then OCR.space, then local PaddleOCR).
3. Once OCR has finished, the AI answer check runs automatically in the signed-in teacher's session. The transcript
   is split by the question numbers the student wrote (`Q1`, `2)`, …); each answer is graded against its answer key,
   the question's attachments and indexed course material. Grading is refused when OCR found no readable text.
4. The result is stored as a **pending suggestion**. Low-confidence grades, OCR problems and possible copying land in
   the teacher's review queue.
5. The teacher reviews, corrects per question (corrections are reused for later students), and publishes. Only
   then does the student see the grade and feedback.

---

## Integrity checks

All results are evidence for a teacher to look at, shown only to the owning teacher, and never change marks.

- **Possible copying** (*Review queue → Possible copying*, and a banner on the grading page). Submissions to the same
  assignment are compared pairwise:
  - *Same PDF file*: identical SHA-256 fingerprint of the uploaded file (OCR engine `GET /api/v1/ocr/file-hash/{job_id}`).
  - *Matching answers*: word 5-gram overlap of the OCR text, ignoring the question text and boilerplate most of the
    class wrote; a pair is flagged at **60 %** of the shorter sheet.
  Both students are flagged because the system cannot tell who copied from whom; the queue shows who handed in first.
- **Matching passages** (`GET /api/v1/submissions/{submission_id}/integrity`): token-sequence matches between the
  submission and others for the same assignment, with OCR page/region references. No internet search is performed.

### Handwriting check

A **within-submission** consistency check (`handwriting_analysis` in the integrity report; computed by the OCR
service at `GET /api/v1/ocr/handwriting/{job_id}`) compares the handwriting style (stroke direction, thickness,
letter size/spacing, texture) of each answer and each page against the rest of the same submission. A part is
flagged only if the difference is large (effect size ≥ 0.9) and unlikely by chance (permutation p < 0.01), with at
least 6 handwritten lines per part; otherwise the result is `insufficient_handwriting`. It never compares different
students, is never shown to students, never blocks publishing, and is labelled "possible different handwriting –
needs teacher review", not a finding.

It is an **unvalidated heuristic** (no trained writer-verification model): pens, paper, scanning and writing speed
also change style. Before relying on it or extending it beyond teacher review, collect consented, labelled
same-writer/different-writer samples across different text, layouts, instruments and image conditions; keep writers
disjoint between calibration and validation, and report false-positive/false-negative rates at the operating
threshold. `ocr-engine/scripts/evaluate_handwriting_consistency.py` runs the check on single-writer jobs (false
positives) and on pages spliced in from another writer (detection); so far it has only been checked on 2 distinct
writers (0 false positives, 2/2 spliced pages detected), which is not a validation. Student submissions must not be
repurposed as labelled identity samples without an explicit consent and retention policy.

---

## Tests

```powershell
.\.venv\Scripts\python.exe -m pytest backend\tests -q      # backend (API, services, RLS-facing repositories with fakes)
cd ai-engine;  ..\.venv\Scripts\python.exe -m pytest -q    # AI Engine (needs pytest-asyncio from its requirements)
cd ocr-engine; ..\.venv\Scripts\python.exe -m pytest -q    # OCR engine (a few minutes; needs PyMuPDF)
cd frontend;   npm run typecheck; npm run build
```

Backend and AI Engine tests use in-memory fakes and mocked HTTP: no Supabase project, OCR key or LLM key is needed.

---

## Known limitations

- Free LLM tiers run out quickly (OpenRouter free models: 50 requests/day). When every provider is rate-limited or
  unavailable, the answer check fails with a clear message and can be retried.
- OCR quality depends on the scan. With OCR.space alone, math and diagrams come out as plain text lines; set a
  Gemini key in `ocr-engine/.env` for the vision reader.
- Automatic answer checks run in a signed-in teacher's browser session (grading uses the teacher's permissions);
  submissions uploaded while no teacher is online are checked the next time one opens the app.
- Pictures embedded *inside* attached PDFs reach the AI as text only; attach important figures as pictures.
- Results from the copy and handwriting checks are not stored; there is no "reviewed, dismiss" state yet.
