"""Module 1: token verification, authentication and role authorization."""

import base64
import hashlib
import hmac
import json
import time
from typing import Annotated
from uuid import uuid4

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from app.core import dependencies
from app.core.config import Settings
from app.core.dependencies import (
    get_token_verifier,
    require_authenticated_user,
    require_student,
    require_teacher,
)
from app.core.security import (
    JwksTokenVerifier,
    SharedSecretTokenVerifier,
    SigningKeyUnavailableError,
    TokenVerificationError,
    TokenVerifierNotConfiguredError,
    build_token_verifier,
)
from app.main import app
from app.services.auth_service import CurrentUser
from app.services.user_service import ProfileRecord, get_profile_repository
from conftest import TEST_AUDIENCE, TEST_ISSUER, TEST_KID, bearer, build_claims


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _unsigned_token(header: dict, claims: dict, signature: bytes = b"") -> str:
    return ".".join([_b64(json.dumps(header).encode()), _b64(json.dumps(claims).encode()), _b64(signature)])


# --------------------------------------------------------------------------
# Token verifier (JWKS / asymmetric keys)
# --------------------------------------------------------------------------


class TestJwksTokenVerifier:
    def test_valid_token_identifies_user(self, verifier, make_token):
        user_id = uuid4()
        claims = verifier.verify(make_token(user_id, email="teacher@example.com"))
        assert claims.user_id == user_id
        assert claims.email == "teacher@example.com"
        assert claims.session_id == "test-session"

    def test_expired_token_rejected(self, verifier, make_token):
        past = int(time.time()) - 3600
        with pytest.raises(TokenVerificationError):
            verifier.verify(make_token(iat=past - 3600, exp=past))

    def test_token_signed_with_other_key_rejected(self, verifier, make_token):
        attacker_key = ec.generate_private_key(ec.SECP256R1())
        with pytest.raises(TokenVerificationError):
            verifier.verify(make_token(key=attacker_key))

    def test_tampered_payload_rejected(self, verifier, make_token):
        header, _, signature = make_token().split(".")
        forged_payload = _b64(json.dumps(build_claims()).encode())
        with pytest.raises(TokenVerificationError):
            verifier.verify(f"{header}.{forged_payload}.{signature}")

    @pytest.mark.parametrize("token", ["", "not-a-jwt", "a.b.c", "a.b", "...."])
    def test_malformed_token_rejected(self, verifier, token):
        with pytest.raises(TokenVerificationError):
            verifier.verify(token)

    @pytest.mark.parametrize("claim", ["sub", "exp", "iat", "iss", "aud", "role"])
    def test_missing_required_claim_rejected(self, verifier, make_token, claim):
        # build_claims drops claims overridden with None.
        with pytest.raises(TokenVerificationError):
            verifier.verify(make_token(**{claim: None}))

    def test_wrong_issuer_rejected(self, verifier, make_token):
        with pytest.raises(TokenVerificationError):
            verifier.verify(make_token(iss="https://other-project.invalid/auth/v1"))

    def test_wrong_audience_rejected(self, verifier, make_token):
        with pytest.raises(TokenVerificationError):
            verifier.verify(make_token(aud="some-other-audience"))

    @pytest.mark.parametrize("postgres_role", ["anon", "service_role", "teacher"])
    def test_non_end_user_token_rejected(self, verifier, make_token, postgres_role):
        with pytest.raises(TokenVerificationError):
            verifier.verify(make_token(role=postgres_role))

    def test_anonymous_session_rejected(self, verifier, make_token):
        with pytest.raises(TokenVerificationError):
            verifier.verify(make_token(is_anonymous=True))

    def test_non_uuid_subject_rejected(self, verifier, make_token):
        with pytest.raises(TokenVerificationError):
            verifier.verify(make_token(sub="not-a-uuid"))

    def test_unknown_key_id_rejected(self, verifier, make_token):
        with pytest.raises(TokenVerificationError):
            verifier.verify(make_token(kid="unknown-kid"))

    def test_alg_none_rejected(self, verifier):
        token = _unsigned_token({"alg": "none", "typ": "JWT", "kid": TEST_KID}, build_claims())
        with pytest.raises(TokenVerificationError):
            verifier.verify(token)

    def test_hs256_with_public_key_as_secret_rejected(self, verifier, signing_key):
        # Classic algorithm-confusion attack: HMAC "signed" with the public key.
        public_pem = signing_key.public_key().public_bytes(
            serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
        )
        header = _b64(json.dumps({"alg": "HS256", "typ": "JWT", "kid": TEST_KID}).encode())
        payload = _b64(json.dumps(build_claims()).encode())
        signature = hmac.new(public_pem, f"{header}.{payload}".encode(), hashlib.sha256).digest()
        with pytest.raises(TokenVerificationError):
            verifier.verify(f"{header}.{payload}.{_b64(signature)}")

    def test_unreachable_jwks_reported_separately(self, verifier, key_source, make_token):
        key_source.unreachable = True
        with pytest.raises(SigningKeyUnavailableError):
            verifier.verify(make_token())

    def test_symmetric_algorithms_not_allowed_for_jwks(self, key_source):
        with pytest.raises(TokenVerifierNotConfiguredError):
            JwksTokenVerifier(key_source, algorithms=["HS256"], issuer=TEST_ISSUER, audience=TEST_AUDIENCE)


