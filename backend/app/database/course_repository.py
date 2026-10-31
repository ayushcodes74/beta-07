"""Supabase implementation of CourseRepository and related database models (Module 2A).

Maps strictly to existing Supabase tables:
- courses:
    id (UUID PK),
    teacher_id (UUID FK),
    name (TEXT),
    description (TEXT),
    created_at (TIMESTAMP)
- course_enrollments:
    id (UUID PK),
    course_id (UUID FK),
    student_id (UUID FK),
    status (TEXT: 'active' / 'inactive'),
    enrolled_at (TIMESTAMP)
- profiles:
    id (UUID PK),
    role (TEXT),
    is_disabled (BOOLEAN),
    display_name (TEXT)

Enforces:
- Isolation under caller's RLS access token (never service role).
- Teacher-only creation and modification.
- Active enrollment state tracking.
"""

from __future__ import annotations

from datetime import UTC, datetime
import logging
from typing import Any
from uuid import UUID, uuid4

from app.database.supabase import get_user_supabase
from app.services.course_service import (
    CourseIntegrationNotConfiguredError,
    CourseRecord,
    CourseRepository,
    CourseRepositoryError,
    DuplicateEnrollmentError,
    EnrolledStudent,
    EnrollmentRecord,
)

logger = logging.getLogger(__name__)


def _parse_datetime(val: Any) -> datetime:
    if isinstance(val, datetime):
        return val if val.tzinfo is not None else val.replace(tzinfo=UTC)
    if isinstance(val, str):
        # Handle trailing Z or offset
        iso_str = val.replace("Z", "+00:00")
        dt = datetime.fromisoformat(iso_str)
        return dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)
    return datetime.now(UTC)


