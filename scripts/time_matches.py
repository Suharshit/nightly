"""Time /matches end to end against a running API. Prints p50/p95 and the top results.

Usage: python scripts/time_matches.py [base_url] [runs_per_query]
"""

import statistics
import sys
import time

import httpx

QUERIES = ["python backend fresher", "frontend react intern", "data analyst sql",
           "devops kubernetes", "machine learning engineer", "android developer kotlin"]


def main() -> None:
    base = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000"
    runs = int(sys.argv[2]) if len(sys.argv) > 2 else 5
    with httpx.Client(base_url=base, timeout=60) as c:
        for _ in range(60):  # wait for startup (the model loads first)
            try:
                c.get("/health").raise_for_status()
                break
            except httpx.HTTPError:
                time.sleep(1)
        c.get("/matches", params={"q": "warm up"})
        wall: list[float] = []
        server: list[int] = []
        for q in QUERIES:
            for i in range(runs):
                t = time.perf_counter()
                r = c.get("/matches", params={"q": q, "limit": 5})
                wall.append((time.perf_counter() - t) * 1000)
                r.raise_for_status()
                body = r.json()
                server.append(body["took_ms"])
                if i == 0:
                    print(f"\n# {q}  (level={body['level']}, {body['count']} results)")
                    for j in body["jobs"]:
                        print(f"  {j['title'][:55]:55} | {j['company'][:16]:16} | "
                              f"{j['seniority'] or '-':7} | {j['city'] or '-'} "
                              f"[kw {j['keyword_rank']}, vec {j['vector_rank']}]")
    for name, xs in (("wall ms", wall), ("server ms", server)):
        xs = sorted(xs)
        p95 = xs[max(0, round(0.95 * len(xs)) - 1)]
        print(f"\n{name}: n={len(xs)} p50={statistics.median(xs):.0f} p95={p95:.0f} "
              f"max={xs[-1]:.0f}")


if __name__ == "__main__":
    main()