# --------------------------------------------------------------------------
# Token verifier (legacy shared secret)
# --------------------------------------------------------------------------

SECRET = "test-only-shared-secret-with-at-least-32-bytes!!"


class TestSharedSecretTokenVerifier:
    @pytest.fixture
    def hs_verifier(self):
        return SharedSecretTokenVerifier(SECRET, algorithms=["HS256"], issuer=TEST_ISSUER, audience=TEST_AUDIENCE)

    def test_valid_token(self, hs_verifier):
        user_id = uuid4()
        token = jwt.encode(build_claims(user_id), SECRET, algorithm="HS256")
        assert hs_verifier.verify(token).user_id == user_id

    def test_wrong_secret_rejected(self, hs_verifier):
        token = jwt.encode(build_claims(), "a-different-secret-that-is-also-32-bytes-long", algorithm="HS256")
        with pytest.raises(TokenVerificationError):
            hs_verifier.verify(token)

    def test_asymmetric_token_rejected(self, hs_verifier, make_token):
        with pytest.raises(TokenVerificationError):
            hs_verifier.verify(make_token())

    def test_asymmetric_algorithms_not_allowed(self):
        with pytest.raises(TokenVerifierNotConfiguredError):
            SharedSecretTokenVerifier(SECRET, algorithms=["ES256"], issuer=TEST_ISSUER, audience=TEST_AUDIENCE)


# --------------------------------------------------------------------------
# Verifier configuration
# --------------------------------------------------------------------------


def _settings(**values) -> Settings:
    return Settings(_env_file=None, **values)


class TestBuildTokenVerifier:
    def test_unconfigured_settings_rejected(self):
        with pytest.raises(TokenVerifierNotConfiguredError):
            build_token_verifier(_settings())

    @pytest.mark.parametrize("method", ["", "JWKS", "none", "hs256"])
    def test_empty_or_unknown_method_rejected(self, method):
        settings = _settings(
            SUPABASE_JWT_VERIFICATION_METHOD=method,
            SUPABASE_JWT_ALGORITHMS="ES256",
            SUPABASE_JWT_ISSUER=TEST_ISSUER,
            SUPABASE_JWT_AUDIENCE=TEST_AUDIENCE,
        )
        with pytest.raises(TokenVerifierNotConfiguredError):
            build_token_verifier(settings)

    def test_jwks_requires_url(self):
        settings = _settings(
            SUPABASE_JWT_VERIFICATION_METHOD="jwks",
            SUPABASE_JWT_ALGORITHMS="ES256",
            SUPABASE_JWT_ISSUER=TEST_ISSUER,
            SUPABASE_JWT_AUDIENCE=TEST_AUDIENCE,
        )
        with pytest.raises(TokenVerifierNotConfiguredError):
            build_token_verifier(settings)

    def test_jwks_with_symmetric_algorithm_rejected(self):
        settings = _settings(
            SUPABASE_JWT_VERIFICATION_METHOD="jwks",
            SUPABASE_JWKS_URL="https://test-project.invalid/auth/v1/.well-known/jwks.json",
            SUPABASE_JWT_ALGORITHMS="HS256",
            SUPABASE_JWT_ISSUER=TEST_ISSUER,
            SUPABASE_JWT_AUDIENCE=TEST_AUDIENCE,
        )
        with pytest.raises(TokenVerifierNotConfiguredError):
            build_token_verifier(settings)

    def test_shared_secret_requires_secret(self):
        settings = _settings(
            SUPABASE_JWT_VERIFICATION_METHOD="shared_secret",
            SUPABASE_JWT_ALGORITHMS="HS256",
            SUPABASE_JWT_ISSUER=TEST_ISSUER,
            SUPABASE_JWT_AUDIENCE=TEST_AUDIENCE,
        )
        with pytest.raises(TokenVerifierNotConfiguredError):
            build_token_verifier(settings)

    def test_complete_jwks_settings_build_verifier(self):
        settings = _settings(
            SUPABASE_JWT_VERIFICATION_METHOD="jwks",
            SUPABASE_JWKS_URL="https://test-project.invalid/auth/v1/.well-known/jwks.json",
            SUPABASE_JWT_ALGORITHMS="ES256, RS256",
            SUPABASE_JWT_ISSUER=TEST_ISSUER,
            SUPABASE_JWT_AUDIENCE=TEST_AUDIENCE,
        )
        assert isinstance(build_token_verifier(settings), JwksTokenVerifier)

    def test_complete_shared_secret_settings_build_verifier(self):
        settings = _settings(
            SUPABASE_JWT_VERIFICATION_METHOD="shared_secret",
            SUPABASE_JWT_SECRET=SECRET,
            SUPABASE_JWT_ALGORITHMS="HS256",
            SUPABASE_JWT_ISSUER=TEST_ISSUER,
            SUPABASE_JWT_AUDIENCE=TEST_AUDIENCE,
        )
        assert isinstance(build_token_verifier(settings), SharedSecretTokenVerifier)


