"""Unit tests for Module 2: RAG and Knowledge Retrieval."""

from unittest.mock import MagicMock
import pytest

from app.rag.chunker import TextChunker
from app.rag.embeddings import (
    MockEmbeddingGenerator,
    SentenceTransformerEmbeddingGenerator,
    get_embedding_generator,
)
from app.rag.vector_store import (
    InMemoryVectorStore,
    SupabaseVectorStore,
    _cosine_similarity,
)
from app.rag.retriever import CourseMaterialRetriever
from app.rag.context_builder import ContextBuilder
from app.schemas.rag import DocumentChunk, RetrievalRequest, RetrievedChunk
from app.llm import prompts


# ---------------------------------------------------------------------------
# Chunker Tests
# ---------------------------------------------------------------------------

def test_chunker_empty_and_whitespace_text():
    """Test chunker gracefully returns empty list on empty or whitespace strings."""
    chunker = TextChunker(chunk_size=100, chunk_overlap=20)
    assert chunker.chunk_text("", course_id="CS101", document_id="doc1") == []
    assert chunker.chunk_text("   \n\t  ", course_id="CS101", document_id="doc1") == []


def test_chunker_short_text():
    """Test short text produces exactly one chunk with full metadata."""
    chunker = TextChunker(chunk_size=200, chunk_overlap=30)
    short_text = "Operating systems manage hardware resources."

    chunks = chunker.chunk_text(
        text=short_text,
        course_id="CS101",
        document_id="lec_1",
        title="Lecture 1 Intro",
        page_number=3,
        section="Architecture Overview",
        metadata={"author": "Prof. Smith"},
    )

    assert len(chunks) == 1
    c = chunks[0]
    assert c.text == short_text
    assert c.course_id == "CS101"
    assert c.document_id == "lec_1"
    assert c.title == "Lecture 1 Intro"
    assert c.page_number == 3
    assert c.section == "Architecture Overview"
    assert c.metadata["author"] == "Prof. Smith"
    assert c.chunk_id == "lec_1_p3_c0"


def test_chunker_overlapping_splits():
    """Test long text is split into multiple overlapping chunks."""
    chunker = TextChunker(chunk_size=100, chunk_overlap=30, min_chunk_size=10)
    long_text = (
        "First sentence of course material. Second sentence with important definitions. "
        "Third sentence describing algorithms and complexity. Fourth sentence covering memory hierarchy. "
        "Fifth sentence summarizing cache performance and miss rates."
    )

    chunks = chunker.chunk_text(
        text=long_text,
        course_id="CS102",
        document_id="textbook",
        page_number=12,
    )

    assert len(chunks) > 1
    # Check consecutive chunk overlap
    for i in range(len(chunks) - 1):
        c1 = chunks[i].text
        c2 = chunks[i + 1].text
        # There should be shared content between consecutive chunks
        assert any(word in c2 for word in c1.split()[-3:] if len(word) > 3)


def test_chunker_document_pages():
    """Test chunking multiple pages preserving page numbers."""
    chunker = TextChunker(chunk_size=150, chunk_overlap=20)
    pages = [
        {"page_number": 1, "text": "Page one explains process scheduling algorithms.", "section": "CPU Scheduling"},
        {"page_number": 2, "text": "Page two explains thread synchronization and semaphores.", "section": "Concurrency"},
    ]

    chunks = chunker.chunk_document_pages(
        pages=pages,
        course_id="CS101",
        document_id="handout_1",
        title="OS Review",
    )

    assert len(chunks) == 2
    assert chunks[0].page_number == 1
    assert chunks[0].section == "CPU Scheduling"
    assert chunks[1].page_number == 2
    assert chunks[1].section == "Concurrency"


def test_chunker_invalid_parameters():
    """Test that invalid chunking parameters raise ValueError."""
    with pytest.raises(ValueError, match="chunk_size must be positive"):
        TextChunker(chunk_size=0)
    with pytest.raises(ValueError, match="chunk_overlap cannot be negative"):
        TextChunker(chunk_size=100, chunk_overlap=-5)
    with pytest.raises(ValueError, match="chunk_overlap .* must be less than chunk_size"):
        TextChunker(chunk_size=100, chunk_overlap=100)


# ---------------------------------------------------------------------------
# Embedding Generator Tests
# ---------------------------------------------------------------------------

