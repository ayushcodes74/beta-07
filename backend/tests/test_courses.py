"""Tests for Course Management API (Module 2A).

Verifies:
- Teacher course creation and validation.
- Student course creation rejection.
- Teacher listing own courses.
- Student listing enrolled courses.
- Unauthorized course access (privacy convention 404).
- Course editing ownership.
- Enrollment creation and validations.
- Duplicate enrollment prevention (409 Conflict).
- Disabled student account rejection.
- Unauthorized student roster listing.
- Enrollment deactivation (soft deactivation to 'inactive').
- Enrollment reactivation on re-enroll.
- Unconfigured repository handling (503).
"""

from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.v1.endpoints import courses
from app.core.dependencies import get_token_verifier
from app.schemas.user import Role
from app.services.course_service import (
    CourseIntegrationNotConfiguredError,
    CourseRecord,
    CourseRepository,
    CourseService,
    EnrolledStudent,
    EnrollmentRecord,
    get_course_repository,
)
from app.services.user_service import get_profile_repository
from conftest import bearer

BASE = "/api/v1/courses"


class FakeCourseRepository:
    """In-memory test double for CourseRepository."""

    def __init__(self) -> None:
        self.courses: dict[UUID, CourseRecord] = {}
        self.enrollments: dict[UUID, EnrollmentRecord] = {}
        self.student_profiles: dict[UUID, dict[str, Any]] = {}
        self.tokens: list[str] = []

    def add_profile(
        self, user_id: UUID, role: str, is_disabled: bool = False, display_name: str | None = None
    ) -> None:
        self.student_profiles[user_id] = {
            "id": user_id,
            "role": role,
            "is_disabled": is_disabled,
            "display_name": display_name or f"User {str(user_id)[:6]}",
        }

    def create(
        self, teacher_id: UUID, name: str, description: str | None, *, access_token: str
    ) -> CourseRecord:
        self.tokens.append(access_token)
        course_id = uuid4()
        record = CourseRecord(
            id=course_id,
            teacher_id=teacher_id,
            name=name,
            description=description,
            created_at=datetime.now(UTC),
            students_count=0,
            instructor_name="Test Instructor",
        )
        self.courses[course_id] = record
        return record

    def get(self, course_id: UUID, *, access_token: str) -> CourseRecord | None:
        self.tokens.append(access_token)
        record = self.courses.get(course_id)
        if not record:
            return None
        active_count = sum(
            1 for e in self.enrollments.values() if e.course_id == course_id and e.status == "active"
        )
        return CourseRecord(
            id=record.id,
            teacher_id=record.teacher_id,
            name=record.name,
            description=record.description,
            created_at=record.created_at,
            students_count=active_count,
            instructor_name=record.instructor_name,
        )

    def list_by_teacher(self, teacher_id: UUID, *, access_token: str) -> list[CourseRecord]:
        self.tokens.append(access_token)
        records: list[CourseRecord] = []
        for c in self.courses.values():
            if c.teacher_id == teacher_id:
                active_count = sum(
                    1 for e in self.enrollments.values() if e.course_id == c.id and e.status == "active"
                )
                records.append(
                    CourseRecord(
                        id=c.id,
                        teacher_id=c.teacher_id,
                        name=c.name,
                        description=c.description,
                        created_at=c.created_at,
                        students_count=active_count,
                        instructor_name=c.instructor_name,
                    )
                )
        return records

    def list_by_student(self, student_id: UUID, *, access_token: str) -> list[CourseRecord]:
        self.tokens.append(access_token)
        enrolled_course_ids = {
            e.course_id for e in self.enrollments.values() if e.student_id == student_id and e.status == "active"
        }
        return [c for c in self.courses.values() if c.id in enrolled_course_ids]

    def is_student_enrolled(self, course_id: UUID, student_id: UUID, *, access_token: str) -> bool:
        self.tokens.append(access_token)
        return any(
            e.course_id == course_id and e.student_id == student_id and e.status == "active"
            for e in self.enrollments.values()
        )

    def update(
        self, course_id: UUID, name: str | None, description: str | None, *, access_token: str
    ) -> CourseRecord | None:
        self.tokens.append(access_token)
        record = self.courses.get(course_id)
        if not record:
            return None
        updated = CourseRecord(
            id=record.id,
            teacher_id=record.teacher_id,
            name=name if name is not None else record.name,
            description=description if description is not None else record.description,
            created_at=record.created_at,
            students_count=record.students_count,
            instructor_name=record.instructor_name,
        )
        self.courses[course_id] = updated
        return self.get(course_id, access_token=access_token)

    def get_student_profile(
        self, course_id: UUID, student_id: UUID, *, access_token: str
    ) -> dict[str, Any] | None:
        self.tokens.append(access_token)
        # Check course exists
        course = self.courses.get(course_id)
        if not course:
            return {
                "_validation_error": "course_not_found",
                "_validation_message": "Course not found or caller is not owner.",
            }
        return self.student_profiles.get(student_id)

    def get_enrollment(
        self, course_id: UUID, student_id: UUID, *, access_token: str
    ) -> EnrollmentRecord | None:
        self.tokens.append(access_token)
        for e in self.enrollments.values():
            if e.course_id == course_id and e.student_id == student_id:
                return e
        return None

    def enroll_student(
        self, course_id: UUID, student_id: UUID, *, access_token: str
    ) -> EnrollmentRecord:
        self.tokens.append(access_token)
        enrollment_id = uuid4()
        record = EnrollmentRecord(
            id=enrollment_id,
            course_id=course_id,
            student_id=student_id,
            status="active",
            enrolled_at=datetime.now(UTC),
        )
        self.enrollments[enrollment_id] = record
        return record

    def reactivate_enrollment(
        self, enrollment_id: UUID, *, access_token: str
    ) -> EnrollmentRecord:
        self.tokens.append(access_token)
        record = self.enrollments[enrollment_id]
        reactivated = EnrollmentRecord(
            id=record.id,
            course_id=record.course_id,
            student_id=record.student_id,
            status="active",
            enrolled_at=datetime.now(UTC),
        )
        self.enrollments[enrollment_id] = reactivated
        return reactivated

    def list_enrolled_students(
        self, course_id: UUID, *, access_token: str
    ) -> list[EnrolledStudent]:
        self.tokens.append(access_token)
        result: list[EnrolledStudent] = []
        for e in self.enrollments.values():
            if e.course_id == course_id and e.status == "active":
                profile = self.student_profiles.get(e.student_id, {})
                result.append(
                    EnrolledStudent(
                        student_id=e.student_id,
                        name=profile.get("display_name"),
                        email=None,
                        status=e.status,
                        enrolled_at=e.enrolled_at,
                    )
                )
        return result

    def deactivate_enrollment(
        self, course_id: UUID, student_id: UUID, *, access_token: str
    ) -> bool:
        self.tokens.append(access_token)
        for eid, e in self.enrollments.items():
            if e.course_id == course_id and e.student_id == student_id and e.status == "active":
                self.enrollments[eid] = EnrollmentRecord(
                    id=e.id,
                    course_id=e.course_id,
                    student_id=e.student_id,
                    status="inactive",
                    enrolled_at=e.enrolled_at,
                )
                return True
        return False


