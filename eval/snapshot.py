"""Freeze the active jobs into the `eval` schema, so every search eval runs on the same data.

The index changes every night; labels only make sense against a fixed set of jobs. Search
code uses unqualified table names, so evals just set `search_path = eval, public`.

Usage:
  python -m eval.snapshot            # create it (refuses if it already exists)
  python -m eval.snapshot --info     # show when it was frozen and what it holds
The schema is not exposed through Supabase's Data API (only `public` is).
"""

import argparse
import json
from pathlib import Path

from worker.db import connect

META = Path(__file__).parent / "snapshot.json"

COPY = """
create schema eval;
revoke all on schema eval from public;
do $$ begin
  if exists (select 1 from pg_roles where rolname = 'anon') then
    revoke all on schema eval from anon, authenticated;
  end if;
end $$;
create table eval.companies as select * from public.companies;
create table eval.jobs (like public.jobs including defaults including generated
                        including indexes);
insert into eval.jobs ({cols}) select {cols} from public.jobs where is_active;
create table eval.meta as
  select now() as frozen_at,
         (select count(*) from eval.jobs) as jobs,
         (select count(*) from eval.jobs where canonical_id is null) as canonical,
         (select count(*) from eval.jobs where embedding is not null) as embedded,
         (select count(*) from eval.jobs where extraction_status = 'done') as extracted;
"""


def exists(cur) -> bool:
    cur.execute("select to_regclass('eval.jobs') is not null")
    return cur.fetchone()[0]


def info(cur) -> dict:
    cur.execute("select frozen_at, jobs, canonical, embedded, extracted from eval.meta")
    frozen_at, jobs, canonical, embedded, extracted = cur.fetchone()
    return {"frozen_at": frozen_at.isoformat(timespec="seconds"), "jobs": jobs,
            "canonical": canonical, "embedded": embedded, "extracted": extracted}


def create(cur) -> dict:
    # Every column except the generated tsv (Postgres computes it on insert).
    cur.execute("""select string_agg(quote_ident(column_name), ', ' order by ordinal_position)
                   from information_schema.columns
                   where table_schema = 'public' and table_name = 'jobs'
                     and is_generated = 'NEVER'""")
    cur.execute(COPY.format(cols=cur.fetchone()[0]))
    return info(cur)


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--info", action="store_true")
    a = p.parse_args()
    with connect() as conn, conn.cursor() as cur:
        if a.info or exists(cur):
            if not exists(cur):
                raise SystemExit("No snapshot yet. Run: python -m eval.snapshot")
            print(json.dumps(info(cur)))
            if not a.info:
                print("A snapshot already exists; labels refer to it, so it is never replaced "
                      "here. Drop the eval schema by hand only if you mean to relabel.")
            return
        meta = create(cur)
        conn.commit()
    META.write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(meta))


if __name__ == "__main__":
    main()
