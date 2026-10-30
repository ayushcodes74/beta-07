"""Teacher-corrected reference examples service and storage abstractions.

Stores approved teacher corrections as few-shot reference guidance for future
evaluations while enforcing strict course isolation, approval gates, and non-retraining rules.
"""

from __future__ import annotations

import datetime
import logging
import uuid
from abc import ABC, abstractmethod
from typing import Dict, List, Optional

from app.schemas.trust import ReferenceExample, ReferenceExampleApprovalStatus

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Abstract Reference Example Store
# ---------------------------------------------------------------------------

class ReferenceExampleStore(ABC):
    """Abstract interface defining the contract for storing teacher-approved corrections."""

    @abstractmethod
    def add_example(self, example: ReferenceExample) -> str:
        """Store a reference example. Returns the example_id."""
        ...

    @abstractmethod
    def get_example(self, example_id: str) -> Optional[ReferenceExample]:
        """Retrieve a specific example by ID."""
        ...

    @abstractmethod
    def get_approved_examples(
        self,
        course_id: str,
        question_id: Optional[str] = None,
    ) -> List[ReferenceExample]:
        """Retrieve only approved, active examples strictly scoped to course_id."""
        ...

    @abstractmethod
    def update_approval_status(
        self,
        example_id: str,
        status: ReferenceExampleApprovalStatus,
        reviewer: str,
    ) -> bool:
        """Update approval status (PENDING, APPROVED, REJECTED)."""
        ...

    @abstractmethod
    def deactivate_example(self, example_id: str) -> bool:
        """Mark an example as inactive without deleting."""
        ...


# ---------------------------------------------------------------------------
# In-Memory Implementation
# ---------------------------------------------------------------------------

class InMemoryReferenceExampleStore(ReferenceExampleStore):
    """In-memory store for development, local testing, and mock mode."""

    def __init__(self):
        self._storage: Dict[str, ReferenceExample] = {}

    def add_example(self, example: ReferenceExample) -> str:
        self._storage[example.example_id] = example
        return example.example_id

    def get_example(self, example_id: str) -> Optional[ReferenceExample]:
        return self._storage.get(example_id)

    def get_approved_examples(
        self,
        course_id: str,
        question_id: Optional[str] = None,
    ) -> List[ReferenceExample]:
        results: List[ReferenceExample] = []
        for ex in self._storage.values():
            # Rule: Must match course_id strictly
            if ex.course_id != course_id:
                continue
            # Rule: Must be active
            if not ex.is_active:
                continue
            # Rule: MUST be approved by a teacher
            if ex.approval_status != ReferenceExampleApprovalStatus.APPROVED:
                continue
            # Optional question filter
            if question_id is not None and ex.question_id != question_id:
                continue
            results.append(ex)
        return results

    def update_approval_status(
        self,
        example_id: str,
        status: ReferenceExampleApprovalStatus,
        reviewer: str,
    ) -> bool:
        ex = self._storage.get(example_id)
        if not ex:
            return False
        ex.approval_status = status
        ex.approved_by = reviewer
        return True

    def deactivate_example(self, example_id: str) -> bool:
        ex = self._storage.get(example_id)
        if not ex:
            return False
        ex.is_active = False
        return True

    def clear(self) -> None:
        self._storage.clear()


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------

class ReferenceExampleService:
    """Manages teacher grading corrections as few-shot reference examples."""

    def __init__(self, store: Optional[ReferenceExampleStore] = None):
        self.store = store or InMemoryReferenceExampleStore()

    def record_correction(
        self,
        course_id: str,
        assignment_id: str,
        question_id: str,
        question_text: str,
        student_answer: str,
        teacher_corrected_marks: float,
        max_marks: float,
        teacher_feedback: str,
        teacher_notes: Optional[str] = None,
        auto_approve: bool = False,
        reviewer_id: Optional[str] = None,
    ) -> ReferenceExample:
        """Create a new reference example from a teacher correction."""
        status = ReferenceExampleApprovalStatus.APPROVED if auto_approve else ReferenceExampleApprovalStatus.PENDING
        ex = ReferenceExample(
            example_id=f"ref_{uuid.uuid4().hex[:8]}",
            course_id=course_id,
            assignment_id=assignment_id,
            question_id=question_id,
            question_text=question_text,
            student_answer=student_answer,
            teacher_corrected_marks=teacher_corrected_marks,
            max_marks=max_marks,
            teacher_feedback=teacher_feedback,
            teacher_notes=teacher_notes,
            approval_status=status,
            is_active=True,
            created_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
            approved_by=reviewer_id if auto_approve else None,
        )
        self.store.add_example(ex)
        return ex

    def approve_example(self, example_id: str, reviewer_id: str) -> bool:
        """Explicitly approve an example for use in grading prompts."""
        return self.store.update_approval_status(
            example_id=example_id,
            status=ReferenceExampleApprovalStatus.APPROVED,
            reviewer=reviewer_id,
        )

    def reject_example(self, example_id: str, reviewer_id: str) -> bool:
        """Reject an example so it is never used in grading prompts."""
        return self.store.update_approval_status(
            example_id=example_id,
            status=ReferenceExampleApprovalStatus.REJECTED,
            reviewer=reviewer_id,
        )

    def get_reference_snippets(
        self,
        course_id: str,
        question_id: Optional[str] = None,
        max_examples: int = 3,
    ) -> List[str]:
        """Retrieve approved reference examples formatted for Module 1 prompts."""
        approved = self.store.get_approved_examples(course_id=course_id, question_id=question_id)
        snippets: List[str] = []

        for ex in approved[:max_examples]:
            note_str = f" Teacher Note: {ex.teacher_notes}" if ex.teacher_notes else ""
            snippet = (
                f"Student Answer Excerpt: '{ex.student_answer[:200]}' -> "
                f"Awarded: {ex.teacher_corrected_marks}/{ex.max_marks}. "
                f"Teacher Feedback: '{ex.teacher_feedback}'.{note_str}"
            )
            snippets.append(snippet)

        return snippets

