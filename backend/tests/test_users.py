"""Module 1: current-user profile endpoints and service."""

from uuid import uuid4

import pytest

from app.schemas.user import ProfileUpdate, Role
from app.services.user_service import (
    DisabledAccountError,
    EmptyProfileUpdateError,
    InvalidRoleError,
    ProfileNotFoundError,
    ProfileRecord,
    ProfileRepositoryError,
    SupabaseProfileRepository,
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

    def test_disabled_user_returns_403_account_disabled(self, client, make_token, profiles):
        user_id = uuid4()
        profiles.add(user_id, "student", is_disabled=True)
        response = client.get(PROFILE, headers=bearer(make_token(user_id)))
        assert response.status_code == 403
        assert response.json() == {
            "detail": {"code": "account_disabled", "message": "This account has been disabled."}
        }


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

    def test_disabled_user_update_rejected(self, client, make_token, profiles):
        user_id = uuid4()
        profiles.add(user_id, "student", is_disabled=True)
        response = client.patch(PROFILE, json={"role": "teacher"}, headers=bearer(make_token(user_id)))
        assert response.status_code == 403
        assert response.json() == {
            "detail": {"code": "account_disabled", "message": "This account has been disabled."}
        }


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
        repo.records[user_id] = ProfileRecord(user_id=uuid4(), role="student", is_disabled=False)
        with pytest.raises(ProfileRepositoryError):
            UserService(repo).update_profile(user_id, _UpdateWithTestField(display_label="x"), access_token="tok")

    def test_disabled_user_update_raises_disabled_account_error(self):
        repo = FakeProfileRepository()
        user_id = uuid4()
        repo.add(user_id, "student", is_disabled=True)
        with pytest.raises(DisabledAccountError):
            UserService(repo).update_profile(user_id, _UpdateWithTestField(display_label="x"), access_token="tok")


class TestSupabaseProfileRepositoryParsing:
    def test_missing_is_disabled_raises_repository_error(self):
        raw = {"id": str(uuid4()), "role": "student"}
        with pytest.raises(ProfileRepositoryError, match="Missing is_disabled field"):
            SupabaseProfileRepository._to_record(raw)

    @pytest.mark.parametrize("invalid_val", ["true", "false", 1, 0, None, [], {}])
    def test_non_boolean_is_disabled_raises_repository_error(self, invalid_val):
        raw = {"id": str(uuid4()), "role": "student", "is_disabled": invalid_val}
        with pytest.raises(ProfileRepositoryError, match="is_disabled must be a boolean"):
            SupabaseProfileRepository._to_record(raw)

    def test_valid_is_disabled_false(self):
        uid = uuid4()
        raw = {"id": str(uid), "role": "student", "is_disabled": False}
        record = SupabaseProfileRepository._to_record(raw)
        assert record == ProfileRecord(user_id=uid, role="student", is_disabled=False)

    def test_valid_is_disabled_true(self):
        uid = uuid4()
        raw = {"id": str(uid), "role": "teacher", "is_disabled": True}
        record = SupabaseProfileRepository._to_record(raw)
        assert record == ProfileRecord(user_id=uid, role="teacher", is_disabled=True)


class TestUserServiceValidation:
    def test_disabled_account_raises_disabled_account_error(self):
        user_id = uuid4()
        record = ProfileRecord(user_id=user_id, role="student", is_disabled=True)
        with pytest.raises(DisabledAccountError):
            UserService._validate(user_id, record)

    def test_active_account_returns_user_profile(self):
        user_id = uuid4()
        record = ProfileRecord(user_id=user_id, role="student", is_disabled=False)
        profile = UserService._validate(user_id, record)
        assert profile.user_id == user_id
        assert profile.role is Role.STUDENT

    def test_missing_profile_raises_not_found(self):
        user_id = uuid4()
        with pytest.raises(ProfileNotFoundError):
            UserService._validate(user_id, None)

    def test_profile_mismatch_raises_repository_error(self):
        user_id = uuid4()
        record = ProfileRecord(user_id=uuid4(), role="student", is_disabled=False)
        with pytest.raises(ProfileRepositoryError):
            UserService._validate(user_id, record)

    def test_invalid_role_raises_invalid_role_error(self):
        user_id = uuid4()
        record = ProfileRecord(user_id=user_id, role="admin", is_disabled=False)
        with pytest.raises(InvalidRoleError):
            UserService._validate(user_id, record)