# --------------------------------------------------------------------------
# GET /api/v1/auth/me
# --------------------------------------------------------------------------

ME = "/api/v1/auth/me"


class TestAuthMe:
    def test_missing_token_returns_401(self, client):
        response = client.get(ME)
        assert response.status_code == 401
        assert response.json()["detail"]["code"] == "not_authenticated"
        assert response.headers["WWW-Authenticate"] == "Bearer"

    def test_non_bearer_scheme_returns_401(self, client):
        response = client.get(ME, headers={"Authorization": "Basic dXNlcjpwYXNz"})
        assert response.status_code == 401

    def test_malformed_token_returns_401_without_details(self, client):
        response = client.get(ME, headers=bearer("not-a-jwt"))
        assert response.status_code == 401
        assert response.json() == {
            "detail": {"code": "invalid_token", "message": "Invalid or expired access token."}
        }

    def test_expired_token_returns_401(self, client, make_token):
        past = int(time.time()) - 3600
        response = client.get(ME, headers=bearer(make_token(iat=past - 3600, exp=past)))
        assert response.status_code == 401
        assert response.json()["detail"]["code"] == "invalid_token"

    def test_invalid_signature_returns_401(self, client, make_token):
        attacker_key = ec.generate_private_key(ec.SECP256R1())
        response = client.get(ME, headers=bearer(make_token(key=attacker_key)))
        assert response.status_code == 401

    def test_missing_claim_returns_401(self, client, make_token):
        response = client.get(ME, headers=bearer(make_token(sub=None)))
        assert response.status_code == 401

    def test_valid_token_identifies_user(self, client, make_token, profiles):
        user_id = uuid4()
        profiles.add(user_id, "teacher")
        token = make_token(user_id, email="teacher@example.com")

        response = client.get(ME, headers=bearer(token))

        assert response.status_code == 200
        assert response.json() == {"id": str(user_id), "email": "teacher@example.com", "role": "teacher"}
        # Profile is looked up for the verified subject, with the caller's token (for RLS).
        assert profiles.get_calls == [(user_id, token)]

    def test_role_in_user_metadata_is_ignored(self, client, make_token, profiles):
        user_id = uuid4()
        profiles.add(user_id, "student")
        token = make_token(user_id, user_metadata={"role": "teacher"}, app_role="teacher")

        response = client.get(ME, headers=bearer(token))

        assert response.status_code == 200
        assert response.json()["role"] == "student"

    def test_role_in_query_or_header_is_ignored(self, client, make_token, profiles):
        user_id = uuid4()
        profiles.add(user_id, "student")
        headers = {**bearer(make_token(user_id)), "X-Role": "teacher"}

        response = client.get(ME, params={"role": "teacher"}, headers=headers)

        assert response.json()["role"] == "student"

    def test_missing_profile_returns_403(self, client, make_token):
        response = client.get(ME, headers=bearer(make_token()))
        assert response.status_code == 403
        assert response.json()["detail"]["code"] == "profile_not_found"

    @pytest.mark.parametrize("stored_role", ["admin", "TEACHER", "", "superuser"])
    def test_unrecognised_role_returns_403(self, client, make_token, profiles, stored_role):
        user_id = uuid4()
        profiles.add(user_id, stored_role)
        response = client.get(ME, headers=bearer(make_token(user_id)))
        assert response.status_code == 403
        assert response.json()["detail"]["code"] == "invalid_role"

    def test_profile_for_other_user_is_never_returned(self, client, make_token, profiles):
        user_id, other_id = uuid4(), uuid4()
        profiles.records[user_id] = ProfileRecord(user_id=other_id, role="teacher")
        response = client.get(ME, headers=bearer(make_token(user_id)))
        assert response.status_code == 503

    def test_unreachable_jwks_returns_503(self, client, key_source, make_token):
        key_source.unreachable = True
        response = client.get(ME, headers=bearer(make_token()))
        assert response.status_code == 503
        assert response.json()["detail"]["code"] == "auth_unavailable"


