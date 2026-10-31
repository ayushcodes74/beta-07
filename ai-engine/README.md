# AI Engine - AI-Assisted Academic Grading System

The **AI Engine** is an independent, modular AI subsystem designed for rubric-grounded academic evaluation, RAG-backed syllabus verification, assignment generation, and adversarial prompt injection defense.

---

## 1. System Architecture & Modules

```
                           +----------------------------------------+
                           |       FastAPI Backend (Teammate)       |
                           +-------------------+--------------------+
                                               |
                                               v
+--------------------------------------------------------------------------------------------------+
|                                    AI Engine (app/)                                              |
|                                                                                                  |
|   +---------------------+   +---------------------+   +--------------------------------------+   |
|   |      Module 1:      |   |      Module 2:      |   |              Module 3:               |   |
|   |   LLM Integration   |   |   RAG & Retrieval   |   |        Syllabus & Assignments        |   |
|   |  - GeminiClient     |   |  - TextChunker      |   |  - SyllabusDetector                  |   |
|   |  - Exponential retry|   |  - Embeddings       |   |  - AssignmentGenerator (DRAFT only)  |   |
|   |  - Pydantic schema  |   |  - VectorStore      |   |  - RubricGenerator                   |   |
|   +----------+----------+   +----------+----------+   +------------------+-------------------+   |
|              |                         |                                 |                       |
|              +-------------------------+---------------------------------+                       |
|                                        |                                                         |
|                                        v                                                         |
|                     +--------------------------------------+                                     |
|                     |              Module 4:               |                                     |
|                     |        AI Grading & Feedback         |                                     |
|                     |  - AnswerEvaluator                   |                                     |
|                     |  - GradingEvidenceRetriever          |                                     |
|                     |  - FeedbackGenerator                 |                                     |
|                     +------------------+-------------------+                                     |
|                                        |                                                         |
|                                        v                                                         |
|                     +--------------------------------------+                                     |
|                     |              Module 5:               |                                     |
|                     |  Trust, Confidence & Human Review    |                                     |
|                     |  - PromptInjectionDetector           |                                     |
|                     |  - ConfidenceEstimator               |                                     |
|                     |  - HumanReviewRouter                 |                                     |
|                     |  - ReferenceExampleService           |                                     |
|                     +--------------------------------------+                                     |
+--------------------------------------------------------------------------------------------------+
```

---

## 2. Directory Structure

```
ai-engine/
├── app/
│   ├── __init__.py
│   ├── config.py                 # Environment configuration & settings
│   │
│   ├── llm/                      # MODULE 1: LLM Integration
│   │   ├── __init__.py
│   │   ├── gemini_client.py      # Reusable Gemini client with retries & validation
│   │   └── prompts.py            # Isolated prompts & system instructions
│   │
│   ├── rag/                      # MODULE 2: RAG & Knowledge Retrieval
│   │   ├── __init__.py
│   │   ├── chunker.py            # Sliding-window sentence-aware chunker
│   │   ├── embeddings.py         # SentenceTransformers & deterministic mock embedder
│   │   ├── vector_store.py       # VectorStore ABC, InMemoryVectorStore, SupabaseVectorStore
│   │   ├── retriever.py          # CourseMaterialRetriever with strict course isolation
│   │   └── context_builder.py    # Formats citations and enforces token budgets
│   │
│   ├── syllabus/                 # MODULE 3A: Syllabus Intelligence
│   │   ├── __init__.py
│   │   └── detector.py           # Syllabus coverage classifier
│   │
│   ├── assignment/               # MODULE 3B & 3C: Assignment & Rubric Generation
│   │   ├── __init__.py
│   │   ├── generator.py          # Draft MCQ & subjective question generator
│   │   └── rubric_generator.py   # Rubric generator with marks reconciliation
│   │
│   ├── grading/                  # MODULE 4: AI Grading & Feedback
│   │   ├── __init__.py
│   │   ├── evidence_retriever.py # Grounding course material retriever
│   │   ├── evaluator.py          # Semantic answer evaluator
│   │   └── feedback_generator.py # Constructive feedback & deduction breakdown
│   │
│   ├── trust/                    # MODULE 5: Trust, Confidence & Human Review
│   │   ├── __init__.py
│   │   ├── injection_detector.py # Adversarial prompt injection defense
│   │   ├── confidence.py         # Multi-factor confidence estimation
│   │   ├── review_router.py      # Human review routing & state transitions
│   │   ├── reference_examples.py # Teacher-corrected reference examples store
│   │   └── service.py            # Unified trust orchestrator
│   │
│   └── schemas/                  # Pydantic Schemas across all modules
│       ├── __init__.py
│       ├── common.py             # SourceReference, ConfidenceScore, ReviewReasonCategory
│       ├── rag.py                # DocumentChunk, RetrievedChunk, RetrievalRequest
│       ├── assignment.py         # AssignmentDraft, QuestionDraft, Rubric, ModelAnswer
│       ├── grading.py            # GradingRequest, CriterionEvaluation, QuestionGrade
│       └── trust.py              # InjectionDetectionResult, ConfidenceBreakdown, HumanReviewItem
│
├── tests/
│   ├── __init__.py
│   ├── test_llm.py               # Module 1 test suite (18 tests)
│   ├── test_rag.py               # Module 2 test suite (18 tests)
│   ├── test_syllabus.py          # Module 3A test suite (5 tests)
│   ├── test_assignment.py        # Module 3B/C test suite (7 tests)
│   ├── test_grading.py           # Module 4 test suite (9 tests)
│   └── test_trust.py             # Module 5 test suite (16 tests)
│
├── .env                          # Local environment variables
├── .env.example                  # Template configuration
├── .gitignore                    # Git ignore file
├── INTEGRATION.md                # Teammate integration contract
├── requirements.txt              # Project dependencies
└── README.md                     # Documentation & usage guide
```

