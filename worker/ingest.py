"""Nightly ingest: fetch -> normalise -> upsert -> expire -> dedupe -> log.

Idempotent: a second run on the same data inserts 0 rows and changes 0 hashes.
Usage: python -m worker.ingest [--companies data/companies.csv]
"""

import argparse
import asyncio
import csv
import hashlib
import json
import logging
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from worker.db import connect
from worker.http import PoliteClient
from worker.models import JobIn
from worker.sources import ashby, greenhouse, lever

ADAPTERS = {"greenhouse": greenhouse, "lever": lever, "ashby": ashby}
EXPIRE_AFTER = "36 hours"
log = logging.getLogger("ingest")


@dataclass
class Company:
    name: str
    ats: str
    slug: str
    city: str | None
    id: int | None = None


@dataclass
class Stats:
    boards_ok: int = 0
    boards_failed: list[str] = field(default_factory=list)
    fetched: int = 0
    inserted: int = 0
    updated: int = 0
    expired: int = 0
    deduped: int = 0


def content_hash(job: JobIn) -> str:
    return hashlib.sha256(f"{job.title}\n{job.description_text}".encode()).hexdigest()


def norm_title(title: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9+#]+", " ", title.lower())).strip()


def load_companies(path: Path) -> list[Company]:
    with open(path, encoding="utf-8") as f:
        return [Company(r["name"], r["ats"], r["slug"], r.get("city") or None)
                for r in csv.DictReader(f)]


async def fetch_all(companies: list[Company], stats: Stats) -> list[tuple[Company, JobIn]]:
    async with PoliteClient() as client:
        async def one(c: Company):
            mod = ADAPTERS[c.ats]
            try:
                data = await client.get_json(mod.url(c.slug))
            except Exception as e:  # one bad board must not stop the run
                log.warning("fetch failed %s/%s: %s", c.ats, c.slug, e)
                stats.boards_failed.append(f"{c.ats}/{c.slug}")
                return []
            if data is None:
                stats.boards_failed.append(f"{c.ats}/{c.slug} (404)")
                return []
            stats.boards_ok += 1
            return [(c, j) for j in mod.parse(data, c.name) if j.india_ok]

        results = await asyncio.gather(*(one(c) for c in companies))
    return [pair for r in results for pair in r]


def upsert_companies(cur, companies: list[Company]) -> None:
    for c in companies:
        cur.execute(
            """insert into companies (name, ats, slug, city) values (%s, %s, %s, %s)
               on conflict (ats, slug) do update set name = excluded.name, city = excluded.city
               returning id""",
            (c.name, c.ats, c.slug, c.city),
        )
        c.id = cur.fetchone()[0]


UPSERT = """
insert into jobs (company_id, source, external_id, title, location_raw, remote, city, work_mode,
                  description_text, apply_url, posted_at, salary_raw, content_hash, last_seen,
                  is_active)
values (%(company_id)s, %(source)s, %(external_id)s, %(title)s, %(location_raw)s, %(remote)s,
        %(city)s, %(work_mode)s, %(description_text)s, %(apply_url)s, %(posted_at)s,
        %(salary_raw)s, %(content_hash)s, now(), true)
on conflict (source, external_id) do update set
  company_id = excluded.company_id,
  title = excluded.title,
  location_raw = excluded.location_raw,
  remote = excluded.remote,
  city = coalesce(excluded.city, jobs.city),
  work_mode = coalesce(excluded.work_mode, jobs.work_mode),
  description_text = excluded.description_text,
  apply_url = excluded.apply_url,
  posted_at = coalesce(excluded.posted_at, jobs.posted_at),
  salary_raw = excluded.salary_raw,
  last_seen = now(),
  is_active = true,
  -- changed-only work: a new hash queues re-extraction and re-embedding
  extraction_status = case when jobs.content_hash is distinct from excluded.content_hash
                           then 'pending' else jobs.extraction_status end,
  embedding = case when jobs.content_hash is distinct from excluded.content_hash
                   then null else jobs.embedding end,
  content_hash = excluded.content_hash
"""


def upsert_jobs(cur, pairs: list[tuple[Company, JobIn]], stats: Stats) -> None:
    cur.execute("select source, external_id, content_hash from jobs")
    known = {(s, e): h for s, e, h in cur.fetchall()}
    seen: set[tuple[str, str]] = set()
    for c, j in pairs:
        key = (j.source, j.external_id)
        if key in seen:  # same posting listed twice in one board response
            continue
        seen.add(key)
        h = content_hash(j)
        if key not in known:
            stats.inserted += 1
        elif known[key] != h:
            stats.updated += 1
        row = j.model_dump(exclude={"company", "india_ok"})
        cur.execute(UPSERT, {**row, "company_id": c.id, "content_hash": h})
    stats.fetched = len(seen)


def expire(cur, stats: Stats) -> None:
    cur.execute(
        f"update jobs set is_active = false "
        f"where is_active and last_seen < now() - interval '{EXPIRE_AFTER}'"
    )
    stats.expired = cur.rowcount


def dedupe_titles(cur, stats: Stats) -> None:
    """Same company name + same normalised title on different sources -> one canonical row.

    Embedding-based dedupe (cosine > 0.95) runs in embed.py once vectors exist.
    """
    cur.execute(
        """select j.id, lower(c.name), j.source, j.title from jobs j
           join companies c on c.id = j.company_id where j.is_active order by j.id"""
    )
    groups: dict[tuple[str, str], list[tuple[int, str]]] = {}
    for jid, company, source, title in cur.fetchall():
        groups.setdefault((company, norm_title(title)), []).append((jid, source))
    # Recompute from scratch each run (embed.py adds embedding-based duplicates afterwards).
    cur.execute("update jobs set canonical_id = null where canonical_id is not null")
    for rows in groups.values():
        if len({s for _, s in rows}) < 2:
            continue
        canonical = rows[0][0]
        dupes = [jid for jid, _ in rows[1:]]
        cur.execute("update jobs set canonical_id = %s where id = any(%s)", (canonical, dupes))
        stats.deduped += len(dupes)


def run(companies_path: Path) -> Stats:
    started = datetime.now(UTC)
    stats = Stats()
    companies = load_companies(companies_path)
    pairs = asyncio.run(fetch_all(companies, stats))
    with connect() as conn, conn.cursor() as cur:
        upsert_companies(cur, companies)
        upsert_jobs(cur, pairs, stats)
        expire(cur, stats)
        dedupe_titles(cur, stats)
        notes = {"boards_ok": stats.boards_ok, "boards_failed": stats.boards_failed,
                 "deduped": stats.deduped}
        cur.execute(
            """insert into ingest_runs (started_at, finished_at, fetched, inserted, updated,
                                        expired, notes)
               values (%s, now(), %s, %s, %s, %s, %s)""",
            (started, stats.fetched, stats.inserted, stats.updated, stats.expired,
             json.dumps(notes)),
        )
    return stats


def main() -> None:
    logging.basicConfig(level=logging.INFO, format='{"level":"%(levelname)s","msg":"%(message)s"}')
    p = argparse.ArgumentParser()
    p.add_argument("--companies", default=str(Path(__file__).resolve().parents[1]
                                               / "data/companies.csv"))
    s = run(Path(p.parse_args().companies))
    log.info("boards_ok=%d boards_failed=%d fetched=%d inserted=%d updated=%d expired=%d "
             "deduped=%d", s.boards_ok, len(s.boards_failed), s.fetched, s.inserted, s.updated,
             s.expired, s.deduped)


if __name__ == "__main__":
    main()
