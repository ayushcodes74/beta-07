"""Supabase client caching: reused within a thread, never shared across threads.

Sharing one supabase-py client between asyncio.to_thread workers caused concurrent socket reads
("[WinError 10035] A non-blocking socket operation could not be completed immediately").
"""

import threading

import httpx

import pytest

from app.database import supabase as sb


class FakeClient:
    def __init__(self):
        self.tokens = []
        self.postgrest = self

    def auth(self, token):
        self.tokens.append(token)


@pytest.fixture(autouse=True)
def fake_create(monkeypatch):
    created = []

    def create_client(url, key):
        client = FakeClient()
        created.append(client)
        return client

    monkeypatch.setattr(sb, "create_client", create_client)
    monkeypatch.setattr(sb, "_get_required_value", lambda value, name: "x")
    # Fresh per-thread state for each test
    monkeypatch.setattr(sb, "_local", threading.local())
    return created


def test_reused_within_a_thread_per_token(fake_create):
    a1 = sb.get_user_supabase("token-a")
    a2 = sb.get_user_supabase("token-a")
    b = sb.get_user_supabase("token-b")
    assert a1 is a2 and a1 is not b
    assert a1.tokens == ["token-a"] and b.tokens == ["token-b"]
    assert sb.get_admin_supabase() is sb.get_admin_supabase()


def test_not_shared_between_threads(fake_create):
    clients = {}

    def worker(name):
        clients[name] = (sb.get_user_supabase("same-token"), sb.get_admin_supabase())

    threads = [threading.Thread(target=worker, args=(n,)) for n in ("t1", "t2")]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert clients["t1"][0] is not clients["t2"][0]
    assert clients["t1"][1] is not clients["t2"][1]


def test_per_thread_cache_is_bounded(fake_create):
    for i in range(sb._PER_THREAD_MAX_CLIENTS + 5):
        sb.get_user_supabase(f"token-{i}")
    assert len(sb._thread_cache()) == sb._PER_THREAD_MAX_CLIENTS


def test_blank_token_rejected():
    with pytest.raises(ValueError):
        sb.get_user_supabase("  ")


class FlakyTransport(httpx.BaseTransport):
    """First request fails like a keep-alive connection Supabase already closed; later ones succeed."""

    def __init__(self):
        self.calls = 0

    def handle_request(self, request):
        self.calls += 1
        if self.calls == 1:
            raise httpx.ReadError("[WinError 10054] An existing connection was forcibly closed by the remote host")
        return httpx.Response(200, json=[{"ok": True}])


def test_stale_connection_get_is_retried_once():
    inner = FlakyTransport()
    with httpx.Client(transport=sb._RetryStaleReadsTransport(inner), base_url="http://x") as client:
        assert client.get("/rest/v1/courses").json() == [{"ok": True}]
    assert inner.calls == 2


def test_writes_are_not_retried():
    inner = FlakyTransport()
    with httpx.Client(transport=sb._RetryStaleReadsTransport(inner), base_url="http://x") as client:
        with pytest.raises(httpx.ReadError):
            client.post("/rest/v1/submissions", json={"id": 1})
    assert inner.calls == 1


def test_retry_installed_on_real_supabase_client(monkeypatch):
    from supabase import create_client as real_create

    monkeypatch.setattr(sb, "create_client", real_create)
    monkeypatch.setattr(sb, "_get_required_value", lambda value, name: (
        "https://example.supabase.co" if name == "SUPABASE_URL" else "anon-key"
    ))
    client = sb.get_user_supabase("token-a")
    assert isinstance(client.postgrest.session._transport, sb._RetryStaleReadsTransport)
