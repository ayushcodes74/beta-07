# AI Engine Integration Contract

This document provides the definitive integration specification for teammate services collaborating with the **AI Engine**:
1. **Main FastAPI Backend Teammate**
2. **OCR / Document Extraction Teammate**
3. **Database / Supabase Teammate**

---

## 1. What Data the OCR Teammate Must Provide

The AI Engine does not perform PDF parsing or computer vision. The OCR teammate extracts text and invokes the `TextChunker`:

### Input Payload for Document Indexing:
```python
pages = [
    {
        "page_number": 1,
        "text": "Extracted text content from page 1...",
        "section": "Chapter 2: Data Link Layer",   # Optional
        "ocr_confidence": 0.94                     # Optional float (0.0 to 1.0)
    },
    ...
]
```

### Python Method Call:
```python
from app.rag import TextChunker, CourseMaterialRetriever

chunker = TextChunker(chunk_size=500, chunk_overlap=100)
chunks = chunker.chunk_document_pages(
    pages=pages,
    course_id="CS301",
    document_id="doc_syllabus_ch2",
    title="Computer Networks Lecture 2",
)

retriever = CourseMaterialRetriever()
retriever.index_documents(chunks)
```

---

## 2. What Data the Main Backend Must Pass to AI Engine

The AI Engine is exposed as pure Python service classes. The FastAPI backend imports these services directly without route duplication.

### A. Syllabus Verification
```python
from app.syllabus import SyllabusDetector

detector = SyllabusDetector()
result = detector.detect_coverage(
    question="What is the difference between TCP and UDP?",
    course_id="CS301",
    syllabus_text="Unit 3: Transport Layer Protocols (optional direct text)"
)
```
- **Returns**: `SyllabusCoverageResult` (`status`: `IN_SYLLABUS`, `PARTIALLY_IN_SYLLABUS`, `OUT_OF_SYLLABUS`, or `UNCERTAIN`).

### B. Assignment Generation
```python
from app.assignment import AssignmentGenerator
from app.schemas.assignment import AssignmentGenerationRequest, QuestionType, DifficultyLevel

generator = AssignmentGenerator()
request = AssignmentGenerationRequest(
    course_id="CS301",
    topic="TCP Congestion Control",
    question_type=QuestionType.MIXED,
    question_count=4,
    total_marks=20.0,
    difficulty=DifficultyLevel.MEDIUM,
    teacher_instructions="Include slow start and congestion avoidance.",
)
draft = generator.generate_assignment(request)
```
- **Returns**: `AssignmentDraft` with **`status="DRAFT"`**.

### C. Semantic Grading & Trust Assessment
```python
from app.grading import AnswerEvaluator
from app.schemas.grading import GradingRequest

evaluator = AnswerEvaluator()
request = GradingRequest(
    course_id="CS301",
    assignment_id="asgn_101",
    submission_id="sub_202",
    question_id="q1",
    question_text="Explain TCP Slow Start mechanism.",
    question_max_marks=5.0,
    student_answer=extracted_student_answer,
    rubric=rubric_object,
    model_answer=model_answer_object,
)

grade = evaluator.evaluate_question(request, ocr_confidence=0.92)
```
- **Returns**: `QuestionGrade` with `awarded_marks`, `criterion_evaluations`, `confidence`, `review_required`, and `review_reasons`.

### D. Full Submission Grading
```python
grading_result = evaluator.grade_submission(
    submission_id="sub_202",
    assignment_id="asgn_101",
    requests=[request_q1, request_q2],
)
```
- **Returns**: `GradingResult` (`percentage`, `total_awarded_marks`, `overall_feedback`, `grading_status`: `COMPLETED` or `NEEDS_REVIEW`).

---

## 3. Operations Requiring Human Teacher Approval

In compliance with academic integrity and ethical AI constraints:
1. **Assignment Publication**: All newly generated assignments have `status="DRAFT"`. Only a teacher can transition the status to published after reviewing questions, marks, and rubrics.
2. **Review Routing**: If `review_required == True` (triggered by low confidence, lack of course evidence, or prompt injection attempts), grades **must not be auto-published**. They enter `PENDING` review for instructor confirmation.
3. **Reference Examples**: Teacher corrections are recorded with `approval_status="PENDING"`. Only examples explicitly transitioned to `APPROVED` by an instructor will be included in future grading prompts.

---

## 4. How the Database Teammate Implements Persistence

The AI Engine provides abstract storage interfaces decoupling it from direct database manipulation:

### Vector Storage (`app.rag.vector_store.VectorStore`)
- Default: `InMemoryVectorStore` for local development and unit tests.
- Supabase Integration: The teammate can connect `SupabaseVectorStore(supabase_client=client)` to interact with the `course_document_chunks` table and `match_document_chunks` pgvector RPC function.

### Reference Examples (`app.trust.reference_examples.ReferenceExampleStore`)
- Default: `InMemoryReferenceExampleStore`.
- The database teammate can implement a `SupabaseReferenceExampleStore(ReferenceExampleStore)` that queries the `teacher_reference_examples` table:
  - Columns: `example_id` (PK), `course_id` (indexed), `assignment_id`, `question_id`, `student_answer`, `teacher_corrected_marks`, `max_marks`, `teacher_feedback`, `approval_status` ('PENDING', 'APPROVED', 'REJECTED'), `is_active` (bool).

