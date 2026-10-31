"""Persistent, course-isolated course-material index for RAG grading (local MVP, no pgvector).

- ``PersistentVectorStore`` reuses ``InMemoryVectorStore`` (course-scoped cosine search) and mirrors
  each course to ``<root>/<course>.json`` (chunks + embeddings + material registry), written
  atomically, so the index survives AI Engine restarts. Courses are loaded lazily from disk.
- ``CourseMaterialIndex`` ingests extracted pages: chunks them with the existing ``TextChunker``,
  embeds with the real SentenceTransformer model (never mock embeddings), skips duplicate uploads
  (same content) and duplicate chunks, and retrieves evidence for a course.
"""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import logging
import os
from pathlib import Path
import re
import threading
from typing import Any, Dict, List, Optional

from app.rag.chunker import TextChunker
from app.rag.embeddings import BaseEmbeddingGenerator, EmbeddingsUnavailableError, get_production_embedder
from app.rag.vector_store import InMemoryVectorStore
from app.schemas.rag import DocumentChunk, RetrievedChunk

logger = logging.getLogger(__name__)

_DEFAULT_ROOT = Path(__file__).resolve().parents[2] / "storage" / "rag_index"
_SAFE = re.compile(r"[^A-Za-z0-9_.-]")


def _normalise(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip().lower()


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class PersistentVectorStore(InMemoryVectorStore):
    """In-memory course-isolated vector store persisted per course as JSON files."""

    FORMAT_VERSION = 1

    def __init__(self, root: Path) -> None:
        super().__init__()
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self._materials: Dict[str, Dict[str, Dict[str, Any]]] = {}  # course -> material_id -> info
        self._loaded: set[str] = set()
        self._lock = threading.RLock()

    # ---- persistence ----------------------------------------------------------------------

    def _path(self, course_id: str) -> Path:
        safe = _SAFE.sub("_", course_id)[:120] or "_"
        return self.root / f"{safe}-{_sha256(course_id)[:10]}.json"

    def _ensure_loaded(self, course_id: str) -> None:
        if course_id in self._loaded:
            return
        path = self._path(course_id)
        if path.exists():
            data = json.loads(path.read_text(encoding="utf-8"))
            for raw in data.get("chunks", []):
                chunk = DocumentChunk.model_validate(raw)
                self._storage[chunk.chunk_id] = chunk
            self._materials[course_id] = data.get("materials", {})
        else:
            self._materials.setdefault(course_id, {})
        self._loaded.add(course_id)

    def _save(self, course_id: str) -> None:
        chunks = [c.model_dump(mode="json") for c in self._storage.values() if c.course_id == course_id]
        payload = {
            "format_version": self.FORMAT_VERSION,
            "course_id": course_id,
            "materials": self._materials.get(course_id, {}),
            "chunks": chunks,
        }
        path = self._path(course_id)
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(payload), encoding="utf-8")
        os.replace(tmp, path)

    # ---- VectorStore API (course-scoped, persisted) ---------------------------------------

    def add_documents(self, documents: List[DocumentChunk]) -> int:
        with self._lock:
            for course_id in {d.course_id for d in documents}:
                self._ensure_loaded(course_id)
            added = super().add_documents(documents)
            for course_id in {d.course_id for d in documents}:
                self._save(course_id)
            return added

    def search_similar(
        self, query_vector: List[float], course_id: str, top_k: int = 5, similarity_threshold: float = 0.0
    ) -> List[RetrievedChunk]:
        with self._lock:
            self._ensure_loaded(course_id)
            return super().search_similar(query_vector, course_id, top_k, similarity_threshold)

    def delete_documents(self, course_id: Optional[str] = None, document_id: Optional[str] = None) -> int:
        if course_id is None:
            raise ValueError("PersistentVectorStore deletes are course-scoped; course_id is required.")
        with self._lock:
            self._ensure_loaded(course_id)
            removed = super().delete_documents(course_id=course_id, document_id=document_id)
            if document_id is None:
                self._materials[course_id] = {}
            else:
                self._materials.get(course_id, {}).pop(document_id, None)
            self._save(course_id)
            return removed

    def health_check(self) -> bool:
        return self.root.is_dir()

    # ---- material registry ----------------------------------------------------------------

    def materials(self, course_id: str) -> Dict[str, Dict[str, Any]]:
        with self._lock:
            self._ensure_loaded(course_id)
            return dict(self._materials.get(course_id, {}))

    def register_material(self, course_id: str, material_id: str, info: Dict[str, Any]) -> None:
        with self._lock:
            self._ensure_loaded(course_id)
            self._materials.setdefault(course_id, {})[material_id] = info
            self._save(course_id)

    def chunk_hashes(self, course_id: str) -> set[str]:
        with self._lock:
            self._ensure_loaded(course_id)
            return {
                c.metadata.get("content_hash", "")
                for c in self._storage.values()
                if c.course_id == course_id
            }

    def chunk_count(self, course_id: str) -> int:
        with self._lock:
            self._ensure_loaded(course_id)
            return sum(1 for c in self._storage.values() if c.course_id == course_id)


