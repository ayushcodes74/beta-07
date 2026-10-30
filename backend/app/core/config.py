
from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    APP_NAME: str = "TrustGrade API"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = True

    # Module 1 (auth): Supabase access-token verification.
    # No defaults on purpose: values must come from the Supabase project's
    # confirmed JWT configuration. While unset, protected routes return 503.
    # "jwks" = asymmetric signing keys; "shared_secret" = legacy HS* secret.
    # Kept as str so an empty/invalid value disables auth (503) instead of
    # preventing the whole app from starting.
    SUPABASE_JWT_VERIFICATION_METHOD: str | None = None
    SUPABASE_JWKS_URL: str | None = None
    SUPABASE_JWT_SECRET: SecretStr | None = None
    # Comma-separated allow-list, e.g. "ES256" or "HS256".
    SUPABASE_JWT_ALGORITHMS: str | None = None
    SUPABASE_JWT_ISSUER: str | None = None
    SUPABASE_JWT_AUDIENCE: str | None = None

    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore"
    )


settings = Settings()