---

## 3. Setup & Environment

### Installation
```bash
cd ai-engine
python -m venv venv
# On Windows:
venv\Scripts\activate
# On Linux/macOS:
source venv/bin/activate

pip install -r requirements.txt
```

### Configuration (`.env`)
```ini
GEMINI_API_KEY=your_gemini_api_key_here
GEMINI_MODEL=gemini-2.5-flash
GEMINI_EMBEDDING_MODEL=text-embedding-004
GEMINI_TEMPERATURE=0.2
GEMINI_MAX_RETRIES=3
GEMINI_REQUEST_TIMEOUT=30.0
```

### LLM fallback chain
All services call LLMs through `FallbackLLMClient` (`app.llm.get_llm_client()`). Each call
tries providers in order and moves to the next one on any provider-side failure (rate limit or
quota exhaustion, timeout, 5xx, missing key, invalid JSON/schema):

```
openrouter:OPENROUTER_MODEL -> openrouter:OPENROUTER_FALLBACK_MODELS... -> gemini:GEMINI_MODEL -> gemini:GEMINI_FALLBACK_MODELS...
```

- OpenRouter is the primary provider; Gemini is the backup. Providers without an API key are skipped.
  Change the order with `LLM_PROVIDER_ORDER` (default `openrouter,gemini`).
- Free OpenRouter models (`:free`) share tight rate limits, so `OPENROUTER_FALLBACK_MODELS` lists alternates
  tried before falling back to Gemini.
- A rate-limited or unreachable model is moved to the back of the chain for `LLM_RATE_LIMIT_COOLDOWN_SECONDS`
  (or `LLM_QUOTA_EXHAUSTED_COOLDOWN_SECONDS` for daily-quota errors), so calls don't keep hitting it.
- OpenRouter is called via its OpenAI-compatible API using `httpx` (no extra dependency).
- Speed: OpenRouter reasoning ("thinking") is off by default (`OPENROUTER_REASONING=off`), which cut
  question generation from ~66s to ~13s on free models; models that can't disable it are retried
  without the setting. Rubrics for subjective questions are generated in parallel.
- `GET /health` lists the active chain under `providers`.

See `.env.example` for all `OPENROUTER_*`, `GEMINI_*` and `LLM_*` settings.

### Course-material RAG for grading (MVP)

Answer checks retrieve passages from the teacher's course notes and pass them to the grader as evidence.

- **Embeddings:** real `sentence-transformers` model `all-MiniLM-L6-v2` (384-d, CPU). Install with
  `pip install torch --index-url https://download.pytorch.org/whl/cpu` then `pip install sentence-transformers`;
  the model downloads on first use. Production code never falls back to the hash `MockEmbeddingGenerator`:
  without the library, indexing returns 503 and grading marks evidence `unavailable`.
- **Index:** `app/rag/course_index.py` — `PersistentVectorStore` (extends `InMemoryVectorStore`) writes one JSON
  file per course to `storage/rag_index/` (gitignored; override with `RAG_INDEX_DIR`). It survives restarts and is
  strictly course-isolated. Re-uploading identical content is a no-op (`duplicate: true`); repeated chunks are skipped.
- **Ingestion:** teachers upload through the backend (`POST /api/v1/courses/{course_id}/materials`, course owner
  only; PDF/DOCX/PPTX/TXT, scanned PDFs via the OCR service). The backend calls this service:
  `POST /v1/materials/index` `{course_id, filename, pages:[{page_number, text}]}`, `GET /v1/materials?course_id=`,
  `DELETE /v1/materials/{material_id}?course_id=`, `POST /v1/materials/search` (inspection).