class UnconfiguredRepo:
    def _fail(self, *args, **kwargs):
        raise CourseIntegrationNotConfiguredError("Unconfigured")

    create = get = list_by_teacher = list_by_student = is_student_enrolled = _fail
    update = get_student_profile = get_enrollment = enroll_student = _fail
    reactivate_enrollment = list_enrolled_students = deactivate_enrollment = _fail


@pytest.fixture
def repo() -> FakeCourseRepository:
    return FakeCourseRepository()


@pytest.fixture
def make_user(verifier, profiles, make_token, repo):
    def _make(role: str = "teacher", is_disabled: bool = False, name: str | None = None):
        user_id = uuid4()
        profiles.add(user_id, role, is_disabled=is_disabled)
        repo.add_profile(user_id, role, is_disabled=is_disabled, display_name=name)
        headers = bearer(make_token(user_id))
        return user_id, headers

    return _make


@pytest.fixture
def api(verifier, profiles, repo) -> TestClient:
    test_app = FastAPI()
    test_app.include_router(courses.router, prefix="/api/v1")
    test_app.dependency_overrides[get_token_verifier] = lambda: verifier
    test_app.dependency_overrides[get_profile_repository] = lambda: profiles
    test_app.dependency_overrides[get_course_repository] = lambda: repo
    return TestClient(test_app)