class TestUnconfiguredIntegrations:
    """Without confirmed config the API fails closed with 503, never with fake data."""

    def test_unconfigured_jwt_settings_return_503(self, monkeypatch, make_token):
        monkeypatch.setattr(dependencies, "settings", _settings())
        dependencies._configured_token_verifier.cache_clear()
        try:
            response = TestClient(app).get(ME, headers=bearer(make_token()))
        finally:
            dependencies._configured_token_verifier.cache_clear()
        assert response.status_code == 503
        assert response.json()["detail"]["code"] == "auth_unavailable"

    def test_missing_token_still_401_when_unconfigured(self, monkeypatch):
        monkeypatch.setattr(dependencies, "settings", _settings())
        dependencies._configured_token_verifier.cache_clear()
        try:
            response = TestClient(app).get(ME)
        finally:
            dependencies._configured_token_verifier.cache_clear()
        assert response.status_code == 401

    def test_unconfigured_profile_repository_returns_503(self, verifier, make_token):
        app.dependency_overrides[get_token_verifier] = lambda: verifier
        try:
            response = TestClient(app).get(ME, headers=bearer(make_token()))
        finally:
            app.dependency_overrides.clear()
        assert response.status_code == 503
        assert response.json()["detail"]["code"] == "profile_service_unavailable"


# --------------------------------------------------------------------------
# Role-based authorization dependencies
# --------------------------------------------------------------------------


@pytest.fixture
def guarded_client(verifier, profiles):
    guarded = FastAPI()

    @guarded.get("/teacher-only")
    def teacher_only(user: Annotated[CurrentUser, Depends(require_teacher)]):
        return {"id": str(user.id), "role": user.role}

    @guarded.get("/student-only")
    def student_only(user: Annotated[CurrentUser, Depends(require_student)]):
        return {"id": str(user.id), "role": user.role}

    @guarded.get("/any-user", dependencies=[Depends(require_authenticated_user)])
    def any_user():
        return {"ok": True}

    guarded.dependency_overrides[get_token_verifier] = lambda: verifier
    guarded.dependency_overrides[get_profile_repository] = lambda: profiles
    return TestClient(guarded)


@pytest.fixture
def teacher_token(make_token, profiles):
    user_id = uuid4()
    profiles.add(user_id, "teacher")
    return make_token(user_id)


@pytest.fixture
def student_token(make_token, profiles):
    user_id = uuid4()
    profiles.add(user_id, "student")
    return make_token(user_id)


class TestRoleAuthorization:
    def test_teacher_dependency_accepts_teacher(self, guarded_client, teacher_token):
        response = guarded_client.get("/teacher-only", headers=bearer(teacher_token))
        assert response.status_code == 200
        assert response.json()["role"] == "teacher"

    def test_student_dependency_accepts_student(self, guarded_client, student_token):
        response = guarded_client.get("/student-only", headers=bearer(student_token))
        assert response.status_code == 200
        assert response.json()["role"] == "student"

    def test_student_cannot_access_teacher_route(self, guarded_client, student_token):
        response = guarded_client.get("/teacher-only", headers=bearer(student_token))
        assert response.status_code == 403
        assert response.json()["detail"]["code"] == "forbidden"

    def test_teacher_cannot_access_student_route(self, guarded_client, teacher_token):
        response = guarded_client.get("/student-only", headers=bearer(teacher_token))
        assert response.status_code == 403

    def test_student_cannot_escalate_via_token_metadata(self, guarded_client, make_token, profiles):
        user_id = uuid4()
        profiles.add(user_id, "student")
        token = make_token(user_id, user_metadata={"role": "teacher"})
        response = guarded_client.get("/teacher-only", headers=bearer(token))
        assert response.status_code == 403

    def test_invalid_role_cannot_access_any_role_route(self, guarded_client, make_token, profiles):
        user_id = uuid4()
        profiles.add(user_id, "admin")
        token = make_token(user_id)
        for path in ("/teacher-only", "/student-only", "/any-user"):
            assert guarded_client.get(path, headers=bearer(token)).status_code == 403

    @pytest.mark.parametrize("path", ["/teacher-only", "/student-only", "/any-user"])
    def test_unauthenticated_requests_rejected(self, guarded_client, path):
        assert guarded_client.get(path).status_code == 401

    @pytest.mark.parametrize("path", ["/teacher-only", "/student-only", "/any-user"])
    def test_invalid_token_rejected(self, guarded_client, path):
        assert guarded_client.get(path, headers=bearer("garbage")).status_code == 401
