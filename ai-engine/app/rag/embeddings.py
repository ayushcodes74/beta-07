"""Embedding generation using Sentence Transformers.

Supports lazy model loading, batch encoding, L2 normalization, dimension validation,
and caching to prevent redundant model instantiation.
"""

from __future__ import annotations

import hashlib
import logging
import math
from abc import ABC, abstractmethod
from typing import Any, List, Optional

logger = logging.getLogger(__name__)


class BaseEmbeddingGenerator(ABC):
    """Abstract interface for embedding generation."""

    @abstractmethod
    def generate_embedding(self, text: str) -> List[float]:
        """Generate a dense vector embedding for a single string."""
        ...

    @abstractmethod
    def generate_embeddings(self, texts: List[str]) -> List[List[float]]:
        """Generate dense vector embeddings for a batch of strings."""
        ...

    @property
    @abstractmethod
    def dimension(self) -> int:
        """Return the vector dimensionality."""
        ...


class SentenceTransformerEmbeddingGenerator(BaseEmbeddingGenerator):
    """Embedding generator powered by SentenceTransformers (e.g. all-MiniLM-L6-v2)."""

    def __init__(
        self,
        model_name: str = "all-MiniLM-L6-v2",
        normalize: bool = True,
        device: str = "cpu",
    ):
        """Initialize settings for the embedding generator.

        Args:
            model_name: HuggingFace model identifier.
            normalize: Whether to normalize output vectors to unit length.
            device: Target device ('cpu' or 'cuda').
        """
        self.model_name = model_name
        self.normalize = normalize
        self.device = device
        self._model: Optional[Any] = None
        self._dimension: Optional[int] = None

    @property
    def model(self) -> Any:
        """Lazily load and cache the SentenceTransformer model."""
        if self._model is None:
            logger.info("Loading SentenceTransformer model '%s' on %s...", self.model_name, self.device)
            try:
                from sentence_transformers import SentenceTransformer
                self._model = SentenceTransformer(self.model_name, device=self.device)
                self._dimension = self._model.get_sentence_embedding_dimension()
            except ImportError as err:
                raise RuntimeError(
                    "sentence-transformers is not installed. "
                    "Install it or use MockEmbeddingGenerator for testing."
                ) from err
        return self._model

    @property
    def dimension(self) -> int:
        """Return the embedding dimension."""
        if self._dimension is None:
            # Trigger lazy load
            _ = self.model
        return self._dimension or 384

    def generate_embedding(self, text: str) -> List[float]:
        """Generate normalized embedding for a single text."""
        if not text or not text.strip():
            # Return zero vector for empty text
            return [0.0] * self.dimension

        embeddings = self.generate_embeddings([text])
        return embeddings[0]

    def generate_embeddings(self, texts: List[str]) -> List[List[float]]:
        """Generate embeddings for a batch of texts."""
        if not texts:
            return []

        # Replace empty strings with single space to avoid tokenizer failure
        cleaned = [t if (t and t.strip()) else " " for t in texts]

        raw_vectors = self.model.encode(
            cleaned,
            normalize_embeddings=self.normalize,
            convert_to_numpy=True,
            show_progress_bar=False,
        )

        result: List[List[float]] = []
        for vec in raw_vectors:
            float_list = [float(x) for x in vec]
            if len(float_list) != self.dimension:
                raise ValueError(
                    f"Embedding dimension mismatch: expected {self.dimension}, got {len(float_list)}"
                )
            result.append(float_list)

        return result


class MockEmbeddingGenerator(BaseEmbeddingGenerator):
    """Deterministic, lightweight embedding generator for unit tests and local mock mode.

    Produces consistent unit-length vectors using SHA-256 hash hashing, eliminating
    the need to download multi-gigabyte models in test environments.
    """

    def __init__(self, dimension: int = 384):
        self._dim = dimension

    @property
    def dimension(self) -> int:
        return self._dim

    def generate_embedding(self, text: str) -> List[float]:
        if not text or not text.strip():
            return [0.0] * self._dim

        # Deterministic pseudo-embedding based on hash of tokens
        vec = [0.0] * self._dim
        words = text.lower().split()
        if not words:
            return [0.0] * self._dim

        for word in words:
            h = int(hashlib.md5(word.encode("utf-8")).hexdigest(), 16)
            idx = h % self._dim
            vec[idx] += 1.0

        # L2 normalize
        norm = math.sqrt(sum(x * x for x in vec))
        if norm > 0:
            vec = [x / norm for x in vec]
        return vec

    def generate_embeddings(self, texts: List[str]) -> List[List[float]]:
        return [self.generate_embedding(t) for t in texts]


# Global cache
_DEFAULT_EMBEDDER: Optional[BaseEmbeddingGenerator] = None


def get_embedding_generator(
    use_mock: bool = False,
    model_name: str = "all-MiniLM-L6-v2",
) -> BaseEmbeddingGenerator:
    """Retrieve or create the singleton embedding generator."""
    global _DEFAULT_EMBEDDER
    if _DEFAULT_EMBEDDER is None:
        if use_mock:
            _DEFAULT_EMBEDDER = MockEmbeddingGenerator()
        else:
            try:
                import sentence_transformers  # noqa: F401
                _DEFAULT_EMBEDDER = SentenceTransformerEmbeddingGenerator(model_name=model_name)
            except ImportError:
                logger.warning("sentence-transformers not available; falling back to MockEmbeddingGenerator.")
                _DEFAULT_EMBEDDER = MockEmbeddingGenerator()
    return _DEFAULT_EMBEDDER