def test_mock_embedding_generator_properties():
    """Test deterministic mock embedder output and normalization."""
    embedder = MockEmbeddingGenerator(dimension=128)
    assert embedder.dimension == 128

    vec1 = embedder.generate_embedding("Binary search trees have logarithmic depth.")
    vec2 = embedder.generate_embedding("Binary search trees have logarithmic depth.")
    vec3 = embedder.generate_embedding("Completely different topic about literature.")

    assert len(vec1) == 128
    # Determinism
    assert vec1 == vec2
    # Dissimilar vectors for distinct texts
    sim_same = _cosine_similarity(vec1, vec2)
    sim_diff = _cosine_similarity(vec1, vec3)
    assert pytest.approx(sim_same, abs=1e-4) == 1.0
    assert sim_diff < 0.9

    # Empty text produces zero vector
    zero_vec = embedder.generate_embedding("")
    assert all(x == 0.0 for x in zero_vec)


def test_mock_batch_embedding():
    """Test batch embedding generation."""
    embedder = MockEmbeddingGenerator(dimension=64)
    texts = ["Quick sort", "Merge sort", "Heap sort"]
    batch_vecs = embedder.generate_embeddings(texts)
    assert len(batch_vecs) == 3
    assert all(len(v) == 64 for v in batch_vecs)


def test_sentence_transformer_lazy_loading(monkeypatch):
    """Test SentenceTransformer generator delays import and load until first access."""
    gen = SentenceTransformerEmbeddingGenerator(model_name="test-model")
    assert gen._model is None

    # Mock the sentence_transformers library
    mock_st_class = MagicMock()
    mock_model_instance = MagicMock()
    mock_model_instance.get_sentence_embedding_dimension.return_value = 384
    mock_st_class.return_value = mock_model_instance

    import sys
    fake_st_module = MagicMock()
    fake_st_module.SentenceTransformer = mock_st_class
    monkeypatch.setitem(sys.modules, "sentence_transformers", fake_st_module)

    # First access to property initializes
    _ = gen.model
    assert gen._model == mock_model_instance
    mock_st_class.assert_called_once_with("test-model", device="cpu")


# ---------------------------------------------------------------------------
# Vector Store Tests
# ---------------------------------------------------------------------------

def test_in_memory_vector_store_add_and_search():
    """Test basic vector addition and cosine similarity retrieval."""
    store = InMemoryVectorStore()
    embedder = MockEmbeddingGenerator(dimension=64)

    doc1 = DocumentChunk(
        chunk_id="c1",
        course_id="CS101",
        document_id="doc_a",
        text="QuickSort has average complexity of O(n log n).",
        embedding=embedder.generate_embedding("QuickSort has average complexity of O(n log n)."),
    )
    doc2 = DocumentChunk(
        chunk_id="c2",
        course_id="CS101",
        document_id="doc_b",
        text="Cellular respiration produces ATP molecules.",
        embedding=embedder.generate_embedding("Cellular respiration produces ATP molecules."),
    )

    store.add_documents([doc1, doc2])
    query_vec = embedder.generate_embedding("QuickSort complexity")

    results = store.search_similar(query_vec, course_id="CS101", top_k=2)
    assert len(results) >= 1
    assert results[0].chunk_id == "c1"
    assert results[0].similarity_score > 0.0


def test_course_level_isolation():
    """Test strict course-level isolation prevents cross-course leakage."""
    store = InMemoryVectorStore()
    embedder = MockEmbeddingGenerator(dimension=64)
    text = "Machine learning gradient descent optimization."
    vec = embedder.generate_embedding(text)

    # Add same text into two different courses
    store.add_documents([
        DocumentChunk(chunk_id="cs101_1", course_id="CS101", document_id="d1", text=text, embedding=vec),
        DocumentChunk(chunk_id="cs202_1", course_id="CS202", document_id="d2", text=text, embedding=vec),
    ])

    query_vec = embedder.generate_embedding("gradient descent")

    # Querying CS101 must NEVER return CS202 chunks
    cs101_results = store.search_similar(query_vec, course_id="CS101", top_k=10)
    assert len(cs101_results) == 1
    assert cs101_results[0].course_id == "CS101"
    assert cs101_results[0].chunk_id == "cs101_1"

    # Querying non-existent course returns empty
    empty_results = store.search_similar(query_vec, course_id="BIO101", top_k=10)
    assert empty_results == []


