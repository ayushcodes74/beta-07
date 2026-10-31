from collections import OrderedDict
import threading

import httpx
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
    """Return a Supabase client scoped to the authenticated user (RLS applies as that user)."""
    if not access_token or not access_token.strip():
        raise ValueError("A valid user access token is required.")
    return _user_client(access_token)


# Clients are cached per (thread, access token) and reused. Creating a client per query opened a
# new HTTPS connection each time (~0.5-0.9s to the hosted project), and a single request makes
# several queries. The cache must be per THREAD: supabase-py's synchronous HTTP client is not safe
# to share between threads, and repository calls run concurrently on the asyncio.to_thread pool —
# sharing one client per token produced "[WinError 10035] A non-blocking socket operation could not
# be completed immediately" read errors (503s) when a page fired several requests at once.
# Pool threads are long-lived, so connection reuse is kept. Tokens expire within about an hour, so a
# small per-thread LRU bounds memory.
_PER_THREAD_MAX_CLIENTS = 32
_local = threading.local()

# Errors meaning a reused keep-alive connection was already closed by Supabase/its proxy while idle
# (e.g. "[WinError 10054] An existing connection was forcibly closed by the remote host").
_STALE_CONNECTION_ERRORS = (httpx.ReadError, httpx.RemoteProtocolError, httpx.WriteError)


class _RetryStaleReadsTransport(httpx.BaseTransport):
    """Retry a GET/HEAD once on a fresh connection if a pooled connection turns out to be dead.

    Only reads are retried: repeating a write could apply it twice.
    """

    def __init__(self, inner: httpx.BaseTransport) -> None:
        self._inner = inner

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        try:
            return self._inner.handle_request(request)
        except _STALE_CONNECTION_ERRORS:
            if request.method not in ("GET", "HEAD"):
                raise
            return self._inner.handle_request(request)

    def close(self) -> None:
        self._inner.close()


def _install_read_retry(client: Client) -> None:
    try:
        session = client.postgrest.session
        if not isinstance(session._transport, _RetryStaleReadsTransport):
            session._transport = _RetryStaleReadsTransport(session._transport)
    except AttributeError:  # different supabase-py internals: run without the retry
        pass


def _thread_cache() -> "OrderedDict[str, Client]":
    cache = getattr(_local, "clients", None)
    if cache is None:
        cache = _local.clients = OrderedDict()
    return cache


def _user_client(access_token: str) -> Client:
    cache = _thread_cache()
    client = cache.get(access_token)
    if client is not None:
        cache.move_to_end(access_token)
        return client

    url = _get_required_value(settings.SUPABASE_URL, "SUPABASE_URL")
    key = _get_required_value(settings.SUPABASE_KEY, "SUPABASE_KEY")
    client = create_client(url, key)
    client.postgrest.auth(access_token)
    _install_read_retry(client)

    cache[access_token] = client
    while len(cache) > _PER_THREAD_MAX_CLIENTS:
        cache.popitem(last=False)
    return client


def get_admin_supabase() -> Client:
    """Return the privileged backend-only Supabase client for the current thread."""
    client = getattr(_local, "admin", None)
    if client is None:
        url = _get_required_value(settings.SUPABASE_URL, "SUPABASE_URL")
        service_key = _get_required_value(
            settings.SUPABASE_SERVICE_ROLE_KEY,
            "SUPABASE_SERVICE_ROLE_KEY",
        )
        client = _local.admin = create_client(url, service_key)
        _install_read_retry(client)
    return client
