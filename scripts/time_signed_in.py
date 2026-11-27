"""Time the signed-in /matches path for a real user, then roll back every write.

Calls the same pipeline.run as GET /matches, with the user's profile (taste, skills,
exclusions, saved prefs), on one connection. Each request is rolled back, so the
'shown' rows it logs are undone and the user's feed is left as it was.

Usage: python scripts/time_signed_in.py [email] [runs_per_case]
  email defaults to the first ADMIN_EMAILS entry.
"""

import os
import statistics
import sys
import time
from contextlib import contextmanager

import psycopg
from dotenv import load_dotenv

from api.app.models import Embedder, Reranker
from api.app.search import pipeline

QUERIES = ["", "python backend fresher", "frontend react intern", "data analyst sql",
           "devops kubernetes", "machine learning engineer", "android developer kotlin"]


class OneConnection:
    """Stands in for the pool: every pool.connection() gets the same open transaction."""

    def __init__(self, conn: psycopg.Connection):
        self.conn = conn

    @contextmanager
    def connection(self):
        yield self.conn


def count_interactions(conn: psycopg.Connection, user_id: str) -> int:
    n = conn.execute("select count(*) from interactions where user_id = %s",
                     (user_id,)).fetchone()[0]
    conn.rollback()
    return n


def pct(xs: list[float], p: float) -> float:
    xs = sorted(xs)
    return xs[max(0, round(p * len(xs)) - 1)]


def main() -> None:
    load_dotenv()
    email = sys.argv[1] if len(sys.argv) > 1 else os.environ["ADMIN_EMAILS"].split(",")[0].strip()
    runs = int(sys.argv[2]) if len(sys.argv) > 2 else 5
    embedder, reranker = Embedder(), Reranker()
    with psycopg.connect(os.environ["DATABASE_URL"], autocommit=False) as conn:
        row = conn.execute("select user_id from profiles where email = %s", (email,)).fetchone()
        conn.rollback()
        if not row:
            sys.exit("No profile for that email: sign in and upload a resume first.")
        user = {"id": str(row[0]), "email": email}
        pool = OneConnection(conn)
        before = count_interactions(conn, user["id"])

        def timed(q: str) -> tuple[float, pipeline.Result]:
            t = time.perf_counter()
            try:
                res = pipeline.run(pool, embedder, reranker, pipeline.Request(q=q, limit=20), user)
            finally:
                conn.rollback()
            return (time.perf_counter() - t) * 1000, res

        timed("warm up")
        by_mode: dict[str, list[float]] = {"feed": [], "query": []}
        for q in QUERIES:
            for i in range(runs):
                ms, res = timed(q)
                by_mode[res.mode].append(ms)
                if i == 0:
                    print(f"# {q or '(feed)'}: {len(res.jobs)} jobs, level={res.level}, "
                          f"first {ms:.0f} ms")
        all_ms = by_mode["feed"] + by_mode["query"]
        for name, xs in (("feed", by_mode["feed"]), ("query", by_mode["query"]),
                         ("all", all_ms)):
            print(f"{name:5}: n={len(xs)} p50={statistics.median(xs):.0f} "
                  f"p95={pct(xs, 0.95):.0f} max={max(xs):.0f} ms")
        after = count_interactions(conn, user["id"])
        print(f"interactions for this user: before {before}, after {after} "
              f"({'unchanged' if before == after else 'CHANGED'})")


if __name__ == "__main__":
    main()