def test_similarity_threshold():
    """Test filtering by similarity threshold."""
    store = InMemoryVectorStore()
    embedder = MockEmbeddingGenerator(dimension=64)

    doc = DocumentChunk(
        chunk_id="c1",
        course_id="CS101",
        document_id="d1",
        text="Photosynthesis in plants.",
        embedding=embedder.generate_embedding("Photosynthesis in plants."),
    )
    store.add_documents([doc])

    query_vec = embedder.generate_embedding("Quantum computing qubits")
    # High threshold should filter out unrelated document
    results = store.search_similar(query_vec, course_id="CS101", top_k=5, similarity_threshold=0.99)
    assert len(results) == 0


def test_delete_documents():
    """Test deletion by course_id and document_id."""
    store = InMemoryVectorStore()
    embedder = MockEmbeddingGenerator(dimension=32)
    dummy_vec = embedder.generate_embedding("dummy")

    store.add_documents([
        DocumentChunk(chunk_id="c1", course_id="CS101", document_id="d1", text="1", embedding=dummy_vec),
        DocumentChunk(chunk_id="c2", course_id="CS101", document_id="d2", text="2", embedding=dummy_vec),
        DocumentChunk(chunk_id="c3", course_id="MATH101", document_id="d3", text="3", embedding=dummy_vec),
    ])

    # Delete doc d1
    deleted = store.delete_documents(course_id="CS101", document_id="d1")
    assert deleted == 1

    # Delete all MATH101
    deleted_math = store.delete_documents(course_id="MATH101")
    assert deleted_math == 1

    # Only c2 should remain
    assert "c2" in store._storage
    assert len(store._storage) == 1


# ---------------------------------------------------------------------------
# Retriever Service Tests
# ---------------------------------------------------------------------------

def test_course_material_retriever_pipeline():
    """Test end-to-end indexing and retrieval flow."""
    store = InMemoryVectorStore()
    embedder = MockEmbeddingGenerator(dimension=64)
    retriever = CourseMaterialRetriever(vector_store=store, embedding_generator=embedder)

    chunks = [
        DocumentChunk(
            chunk_id="c_hash",
            course_id="CS101",
            document_id="data_structures",
            title="Data Structures Textbook",
            page_number=45,
            section="Hash Tables",
            text="Hash tables offer average O(1) time complexity for lookup and insertion operations.",
        ),
        DocumentChunk(
            chunk_id="c_graph",
            course_id="CS101",
            document_id="data_structures",
            title="Data Structures Textbook",
            page_number=90,
            section="Graph Traversal",
            text="Dijkstra's algorithm finds the shortest path between nodes in a weighted graph.",
        ),
    ]

    indexed_count = retriever.index_documents(chunks)
    assert indexed_count == 2
    # Embeddings should have been generated automatically
    assert chunks[0].embedding is not None

    req = RetrievalRequest(
        query="What is the average time complexity of a hash table lookup?",
        course_id="CS101",
        top_k=2,
    )
    result = retriever.retrieve_by_request(req)

    assert result.total_found >= 1
    top_chunk = result.chunks[0]
    assert top_chunk.chunk_id == "c_hash"
    assert top_chunk.title == "Data Structures Textbook"
    assert top_chunk.page_number == 45
    assert top_chunk.section == "Hash Tables"

    # Conversion to SourceReference
    src_ref = top_chunk.to_source_reference()
    assert src_ref.document_id == "data_structures"
    assert src_ref.page_number == 45
    assert src_ref.similarity_score == top_chunk.similarity_score


def test_retriever_empty_query():
    """Test retriever with empty query or course ID."""
    retriever = CourseMaterialRetriever()
    res = retriever.retrieve(query="", course_id="CS101")
    assert res.total_found == 0
    assert res.chunks == []

    res2 = retriever.retrieve(query="valid query", course_id="")
    assert res2.total_found == 0


# ---------------------------------------------------------------------------
# Context Builder Tests
# ---------------------------------------------------------------------------

