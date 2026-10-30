# TrustGrade 🎓

### AI-Assisted Grading You Can Trust

**Every mark has a reason. Every decision has evidence.**

TrustGrade is an AI-assisted assignment evaluation platform designed to make academic grading faster, more transparent, consistent, and reliable.

It combines OCR technology, AI-powered evaluation, evidence-based feedback, and teacher supervision to simplify the assignment evaluation process while keeping teachers in control of final academic decisions.

> **AI suggests. Evidence supports. Teachers decide.**

---

## 📌 Table of Contents

- [Problem Statement](#-problem-statement)
- [Our Solution](#-our-solution)
- [Key Features](#-key-features)
- [How TrustGrade Works](#-how-trustgrade-works)
- [System Architecture](#-system-architecture)
- [Technology Stack](#-technology-stack)
- [Project Structure](#-project-structure)
- [Backend Architecture](#-backend-architecture)
- [Core Modules](#-core-modules)
- [Assignment Evaluation Workflow](#-assignment-evaluation-workflow)
- [Database and Storage](#-database-and-storage)
- [API Structure](#-api-structure)
- [Security and Reliability](#-security-and-reliability)
- [Installation and Setup](#-installation-and-setup)
- [Environment Variables](#-environment-variables)
- [Running the Application](#-running-the-application)
- [Team Responsibilities](#-team-responsibilities)
- [Development Roadmap](#-development-roadmap)
- [Future Scope](#-future-scope)
- [Project Philosophy](#-project-philosophy)

---

## 🚨 Problem Statement

Traditional assignment evaluation is time-consuming, repetitive, and often inconsistent.

Teachers spend significant time reading handwritten submissions, checking answers against marking schemes, calculating marks, and preparing feedback.

Some major challenges include:

- Manual evaluation of large numbers of assignments.
- Difficulty reading handwritten submissions.
- Inconsistent marking across students.
- Time-consuming subjective answer evaluation.
- Lack of transparent explanations for awarded marks.
- Difficulty managing assignment deadlines and late submissions.
- Limited personalized feedback for students.
- Difficulty maintaining consistent grading standards.

Traditional automated grading systems may also produce marks without providing sufficient evidence or allowing teachers to verify the reasoning.

TrustGrade aims to address these challenges through evidence-based AI-assisted grading.

---

## 💡 Our Solution

TrustGrade provides an integrated platform where teachers can manage courses, upload study materials, create assignments, evaluate student submissions, and publish results.

The platform uses:

1. **OCR technology** to extract text from handwritten assignment PDFs.
2. **AI-powered evaluation** to assess subjective answers against assignment questions, rubrics, and available educational materials.
3. **Evidence-based feedback** to explain awarded marks.
4. **Teacher supervision** to review, modify, approve, and publish final grades.
5. **Automated MCQ evaluation** using deterministic scoring logic.

AI-generated marks are suggestions, not final academic decisions.

Teachers retain control over grading and publication.

---

## ✨ Key Features

### 👨‍🏫 Teacher Dashboard

- Create and manage courses.
- Enroll and manage students.
- Upload course materials.
- Create assignments manually.
- Generate assignments using AI.
- Review and approve AI-generated assignments.
- Configure questions, marks, rubrics, and deadlines.
- View student submissions.
- Review OCR extraction results.
- Accept or reject late submissions.
- Review AI-generated marks and feedback.
- Modify and approve grades.
- Publish final results.
- View class performance analytics.
- Enable or disable leaderboards.

### 👨‍🎓 Student Dashboard

- View enrolled courses.
- Access published assignments.
- View assignment instructions and deadlines.
- Submit handwritten assignments as PDFs.
- Attempt MCQs online.
- Track submission status.
- View published marks.
- Receive question-wise feedback.
- View explanations for awarded marks.
- Access expected solutions when released.
- View leaderboards when enabled.

### 📄 OCR-Based Handwriting Recognition

- Process handwritten assignment PDFs.
- Extract text from scanned pages.
- Support mathematical expressions through the OCR service.
- Track OCR processing status.
- Identify low-confidence extraction.
- Allow teacher review and correction.
- Preserve original submissions and OCR outputs.

### 🤖 AI-Powered Assignment Generation

Teachers can request AI-generated assignments based on available educational context.

The AI engine can generate:

- Multiple-choice questions.
- Subjective questions.
- Suggested answers.
- Suggested marking schemes.
- Suggested rubrics.

Generated assignments remain drafts until approved by the teacher.

### 🧠 AI-Assisted Subjective Grading

- Evaluate answers against question requirements.
- Consider teacher-provided rubrics.
- Use available course materials and syllabus context.
- Generate question-wise marks.
- Provide explanations and feedback.
- Identify supporting evidence.
- Flag uncertain evaluations for teacher review.

### 📊 Transparent Results

- Question-wise marks.
- Total marks.
- Feedback and explanations.
- Teacher-approved results.
- Optional expected solutions.
- Course leaderboards.
- Performance analytics.

---

## 🔄 How TrustGrade Works

```text
          TEACHER
             |
             v
      Create Course
             |
             v
      Upload Materials
             |
             v
    Create Assignment
       /          \
   Manual         AI
       \          /
        \        /
         v      v
      Teacher Approval
             |
             v
      Publish Assignment
             |
             v
           STUDENT
             |
             v
       Submit Assignment
        /           \
   Handwritten       MCQ
       PDF          Online
        |
        v
     OCR Engine
        |
        v
   Extracted Text
        |
        v
   AI Grading Engine
        |
        v
  Marks + Evidence
        |
        v
   Teacher Review
        |
        v
   Teacher Approval
        |
        v
   Publish Results
        |
        v
   Student Feedback
```

---

## 🏗️ System Architecture

TrustGrade follows a modular architecture with separate components for the frontend, backend, OCR processing, and AI evaluation.

```text
                  TRUSTGRADE
                       |
          +------------+------------+
          |                         |
          v                         v
     FRONTEND                  FASTAPI BACKEND
   React + Tailwind                 |
          |                         |
          +------ REST APIs --------+
                                    |
               +--------------------+-------------------+
               |                    |                   |
               v                    v                   v
         AUTH MODULE         COURSE MODULE       ASSIGNMENT MODULE
               |                    |                   |
               +--------------------+-------------------+
                                    |
                                    v
                           SUBMISSION MODULE
                                    |
                         +----------+----------+
                         |                     |
                         v                     v
                     OCR ENGINE           MCQ SCORING
                         |
                         v
                    AI GRADING ENGINE
                         |
                         v
                  GRADING & RESULTS
                         |
                         v
                    TEACHER REVIEW
                         |
                         v
                   PUBLISHED RESULTS

                SUPABASE
          PostgreSQL + Auth + Storage
```

### Main Components

| Component | Responsibility |
|---|---|
| Frontend | Teacher and student interfaces |
| FastAPI Backend | APIs, authorization, workflows and integrations |
| OCR Engine | Handwriting and document text extraction |
| AI Engine | Assignment generation and subjective evaluation |
| Supabase | Database, authentication and file storage |

---

## 🛠️ Technology Stack

### Backend

- Python
- FastAPI
- Uvicorn
- Pydantic
- HTTPX
- PyJWT

### Frontend

- React
- Vite
- Tailwind CSS
- Axios
- React Router

### Database and Storage

- Supabase
- PostgreSQL
- Supabase Auth
- Supabase Storage
- pgvector (for vector search, if enabled and required by the AI integration)

### OCR Engine

- PaddleOCR
- PyMuPDF
- TrOCR Math

### AI Engine

- Large Language Models
- Embeddings
- Retrieval-Augmented Generation (RAG)
- Vector search
- Evidence-based evaluation

*Specific model providers and deployment configurations will be finalized during implementation.*

---

## 📁 Project Structure

```text
beta-07/
│
├── backend/
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py
│   │   │
│   │   ├── core/
│   │   │   ├── __init__.py
│   │   │   ├── config.py
│   │   │   ├── security.py
│   │   │   └── dependencies.py
│   │   │
│   │   ├── api/
│   │   │   ├── __init__.py
│   │   │   └── v1/
│   │   │       ├── __init__.py
│   │   │       ├── router.py
│   │   │       └── endpoints/
│   │   │
│   │   ├── schemas/
│   │   │   ├── __init__.py
│   │   │   ├── auth.py
│   │   │   ├── user.py
│   │   │   ├── course.py
│   │   │   ├── material.py
│   │   │   ├── assignment.py
│   │   │   ├── submission.py
│   │   │   └── grading.py
│   │   │
│   │   ├── services/
│   │   │   ├── __init__.py
│   │   │   ├── auth_service.py
│   │   │   ├── course_service.py
│   │   │   ├── material_service.py
│   │   │   ├── assignment_service.py
│   │   │   ├── submission_service.py
│   │   │   ├── storage_service.py
│   │   │   ├── ocr_client.py
│   │   │   ├── ai_client.py
│   │   │   ├── grading_service.py
│   │   │   └── leaderboard_service.py
│   │   │
│   │   ├── workers/
│   │   │   └── processing.py
│   │   │
│   │   └── utils/
│   │       └── file_validator.py
│   │
│   ├── tests/
│   ├── .env.example
│   ├── .gitignore
│   └── requirements.txt
│
├── frontend/
│
├── ai-engine/
│
├── ocr-engine/
│
└── README.md
```

---

## ⚙️ Backend Architecture

The backend is divided into five functional modules.

Each module contains API endpoints, Pydantic schemas, and service-layer logic.

### Module 1: Authentication & User Management

**Purpose:** Manage user identity, authentication, and authorization.

Responsibilities:

- Registration and login.
- JWT verification.
- User profile management.
- Teacher and student roles.
- Role-based access control.
- Authenticated user information.

### Module 2: Course & Study Material Management

**Purpose:** Manage courses and educational resources.

Responsibilities:

- Course creation and management.
- Student enrollment.
- Course-level permissions.
- Uploading syllabus and rulebooks.
- Uploading notes, PDFs, and PPTs.
- Secure file storage.
- Material metadata management.

### Module 3: Assignment Management

**Purpose:** Handle assignment creation, configuration, and publishing.

Responsibilities:

- Manual assignment creation.
- AI-generated assignment integration.
- Question management.
- MCQ and subjective question configuration.
- Rubric management.
- Expected solutions.
- Assignment deadlines.
- Assignment publishing.
- Assignment version management.

### Module 4: Submission & OCR Management

**Purpose:** Manage student submissions and document processing.

Responsibilities:

- PDF assignment submissions.
- Online MCQ submissions.
- Submission timestamps.
- Deadline validation.
- Late submission handling.
- Teacher acceptance or rejection of late submissions.
- OCR service integration.
- OCR status tracking.
- OCR correction and review.

### Module 5: Grading, Results & Analytics

**Purpose:** Manage evaluation, teacher review, and final results.

Responsibilities:

- AI grading service integration.
- Deterministic MCQ scoring.
- Question-wise marks.
- Evidence and feedback management.
- Teacher grading review.
- Grade modification and approval.
- Result publication.
- Student result access.
- Leaderboard generation.
- Course performance analytics.

---

## 📝 Assignment Evaluation Workflow

### 1. Assignment Creation

Teachers can manually create assignments or request AI-generated assignments.

AI-generated assignments are returned as drafts.

Teachers can edit and approve them before publishing.

### 2. Student Submission

Students can submit:

- Handwritten assignment PDFs.
- Online MCQ answers.

The backend records the actual server-side submission timestamp.

### 3. Late Submission Handling

If a submission arrives after the deadline:

- The submission is still recorded.
- It is marked as late.
- It is placed in a pending teacher decision state.
- The teacher can accept or reject it.

Late submissions are not automatically rejected.

### 4. OCR Processing

Handwritten PDFs are sent to the OCR engine.

The OCR service extracts text and provides processing information.

Low-confidence or failed OCR results are flagged for review.

OCR failures must never automatically result in zero marks.

### 5. AI Evaluation

Verified extracted text, assignment questions, rubrics, and available context are sent to the AI grading engine.

The AI engine returns suggested marks, feedback, and supporting evidence.

### 6. Teacher Review

Teachers can:

- Inspect AI-generated marks.
- Review supporting evidence.
- Edit marks.
- Modify feedback.
- Approve or request reevaluation.

### 7. Result Publication

Only teacher-approved grades are published.

Students can then access their marks, feedback, and released expected solutions.

---

## 🗄️ Database and Storage

TrustGrade uses Supabase as its planned database and storage platform.

The database schema and database management are maintained separately from the FastAPI backend.

### Planned capabilities

- User and course data.
- Enrollment management.
- Assignment metadata.
- Question and rubric information.
- Submission records.
- OCR processing records.
- Grading results.
- Teacher review history.
- Published results.
- Audit logs.

### Storage

Supabase Storage is intended to manage:

- Student assignment PDFs.
- Teacher-uploaded study materials.
- Supporting educational documents.

Private file access and authorization must be enforced.

The backend will integrate with the database through the agreed schema and access contract.

---

## 🔌 API Structure

The backend exposes versioned REST APIs.

Base URL:

```text
/api/v1
```

### Authentication

| Method | Endpoint | Purpose |
|---|---|---|
| POST | `/auth/register` | Register user |
| POST | `/auth/login` | Login |
| POST | `/auth/logout` | Logout |
| GET | `/auth/me` | Get authenticated user |

### Users

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/users/me` | Get profile |
| PATCH | `/users/me` | Update profile |

### Courses

| Method | Endpoint | Purpose |
|---|---|---|
| POST | `/courses` | Create course |
| GET | `/courses` | List courses |
| GET | `/courses/{course_id}` | Get course |
| PATCH | `/courses/{course_id}` | Update course |
| DELETE | `/courses/{course_id}` | Archive/delete course |
| POST | `/courses/{course_id}/enroll` | Enroll student |

### Study Materials

| Method | Endpoint | Purpose |
|---|---|---|
| POST | `/courses/{course_id}/materials` | Upload material |
| GET | `/courses/{course_id}/materials` | List materials |
| GET | `/materials/{material_id}` | Get material |
| DELETE | `/materials/{material_id}` | Delete/archive material |

### Assignments

| Method | Endpoint | Purpose |
|---|---|---|
| POST | `/assignments` | Create assignment |
| GET | `/assignments` | List assignments |
| GET | `/assignments/{assignment_id}` | Get assignment |
| PATCH | `/assignments/{assignment_id}` | Update assignment |
| POST | `/assignments/generate` | Request AI generation |
| POST | `/assignments/{assignment_id}/publish` | Publish assignment |

### Submissions

| Method | Endpoint | Purpose |
|---|---|---|
| POST | `/submissions` | Submit assignment |
| GET | `/submissions/{submission_id}` | Get submission |
| POST | `/submissions/{submission_id}/ocr` | Trigger OCR |
| GET | `/submissions/{submission_id}/ocr` | Get OCR status/result |
| PATCH | `/submissions/{submission_id}/late-decision` | Decide late submission |

### Grading and Results

| Method | Endpoint | Purpose |
|---|---|---|
| POST | `/grading/{submission_id}/evaluate` | Trigger grading |
| GET | `/grading/{grading_id}` | Get grading result |
| PATCH | `/grading/{grading_id}/review` | Review grading |
| POST | `/grading/{grading_id}/approve` | Approve grading |
| POST | `/results/{result_id}/publish` | Publish result |
| GET | `/results/me` | Get student results |
| GET | `/courses/{course_id}/leaderboard` | Get leaderboard |

*These are planned API routes. Actual implementations and request/response contracts will be finalized during development.*

---

## 🔐 Security and Reliability

TrustGrade is designed with the following safeguards:

- JWT-based authentication.
- Role-based access control.
- Course-level authorization.
- Secure file uploads.
- Private storage for student submissions.
- Environment-based configuration.
- No hardcoded credentials.
- Input validation using Pydantic.
- Server-side deadline enforcement.
- Teacher approval before result publication.
- Auditability of grading decisions.
- Preservation of original submissions.
- Separate tracking of OCR and grading status.

### Important grading safeguards

1. OCR failure must not mean zero marks.
2. AI-generated marks must not automatically become final grades.
3. Students must not access other students' submissions or results.
4. Unpublished expected solutions must remain private.
5. Teacher corrections must be traceable.
6. Uncertain evaluations must be flagged for review.

---

## 🚀 Installation and Setup

### Prerequisites

Install:

- Python 3.12 or 3.13 (recommended for the project).
- Git.
- Node.js and npm for frontend development.

### 1. Clone the repository

```bash
git clone https://github.com/ayushcodes74/beta-07.git

cd beta-07
```

### 2. Navigate to backend

```bash
cd backend
```

### 3. Create a virtual environment

Windows:

```powershell
python -m venv venv
venv\Scripts\activate
```

Linux/macOS:

```bash
python -m venv venv
source venv/bin/activate
```

### 4. Install dependencies

```bash
pip install -r requirements.txt
```

### 5. Configure environment variables

Create a `.env` file using `.env.example` as a reference.

Fill in the required configuration values when the corresponding services are available.

Never commit `.env` to GitHub.

### 6. Start the FastAPI server

```bash
uvicorn app.main:app --reload
```

### 7. Access API documentation

Open:

```text
http://127.0.0.1:8000/docs
```

Other useful endpoints:

```text
http://127.0.0.1:8000/
http://127.0.0.1:8000/health
http://127.0.0.1:8000/api/v1/health
```

---

## 🔑 Environment Variables

The following are examples of configuration variables expected as integrations are implemented.

```env
# Application
APP_NAME=TrustGrade API
APP_VERSION=1.0.0
DEBUG=True

# Supabase
SUPABASE_URL=
SUPABASE_KEY=

# OCR Service
OCR_SERVICE_URL=

# AI Service
AI_SERVICE_URL=

# Security
JWT_SECRET_KEY=
JWT_ALGORITHM=HS256
```

Only configure variables that are required by the currently implemented modules.

Never commit actual secrets or service-role keys.

---

## 👥 Team Responsibilities

TrustGrade is developed collaboratively with separate responsibilities.

| Team Member / Role | Responsibility |
|---|---|
| Backend Developer | FastAPI APIs, authentication, business logic and service integration |
| Database Developer | Supabase PostgreSQL schema, database management and access policies |
| OCR Developer | Handwriting recognition, PDF processing and OCR output |
| AI Developer | RAG, assignment generation and subjective grading |
| Frontend Developer | React interface, dashboards and backend integration |

### Integration between teams

The backend communicates with the OCR and AI engines through agreed API contracts.

The database developer provides the backend with the finalized schema and access details.

The frontend communicates with FastAPI through REST APIs.

---

## 📅 Development Roadmap

### Phase 1 — Backend Foundation

- [ ] FastAPI project setup.
- [ ] Configuration management.
- [ ] API routing.
- [ ] Swagger documentation.
- [ ] Error handling.

### Phase 2 — Authentication and Courses

- [ ] Authentication APIs.
- [ ] JWT verification.
- [ ] Role-based authorization.
- [ ] Course management.
- [ ] Student enrollment.
- [ ] Study material management.

### Phase 3 — Assignment Management

- [ ] Manual assignment creation.
- [ ] Question management.
- [ ] Rubric management.
- [ ] AI assignment generation integration.
- [ ] Assignment publishing.

### Phase 4 — Submission and OCR

- [ ] PDF submission.
- [ ] MCQ submission.
- [ ] Deadline validation.
- [ ] Late submission decisions.
- [ ] OCR integration.
- [ ] OCR review workflow.

### Phase 5 — Grading and Results

- [ ] MCQ scoring.
- [ ] AI grading integration.
- [ ] Evidence and feedback.
- [ ] Teacher grading review.
- [ ] Grade approval.
- [ ] Result publication.
- [ ] Leaderboard and analytics.

### Phase 6 — Testing and Deployment

- [ ] Backend integration testing.
- [ ] Authorization testing.
- [ ] Frontend integration.
- [ ] OCR and AI integration testing.
- [ ] Error handling and reliability checks.
- [ ] Deployment.

---

## 🔮 Future Scope

Potential future improvements include:

- Multilingual handwriting recognition.
- Advanced mathematical answer evaluation.
- More detailed grading analytics.
- Personalized learning recommendations.
- Adaptive question generation.
- Improved rubric recommendations.
- Historical grading consistency analysis.
- More advanced teacher feedback analytics.

---

## 💬 Project Philosophy

TrustGrade is not designed to replace teachers.

It is designed to reduce repetitive work, provide useful evaluation assistance, and make grading more transparent.

Every evaluation should be explainable.

Every awarded mark should have supporting evidence.

Every final grading decision should remain under teacher control.

**AI suggests. Evidence supports. Teachers decide.**

---

## 🏆 Project Information

**Project:** TrustGrade  
**Event:** Version Beta 9.0  
**Problem Statement:** Problem Statement 3 — AI-Assisted Grading You Can Trust  
**Repository:** https://github.com/ayushcodes74/beta-07

---

<p align="center">
  <strong>TrustGrade — Every mark has a reason. Every decision has evidence.</strong>
</p>