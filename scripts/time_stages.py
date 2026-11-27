"""Where /matches spends its time, per stage, against a running API (anonymous searches).

Prints p50/p95 for each pipeline stage the server reports (embed, search, rerank,
personalise), the server total, the client's wall-clock time, and the server's own database
round trip from /health. Wall minus server total is the network between here and the API.

Usage: python scripts/time_stages.py [base_url] [runs_per_query] [key=value ...]
  e.g. python scripts/time_stages.py https://suharshit-nightly-api.hf.space 3
"""

import statistics
import sys
import time

import httpx

QUERIES = ["python backend fresher", "frontend react intern", "data analyst sql",
           "devops kubernetes", "machine learning engineer", "android developer kotlin"]


def pct(xs: list[float], p: float) -> float:
    xs = sorted(xs)
    return xs[max(0, round(p * len(xs)) - 1)]


def main() -> None:
    base = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000"
    runs = int(sys.argv[2]) if len(sys.argv) > 2 else 3
    extra = dict(a.split("=", 1) for a in sys.argv[3:])
    stages: dict[str, list[float]] = {}
    wall, total, db = [], [], []
    with httpx.Client(base_url=base, timeout=120, headers={"User-Agent": "nightly-timing"}) as c:
        c.get("/matches", params={"q": "warm up", "limit": 5} | extra)
        for _ in range(5):
            db.append(c.get("/health").json()["db_ms"])
        for q in QUERIES:
            for _ in range(runs):
                t = time.perf_counter()
                r = c.get("/matches", params={"q": q, "limit": 5} | extra)
                wall.append((time.perf_counter() - t) * 1000)
                r.raise_for_status()
                body = r.json()
                total.append(body["took_ms"])
                for name, ms in body["timings"].items():
                    stages.setdefault(name, []).append(ms)
    rows = [(name, xs) for name, xs in stages.items()]
    rows += [("server total", total), ("client wall", wall),
             ("network (wall - total)", [w - s for w, s in zip(wall, total, strict=True)]),
             ("db round trip (/health)", db)]
    print(f"{base}, {len(wall)} searches ({len(QUERIES)} queries x {runs})")
    print(f"{'stage':26} {'p50 ms':>8} {'p95 ms':>8} {'max ms':>8}")
    for name, xs in rows:
        print(f"{name:26} {statistics.median(xs):8.0f} {pct(xs, 0.95):8.0f} {max(xs):8.0f}")


if __name__ == "__main__":
    main()