# --------------------------------------------------------------------------
# Course Creation
# --------------------------------------------------------------------------


class TestCourseCreation:
    def test_teacher_can_create_course(self, api, make_user):
        teacher_id, headers = make_user("teacher")
        payload = {"name": "Data Structures", "description": "CS 204 Course"}
        resp = api.post(BASE, json=payload, headers=headers)
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "Data Structures"
        assert data["description"] == "CS 204 Course"
        assert data["teacher_id"] == str(teacher_id)
        assert data["students"] == 0
        assert "created_at" in data
        assert data["code"] == "DS"

    def test_student_cannot_create_course(self, api, make_user):
        _, headers = make_user("student")
        payload = {"name": "Hacked Course"}
        resp = api.post(BASE, json=payload, headers=headers)
        assert resp.status_code == 403
        assert resp.json()["detail"]["code"] == "forbidden"

    def test_course_creation_invalid_name(self, api, make_user):
        _, headers = make_user("teacher")
        resp = api.post(BASE, json={"name": ""}, headers=headers)
        assert resp.status_code == 422


# --------------------------------------------------------------------------
# Course Listing
# --------------------------------------------------------------------------


class TestCourseListing:
    def test_teacher_lists_own_courses(self, api, make_user):
        t1_id, t1_auth = make_user("teacher")
        t2_id, t2_auth = make_user("teacher")

        api.post(BASE, json={"name": "Course 1"}, headers=t1_auth)
        api.post(BASE, json={"name": "Course 2"}, headers=t1_auth)
        api.post(BASE, json={"name": "Other Teacher Course"}, headers=t2_auth)

        resp = api.get(BASE, headers=t1_auth)
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2
        names = {c["name"] for c in data}
        assert names == {"Course 1", "Course 2"}

    def test_student_lists_enrolled_courses(self, api, make_user):
        teacher_id, teacher_auth = make_user("teacher")
        s1_id, s1_auth = make_user("student")
        s2_id, s2_auth = make_user("student")

        c1 = api.post(BASE, json={"name": "Math 101"}, headers=teacher_auth).json()
        c2 = api.post(BASE, json={"name": "Physics 201"}, headers=teacher_auth).json()

        # Enroll s1 in c1
        api.post(f"{BASE}/{c1['id']}/enrollments", json={"student_id": str(s1_id)}, headers=teacher_auth)

        # s1 should see Math 101
        resp1 = api.get(BASE, headers=s1_auth)
        assert resp1.status_code == 200
        assert len(resp1.json()) == 1
        assert resp1.json()[0]["id"] == c1["id"]

        # s2 (not enrolled) should see empty list
        resp2 = api.get(BASE, headers=s2_auth)
        assert resp2.status_code == 200
        assert resp2.json() == []


# --------------------------------------------------------------------------
# Course Detail & Privacy
# --------------------------------------------------------------------------


