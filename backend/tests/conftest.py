"""Shared fixtures for Module 1 tests.

Tokens are signed with throwaway keys generated per test session, and the
Supabase JWKS endpoint and profile store are replaced by in-memory fakes. No
production credentials or network access are used.
"""

import sys
import time
from collections.abc import Iterator, Mapping
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.dependencies import get_token_verifier  # noqa: E402
from app.core.security import JwksTokenVerifier  # noqa: E402
from app.main import app  # noqa: E402
from app.services.user_service import ProfileRecord, get_profile_repository  # noqa: E402

TEST_ISSUER = "https://test-project.invalid/auth/v1"
TEST_AUDIENCE = "authenticated"
TEST_KID = "test-signing-key"


class FakeKeySource:
    """Stands in for ``jwt.PyJWKClient`` with an in-memory key set."""

    def __init__(self, keys: dict[str, jwt.PyJWK]) -> None:
        self.keys = keys
        self.unreachable = False

    def get_signing_key_from_jwt(self, token: str) -> jwt.PyJWK:
        if self.unreachable:
            raise jwt.PyJWKClientConnectionError("JWKS endpoint unreachable")
        kid = jwt.get_unverified_header(token).get("kid")
        if kid not in self.keys:
            raise jwt.PyJWKClientError("Unable to find a signing key that matches")
        return self.keys[kid]


class FakeProfileRepository:
    """In-memory profile store that records how it was called."""

    def __init__(self) -> None:
        self.records: dict[UUID, ProfileRecord] = {}
        self.get_calls: list[tuple[UUID, str]] = []
        self.update_calls: list[tuple[UUID, dict[str, Any], str]] = []

    def add(self, user_id: UUID, role: str) -> None:
        self.records[user_id] = ProfileRecord(user_id=user_id, role=role)

    def get_profile(self, user_id: UUID, *, access_token: str) -> ProfileRecord | None:
        self.get_calls.append((user_id, access_token))
        return self.records.get(user_id)

    def update_profile(
        self, user_id: UUID, changes: Mapping[str, Any], *, access_token: str
    ) -> ProfileRecord | None:
        self.update_calls.append((user_id, dict(changes), access_token))
        return self.records.get(user_id)


@pytest.fixture(scope="session")
def signing_key() -> ec.EllipticCurvePrivateKey:
    return ec.generate_private_key(ec.SECP256R1())


@pytest.fixture
def key_source(signing_key: ec.EllipticCurvePrivateKey) -> FakeKeySource:
    jwk = jwt.algorithms.ECAlgorithm.to_jwk(signing_key.public_key(), as_dict=True)
    jwk.update({"kid": TEST_KID, "alg": "ES256", "use": "sig"})
    return FakeKeySource({TEST_KID: jwt.PyJWK(jwk)})


@pytest.fixture
def verifier(key_source: FakeKeySource) -> JwksTokenVerifier:
    return JwksTokenVerifier(key_source, algorithms=["ES256"], issuer=TEST_ISSUER, audience=TEST_AUDIENCE)


def build_claims(user_id: UUID | None = None, **overrides: Any) -> dict[str, Any]:
    now = int(time.time())
    claims: dict[str, Any] = {
        "sub": str(user_id or uuid4()),
        "iss": TEST_ISSUER,
        "aud": TEST_AUDIENCE,
        "iat": now,
        "exp": now + 3600,
        "role": "authenticated",
        "email": "user@example.com",
        "session_id": "test-session",
        "is_anonymous": False,
    }
    claims.update(overrides)
    return {key: value for key, value in claims.items() if value is not None}


@pytest.fixture
def make_token(signing_key: ec.EllipticCurvePrivateKey):
    def _make(user_id: UUID | None = None, *, key: Any = None, kid: str = TEST_KID, **overrides: Any) -> str:
        return jwt.encode(
            build_claims(user_id, **overrides),
            key or signing_key,
            algorithm="ES256",
            headers={"kid": kid},
        )

    return _make


@pytest.fixture
def profiles() -> FakeProfileRepository:
    return FakeProfileRepository()


@pytest.fixture
def client(verifier: JwksTokenVerifier, profiles: FakeProfileRepository) -> Iterator[TestClient]:
    app.dependency_overrides[get_token_verifier] = lambda: verifier
    app.dependency_overrides[get_profile_repository] = lambda: profiles
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}
