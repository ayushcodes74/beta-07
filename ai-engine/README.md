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

## Running Tests

```bash
pytest tests/test_llm.py -v
```

