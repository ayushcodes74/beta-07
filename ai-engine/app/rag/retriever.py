"""Retriever service for semantic knowledge search.

Coordinates query embedding generation, course-isolated vector store querying,
similarity thresholding, and source citation preservation.
"""

from __future__ import annotations

import logging
from typing import List, Optional

from app.rag.embeddings import BaseEmbeddingGenerator, get_embedding_generator
from app.rag.vector_store import InMemoryVectorStore, VectorStore
from app.schemas.rag import DocumentChunk, RetrievalRequest, RetrievalResult, RetrievedChunk

logger = logging.getLogger(__name__)


class CourseMaterialRetriever:
    """Service for indexing and retrieving course materials with strict course isolation."""

    def __init__(
        self,
        vector_store: Optional[VectorStore] = None,
        embedding_generator: Optional[BaseEmbeddingGenerator] = None,
    ):
        """Initialize the retriever.

        Args:
            vector_store: Vector store instance (defaults to InMemoryVectorStore).
            embedding_generator: Embeddings generator (defaults to global embedder).
        """
        self.vector_store = vector_store or InMemoryVectorStore()
        self.embedder = embedding_generator or get_embedding_generator()

    def index_documents(self, documents: List[DocumentChunk]) -> int:
        """Embed un-embedded document chunks and add them to the vector store.

        Args:
            documents: List of DocumentChunk instances to index.

        Returns:
            Number of documents indexed.
        """
        if not documents:
            return 0

        # Identify documents needing embeddings
        to_embed = [doc for doc in documents if doc.embedding is None]
        if to_embed:
            texts = [doc.text for doc in to_embed]
            embeddings = self.embedder.generate_embeddings(texts)
            for doc, emb in zip(to_embed, embeddings):
                doc.embedding = emb

        return self.vector_store.add_documents(documents)

    def retrieve(
        self,
        query: str,
        course_id: str,
        top_k: int = 5,
        similarity_threshold: float = 0.0,
    ) -> RetrievalResult:
        """Retrieve relevant course excerpts matching the query.

        Args:
            query: Question, student answer, or topic query.
            course_id: Course ID to strictly isolate results.
            top_k: Max chunks to retrieve.
            similarity_threshold: Min similarity score required.

        Returns:
            RetrievalResult containing matched chunks and metadata.
        """
        clean_query = query.strip() if query else ""
        clean_course = course_id.strip() if course_id else ""

        if not clean_query or not clean_course:
            return RetrievalResult(
                query=clean_query,
                course_id=clean_course,
                chunks=[],
                total_found=0,
            )

        # Generate query embedding
        query_vector = self.embedder.generate_embedding(clean_query)

        # Search vector store strictly scoped to course_id
        matched_chunks = self.vector_store.search_similar(
            query_vector=query_vector,
            course_id=clean_course,
            top_k=top_k,
            similarity_threshold=similarity_threshold,
        )

        return RetrievalResult(
            query=clean_query,
            course_id=clean_course,
            chunks=matched_chunks,
            total_found=len(matched_chunks),
        )

    def retrieve_by_request(self, request: RetrievalRequest) -> RetrievalResult:
        """Retrieve using a typed RetrievalRequest schema."""
        return self.retrieve(
            query=request.query,
            course_id=request.course_id,
            top_k=request.top_k,
            similarity_threshold=request.similarity_threshold,
        )

