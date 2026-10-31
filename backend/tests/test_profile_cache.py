"""Short-lived profile cache in SupabaseProfileRepository: one profiles query per (user, token) per TTL."""

from uuid import uuid4

import pytest

from app.services import user_service as us

USER = uuid4()
ROW = {"id": str(USER), "role": "teacher", "is_disabled": False, "display_name": "Ada"}


class FakeQuery:
    def __init__(self, log, data):
        self.log, self.data = log, data

    def __getattr__(self, name):  # select / eq / update chain back to the query
        return lambda *a, **k: self

    def execute(self):
        self.log.append("query")
        return type("Resp", (), {"data": [dict(self.data)]})()


@pytest.fixture
def queries(monkeypatch):
    log = []
    monkeypatch.setattr(us, "get_user_supabase", lambda token: type("C", (), {"table": lambda self, name: FakeQuery(log, ROW)})())
    us.invalidate_profile_cache()
    yield log
    us.invalidate_profile_cache()


def test_second_lookup_with_same_token_is_cached(queries):
    repo = us.SupabaseProfileRepository()
    assert repo.get_profile(USER, access_token="t1").role == "teacher"
    assert repo.get_profile(USER, access_token="t1").display_name == "Ada"
    assert queries == ["query"]


def test_new_token_is_not_served_from_cache(queries):
    repo = us.SupabaseProfileRepository()
    repo.get_profile(USER, access_token="t1")
    repo.get_profile(USER, access_token="t2")
    assert queries == ["query", "query"]


def test_profile_update_drops_cached_entries(queries):
    repo = us.SupabaseProfileRepository()
    repo.get_profile(USER, access_token="t1")
    repo.update_profile(USER, {"display_name": "Ada L."}, access_token="t1")
    repo.get_profile(USER, access_token="t1")
    assert queries == ["query", "query", "query"]  # lookup, update, fresh lookup


def test_entries_expire(queries, monkeypatch):
    repo = us.SupabaseProfileRepository()
    repo.get_profile(USER, access_token="t1")
    now = us.time.monotonic()
    monkeypatch.setattr(us.time, "monotonic", lambda: now + us.PROFILE_CACHE_TTL_SECONDS + 1)
    repo.get_profile(USER, access_token="t1")
    assert queries == ["query", "query"]
