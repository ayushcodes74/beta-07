"""Course-material RAG for grading: real semantic retrieval, course isolation, persistence,
de-duplication, explicit missing-evidence reporting, and the grading endpoint end to end.

Uses the real all-MiniLM-L6-v2 sentence-transformer (no hash/mock embeddings). The LLM is faked so
the tests can inspect exactly what evidence reaches the grader prompt.
"""

from __future__ import annotations

import sys

import pytest
from fastapi.testclient import TestClient

pytest.importorskip("sentence_transformers")

from app import server  # noqa: E402
from app.grading.evaluator import AnswerEvaluator, _LLMCriterionEvaluation, _LLMQuestionGradeResponse  # noqa: E402
from app.grading.evidence_retriever import IndexEvidenceRetriever  # noqa: E402
from app.rag import course_index as course_index_module  # noqa: E402
from app.rag import embeddings as embeddings_module  # noqa: E402
from app.rag.course_index import CourseMaterialIndex  # noqa: E402
from app.rag.embeddings import EmbeddingsUnavailableError, SentenceTransformerEmbeddingGenerator  # noqa: E402

NOTES = [
    {"page_number": 1, "text": (
        "The Great Stupa at Sanchi is a large hemispherical brick dome built over relics of the Buddha. "
        "It was later enlarged and encased in stone, and is crowned by a harmika and a triple-tiered chatra."
    )},
    {"page_number": 2, "text": (
        "Four ornamental gateways called Toranas stand at the cardinal directions around the monument. "
        "Added in the 1st century BCE, their sculpted panels show scenes from the life of the Buddha and "
        "the Jataka tales."
    )},
    {"page_number": 3, "text": "Photosynthesis converts light energy into chemical energy inside chloroplasts."},
]


@pytest.fixture
def index(tmp_path):
    return CourseMaterialIndex(root=tmp_path / "rag")


def test_real_embeddings_are_used(index):
    assert isinstance(index.embedder, SentenceTransformerEmbeddingGenerator)
    assert index.embedder.model_name == "all-MiniLM-L6-v2"
    assert index.embedder.dimension == 384


def test_semantic_retrieval_matches_paraphrase(index):
    index.index_material("course-a", "sanchi.txt", NOTES)
    # No shared keywords with page 2 ("intricate carvings" vs "sculpted panels", "entrances" vs "gateways")
    results = index.retrieve("course-a", "intricate carvings on the four entrances", top_k=3, similarity_threshold=0.0)
    assert results[0].page_number == 2
    assert results[0].similarity_score > 0.3
    assert results[0].title == "sanchi.txt"
    assert results[0].metadata["material_id"].startswith("mat_")
    # Unrelated content scores far lower (negative cosine clamps to 0, not ~0.5)
    unrelated = [r for r in results if r.page_number == 3]
    assert not unrelated or unrelated[0].similarity_score < 0.2


def test_course_isolation(index):
    index.index_material("course-a", "sanchi.txt", NOTES)
    index.index_material("course-b", "biology.txt", [{"page_number": 1, "text": NOTES[2]["text"]}])

    a = index.retrieve("course-a", "Toranas gateways", top_k=10, similarity_threshold=0.0)
    b = index.retrieve("course-b", "Toranas gateways", top_k=10, similarity_threshold=0.0)
    assert {r.course_id for r in a} == {"course-a"}
    assert {r.course_id for r in b} == {"course-b"}
    assert all("Toranas" not in r.text for r in b)
    assert index.retrieve("course-c", "Toranas gateways") == []


def test_persists_across_restart(tmp_path):
    first = CourseMaterialIndex(root=tmp_path / "rag")
    created = first.index_material("course-a", "sanchi.txt", NOTES)
    del first  # simulate AI Engine restart: new process state, same directory

    restarted = CourseMaterialIndex(root=tmp_path / "rag")
    assert [m["filename"] for m in restarted.list_materials("course-a")] == ["sanchi.txt"]
    assert restarted.store.chunk_count("course-a") == created["chunks_indexed"]
    top = restarted.retrieve("course-a", "harmika and chatra on top of the dome", top_k=1, similarity_threshold=0.0)
    assert top[0].page_number == 1


