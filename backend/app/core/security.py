"""Verification of Supabase-issued access tokens (Module 1).

The verification method is chosen by configuration, never guessed:

* ``jwks``          - the project's asymmetric signing keys, fetched from the
                      configured JWKS URL (e.g. ES256 / RS256).
* ``shared_secret`` - the project's legacy symmetric JWT secret (HS256/384/512).

Only claims returned by a ``TokenVerifier`` are trusted. Nothing in this module
decodes a token without verifying its signature first.
"""

import logging
from dataclasses import dataclass
from typing import Any, Protocol
from uuid import UUID

import jwt
from jwt.types import Options

from app.core.config import Settings

logger = logging.getLogger(__name__)

# Small tolerance for clock skew between Supabase Auth and this server.
CLOCK_SKEW_LEEWAY_SECONDS = 30

# Claims every accepted access token must carry.
REQUIRED_CLAIMS = ("sub", "exp", "iat", "iss", "aud", "role")

# Supabase puts the Postgres role in the ``role`` claim. Signed-in end users
# carry "authenticated"; anon/service-role keys carry "anon"/"service_role".
# This is NOT the TrustGrade teacher/student role.
END_USER_POSTGRES_ROLE = "authenticated"

ASYMMETRIC_ALGORITHMS = frozenset(
    {"RS256", "RS384", "RS512", "PS256", "PS384", "PS512", "ES256", "ES384", "ES512", "EdDSA"}
)
SYMMETRIC_ALGORITHMS = frozenset({"HS256", "HS384", "HS512"})


class TokenVerificationError(Exception):
    """The token is missing, malformed, expired, forged or otherwise unacceptable.

    The message is for server-side logs only; never return it to clients.
    """


class TokenVerifierNotConfiguredError(Exception):
    """JWT verification settings are missing or invalid."""


class SigningKeyUnavailableError(Exception):
    """The signing keys could not be retrieved (e.g. JWKS endpoint unreachable)."""


@dataclass(frozen=True)
class VerifiedClaims:
    """Identity extracted from a token whose signature and claims were verified."""

    user_id: UUID
    email: str | None
    session_id: str | None


class TokenVerifier(Protocol):
    def verify(self, token: str) -> VerifiedClaims: ...


class SigningKeySource(Protocol):
    """Subset of ``jwt.PyJWKClient`` used here; lets tests supply local keys."""

    def get_signing_key_from_jwt(self, token: str) -> jwt.PyJWK: ...


def _decode_options() -> Options:
    return {
        "require": list(REQUIRED_CLAIMS),
        "verify_signature": True,
        "verify_exp": True,
        "verify_iat": True,
        "verify_nbf": True,
        "verify_iss": True,
        "verify_aud": True,
        "enforce_minimum_key_length": True,
    }


def _claims_to_identity(claims: dict[str, Any]) -> VerifiedClaims:
    if claims.get("role") != END_USER_POSTGRES_ROLE:
        raise TokenVerificationError("token is not an end-user access token")
    # Anonymous sign-ins are not part of TrustGrade's flow.
    if claims.get("is_anonymous") is True:
        raise TokenVerificationError("anonymous sessions are not accepted")

    try:
        user_id = UUID(str(claims["sub"]))
    except (KeyError, ValueError) as exc:
        raise TokenVerificationError("subject claim is not a valid user id") from exc

    email = claims.get("email")
    session_id = claims.get("session_id")
    return VerifiedClaims(
        user_id=user_id,
        email=email if isinstance(email, str) and email else None,
        session_id=session_id if isinstance(session_id, str) else None,
    )


