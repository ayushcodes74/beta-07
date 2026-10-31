from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    APP_NAME: str = "TrustGrade API"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = True
        # Supabase connection
    SUPABASE_URL: str | None = None
    SUPABASE_KEY: SecretStr | None = None
    SUPABASE_SERVICE_ROLE_KEY: SecretStr | None = None
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

    # Module 5 (OCR Engine Integration): Microservice configuration
    OCR_SERVICE_URL: str = "http://127.0.0.1:8001"
    OCR_CONNECT_TIMEOUT_SECONDS: float = 5.0
    OCR_READ_TIMEOUT_SECONDS: float = 30.0
    OCR_POLL_TIMEOUT_SECONDS: float = 120.0
    OCR_POLL_INTERVAL_SECONDS: float = 1.0
    OCR_API_KEY: SecretStr | None = None

    # AI Engine (ai-engine/app/server.py): internal assignment-generation service.
    # Generation makes one Gemini call plus one per subjective question (rubrics), so reads are slow.
    AI_SERVICE_URL: str = "http://127.0.0.1:8002"
    AI_CONNECT_TIMEOUT_SECONDS: float = 5.0
    AI_READ_TIMEOUT_SECONDS: float = 240.0

    # AI answer-check scoring policy: a question earns full marks once the student covers this share
    # of its key-point marks (score = min(max, raw / GRADING_FULL_MARKS_AT)). 1.0 = no scaling.
    # Applied identically to every submission; the unscaled AI score is kept as raw_awarded_marks.
    GRADING_FULL_MARKS_AT: float = Field(default=0.7, gt=0.0, le=1.0)

    # Teacher review queue thresholds (GET /reviews/queue).
    # OCR: mean text-block confidence below this sends a submission to "OCR review"
    # (matches LOW_OCR_CONFIDENCE in services/plagiarism.py).
    REVIEW_OCR_CONFIDENCE_THRESHOLD: float = Field(default=0.65, ge=0.0, le=1.0)
    # Trust: AI answer-check confidence below this sends a pending grade to "Low trust score"
    # (matches the AI Engine's review_threshold in ai-engine/app/trust/confidence.py).
    REVIEW_TRUST_THRESHOLD: float = Field(default=0.70, ge=0.0, le=1.0)

    # Untaught-but-valid methods (AI answer check). When the AI verifies that a student answered a question
    # correctly with a method the course did not teach, the backend looks the method up on the web (TinyFish
    # Search) so the teacher can see it is a recognised technique, and suggests bonus marks for that question.
    # Only the question text and the method's name are searched for; never the student's answer or identity.
    # Without a key the check still runs; the teacher just sees no web sources.
    TINYFISH_API_KEY: SecretStr | None = None
    TINYFISH_SEARCH_URL: str = "https://api.search.tinyfish.ai"
    TINYFISH_TIMEOUT_SECONDS: float = 12.0
    # Suggested bonus = this share of the question's marks (rounded to 0.5), for an answer scoring at least
    # METHOD_BONUS_MIN_SCORE of the question. Teachers may award up to METHOD_BONUS_MAX_SHARE per question.
    METHOD_BONUS_SUGGESTED_SHARE: float = Field(default=0.2, ge=0.0, le=1.0)
    METHOD_BONUS_MIN_SCORE: float = Field(default=0.9, ge=0.0, le=1.0)
    METHOD_BONUS_MAX_SHARE: float = Field(default=0.5, ge=0.0, le=1.0)

    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore"
    )


settings = Settings()