class SupabaseCourseRepository:
    """Supabase-backed implementation of CourseRepository."""

    @staticmethod
    def _client(access_token: str):
        try:
            return get_user_supabase(access_token)
        except Exception as exc:
            raise CourseIntegrationNotConfiguredError(str(exc)) from exc

    def create(
        self, teacher_id: UUID, name: str, description: str | None, *, access_token: str
    ) -> CourseRecord:
        client = self._client(access_token)
        course_id = uuid4()
        now = datetime.now(UTC)
        payload = {
            "id": str(course_id),
            "teacher_id": str(teacher_id),
            "name": name,
            "description": description,
            "created_at": now.isoformat(),
        }
        try:
            resp = client.table("courses").insert(payload).execute()
            rows = resp.data or []
            if not rows:
                raise CourseRepositoryError("Failed to insert course record")
            row = rows[0]
            return CourseRecord(
                id=UUID(str(row["id"])),
                teacher_id=UUID(str(row["teacher_id"])),
                name=row["name"],
                description=row.get("description"),
                created_at=_parse_datetime(row["created_at"]),
                students_count=0,
            )
        except CourseRepositoryError:
            raise
        except Exception as exc:
            logger.exception("Failed to create course in Supabase: %s", exc)
            raise CourseRepositoryError(f"Database error creating course: {exc}") from exc

    def get(self, course_id: UUID, *, access_token: str) -> CourseRecord | None:
        client = self._client(access_token)
        try:
            resp = (
                client.table("courses")
                .select("id, teacher_id, name, description, created_at")
                .eq("id", str(course_id))
                .execute()
            )
            rows = resp.data or []
            if not rows:
                return None
            row = rows[0]

            # Count active enrolled students
            enroll_resp = (
                client.table("course_enrollments")
                .select("id")
                .eq("course_id", str(course_id))
                .eq("status", "active")
                .execute()
            )
            students_count = len(enroll_resp.data or [])

            return CourseRecord(
                id=UUID(str(row["id"])),
                teacher_id=UUID(str(row["teacher_id"])),
                name=row["name"],
                description=row.get("description"),
                created_at=_parse_datetime(row["created_at"]),
                students_count=students_count,
            )
        except CourseRepositoryError:
            raise
        except Exception as exc:
            logger.exception("Failed to fetch course %s: %s", course_id, exc)
            raise CourseRepositoryError(f"Database error fetching course: {exc}") from exc

    def list_by_teacher(self, teacher_id: UUID, *, access_token: str) -> list[CourseRecord]:
        client = self._client(access_token)
        try:
            resp = (
                client.table("courses")
                .select("id, teacher_id, name, description, created_at")
                .eq("teacher_id", str(teacher_id))
                .order("created_at", desc=True)
                .execute()
            )
            rows = resp.data or []
            records: list[CourseRecord] = []
            for row in rows:
                c_id = str(row["id"])
                enroll_resp = (
                    client.table("course_enrollments")
                    .select("id")
                    .eq("course_id", c_id)
                    .eq("status", "active")
                    .execute()
                )
                students_count = len(enroll_resp.data or [])
                records.append(
                    CourseRecord(
                        id=UUID(c_id),
                        teacher_id=UUID(str(row["teacher_id"])),
                        name=row["name"],
                        description=row.get("description"),
                        created_at=_parse_datetime(row["created_at"]),
                        students_count=students_count,
                    )
                )
            return records
        except CourseRepositoryError:
            raise
        except Exception as exc:
            logger.exception("Failed to list courses for teacher %s: %s", teacher_id, exc)
            raise CourseRepositoryError(f"Database error listing teacher courses: {exc}") from exc

    def list_by_student(self, student_id: UUID, *, access_token: str) -> list[CourseRecord]:
        client = self._client(access_token)
        try:
            enroll_resp = (
                client.table("course_enrollments")
                .select("course_id")
                .eq("student_id", str(student_id))
                .eq("status", "active")
                .execute()
            )
            rows = enroll_resp.data or []
            course_ids = [r["course_id"] for r in rows if "course_id" in r]
            if not course_ids:
                return []

            resp = (
                client.table("courses")
                .select("id, teacher_id, name, description, created_at")
                .in_("id", course_ids)
                .order("created_at", desc=True)
                .execute()
            )
            course_rows = resp.data or []
            records: list[CourseRecord] = []
            for row in course_rows:
                records.append(
                    CourseRecord(
                        id=UUID(str(row["id"])),
                        teacher_id=UUID(str(row["teacher_id"])),
                        name=row["name"],
                        description=row.get("description"),
                        created_at=_parse_datetime(row["created_at"]),
                        students_count=0,
                    )
                )
            return records
        except CourseRepositoryError:
            raise
        except Exception as exc:
            logger.exception("Failed to list courses for student %s: %s", student_id, exc)
            raise CourseRepositoryError(f"Database error listing student courses: {exc}") from exc

    def is_student_enrolled(self, course_id: UUID, student_id: UUID, *, access_token: str) -> bool:
        client = self._client(access_token)
        try:
            resp = (
                client.table("course_enrollments")
                .select("id")
                .eq("course_id", str(course_id))
                .eq("student_id", str(student_id))
                .eq("status", "active")
                .execute()
            )
            return bool(resp.data)
        except Exception as exc:
            logger.exception("Failed to check enrollment: %s", exc)
            raise CourseRepositoryError(f"Database error checking enrollment: {exc}") from exc

    def update(
        self, course_id: UUID, name: str | None, description: str | None, *, access_token: str
    ) -> CourseRecord | None:
        client = self._client(access_token)
        payload: dict[str, Any] = {}
        if name is not None:
            payload["name"] = name
        if description is not None:
            payload["description"] = description

        if not payload:
            return self.get(course_id, access_token=access_token)

        try:
            resp = client.table("courses").update(payload).eq("id", str(course_id)).execute()
            rows = resp.data or []
            if not rows:
                return None
            return self.get(course_id, access_token=access_token)
        except CourseRepositoryError:
            raise
        except Exception as exc:
            logger.exception("Failed to update course %s: %s", course_id, exc)
            raise CourseRepositoryError(f"Database error updating course: {exc}") from exc

    def get_student_profile(self, student_id: UUID, *, access_token: str) -> dict[str, Any] | None:
        client = self._client(access_token)
        # 1. Attempt secure RPC first (validate_student_enrollment_target)
        try:
            rpc_res = client.rpc(
                "validate_student_enrollment_target",
                {"target_student_id": str(student_id)},
            ).execute()
            data = rpc_res.data
            if isinstance(data, dict):
                if not data.get("is_valid", False):
                    err_code = data.get("error_code")
                    if err_code == "student_not_found":
                        return None
                    return {
                        "id": student_id,
                        "role": data.get("role", "unknown"),
                        "is_disabled": data.get("is_disabled", False),
                        "display_name": data.get("display_name"),
                        "_validation_error": err_code,
                        "_validation_message": data.get("error_message", "Validation failed."),
                    }
                return {
                    "id": student_id,
                    "role": data.get("role", "student"),
                    "is_disabled": data.get("is_disabled", False),
                    "display_name": data.get("display_name"),
                }
        except Exception as rpc_err:
            logger.debug("validate_student_enrollment_target RPC not available: %s", rpc_err)

        # 2. Fallback to direct profiles table select
        try:
            resp = (
                client.table("profiles")
                .select("id, role, is_disabled, display_name")
                .eq("id", str(student_id))
                .execute()
            )
            rows = resp.data or []
            if not rows:
                return None
            return rows[0]
        except Exception as exc:
            logger.exception("Failed to fetch student profile %s: %s", student_id, exc)
            raise CourseRepositoryError(f"Database error fetching profile: {exc}") from exc

    def get_enrollment(
        self, course_id: UUID, student_id: UUID, *, access_token: str
    ) -> EnrollmentRecord | None:
        client = self._client(access_token)
        try:
            resp = (
                client.table("course_enrollments")
                .select("id, course_id, student_id, status, enrolled_at")
                .eq("course_id", str(course_id))
                .eq("student_id", str(student_id))
                .execute()
            )
            rows = resp.data or []
            if not rows:
                return None
            row = rows[0]
            return EnrollmentRecord(
                id=UUID(str(row["id"])),
                course_id=UUID(str(row["course_id"])),
                student_id=UUID(str(row["student_id"])),
                status=str(row["status"]),
                enrolled_at=_parse_datetime(row["enrolled_at"]),
            )
        except CourseRepositoryError:
            raise
        except Exception as exc:
            logger.exception("Failed to get enrollment: %s", exc)
            raise CourseRepositoryError(f"Database error fetching enrollment: {exc}") from exc

    def enroll_student(
        self, course_id: UUID, student_id: UUID, *, access_token: str
    ) -> EnrollmentRecord:
        client = self._client(access_token)
        enrollment_id = uuid4()
        now = datetime.now(UTC)
        payload = {
            "id": str(enrollment_id),
            "course_id": str(course_id),
            "student_id": str(student_id),
            "status": "active",
            "enrolled_at": now.isoformat(),
        }
        try:
            resp = client.table("course_enrollments").insert(payload).execute()
            rows = resp.data or []
            if not rows:
                raise CourseRepositoryError("Failed to insert enrollment")
            row = rows[0]
            return EnrollmentRecord(
                id=UUID(str(row["id"])),
                course_id=UUID(str(row["course_id"])),
                student_id=UUID(str(row["student_id"])),
                status=str(row["status"]),
                enrolled_at=_parse_datetime(row["enrolled_at"]),
            )
        except DuplicateEnrollmentError:
            raise
        except CourseRepositoryError:
            raise
        except Exception as exc:
            exc_str = str(exc)
            if "23505" in exc_str or "unique" in exc_str.lower() or getattr(exc, "code", None) == "23505":
                raise DuplicateEnrollmentError("Student is already actively enrolled in this course.") from exc
            logger.exception("Failed to enroll student: %s", exc)
            raise CourseRepositoryError(f"Database error enrolling student: {exc}") from exc

    def reactivate_enrollment(
        self, enrollment_id: UUID, *, access_token: str
    ) -> EnrollmentRecord:
        client = self._client(access_token)
        now = datetime.now(UTC)
        try:
            resp = (
                client.table("course_enrollments")
                .update({"status": "active", "enrolled_at": now.isoformat()})
                .eq("id", str(enrollment_id))
                .execute()
            )
            rows = resp.data or []
            if not rows:
                raise CourseRepositoryError("Failed to reactivate enrollment")
            row = rows[0]
            return EnrollmentRecord(
                id=UUID(str(row["id"])),
                course_id=UUID(str(row["course_id"])),
                student_id=UUID(str(row["student_id"])),
                status=str(row["status"]),
                enrolled_at=_parse_datetime(row["enrolled_at"]),
            )
        except DuplicateEnrollmentError:
            raise
        except CourseRepositoryError:
            raise
        except Exception as exc:
            exc_str = str(exc)
            if "23505" in exc_str or "unique" in exc_str.lower() or getattr(exc, "code", None) == "23505":
                raise DuplicateEnrollmentError("Student is already actively enrolled in this course.") from exc
            logger.exception("Failed to reactivate enrollment: %s", exc)
            raise CourseRepositoryError(f"Database error reactivating enrollment: {exc}") from exc

    def list_enrolled_students(
        self, course_id: UUID, *, access_token: str
    ) -> list[EnrolledStudent]:
        client = self._client(access_token)
        try:
            resp = (
                client.table("course_enrollments")
                .select("student_id, status, enrolled_at")
                .eq("course_id", str(course_id))
                .eq("status", "active")
                .order("enrolled_at", desc=False)
                .execute()
            )
            rows = resp.data or []
            if not rows:
                return []

            student_ids = [r["student_id"] for r in rows if "student_id" in r]
            profiles_map: dict[str, str | None] = {}
            if student_ids:
                prof_resp = (
                    client.table("profiles")
                    .select("id, display_name")
                    .in_("id", student_ids)
                    .execute()
                )
                for p in prof_resp.data or []:
                    profiles_map[str(p["id"])] = p.get("display_name")

            students: list[EnrolledStudent] = []
            for r in rows:
                s_id = str(r["student_id"])
                students.append(
                    EnrolledStudent(
                        student_id=UUID(s_id),
                        name=profiles_map.get(s_id),
                        email=None,
                        status=str(r["status"]),
                        enrolled_at=_parse_datetime(r["enrolled_at"]),
                    )
                )
            return students
        except CourseRepositoryError:
            raise
        except Exception as exc:
            logger.exception("Failed to list enrolled students for course %s: %s", course_id, exc)
            raise CourseRepositoryError(f"Database error listing enrolled students: {exc}") from exc

    def deactivate_enrollment(
        self, course_id: UUID, student_id: UUID, *, access_token: str
    ) -> bool:
        client = self._client(access_token)
        try:
            resp = (
                client.table("course_enrollments")
                .update({"status": "inactive"})
                .eq("course_id", str(course_id))
                .eq("student_id", str(student_id))
                .eq("status", "active")
                .execute()
            )
            return bool(resp.data)
        except Exception as exc:
            logger.exception("Failed to deactivate enrollment: %s", exc)
            raise CourseRepositoryError(f"Database error deactivating enrollment: {exc}") from exc

