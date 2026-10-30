"""Module 1: current-user profile endpoints and service."""

from uuid import uuid4

import pytest

from app.schemas.user import ProfileUpdate, Role
from app.services.user_service import (
    EmptyProfileUpdateError,
    ProfileNotFoundError,
    ProfileRecord,
    ProfileRepositoryError,
    UserService,
)
from conftest import FakeProfileRepository, bearer

PROFILE = "/api/v1/users/me"


@pytest.fixture
def student(make_token, profiles):
    user_id = uuid4()
    profiles.add(user_id, "student")
    return user_id, make_token(user_id, email="student@example.com")


class TestGetMyProfile:
    def test_returns_own_profile(self, client, student, profiles):
        user_id, token = student
        response = client.get(PROFILE, headers=bearer(token))
        assert response.status_code == 200
        assert response.json() == {"id": str(user_id), "email": "student@example.com", "role": "student"}
        assert profiles.get_calls == [(user_id, token)]

    def test_cannot_select_another_user(self, client, student, profiles):
        user_id, token = student
        other_id = uuid4()
        profiles.add(other_id, "teacher")

        response = client.get(PROFILE, params={"id": str(other_id), "user_id": str(other_id)}, headers=bearer(token))

        assert response.json()["id"] == str(user_id)
        assert all(call_user == user_id for call_user, _ in profiles.get_calls)

    def test_unauthenticated_returns_401(self, client):
        assert client.get(PROFILE).status_code == 401

    def test_missing_profile_returns_403(self, client, make_token):
        response = client.get(PROFILE, headers=bearer(make_token()))
        assert response.status_code == 403


class TestUpdateMyProfile:
    @pytest.mark.parametrize(
        "body",
        [
            {"role": "teacher"},
            {"id": str(uuid4())},
            {"user_id": str(uuid4())},
            {"email": "someone-else@example.com"},
            {"is_active": True},
            {"app_metadata": {"role": "teacher"}},
        ],
    )
    def test_protected_or_unknown_fields_rejected(self, client, student, profiles, body):
        _, token = student
        response = client.patch(PROFILE, json=body, headers=bearer(token))
        assert response.status_code == 422
        assert profiles.update_calls == []

    def test_role_unchanged_after_rejected_role_change(self, client, student):
        _, token = student
        client.patch(PROFILE, json={"role": "teacher"}, headers=bearer(token))
        assert client.get(PROFILE, headers=bearer(token)).json()["role"] == "student"

    @pytest.mark.parametrize("raw_body", ["not json", "[1, 2, 3]", '"string"', "null"])
    def test_invalid_body_rejected(self, client, student, profiles, raw_body):
        _, token = student
        headers = {**bearer(token), "Content-Type": "application/json"}
        response = client.patch(PROFILE, content=raw_body, headers=headers)
        assert response.status_code == 422
        assert profiles.update_calls == []

    def test_empty_update_rejected(self, client, student, profiles):
        _, token = student
        response = client.patch(PROFILE, json={}, headers=bearer(token))
        assert response.status_code == 422
        assert response.json()["detail"]["code"] == "empty_update"
        assert profiles.update_calls == []

    def test_unauthenticated_returns_401(self, client):
        assert client.patch(PROFILE, json={"role": "teacher"}).status_code == 401


# The editable profile fields are not confirmed yet, so ``ProfileUpdate`` has
# none. This test-only subclass exercises the update path end to end; replace
# it with the real fields once the database contract is confirmed.
class _UpdateWithTestField(ProfileUpdate):
    display_label: str | None = None


class TestUserServiceUpdate:
    def test_updates_only_the_callers_profile(self):
        repo = FakeProfileRepository()
        user_id = uuid4()
        repo.add(user_id, "student")

        profile = UserService(repo).update_profile(
            user_id, _UpdateWithTestField(display_label="  Example  "), access_token="tok"
        )

        assert profile.user_id == user_id
        assert profile.role is Role.STUDENT
        # Only explicitly sent fields are forwarded, whitespace-trimmed, for the token subject.
        assert repo.update_calls == [(user_id, {"display_label": "Example"}, "tok")]

    def test_update_model_still_forbids_protected_fields(self):
        with pytest.raises(ValueError):
            _UpdateWithTestField.model_validate({"display_label": "x", "role": "teacher"})

    def test_empty_update_rejected(self):
        repo = FakeProfileRepository()
        with pytest.raises(EmptyProfileUpdateError):
            UserService(repo).update_profile(uuid4(), _UpdateWithTestField(), access_token="tok")
        assert repo.update_calls == []

    def test_missing_profile_on_update(self):
        with pytest.raises(ProfileNotFoundError):
            UserService(FakeProfileRepository()).update_profile(
                uuid4(), _UpdateWithTestField(display_label="x"), access_token="tok"
            )

    def test_record_for_other_user_rejected(self):
        repo = FakeProfileRepository()
        user_id = uuid4()
        repo.records[user_id] = ProfileRecord(user_id=uuid4(), role="student")
        with pytest.raises(ProfileRepositoryError):
            UserService(repo).update_profile(user_id, _UpdateWithTestField(display_label="x"), access_token="tok")
