"""Rerank the fused candidates with a cross-encoder that reads query and job together.

RRF only knows ranks; the cross-encoder judges each (query, job) pair directly, which is
what pushes e.g. a Product Management intern below a frontend intern for "frontend react
intern". Scores are logits, squashed to 0..1 (rerank_norm) for the personalisation step.
"""

import math

# Measured on the laptop CPU, 30 pairs: 256 tokens / 400 chars took 714 ms; 128 / 200 took
# 448 ms with the same top 5 on a sample query. The eval checks this properly.
JOB_CHARS = 200
MAX_TOKENS = 128


def job_text(job: dict) -> str:
    place = job.get("city") or ("remote" if job.get("remote") else None)
    parts = [job["title"], job.get("company"), place, job.get("work_mode"),
             ", ".join(job.get("skills") or []),
             " ".join((job.get("snippet") or "").split())[:JOB_CHARS]]
    return " | ".join(p for p in parts if p)


def sigmoid(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-x))


def rerank(reranker, q: str, jobs: list[dict]) -> list[dict]:
    """Best first by cross-encoder score; ties keep the fused order."""
    if not jobs:
        return []
    scores = reranker.score(q, [job_text(j) for j in jobs])
    out = [j | {"rerank_score": round(sigmoid(s), 5)}
           for j, s in zip(jobs, scores, strict=True)]
    return sorted(out, key=lambda j: -j["rerank_score"])
