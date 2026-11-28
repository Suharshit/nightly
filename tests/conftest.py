"""Shared fakes for API route tests: no models, no Supabase, and a pool that records SQL."""

import os
from pathlib import Path
from urllib.parse import urlparse

import pytest
from dotenv import dotenv_values
from fastapi import HTTPException
from fastapi.testclient import TestClient

from api.app import main
from api.app import profile as prof
from worker.embed import DIM

# Tests never touch the live database. In .env, DATABASE_URL is Supabase and DATABASE_URL_LOCAL
# is the local Docker Postgres, so the whole run uses the local one. CI sets DATABASE_URL to a
# local service and has no DATABASE_URL_LOCAL. Assigning here wins over worker/db.py's
# load_dotenv, which never overrides a variable that is already set.
_local = (os.environ.get("DATABASE_URL_LOCAL")
          or dotenv_values(Path(__file__).resolve().parents[1] / ".env").get("DATABASE_URL_LOCAL"))
if _local:
    os.environ["DATABASE_URL"] = _local
LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1", "db"}


def pytest_configure(config):
    url = os.environ.get("DATABASE_URL")
    if url and urlparse(url).hostname not in LOCAL_HOSTS:
        raise pytest.UsageError(
            "DATABASE_URL points at a non-local database; set DATABASE_URL_LOCAL for tests.")


@pytest.fixture(autouse=True)
def _empty_profile_cache():
    """The profile cache and rate counters are process-wide; tests must not share them."""
    from api.app import limits
    prof._profiles.clear()
    limits._hits.clear()
    yield
    prof._profiles.clear()
    limits._hits.clear()


class FakeEmbedder:
    def __init__(self):
        self.texts: list[str] = []

    def query(self, text):
        self.texts.append(text)
        return [0.0] * DIM


class FakeReranker:
    """Scores a job by how many query words its text contains (as a logit)."""

    def __init__(self):
        self.calls: list[tuple[str, list[str]]] = []

    def score(self, query, texts):
        self.calls.append((query, texts))
        words = query.lower().split()
        return [float(sum(w in t.lower() for w in words)) - 1.0 for t in texts]


class FakeCursor:
    def __init__(self, pool):
        self.pool = pool

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def execute(self, sql, params=None):
        self.pool.executed.append((sql, params))

    def fetchone(self):
        return self.pool.fetchone


class FakePool:
    def __init__(self):
        self.executed: list[tuple] = []
        self.fetchone = None

    def connection(self):
        return FakeCursor(self)  # a connection and a cursor behave the same here

    def close(self):
        pass


FakeCursor.cursor = lambda self: self
FakeCursor.transaction = lambda self: self  # the cursor is also a no-op context manager


class FakeAuth:
    USERS = {"good-token": {"id": "00000000-0000-0000-0000-0000000000aa",
                            "email": "student@example.com"}}

    def __init__(self):
        self.forgotten: list[str] = []

    def user(self, token):
        if token not in self.USERS:
            raise HTTPException(401, "Invalid or expired sign-in. Please sign in again.")
        return self.USERS[token]

    def forget(self, user_id):
        self.forgotten.append(user_id)


@pytest.fixture
def api():
    """A TestClient wired to fakes; yields (client, pool, embedder)."""
    pool, embedder = FakePool(), FakeEmbedder()
    main.app.state.pool, main.app.state.embedder, main.app.state.auth = (
        pool, embedder, FakeAuth())
    main.app.state.reranker = FakeReranker()
    with TestClient(main.app) as c:
        yield c, pool, embedder
    del main.app.state.pool, main.app.state.embedder, main.app.state.auth
    del main.app.state.reranker
