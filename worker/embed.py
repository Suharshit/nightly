"""Embed active jobs with bge-small (CPU), then mark near-duplicate postings.

Resumable: it only embeds rows with embedding IS NULL (ingest clears the vector when a
job's content changes) and commits after every batch.

Usage:
  python -m worker.embed                 # embed everything pending, then dedupe
  python -m worker.embed --limit 200     # a quick partial run
"""

import argparse
import json
import logging
import os
import time

from worker.db import connect

log = logging.getLogger("embed")

DIM = 384
DESC_CHARS = 800
# Brief: near-identical postings (cosine > 0.95) of one company across sources share a
# canonical row. pgvector's <=> is cosine distance, i.e. 1 - cosine.
DUP_DISTANCE = 0.05


def doc_text(title: str, company: str | None, city: str | None, work_mode: str | None,
             skills: list[str] | None, description: str | None) -> str:
    """title | company | city | work_mode | skills | first 800 chars of description."""
    parts = [title, company, city, work_mode, ", ".join(skills or []),
             " ".join((description or "").split())[:DESC_CHARS]]
    return " | ".join(p.strip() for p in parts if p and p.strip())


def to_pgvector(vec) -> str:
    """A pgvector text literal, so no adapter has to be registered on the connection."""
    if len(vec) != DIM:
        raise ValueError(f"expected {DIM} dims, got {len(vec)}")
    return "[" + ",".join(f"{float(x):.6f}" for x in vec) + "]"


def load_model():
    # Imported here so the rest of the worker (and CI) doesn't need torch.
    from sentence_transformers import SentenceTransformer
    return SentenceTransformer(os.getenv("EMBED_MODEL", "BAAI/bge-small-en-v1.5"), device="cpu")


PENDING = """
select j.id, j.title, c.name, j.city, j.work_mode, j.skills, j.description_text
from jobs j join companies c on c.id = j.company_id
where j.embedding is null and j.is_active
order by j.id limit %s
"""

# One pass for the whole table: cheap at a few thousand rows, and it has to be recomputed
# after every ingest because ingest's title dedupe resets canonical_id first.
DEDUPE = """
with pairs as (
  select d.id as dup, min(c.id) as canon
  from jobs d
  join companies dc on dc.id = d.company_id
  join jobs c on c.id < d.id and c.source <> d.source
  join companies cc on cc.id = c.company_id and lower(cc.name) = lower(dc.name)
  where d.is_active and c.is_active
    and d.canonical_id is null and c.canonical_id is null
    and d.embedding is not null and c.embedding is not null
    and (c.embedding <=> d.embedding) < %s
  group by d.id
)
update jobs set canonical_id = pairs.canon from pairs where jobs.id = pairs.dup
"""

# A -> B -> C chains (A~B and B~C but not A~C): point everything at the root.
FLATTEN = """
update jobs d set canonical_id = p.canonical_id
from jobs p where d.canonical_id = p.id and p.canonical_id is not null
"""


def dedupe(cur) -> int:
    cur.execute(DEDUPE, (DUP_DISTANCE,))
    marked = cur.rowcount
    cur.execute(FLATTEN)
    return marked


def run(limit: int | None, batch: int) -> dict:
    stats = {"embedded": 0, "deduped": 0}
    with connect() as conn, conn.cursor() as cur:
        cur.execute(PENDING, (limit,))
        rows = cur.fetchall()
        if rows:
            model = load_model()
            started = time.monotonic()
            for start in range(0, len(rows), batch):
                chunk = rows[start:start + batch]
                texts = [doc_text(*r[1:]) for r in chunk]
                # bge v1.5: documents get no instruction prefix; only queries do.
                vecs = model.encode(texts, batch_size=batch, normalize_embeddings=True,
                                 show_progress_bar=False)
                cur.executemany("update jobs set embedding = %s::vector where id = %s",
                                [(to_pgvector(v), r[0]) for r, v in zip(chunk, vecs, strict=True)])
                conn.commit()
                stats["embedded"] += len(chunk)
                log.info("progress %d/%d (%.1f jobs/s)", stats["embedded"], len(rows),
                         stats["embedded"] / (time.monotonic() - started))
            stats["seconds"] = round(time.monotonic() - started, 1)
        stats["deduped"] = dedupe(cur)
        cur.execute("select count(*) filter (where embedding is not null), count(*) "
                    "from jobs where is_active")
        stats["active_embedded"], stats["active"] = cur.fetchone()
    return stats


def main() -> None:
    logging.basicConfig(level=logging.INFO,
                        format='{"level":"%(levelname)s","msg":"%(message)s"}')
    p = argparse.ArgumentParser()
    p.add_argument("--limit", type=int)
    p.add_argument("--batch", type=int, default=64)
    a = p.parse_args()
    log.info(json.dumps(run(a.limit, a.batch)))


if __name__ == "__main__":
    main()
