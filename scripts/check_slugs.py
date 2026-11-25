"""Re-check data/companies.csv: drop boards that 404 or have zero India/remote jobs.

Usage: python -m scripts.check_slugs [--write]
Without --write it only reports.
"""

import asyncio
import csv
import sys
from pathlib import Path

from worker.http import PoliteClient
from worker.sources import ashby, greenhouse, lever

ADAPTERS = {"greenhouse": greenhouse, "lever": lever, "ashby": ashby}
CSV = Path(__file__).resolve().parents[1] / "data/companies.csv"


async def check(client, row):
    mod = ADAPTERS[row["ats"]]
    data = await client.get_json(mod.url(row["slug"]))
    if data is None:
        return row, "404"
    n = sum(j.india_ok for j in mod.parse(data, row["name"]))
    return row, n


async def main(write: bool) -> None:
    with open(CSV, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    async with PoliteClient() as client:
        results = await asyncio.gather(*(check(client, r) for r in rows))
    keep = [r for r, n in results if isinstance(n, int) and n > 0]
    for r, n in results:
        if not (isinstance(n, int) and n > 0):
            print(f"drop {r['ats']}/{r['slug']}: {n}")
    total = sum(n for _, n in results if isinstance(n, int))
    print(f"boards={len(rows)} kept={len(keep)} india_jobs={total}")
    if write:
        with open(CSV, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=["name", "ats", "slug", "city"])
            w.writeheader()
            w.writerows(keep)


if __name__ == "__main__":
    asyncio.run(main("--write" in sys.argv))