class TestCourseDetail:
    def test_owner_teacher_can_view_course(self, api, make_user):
        teacher_id, teacher_auth = make_user("teacher")
        created = api.post(BASE, json={"name": "Algorithms"}, headers=teacher_auth).json()

        resp = api.get(f"{BASE}/{created['id']}", headers=teacher_auth)
        assert resp.status_code == 200
        assert resp.json()["id"] == created["id"]

    def test_enrolled_student_can_view_course(self, api, make_user):
        teacher_id, teacher_auth = make_user("teacher")
        s_id, s_auth = make_user("student")
        created = api.post(BASE, json={"name": "Algorithms"}, headers=teacher_auth).json()

        api.post(f"{BASE}/{created['id']}/enrollments", json={"student_id": str(s_id)}, headers=teacher_auth)

        resp = api.get(f"{BASE}/{created['id']}", headers=s_auth)
        assert resp.status_code == 200
        assert resp.json()["id"] == created["id"]

    def test_unauthorized_teacher_receives_404(self, api, make_user):
        _, t1_auth = make_user("teacher")
        _, t2_auth = make_user("teacher")
        created = api.post(BASE, json={"name": "Private Course"}, headers=t1_auth).json()

        # Teacher 2 may not view Teacher 1's course
        resp = api.get(f"{BASE}/{created['id']}", headers=t2_auth)
        assert resp.status_code == 404
        assert resp.json()["detail"]["code"] == "course_not_found"

    def test_unenrolled_student_receives_404(self, api, make_user):
        _, teacher_auth = make_user("teacher")
        _, s_auth = make_user("student")
        created = api.post(BASE, json={"name": "Private Course"}, headers=teacher_auth).json()

        resp = api.get(f"{BASE}/{created['id']}", headers=s_auth)
        assert resp.status_code == 404
        assert resp.json()["detail"]["code"] == "course_not_found"


# --------------------------------------------------------------------------
# Course Editing Ownership
# --------------------------------------------------------------------------


class TestCourseEditing:
    def test_owner_can_update_course(self, api, make_user):
        _, teacher_auth = make_user("teacher")
        created = api.post(BASE, json={"name": "Old Title", "description": "Old desc"}, headers=teacher_auth).json()

        resp = api.patch(f"{BASE}/{created['id']}", json={"name": "New Title"}, headers=teacher_auth)
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "New Title"
        assert data["description"] == "Old desc"

    def test_empty_update_rejected(self, api, make_user):
        _, teacher_auth = make_user("teacher")
        created = api.post(BASE, json={"name": "Title"}, headers=teacher_auth).json()

        resp = api.patch(f"{BASE}/{created['id']}", json={}, headers=teacher_auth)
        assert resp.status_code == 422

    def test_non_owner_teacher_update_rejected_404(self, api, make_user):
        _, t1_auth = make_user("teacher")
        _, t2_auth = make_user("teacher")
        created = api.post(BASE, json={"name": "Title"}, headers=t1_auth).json()

        resp = api.patch(f"{BASE}/{created['id']}", json={"name": "Hacked"}, headers=t2_auth)
        assert resp.status_code == 404

    def test_student_cannot_update_course(self, api, make_user):
        _, teacher_auth = make_user("teacher")
        _, s_auth = make_user("student")
        created = api.post(BASE, json={"name": "Title"}, headers=teacher_auth).json()

        resp = api.patch(f"{BASE}/{created['id']}", json={"name": "Hacked"}, headers=s_auth)
        assert resp.status_code == 403


# --------------------------------------------------------------------------
# Enrollment Management
# --------------------------------------------------------------------------


