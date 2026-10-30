# AI Engine - AI-Assisted Academic Grading System

The AI Engine is an independent, modular AI subsystem responsible for:
1. **LLM Integration**: Reusable Gemini client powered by the official `google-genai` SDK with retry, backoff, and Pydantic validation.
2. **RAG & Knowledge Retrieval**: Semantic chunking, sentence embeddings, and Supabase pgvector adapter with in-memory fallback.
3. **Syllabus & Assignment Intelligence**: Strict syllabus boundary verification and rubric/assignment drafting.
4. **AI Grading & Feedback**: Rubric-grounded semantic grading with partial marking, evidence citations, and deduction reasoning.
5. **Trust, Confidence & Human Review**: Prompt injection defense on untrusted submissions, multi-factor confidence estimation, and teacher review routing.

---

## Workspace Architecture

```
beta-07/
├── ai-engine/       # AI services (Isolated Python engine)
└── backend/         # Main FastAPI backend & Supabase DB (Teammate)
```

The AI Engine exposes pure Python service classes and Pydantic schemas, enabling seamless integration with the backend without route duplication.

---

## Setup & Installation

### 1. Create and Activate Virtual Environment
```bash
cd ai-engine
python -m venv venv
# On Windows:
venv\Scripts\activate
# On Linux/macOS:
source venv/bin/activate
```

### 2. Install Dependencies
```bash
pip install -r requirements.txt
```

### 3. Configure Environment Variables
Copy `.env.example` to `.env` and fill in your Gemini API key:
```bash
cp .env.example .env
```

```ini
GEMINI_API_KEY=your_gemini_api_key_here
GEMINI_MODEL=gemini-2.5-flash
GEMINI_EMBEDDING_MODEL=text-embedding-004
GEMINI_TEMPERATURE=0.2
GEMINI_MAX_RETRIES=3
GEMINI_REQUEST_TIMEOUT=30.0
```

---

## Module 1: LLM Integration Usage

```python
from app.llm import get_gemini_client, prompts
from pydantic import BaseModel

class GradingResponse(BaseModel):
    score: float
    feedback: str

client = get_gemini_client()

# Reusable text generation:
text = client.generate_text(
    prompt="Summarize the core premise of Newton's third law.",
    system_instruction="Be concise and academic."
)

# Structured JSON generation with strict Pydantic validation:
result = client.generate_structured(
    prompt="Grade: What is photosynthesis?",
    response_schema=GradingResponse,
    system_instruction="Evaluate strictly against the rubric."
)
print(result.score, result.feedback)
```

---

## Module 2: RAG & Knowledge Retrieval

### RAG Architecture

```
OCR Extracted Text (Teammate)
              │
              ▼
   ┌────────────────────┐
   │    TextChunker     │  Sliding window with sentence-break awareness
   └──────────┬─────────┘  Preserves document_id, page_number, course_id
              │ DocumentChunk
              ▼
   ┌────────────────────┐
   │ EmbeddingGenerator │  SentenceTransformers (all-MiniLM-L6-v2)
   └──────────┬─────────┘  Lazy-loaded, L2 normalized, 384 dimensions
              │ Chunks with dense vectors
              ▼
   ┌────────────────────┐
   │    VectorStore     │  InMemoryVectorStore (Local / Testing)
   │     (Interface)    │  SupabaseVectorStore (pgvector RPC Adapter)
   └──────────┬─────────┘
              │ Cosine similarity query (course-isolated)
              ▼
   ┌────────────────────┐
   │   ContextBuilder   │  Formats citations & enforces token character budget
   └──────────┬─────────┘
              │ Verified course evidence snippets
              ▼
   Passed to Gemini Grading & Syllabus Services
```

---

## Module 3: Syllabus & Assignment Intelligence

### 1. Syllabus Detection (`SyllabusDetector`)

Verifies question alignment strictly against retrieved course documents and syllabus outlines.

```python
from app.syllabus import SyllabusDetector
from app.rag import CourseMaterialRetriever

detector = SyllabusDetector(retriever=CourseMaterialRetriever())

result = detector.detect_coverage(
    question="Explain Dijkstra's shortest path algorithm.",
    course_id="CS101",
    syllabus_text="Unit 4: Graph Algorithms and Shortest Paths."
)

print(result.status)            # SyllabusCoverageStatus.IN_SYLLABUS
print(result.covered_concepts)  # ["Dijkstra's Algorithm", "Shortest Path"]
```

### 2. Assignment Generation (`AssignmentGenerator`)

Generates draft assignments with full teacher oversight:
- **Strict Draft Status**: All generated assignments have `status="DRAFT"`.
- **Question Types**: Multiple Choice Questions (MCQ), Subjective, or Mixed.
- **Auto Model Answers & Rubrics**: Complete model answers, key points, and objective rubrics.

---

## Module 4: AI Grading and Feedback

### Semantic Grading Architecture

```
Student Answer (OCR Teammate) + Question + Rubric + Model Answer
                           │
                           ▼
              ┌───────────────────────────┐
              │ GradingEvidenceRetriever  │ (RAG course grounding, course-isolated)
              └────────────┬──────────────┘
                           │
                           ▼
              ┌───────────────────────────┐
              │      AnswerEvaluator      │ (Gemini semantic rubric evaluator)
              └────────────┬──────────────┘
                           │
                           ▼
              ┌───────────────────────────┐
              │     FeedbackGenerator     │ (Constructive deduction & concept summary)
              └────────────┬──────────────┘
                           │
                           ▼
                     GradingResult
             (Pydantic output with citations,
          awarded marks, and review flags)
```

### Example Usage: Semantic Grading

```python
from app.grading import AnswerEvaluator
from app.schemas.grading import GradingRequest
from app.schemas.assignment import Rubric, RubricCriterion

evaluator = AnswerEvaluator()

rubric = Rubric(
    total_marks=5.0,
    criteria=[
        RubricCriterion(
            criterion_id="c1",
            description="Define Photosynthesis and light absorption.",
            max_marks=5.0,
            expected_concepts=["Chlorophyll", "Light energy to chemical energy"],
            acceptable_alternatives=["Solar energy conversion"],
        )
    ],
)

request = GradingRequest(
    course_id="BIO101",
    assignment_id="asgn_1",
    submission_id="sub_456",
    question_id="q1",
    question_text="Explain the process of photosynthesis.",
    question_max_marks=5.0,
    student_answer="Plants use solar energy captured by chlorophyll to synthesize sugars.",
    rubric=rubric,
)

grade = evaluator.evaluate_question(request)
print(f"Awarded: {grade.awarded_marks}/{grade.max_marks}")
print(f"Explanation: {grade.overall_explanation}")
print(f"Review Required: {grade.review_required}")
```

---

## Running Tests

Run all unit tests across all modules:
```bash
pytest tests/ -v
```

Run specific module tests:
```bash
pytest tests/test_llm.py -v
pytest tests/test_rag.py -v
pytest tests/test_syllabus.py -v
pytest tests/test_assignment.py -v
pytest tests/test_grading.py -v
```