class CourseMaterialIndex:
    """Ingest, de-duplicate and retrieve course materials, strictly per course."""

    def __init__(
        self,
        root: Optional[Path] = None,
        embedder: Optional[BaseEmbeddingGenerator] = None,
        chunker: Optional[TextChunker] = None,
    ) -> None:
        self.store = PersistentVectorStore(Path(root or os.getenv("RAG_INDEX_DIR") or _DEFAULT_ROOT))
        self._embedder = embedder
        self.chunker = chunker or TextChunker(chunk_size=700, chunk_overlap=120, min_chunk_size=30)
        self._ingest_lock = threading.Lock()

    @property
    def embedder(self) -> BaseEmbeddingGenerator:
        """The real embedder (raises EmbeddingsUnavailableError; there is no mock fallback)."""
        if self._embedder is None:
            self._embedder = get_production_embedder()
        return self._embedder

    @property
    def embedding_model(self) -> Optional[str]:
        return getattr(self._embedder, "model_name", None) if self._embedder else os.getenv(
            "RAG_EMBEDDING_MODEL", "all-MiniLM-L6-v2"
        )

    def index_material(
        self,
        course_id: str,
        filename: str,
        pages: List[Dict[str, Any]],
        material_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Chunk, embed and store extracted pages ``[{"page_number": int, "text": str}]``.

        Re-uploading identical content is a no-op (``duplicate=True``); chunks whose text already
        exists in the course are skipped.
        """
        course_id = course_id.strip()
        if not course_id:
            raise ValueError("course_id is required")
        pages = [p for p in pages if str(p.get("text", "")).strip()]
        if not pages:
            raise ValueError("No text to index")

        content_hash = _sha256("\n".join(_normalise(p["text"]) for p in pages))
        material_id = (material_id or f"mat_{content_hash[:16]}").strip()

        with self._ingest_lock:
            existing = self.store.materials(course_id)
            for mid, info in existing.items():
                if info.get("content_hash") == content_hash:
                    return {
                        "course_id": course_id, "material_id": mid, "filename": info.get("filename"),
                        "duplicate": True, "chunks_indexed": 0, "chunks_skipped": info.get("chunks", 0),
                        "course_chunk_count": self.store.chunk_count(course_id),
                    }

            chunks = self.chunker.chunk_document_pages(
                pages=[{"text": p["text"], "page_number": int(p.get("page_number") or i + 1)}
                       for i, p in enumerate(pages)],
                course_id=course_id,
                document_id=material_id,
                title=filename,
            )
            seen = self.store.chunk_hashes(course_id)
            fresh: List[DocumentChunk] = []
            for chunk in chunks:
                chunk_hash = _sha256(_normalise(chunk.text))
                if chunk_hash in seen:
                    continue
                seen.add(chunk_hash)
                chunk.chunk_id = f"{course_id}:{material_id}:{chunk_hash[:16]}"
                chunk.metadata = {
                    **chunk.metadata,
                    "material_id": material_id,
                    "filename": filename,
                    "content_hash": chunk_hash,
                }
                fresh.append(chunk)

            if fresh:
                vectors = self.embedder.generate_embeddings([c.text for c in fresh])
                for chunk, vector in zip(fresh, vectors):
                    chunk.embedding = vector
                self.store.add_documents(fresh)

            self.store.register_material(course_id, material_id, {
                "material_id": material_id,
                "filename": filename,
                "content_hash": content_hash,
                "pages": len(pages),
                "chunks": len(fresh),
                "embedding_model": self.embedding_model,
                "indexed_at": datetime.now(timezone.utc).isoformat(),
            })
            return {
                "course_id": course_id, "material_id": material_id, "filename": filename,
                "duplicate": False, "chunks_indexed": len(fresh), "chunks_skipped": len(chunks) - len(fresh),
                "course_chunk_count": self.store.chunk_count(course_id),
            }

    def list_materials(self, course_id: str) -> List[Dict[str, Any]]:
        return sorted(self.store.materials(course_id).values(), key=lambda m: m.get("indexed_at", ""))

    def delete_material(self, course_id: str, material_id: str) -> int:
        return self.store.delete_documents(course_id=course_id, document_id=material_id)

    def retrieve(
        self, course_id: str, query: str, top_k: int = 4, similarity_threshold: float = 0.3
    ) -> List[RetrievedChunk]:
        """Top course passages for ``query``. Raises EmbeddingsUnavailableError without real embeddings."""
        if not course_id or not query.strip() or self.store.chunk_count(course_id) == 0:
            return []
        vector = self.embedder.generate_embedding(query)
        return self.store.search_similar(vector, course_id, top_k=top_k, similarity_threshold=similarity_threshold)


_INDEX: Optional[CourseMaterialIndex] = None
_INDEX_LOCK = threading.Lock()


def get_course_index() -> CourseMaterialIndex:
    global _INDEX
    with _INDEX_LOCK:
        if _INDEX is None:
            _INDEX = CourseMaterialIndex()
        return _INDEX


__all__ = ["CourseMaterialIndex", "PersistentVectorStore", "get_course_index", "EmbeddingsUnavailableError"]