class TestEnrollments:
    def test_teacher_can_enroll_student(self, api, make_user):
        teacher_id, teacher_auth = make_user("teacher")
        s_id, _ = make_user("student", name="Alice Chen")
        created = api.post(BASE, json={"name": "Biology"}, headers=teacher_auth).json()

        resp = api.post(f"{BASE}/{created['id']}/enrollments", json={"student_id": str(s_id)}, headers=teacher_auth)
        assert resp.status_code == 201
        data = resp.json()
        assert data["course_id"] == created["id"]
        assert data["student_id"] == str(s_id)
        assert data["status"] == "active"

        # Verify students count in course increased
        course_resp = api.get(f"{BASE}/{created['id']}", headers=teacher_auth)
        assert course_resp.json()["students"] == 1

    def test_duplicate_enrollment_rejected(self, api, make_user):
        _, teacher_auth = make_user("teacher")
        s_id, _ = make_user("student")
        created = api.post(BASE, json={"name": "Biology"}, headers=teacher_auth).json()

        # First enrollment
        api.post(f"{BASE}/{created['id']}/enrollments", json={"student_id": str(s_id)}, headers=teacher_auth)

        # Duplicate enrollment
        dup_resp = api.post(f"{BASE}/{created['id']}/enrollments", json={"student_id": str(s_id)}, headers=teacher_auth)
        assert dup_resp.status_code == 409
        assert dup_resp.json()["detail"]["code"] == "duplicate_enrollment"

    def test_cannot_enroll_teacher_account(self, api, make_user):
        _, teacher_auth = make_user("teacher")
        other_teacher_id, _ = make_user("teacher")
        created = api.post(BASE, json={"name": "Biology"}, headers=teacher_auth).json()

        resp = api.post(
            f"{BASE}/{created['id']}/enrollments",
            json={"student_id": str(other_teacher_id)},
            headers=teacher_auth,
        )
        assert resp.status_code == 422
        assert resp.json()["detail"]["code"] == "invalid_role"

    def test_cannot_enroll_disabled_account(self, api, make_user):
        _, teacher_auth = make_user("teacher")
        disabled_s_id, _ = make_user("student", is_disabled=True)
        created = api.post(BASE, json={"name": "Biology"}, headers=teacher_auth).json()

        resp = api.post(
            f"{BASE}/{created['id']}/enrollments",
            json={"student_id": str(disabled_s_id)},
            headers=teacher_auth,
        )
        assert resp.status_code == 422
        assert resp.json()["detail"]["code"] == "account_disabled"

    def test_cannot_enroll_nonexistent_account(self, api, make_user):
        _, teacher_auth = make_user("teacher")
        created = api.post(BASE, json={"name": "Biology"}, headers=teacher_auth).json()

        resp = api.post(
            f"{BASE}/{created['id']}/enrollments",
            json={"student_id": str(uuid4())},
            headers=teacher_auth,
        )
        assert resp.status_code == 422
        assert resp.json()["detail"]["code"] == "student_not_found"

    def test_teacher_cannot_enroll_student_in_another_teachers_course(self, api, make_user):
        _, t1_auth = make_user("teacher")
        _, t2_auth = make_user("teacher")
        s_id, _ = make_user("student")
        created = api.post(BASE, json={"name": "Teacher 1 Course"}, headers=t1_auth).json()

        # Teacher 2 tries to enroll student in Teacher 1's course
        resp = api.post(
            f"{BASE}/{created['id']}/enrollments",
            json={"student_id": str(s_id)},
            headers=t2_auth,
        )
        assert resp.status_code == 404
        assert resp.json()["detail"]["code"] == "course_not_found"

    def test_rpc_course_not_found_returns_404(self, api, repo, make_user):
        _, teacher_auth = make_user("teacher")
        s_id, _ = make_user("student")
        created = api.post(BASE, json={"name": "Biology"}, headers=teacher_auth).json()

        # Simulate RPC indicating caller does not own course or course not found
        original_get_profile = repo.get_student_profile
        repo.get_student_profile = lambda c_id, s_id, **kw: {
            "id": s_id,
            "_validation_error": "course_not_found",
            "_validation_message": "Course not found or caller is not owner.",
        }

        resp = api.post(
            f"{BASE}/{created['id']}/enrollments",
            json={"student_id": str(s_id)},
            headers=teacher_auth,
        )
        assert resp.status_code == 404
        assert resp.json()["detail"]["code"] == "course_not_found"
        repo.get_student_profile = original_get_profile

    def test_rpc_unavailable_fails_closed_returns_503(self, api, repo, make_user):
        from app.services.course_service import CourseRepositoryError

        _, teacher_auth = make_user("teacher")
        s_id, _ = make_user("student")
        created = api.post(BASE, json={"name": "Biology"}, headers=teacher_auth).json()

        original_get_profile = repo.get_student_profile
        def _failing_get_profile(*args, **kwargs):
            raise CourseRepositoryError("PostgREST RPC connection failure: 502 Bad Gateway")
        repo.get_student_profile = _failing_get_profile

        resp = api.post(
            f"{BASE}/{created['id']}/enrollments",
            json={"student_id": str(s_id)},
            headers=teacher_auth,
        )
        assert resp.status_code == 503
        assert resp.json()["detail"]["code"] == "course_service_unavailable"
        repo.get_student_profile = original_get_profile

    @pytest.mark.parametrize("error_code,error_msg", [
        ("invalid_role", "Only student accounts can be enrolled in courses."),
        ("account_disabled", "Cannot enroll a disabled student account."),
        ("student_not_found", "The specified student profile was not found."),
    ])
    def test_rpc_validation_errors_retain_codes(self, api, repo, make_user, error_code, error_msg):
        _, teacher_auth = make_user("teacher")
        target_id = uuid4()
        created = api.post(BASE, json={"name": "Biology"}, headers=teacher_auth).json()

        original_get_profile = repo.get_student_profile
        repo.get_student_profile = lambda c_id, s_id, **kw: {
            "id": target_id,
            "_validation_error": error_code,
            "_validation_message": error_msg,
        }

        resp = api.post(
            f"{BASE}/{created['id']}/enrollments",
            json={"student_id": str(target_id)},
            headers=teacher_auth,
        )
        assert resp.status_code == 422
        assert resp.json()["detail"]["code"] == error_code
        repo.get_student_profile = original_get_profile

    def test_database_unique_constraint_translates_to_409(self, api, repo, make_user):
        _, teacher_auth = make_user("teacher")
        s_id, _ = make_user("student")
        created = api.post(BASE, json={"name": "Biology"}, headers=teacher_auth).json()

        # Simulate concurrent insertion triggering PostgreSQL 23505 unique_violation
        from app.services.course_service import DuplicateEnrollmentError
        original_enroll = repo.enroll_student
        def _failing_enroll(*args, **kwargs):
            raise DuplicateEnrollmentError("Student is already actively enrolled in this course.")
        repo.enroll_student = _failing_enroll

        resp = api.post(
            f"{BASE}/{created['id']}/enrollments",
            json={"student_id": str(s_id)},
            headers=teacher_auth,
        )
        assert resp.status_code == 409
        assert resp.json()["detail"]["code"] == "duplicate_enrollment"
        repo.enroll_student = original_enroll

    def test_supabase_course_repo_unique_violation_translation(self):
        from unittest.mock import MagicMock
        from app.database.course_repository import SupabaseCourseRepository
        from app.services.course_service import DuplicateEnrollmentError

        repo = SupabaseCourseRepository()
        mock_client = MagicMock()
        mock_table = MagicMock()
        mock_client.table.return_value = mock_table

        # Simulate 23505 in insert
        mock_table.insert.return_value.execute.side_effect = Exception(
            "{'code': '23505', 'message': 'duplicate key value violates unique constraint'}"
        )
        repo._client = MagicMock(return_value=mock_client)

        with pytest.raises(DuplicateEnrollmentError):
            repo.enroll_student(uuid4(), uuid4(), access_token="fake")

        # Simulate 23505 in update (reactivate)
        mock_table.update.return_value.eq.return_value.execute.side_effect = Exception(
            "unique_violation: code 23505"
        )
        with pytest.raises(DuplicateEnrollmentError):
            repo.reactivate_enrollment(uuid4(), access_token="fake")