def test_context_builder_formatting_and_budget():
    """Test context builder formats sources with citations and respects character budgets."""
    builder = ContextBuilder(max_characters=250)

    chunks = [
        RetrievedChunk(
            chunk_id="c1",
            course_id="CS101",
            document_id="doc_a",
            title="Operating Systems Concept",
            page_number=14,
            section="Deadlocks",
            text="Four Coffman conditions are required for a deadlock: mutual exclusion, hold and wait, no preemption, and circular wait.",
            similarity_score=0.92,
        ),
        RetrievedChunk(
            chunk_id="c2",
            course_id="CS101",
            document_id="doc_a",
            title="Operating Systems Concept",
            page_number=18,
            section="Deadlock Prevention",
            text="Deadlock prevention eliminates at least one of the four Coffman conditions.",
            similarity_score=0.88,
        ),
    ]

    context_str = builder.build_context_block(chunks)
    assert "[Source 1: Operating Systems Concept, Page 14, Section: 'Deadlocks']" in context_str
    assert "Four Coffman conditions" in context_str

    # Test snippet extraction for prompts
    snippets = builder.extract_snippets_for_prompts(chunks)
    assert len(snippets) == 2
    assert "[Ref: Operating Systems Concept (p. 14)]" in snippets[0]

    # Test empty chunks
    empty_block = builder.build_context_block([])
    assert "No verified course materials retrieved" in empty_block


# ---------------------------------------------------------------------------
# Integration with Module 1 (Prompts & Grading Prompt)
# ---------------------------------------------------------------------------

def test_rag_and_module1_prompt_integration():
    """Verify retrieved chunks can be seamlessly piped into Module 1 grading prompts."""
    chunk = RetrievedChunk(
        chunk_id="chunk_mitosis",
        course_id="BIO101",
        document_id="bio_notes",
        title="Cell Biology",
        page_number=22,
        section="Cell Division",
        text="Mitosis results in two genetically identical diploid daughter cells.",
        similarity_score=0.95,
    )

    snippets = ContextBuilder.extract_snippets_for_prompts([chunk])
    grading_prompt = prompts.build_grading_prompt(
        question="Describe the outcome of mitosis.",
        student_answer="Mitosis produces 2 identical diploid cells.",
        max_marks=5.0,
        rubric_text="Award 5 marks for mentioning 2 identical diploid daughter cells.",
        retrieved_evidence=snippets,
    )

    assert "[Evidence 1]: Mitosis results in two genetically identical diploid daughter cells. [Ref: Cell Biology (p. 22)]" in grading_prompt
    assert "<untrusted_student_submission>" in grading_prompt
    assert "Mitosis produces 2 identical diploid cells." in grading_prompt


# ---------------------------------------------------------------------------
# Supabase Vector Store Adapter Contract Test
# ---------------------------------------------------------------------------

def test_supabase_adapter_without_client_raises():
    """Test Supabase adapter requires client and fails clearly if unconfigured."""
    adapter = SupabaseVectorStore(supabase_client=None)
    assert adapter.health_check() is False

    with pytest.raises(RuntimeError, match="Supabase client is not connected"):
        adapter.add_documents([])

    with pytest.raises(RuntimeError, match="Supabase client is not connected"):
        adapter.search_similar(query_vector=[0.1] * 10, course_id="CS101")


def test_supabase_adapter_mock_client():
    """Test Supabase adapter calls RPC procedure correctly with expected schema."""
    mock_client = MagicMock()
    mock_rpc_resp = MagicMock()
    mock_rpc_resp.data = [
        {
            "id": "chunk_sb_1",
            "course_id": "CS101",
            "document_id": "doc_sb",
            "title": "Cloud Architecture",
            "page_number": 5,
            "section": "Microservices",
            "content": "Microservices offer independent scalability.",
            "similarity": 0.89,
            "metadata": {},
        }
    ]
    mock_client.rpc.return_value.execute.return_value = mock_rpc_resp

    adapter = SupabaseVectorStore(supabase_client=mock_client)
    results = adapter.search_similar(
        query_vector=[0.1, 0.2, 0.3],
        course_id="CS101",
        top_k=3,
        similarity_threshold=0.7,
    )

    assert len(results) == 1
    assert results[0].chunk_id == "chunk_sb_1"
    assert results[0].text == "Microservices offer independent scalability."
    assert results[0].similarity_score == 0.89

    # Verify RPC arguments
    mock_client.rpc.assert_called_once_with(
        "match_document_chunks",
        {
            "query_embedding": [0.1, 0.2, 0.3],
            "filter_course_id": "CS101",
            "match_count": 3,
            "match_threshold": 0.7,
        },
    )

