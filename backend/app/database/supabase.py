from functools import lru_cache

from supabase import Client, create_client

from app.core.config import settings


def _get_required_value(value, setting_name: str) -> str:
    """Return a configured secret or raise a safe configuration error."""
    if value is None:
        raise RuntimeError(f"{setting_name} is not configured.")

    secret = (
        value.get_secret_value()
        if hasattr(value, "get_secret_value")
        else value
    )

    if not secret.strip():
        raise RuntimeError(f"{setting_name} is not configured.")

    return secret


def get_user_supabase(access_token: str) -> Client:
    """Create a Supabase client scoped to the authenticated user."""
    if not access_token or not access_token.strip():
        raise ValueError("A valid user access token is required.")

    url = _get_required_value(settings.SUPABASE_URL, "SUPABASE_URL")
    key = _get_required_value(settings.SUPABASE_KEY, "SUPABASE_KEY")

    client = create_client(url, key)
    client.postgrest.auth(access_token)

    return client


@lru_cache(maxsize=1)
def get_admin_supabase() -> Client:
    """Create a privileged backend-only Supabase client."""
    url = _get_required_value(settings.SUPABASE_URL, "SUPABASE_URL")
    service_key = _get_required_value(
        settings.SUPABASE_SERVICE_ROLE_KEY,
        "SUPABASE_SERVICE_ROLE_KEY",
    )

    return create_client(url, service_key)