def test_duplicate_upload_adds_no_chunks(index):
    first = index.index_material("course-a", "sanchi.txt", NOTES)
    again = index.index_material("course-a", "sanchi-copy.txt", NOTES)  # same content, new name
    assert first["duplicate"] is False and first["chunks_indexed"] > 0
    assert again["duplicate"] is True and again["chunks_indexed"] == 0
    assert again["material_id"] == first["material_id"]
    assert index.store.chunk_count("course-a") == first["chunks_indexed"]

    # Different file that repeats an already indexed page: only the new page is added
    overlap = index.index_material("course-a", "extra.txt", [NOTES[1], {"page_number": 2, "text": "Stupa 3 holds relics of Sariputra."}])
    assert overlap["duplicate"] is False
    assert overlap["chunks_indexed"] == 1 and overlap["chunks_skipped"] == 1


def test_delete_material(index):
    created = index.index_material("course-a", "sanchi.txt", NOTES)
    assert index.delete_material("course-a", created["material_id"]) == created["chunks_indexed"]
    assert index.list_materials("course-a") == []
    assert index.retrieve("course-a", "stupa dome") == []


def test_no_mock_fallback_when_sentence_transformers_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(embeddings_module, "_PRODUCTION_EMBEDDER", None)
    monkeypatch.setitem(sys.modules, "sentence_transformers", None)  # import now fails
    idx = CourseMaterialIndex(root=tmp_path / "rag")
    with pytest.raises(EmbeddingsUnavailableError):
        idx.index_material("course-a", "sanchi.txt", NOTES)


# ---------------------------------------------------------------------------
# Grading endpoint integration
# ---------------------------------------------------------------------------

Q2_KEY = (
    "The Toranas are four elaborately carved stone gateways facing the cardinal directions, with bas-reliefs "
    "depicting the life of the Buddha.\n\nKey points:\n"
    "- Four elaborately carved stone gateways (1 mark)\n"
    "- Face the four cardinal directions (1 mark)\n"
    "- Bas-reliefs depicting life of Buddha and Jataka tales (2 marks)\n"
)


class RecordingLLM:
    """Fake LLM: records grading prompts and awards every rubric point."""

    def __init__(self):
        self.prompts: list[str] = []

    def generate_structured(self, prompt, response_schema, system_instruction=None, **kwargs):
        if response_schema is not _LLMQuestionGradeResponse:
            raise RuntimeError("only grading calls are faked")
        self.prompts.append(prompt)
        return _LLMQuestionGradeResponse(
            awarded_marks=4,
            criterion_evaluations=[
                _LLMCriterionEvaluation(criterion_id=f"point_{i}", awarded_marks=m, max_marks=m,
                                        explanation="present", matched_concepts=["x"])
                for i, m in ((1, 1), (2, 1), (3, 2))
            ],
            overall_explanation="All points covered.",
            confidence=0.9,
        )


@pytest.fixture
def wired(index, monkeypatch):
    llm = RecordingLLM()
    evaluator = AnswerEvaluator(gemini_client=llm, evidence_retriever=IndexEvidenceRetriever(index=index))
    monkeypatch.setattr(server, "get_course_index", lambda: index)
    monkeypatch.setattr(server, "get_evaluator", lambda: evaluator)
    return TestClient(server.app), index, llm


def _body(course_id):
    return {
        "submission_id": "sub-1",
        "assignment_id": "asg-1",
        "course_id": course_id,
        # Semantically equivalent wording, no shared keywords with the notes' "sculpted panels"
        "student_text": "Q2. The Toranas are four beautifully carved entrances placed at the cardinal points, "
                        "decorated with intricate carvings about Buddha's life.",
        "ocr_confidence": 0.95,
        "questions": [{
            "question_id": "q2", "type": "subjective", "marks": 4, "expected_answer": Q2_KEY,
            "text": "Explain the features of the Toranas.",
        }],
    }


