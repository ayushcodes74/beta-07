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