# --------------------------------------------------------------------------
# Student Roster & Deactivation
# --------------------------------------------------------------------------


class TestStudentRosterAndDeactivation:
    def test_teacher_lists_enrolled_students(self, api, make_user):
        _, teacher_auth = make_user("teacher")
        s1_id, _ = make_user("student", name="Bob Smith")
        s2_id, _ = make_user("student", name="Charlie Brown")
        created = api.post(BASE, json={"name": "Chemistry"}, headers=teacher_auth).json()

        api.post(f"{BASE}/{created['id']}/enrollments", json={"student_id": str(s1_id)}, headers=teacher_auth)
        api.post(f"{BASE}/{created['id']}/enrollments", json={"student_id": str(s2_id)}, headers=teacher_auth)

        roster_resp = api.get(f"{BASE}/{created['id']}/students", headers=teacher_auth)
        assert roster_resp.status_code == 200
        roster = roster_resp.json()
        assert len(roster) == 2
        student_ids = {r["student_id"] for r in roster}
        assert student_ids == {str(s1_id), str(s2_id)}
        assert all(r["status"] == "active" for r in roster)

    def test_unauthorized_user_cannot_list_roster(self, api, make_user):
        _, t1_auth = make_user("teacher")
        _, t2_auth = make_user("teacher")
        _, s_auth = make_user("student")
        created = api.post(BASE, json={"name": "Chemistry"}, headers=t1_auth).json()

        # Non-owner teacher gets 404
        assert api.get(f"{BASE}/{created['id']}/students", headers=t2_auth).status_code == 404

        # Student gets 403
        assert api.get(f"{BASE}/{created['id']}/students", headers=s_auth).status_code == 403

    def test_deactivate_enrollment(self, api, make_user):
        _, teacher_auth = make_user("teacher")
        s_id, s_auth = make_user("student")
        created = api.post(BASE, json={"name": "Art History"}, headers=teacher_auth).json()

        # Enroll
        api.post(f"{BASE}/{created['id']}/enrollments", json={"student_id": str(s_id)}, headers=teacher_auth)

        # Deactivate
        del_resp = api.delete(f"{BASE}/{created['id']}/enrollments/{s_id}", headers=teacher_auth)
        assert del_resp.status_code == 204

        # Student should no longer see course in list
        assert api.get(BASE, headers=s_auth).json() == []

        # Roster should be empty
        assert api.get(f"{BASE}/{created['id']}/students", headers=teacher_auth).json() == []

        # Deactivating again returns 404
        assert api.delete(f"{BASE}/{created['id']}/enrollments/{s_id}", headers=teacher_auth).status_code == 404

        # Re-enrolling student reactivates enrollment
        re_resp = api.post(f"{BASE}/{created['id']}/enrollments", json={"student_id": str(s_id)}, headers=teacher_auth)
        assert re_resp.status_code == 201
        assert re_resp.json()["status"] == "active"


# --------------------------------------------------------------------------
# Service Unavailability
# --------------------------------------------------------------------------


def test_unconfigured_repository_returns_503(verifier, profiles, make_user):
    _, teacher_auth = make_user("teacher")
    test_app = FastAPI()
    test_app.include_router(courses.router, prefix="/api/v1")
    test_app.dependency_overrides[get_token_verifier] = lambda: verifier
    test_app.dependency_overrides[get_profile_repository] = lambda: profiles
    test_app.dependency_overrides[get_course_repository] = lambda: UnconfiguredRepo()

    client = TestClient(test_app)
    resp = client.get(BASE, headers=teacher_auth)
    assert resp.status_code == 503
    assert resp.json()["detail"]["code"] == "course_service_unavailable"

