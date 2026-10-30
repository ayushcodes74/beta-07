# TrustGrade

TrustGrade is a teacher-led academic grading workspace. The current frontend is a dependency-free browser prototype with responsive teacher and student views.

## Run the frontend

Open [`frontend/index.html`](./frontend/index.html) in a browser. No build step or package installation is required.

The prototype includes the classroom overview, courses, course materials, assignment authoring, submissions, OCR review, AI grading review, results, leaderboard, settings, and a student workspace preview. Navigation, filters, question editing, mock file uploads, grade review, and CSV export are interactive.

## Prototype data

The frontend currently uses in-memory sample data. AI question generation, OCR status, grading suggestions, course actions, publishing, and upload processing are demonstrations only; they do not call the TrustGrade API or persist changes. Refreshing the page resets the sample state.

The FastAPI backend is in [`backend/`](./backend). Connecting frontend actions to API endpoints is a separate integration step.