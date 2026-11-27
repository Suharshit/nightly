"""Shared by the eval scripts: queries, labels, the five search variants, and a DB pool that
reads the frozen snapshot (search_path = eval, public)."""

import json
import os
import random
from pathlib import Path

from api.app.search import pipeline

ROOT = Path(__file__).parent
QUERIES = ROOT / "queries.jsonl"
POOL = ROOT / "pool.jsonl"
LABELS = ROOT / "labels.jsonl"
POOL_DEPTH = 20   # brief: label the pooled top 20 from every variant
EVAL_LIMIT = 30   # the most any variant returns (the reranker sees the fused top 30)

# Each variant adds one stage to the one before, so the table shows what each stage adds.
VARIANTS: dict[str, dict] = {
    "keyword only": {"use_vector": False, "use_rerank": False, "use_final": False},
    "vector only": {"use_keyword": False, "use_rerank": False, "use_final": False},
    "hybrid RRF": {"use_rerank": False, "use_final": False},
    "hybrid + rerank": {"use_final": False},
    # Anonymous queries have no profile, so this stage adds freshness + company diversity.
    # Searches with a query no longer use it (it scored lower); kept to show why.
    "+ freshness & diversity": {"use_fresh": True, "use_diversity": True},
    "as served (query)": {},  # what /matches does for a typed search today
    # Tried 28 Nov and not served: level searches leave out jobs stating no level or years.
    "as served, unknown level hidden": {"hide_unknown_level": True},
}


def load_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()]


def load_queries() -> list[dict]:
    return load_jsonl(QUERIES)


def load_labels() -> dict[str, dict[int, int]]:
    """{qid: {job_id: grade}}; a later line for the same pair overrides an earlier one."""
    out: dict[str, dict[int, int]] = {}
    for row in load_jsonl(LABELS):
        out.setdefault(row["qid"], {})[row["job_id"]] = row["grade"]
    return out


def eval_pool():
    from psycopg_pool import ConnectionPool

    def configure(conn):
        conn.execute("set search_path = eval, public")

    return ConnectionPool(os.environ["DATABASE_URL"], min_size=1, max_size=2, open=True,
                          configure=configure, kwargs={"autocommit": True})


def load_models():
    from api.app.models import Embedder, Reranker
    return Embedder(), Reranker()


def run_variant(pool, embedder, reranker, query: dict, flags: dict,
                limit: int = EVAL_LIMIT) -> list[int]:
    req = pipeline.Request(q=query["q"], level=query.get("level"),
                           cities=query.get("city") or [], remote=bool(query.get("remote")),
                           limit=limit, log_shown=False, **flags)
    return [j["id"] for j in pipeline.run(pool, embedder, reranker, req, None).jobs]


def pooled(per_variant: list[list[int]], qid: str, depth: int = POOL_DEPTH) -> list[int]:
    """Union of each variant's top `depth`, shuffled with a per-query seed so the labeller
    can't tell which variant (or rank) a job came from, and the order is reproducible."""
    ids = sorted({d for ranked in per_variant for d in ranked[:depth]})
    random.Random(qid).shuffle(ids)
    return ids
