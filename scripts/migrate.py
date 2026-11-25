"""Apply db/migrations/*.sql in order, once each, recording them in schema_migrations.

Usage:
  python -m scripts.migrate             # apply new migrations to DATABASE_URL
  python -m scripts.migrate --baseline  # mark all as applied (a DB created by docker initdb)
Never applies db/local/ (the auth stub is local-only).
"""

import sys
from pathlib import Path

from worker.db import connect

MIGRATIONS = Path(__file__).resolve().parents[1] / "db/migrations"


def main(baseline: bool) -> None:
    files = sorted(MIGRATIONS.glob("*.sql"))
    with connect() as conn, conn.cursor() as cur:
        cur.execute("create table if not exists schema_migrations "
                    "(name text primary key, applied_at timestamptz default now())")
        cur.execute("select name from schema_migrations")
        done = {r[0] for r in cur.fetchall()}
        for f in files:
            if f.name in done:
                continue
            if not baseline:
                print(f"applying {f.name}")
                cur.execute(f.read_text(encoding="utf-8"))
            cur.execute("insert into schema_migrations (name) values (%s)", (f.name,))
        conn.commit()
    print(f"up to date: {len(files)} migrations")


if __name__ == "__main__":
    main("--baseline" in sys.argv)