- **Grading:** `POST /v1/grading/grade-submission` retrieves the top `RAG_TOP_K` (default 4) passages with cosine
  similarity ≥ `RAG_MIN_SIMILARITY` (default 0.3) per question (query = question + answer key) and gives them,
  with the student answer, question, answer key and rubric, to the LLM. Each question in the response carries
  `evidence_status` (`available`/`unavailable`), `evidence_unavailable_reason` and `evidence` (passages with
  `similarity_score`, file, page); `rag` summarizes the course. Suggestions are never published automatically.

---

## 4. Public Service Interfaces

### 1. `GeminiClient` / `FallbackLLMClient` (`app.llm`)
`FallbackLLMClient` (from `get_llm_client()`) and `OpenAICompatibleClient` expose the same two methods:
- `generate_text(prompt, system_instruction=None, model=None, temperature=None) -> str`
- `generate_structured(prompt, response_schema=T, system_instruction=None) -> T`

### 2. `CourseMaterialRetriever` (`app.rag.CourseMaterialRetriever`)
- `index_documents(documents: List[DocumentChunk]) -> int`
- `retrieve(query: str, course_id: str, top_k=5, similarity_threshold=0.0) -> RetrievalResult`

### 3. `SyllabusDetector` (`app.syllabus.SyllabusDetector`)
- `detect_coverage(question: str, course_id: str, retrieved_evidence=None, syllabus_text=None) -> SyllabusCoverageResult`

### 4. `AssignmentGenerator` (`app.assignment.AssignmentGenerator`)
- `generate_assignment(request: AssignmentGenerationRequest) -> AssignmentDraft` (always returns `status="DRAFT"`)
- `edit_question(assignment: AssignmentDraft, question_id: str, ...) -> AssignmentDraft`

### 5. `AnswerEvaluator` (`app.grading.AnswerEvaluator`)
- `evaluate_question(request: GradingRequest, ocr_confidence=None) -> QuestionGrade`
- `grade_submission(submission_id: str, assignment_id: str, requests: List[GradingRequest]) -> GradingResult`

### 6. `TrustService` (`app.trust.TrustService`)
- `assess_submission(...) -> TrustAssessmentResult`
- `get_approved_reference_snippets(course_id: str, question_id=None) -> List[str]`
- `record_teacher_correction(...) -> ReferenceExample`

---

## 5. Confidence Formula & Thresholds

Confidence is calculated deterministically via `ConfidenceEstimator`:
$$\text{Overall Confidence} = (0.30 \times E_{\text{qual}}) + (0.25 \times E_{\text{cov}}) + (0.15 \times R_{\text{clarity}}) + (0.15 \times \text{OCR}) + (0.15 \times C_{\text{eval}})$$

- **`HIGH`**: $\ge 0.80$
- **`MEDIUM`**: $0.60 - 0.79$
- **`LOW`**: $< 0.60$
- **Review Threshold**: Overall $< 0.70$ or any critical factor $< 0.30$ flags submission for teacher review.

---

## 6. Review Routing & Teacher Control

A submission is flagged for teacher review (`review_required=True`, status `NEEDS_REVIEW`) whenever:
1. Prompt injection / adversarial instructions are detected.
2. Course materials lack evidence (`has_sufficient_evidence=False`).
3. Confidence score falls below the 0.70 threshold.
4. OCR confidence falls below 0.65.
5. Evaluator flags unusual student derivations or ambiguous rubrics.

**Important Academic Safeguards**:
- Prompt injection detection **never** automatically deducts marks.
- Low confidence or missing evidence triggers human review rather than an arbitrary deduction.
- Freshly generated assignments **always** require teacher approval (`status="DRAFT"`).
- Teacher corrections require explicit approval (`status="APPROVED"`) before inclusion as reference examples.

---

## 7. Running Tests

Run the full test suite across all 5 modules:
```bash
pytest tests/ -v
```

All 73 unit tests execute in ~1.1 seconds with complete isolation and mocks for external services.

---

## 8. Known Boundaries & Limitations

1. **No External DB Auto-Creation**: The AI Engine does not create database tables or assume external schemas. Supabase pgvector operations use the adapter interface defined in `SupabaseVectorStore`.
2. **No OCR/Vision**: Text extraction from images/PDFs must be performed by the OCR service prior to passing text to the `TextChunker`.
3. **No Autonomous Grade Publication**: In compliance with academic integrity guidelines, the AI Engine acts solely as an evaluation assistant. All grades and assignments remain drafts or pending reviews until authorized by human instructors.
