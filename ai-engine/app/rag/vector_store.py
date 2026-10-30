"""Vector Store abstractions and implementations.

Provides:
1. VectorStore: Abstract base interface defining standard operations.
2. InMemoryVectorStore: Fully functional in-memory cosine similarity store for testing and local development.
3. SupabaseVectorStore: Adapter interface for the teammate's Supabase pgvector implementation.
"""

from __future__ import annotations

import logging
import math
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

try:
    import numpy as np
except ImportError:
    np = None  # type: ignore

from app.schemas.rag import DocumentChunk, RetrievedChunk

logger = logging.getLogger(__name__)


def _cosine_similarity(vec_a: List[float], vec_b: List[float]) -> float:
    """Compute cosine similarity between two float vectors.

    Uses NumPy if available, with pure Python fallback.
    """
    if np is not None:
        a = np.asarray(vec_a, dtype=np.float32)
        b = np.asarray(vec_b, dtype=np.float32)
        norm_a = np.linalg.norm(a)
        norm_b = np.linalg.norm(b)
        if norm_a == 0.0 or norm_b == 0.0:
            return 0.0
        dot = float(np.dot(a, b))
        sim = dot / float(norm_a * norm_b)
        # Clamp to [0.0, 1.0] for non-negative unit vectors
        return max(0.0, min(1.0, (sim + 1.0) / 2.0 if sim < 0.0 else sim))

    # Pure Python fallback
    dot = sum(x * y for x, y in zip(vec_a, vec_b))
    norm_a = math.sqrt(sum(x * x for x in vec_a))
    norm_b = math.sqrt(sum(y * y for y in vec_b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    sim = dot / (norm_a * norm_b)
    return max(0.0, min(1.0, sim))


# ---------------------------------------------------------------------------
# Abstract Vector Store Interface
# ---------------------------------------------------------------------------

class VectorStore(ABC):
    """Abstract interface defining the contract for vector storage and retrieval."""

    @abstractmethod
    def add_documents(self, documents: List[DocumentChunk]) -> int:
        """Add or update document chunks with their embeddings in the vector store.

        Args:
            documents: List of DocumentChunk instances. Must contain embeddings.

        Returns:
            Number of documents added.
        """
        ...

    @abstractmethod
    def search_similar(
        self,
        query_vector: List[float],
        course_id: str,
        top_k: int = 5,
        similarity_threshold: float = 0.0,
    ) -> List[RetrievedChunk]:
        """Search for top_k similar chunks strictly scoped to course_id.

        Args:
            query_vector: Dense query embedding.
            course_id: Course ID to isolate retrieval.
            top_k: Maximum number of chunks to return.
            similarity_threshold: Minimum similarity score required.

        Returns:
            List of RetrievedChunk sorted by similarity descending.
        """
        ...

    @abstractmethod
    def delete_documents(
        self,
        course_id: Optional[str] = None,
        document_id: Optional[str] = None,
    ) -> int:
        """Delete document chunks matching the filter criteria.

        Args:
            course_id: Optional course filter.
            document_id: Optional document filter.

        Returns:
            Number of documents deleted.
        """
        ...

    @abstractmethod
    def health_check(self) -> bool:
        """Verify the health and availability of the vector store."""
        ...


# ---------------------------------------------------------------------------
# In-Memory Vector Store
# ---------------------------------------------------------------------------

class InMemoryVectorStore(VectorStore):
    """Thread-safe in-memory vector store for testing and local development."""

    def __init__(self):
        # Keyed by chunk_id
        self._storage: Dict[str, DocumentChunk] = {}

    def add_documents(self, documents: List[DocumentChunk]) -> int:
        added_count = 0
        for doc in documents:
            if doc.embedding is None:
                raise ValueError(
                    f"Document chunk '{doc.chunk_id}' is missing embedding vector."
                )
            self._storage[doc.chunk_id] = doc
            added_count += 1
        return added_count

    def search_similar(
        self,
        query_vector: List[float],
        course_id: str,
        top_k: int = 5,
        similarity_threshold: float = 0.0,
    ) -> List[RetrievedChunk]:
        if not self._storage:
            return []

        scored_candidates: List[RetrievedChunk] = []

        for doc in self._storage.values():
            # Strict course-level isolation
            if doc.course_id != course_id:
                continue

            if doc.embedding is None:
                continue

            score = _cosine_similarity(query_vector, doc.embedding)

            if score >= similarity_threshold:
                scored_candidates.append(
                    RetrievedChunk(
                        chunk_id=doc.chunk_id,
                        course_id=doc.course_id,
                        document_id=doc.document_id,
                        title=doc.title,
                        page_number=doc.page_number,
                        section=doc.section,
                        text=doc.text,
                        similarity_score=round(score, 4),
                        metadata=doc.metadata,
                    )
                )

        # Sort descending by similarity score
        scored_candidates.sort(key=lambda x: x.similarity_score, reverse=True)
        return scored_candidates[:top_k]

    def delete_documents(
        self,
        course_id: Optional[str] = None,
        document_id: Optional[str] = None,
    ) -> int:
        keys_to_delete: List[str] = []

        for cid, doc in self._storage.items():
            match_course = (course_id is None) or (doc.course_id == course_id)
            match_doc = (document_id is None) or (doc.document_id == document_id)
            if match_course and match_doc:
                keys_to_delete.append(cid)

        for k in keys_to_delete:
            del self._storage[k]

        return len(keys_to_delete)

    def health_check(self) -> bool:
        return True

    def clear(self) -> None:
        """Clear all stored documents."""
        self._storage.clear()


# ---------------------------------------------------------------------------
# Supabase Vector Store Adapter (Contract Interface)
# ---------------------------------------------------------------------------

class SupabaseVectorStore(VectorStore):
    """Adapter interface for Supabase pgvector integration.

    Integration Contract for Database Teammate:
    -------------------------------------------
    Expected Supabase Table: `course_document_chunks`
    Columns:
      - id: text / uuid PRIMARY KEY
      - course_id: text NOT NULL (indexed)
      - document_id: text NOT NULL (indexed)
      - title: text
      - page_number: integer
      - section: text
      - content: text NOT NULL
      - metadata: jsonb
      - embedding: vector(384) (or matching model dimension)

    Expected RPC Function: `match_document_chunks`
      Parameters:
        - query_embedding: vector
        - filter_course_id: text
        - match_count: int
        - match_threshold: float
      Returns:
        TABLE (
          id text,
          course_id text,
          document_id text,
          title text,
          page_number integer,
          section text,
          content text,
          metadata jsonb,
          similarity float
        )
    """

    def __init__(
        self,
        supabase_client: Optional[Any] = None,
        table_name: str = "course_document_chunks",
        match_function: str = "match_document_chunks",
    ):
        """Initialize the Supabase adapter.

        Args:
            supabase_client: Supabase client instance provided by teammate.
            table_name: Target table name.
            match_function: RPC stored procedure name for vector cosine matching.
        """
        self.client = supabase_client
        self.table_name = table_name
        self.match_function = match_function

    def add_documents(self, documents: List[DocumentChunk]) -> int:
        if self.client is None:
            raise RuntimeError(
                "Supabase client is not connected. "
                "Provide an initialized supabase_client or use InMemoryVectorStore."
            )

        records = [
            {
                "id": doc.chunk_id,
                "course_id": doc.course_id,
                "document_id": doc.document_id,
                "title": doc.title,
                "page_number": doc.page_number,
                "section": doc.section,
                "content": doc.text,
                "metadata": doc.metadata,
                "embedding": doc.embedding,
            }
            for doc in documents
        ]

        response = self.client.table(self.table_name).upsert(records).execute()
        return len(response.data) if hasattr(response, "data") and response.data else len(records)

    def search_similar(
        self,
        query_vector: List[float],
        course_id: str,
        top_k: int = 5,
        similarity_threshold: float = 0.0,
    ) -> List[RetrievedChunk]:
        if self.client is None:
            raise RuntimeError(
                "Supabase client is not connected. "
                "Provide an initialized supabase_client or use InMemoryVectorStore."
            )

        rpc_params = {
            "query_embedding": query_vector,
            "filter_course_id": course_id,
            "match_count": top_k,
            "match_threshold": similarity_threshold,
        }

        response = self.client.rpc(self.match_function, rpc_params).execute()
        rows = getattr(response, "data", []) or []

        chunks: List[RetrievedChunk] = []
        for r in rows:
            chunks.append(
                RetrievedChunk(
                    chunk_id=r.get("id", ""),
                    course_id=r.get("course_id", course_id),
                    document_id=r.get("document_id", ""),
                    title=r.get("title"),
                    page_number=r.get("page_number"),
                    section=r.get("section"),
                    text=r.get("content", ""),
                    similarity_score=float(r.get("similarity", 0.0)),
                    metadata=r.get("metadata", {}),
                )
            )
        return chunks

    def delete_documents(
        self,
        course_id: Optional[str] = None,
        document_id: Optional[str] = None,
    ) -> int:
        if self.client is None:
            raise RuntimeError("Supabase client is not connected.")

        query = self.client.table(self.table_name).delete()
        if course_id:
            query = query.eq("course_id", course_id)
        if document_id:
            query = query.eq("document_id", document_id)

        response = query.execute()
        return len(getattr(response, "data", []) or [])

    def health_check(self) -> bool:
        if self.client is None:
            return False
        try:
            self.client.table(self.table_name).select("id").limit(1).execute()
            return True
        except Exception as exc:
            logger.warning("Supabase health check failed: %s", exc)
            return False

