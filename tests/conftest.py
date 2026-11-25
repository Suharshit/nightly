"""Shared fakes for API route tests: no models, no Supabase, and a pool that records SQL."""

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from api.app import main
from worker.embed import DIM


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


class FakeAuth:
    USERS = {"good-token": {"id": "00000000-0000-0000-0000-0000000000aa",
                            "email": "student@example.com"}}

    def user(self, token):
        if token not in self.USERS:
            raise HTTPException(401, "Invalid or expired sign-in. Please sign in again.")
        return self.USERS[token]


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