def test_grading_uses_retrieved_course_evidence(wired):
    client, index, llm = wired
    index.index_material("course-a", "sanchi.txt", NOTES)

    response = client.post("/v1/grading/grade-submission", json=_body("course-a"))

    assert response.status_code == 200, response.text
    result = response.json()
    question = result["question_results"][0]
    assert question["evidence_status"] == "available"
    assert question["evidence_unavailable_reason"] is None
    top = question["evidence"][0]
    assert top["page_number"] == 2 and top["title"] == "sanchi.txt"
    assert top["similarity_score"] >= 0.3
    assert "sculpted panels" in top["snippet"]
    # Evidence, answer key, rubric and student answer all reach the grader prompt
    prompt = llm.prompts[0]
    assert "sculpted panels" in prompt and "[Ref: sanchi.txt (p. 2)]" in prompt
    assert "Bas-reliefs depicting life of Buddha" in prompt  # rubric point / answer key
    assert "beautifully carved entrances" in prompt          # student answer
    # Unrelated page never becomes evidence
    assert all("Photosynthesis" not in e["snippet"] for e in question["evidence"])
    assert result["rag"]["status"] == "available"
    assert result["rag"]["embedding_model"] == "all-MiniLM-L6-v2"
    assert result["rag"]["materials_indexed"] == 1
    assert not any("Insufficient course evidence" in r for r in question["review_reasons"])


def test_grading_marks_evidence_unavailable_without_materials(wired):
    client, _, llm = wired

    result = client.post("/v1/grading/grade-submission", json=_body("course-empty")).json()

    question = result["question_results"][0]
    assert question["evidence_status"] == "unavailable"
    assert "No course materials have been indexed" in question["evidence_unavailable_reason"]
    assert question["evidence"] == []
    assert result["rag"]["status"] == "unavailable"
    assert "No specific course excerpts retrieved." in llm.prompts[0]  # grader told explicitly: no evidence
    assert any("Insufficient course evidence" in r for r in question["review_reasons"])


def test_grading_marks_evidence_unavailable_without_course(wired):
    client, _, _ = wired
    body = _body("course-a")
    body["course_id"] = None

    result = client.post("/v1/grading/grade-submission", json=body).json()

    assert result["question_results"][0]["evidence_status"] == "unavailable"
    assert "not linked to a course" in result["rag"]["reason"]


def test_irrelevant_materials_are_not_used_as_evidence(wired):
    client, index, _ = wired
    index.index_material("course-bio", "bio.txt", [{"page_number": 1, "text": NOTES[2]["text"]}])

    result = client.post("/v1/grading/grade-submission", json=_body("course-bio")).json()

    question = result["question_results"][0]
    assert question["evidence_status"] == "unavailable"
    assert "relevant enough" in question["evidence_unavailable_reason"]


def test_materials_endpoints(wired):
    client, _, _ = wired
    body = {"course_id": "course-a", "filename": "sanchi.txt", "pages": NOTES}
    created = client.post("/v1/materials/index", json=body).json()
    assert created["duplicate"] is False and created["chunks_indexed"] == 3
    assert client.post("/v1/materials/index", json=body).json()["duplicate"] is True

    listing = client.get("/v1/materials", params={"course_id": "course-a"}).json()
    assert [m["filename"] for m in listing["materials"]] == ["sanchi.txt"]
    assert listing["chunk_count"] == 3

    found = client.post("/v1/materials/search", json={"course_id": "course-a", "query": "umbrella on top"}).json()
    assert found["results"][0]["page_number"] == 1

    deleted = client.delete(f"/v1/materials/{created['material_id']}", params={"course_id": "course-a"}).json()
    assert deleted["deleted_chunks"] == 3
    assert client.delete(f"/v1/materials/{created['material_id']}", params={"course_id": "course-a"}).status_code == 404