class JwksTokenVerifier:
    """Verifies tokens signed with the project's asymmetric signing keys."""

    def __init__(
        self,
        key_source: SigningKeySource,
        *,
        algorithms: list[str],
        issuer: str,
        audience: str,
    ) -> None:
        if not algorithms or not set(algorithms) <= ASYMMETRIC_ALGORITHMS:
            raise TokenVerifierNotConfiguredError("JWKS verification needs asymmetric algorithms only")
        self._key_source = key_source
        self._algorithms = list(algorithms)
        self._issuer = issuer
        self._audience = audience

    def verify(self, token: str) -> VerifiedClaims:
        try:
            # The PyJWK is bound to its own algorithm, so a token header cannot
            # switch verification to a different (e.g. symmetric) algorithm.
            signing_key = self._key_source.get_signing_key_from_jwt(token)
        except jwt.PyJWKClientConnectionError as exc:
            raise SigningKeyUnavailableError("could not fetch signing keys") from exc
        except (jwt.PyJWKClientError, jwt.PyJWKError, jwt.InvalidTokenError) as exc:
            # Malformed header, unknown kid, unusable key.
            raise TokenVerificationError(type(exc).__name__) from exc

        try:
            claims = jwt.decode(
                token,
                signing_key,
                algorithms=self._algorithms,
                issuer=self._issuer,
                audience=self._audience,
                leeway=CLOCK_SKEW_LEEWAY_SECONDS,
                options=_decode_options(),
            )
        except jwt.InvalidTokenError as exc:
            raise TokenVerificationError(type(exc).__name__) from exc
        return _claims_to_identity(claims)


class SharedSecretTokenVerifier:
    """Verifies tokens signed with the project's legacy symmetric JWT secret."""

    def __init__(self, secret: str, *, algorithms: list[str], issuer: str, audience: str) -> None:
        if not secret:
            raise TokenVerifierNotConfiguredError("shared secret is empty")
        if not algorithms or not set(algorithms) <= SYMMETRIC_ALGORITHMS:
            raise TokenVerifierNotConfiguredError("shared-secret verification needs HS* algorithms only")
        self._secret = secret
        self._algorithms = list(algorithms)
        self._issuer = issuer
        self._audience = audience

    def verify(self, token: str) -> VerifiedClaims:
        try:
            claims = jwt.decode(
                token,
                self._secret,
                algorithms=self._algorithms,
                issuer=self._issuer,
                audience=self._audience,
                leeway=CLOCK_SKEW_LEEWAY_SECONDS,
                options=_decode_options(),
            )
        except jwt.InvalidTokenError as exc:
            raise TokenVerificationError(type(exc).__name__) from exc
        return _claims_to_identity(claims)


def _parse_algorithms(raw: str | None) -> list[str]:
    return [alg.strip() for alg in (raw or "").split(",") if alg.strip()]


def build_token_verifier(settings: Settings) -> TokenVerifier:
    """Build the verifier described by settings, or raise if it is incomplete."""
    method = settings.SUPABASE_JWT_VERIFICATION_METHOD
    algorithms = _parse_algorithms(settings.SUPABASE_JWT_ALGORITHMS)
    issuer = settings.SUPABASE_JWT_ISSUER
    audience = settings.SUPABASE_JWT_AUDIENCE

    missing = [
        name
        for name, value in (
            ("SUPABASE_JWT_VERIFICATION_METHOD", method),
            ("SUPABASE_JWT_ALGORITHMS", algorithms),
            ("SUPABASE_JWT_ISSUER", issuer),
            ("SUPABASE_JWT_AUDIENCE", audience),
        )
        if not value
    ]
    if missing or not issuer or not audience:
        raise TokenVerifierNotConfiguredError(f"missing settings: {', '.join(missing)}")

    if method == "jwks":
        if not settings.SUPABASE_JWKS_URL:
            raise TokenVerifierNotConfiguredError("missing settings: SUPABASE_JWKS_URL")
        key_source = jwt.PyJWKClient(settings.SUPABASE_JWKS_URL, cache_jwk_set=True, lifespan=300, timeout=5)
        return JwksTokenVerifier(key_source, algorithms=algorithms, issuer=issuer, audience=audience)

    if method == "shared_secret":
        if settings.SUPABASE_JWT_SECRET is None:
            raise TokenVerifierNotConfiguredError("missing settings: SUPABASE_JWT_SECRET")
        return SharedSecretTokenVerifier(
            settings.SUPABASE_JWT_SECRET.get_secret_value(),
            algorithms=algorithms,
            issuer=issuer,
            audience=audience,
        )

    raise TokenVerifierNotConfiguredError("unknown verification method")
