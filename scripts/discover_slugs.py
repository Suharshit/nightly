"""Find which candidate companies have a public board on Greenhouse, Lever or Ashby.

Probes data/candidates.txt against all three APIs (1 req/s per host), keeps boards
with at least one India/remote-open job, and writes data/companies.csv plus a report.

Usage: python -m scripts.discover_slugs
"""

import asyncio
import csv
import re
from collections import Counter
from pathlib import Path

from worker.http import PoliteClient
from worker.sources import ashby, greenhouse, lever

ADAPTERS = {"greenhouse": greenhouse, "lever": lever, "ashby": ashby}
ROOT = Path(__file__).resolve().parents[1]


def candidates() -> list[tuple[str, list[str]]]:
    out = []
    for line in (ROOT / "data/candidates.txt").read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        name, _, slugs = line.partition("|")
        base = re.sub(r"[^a-z0-9]", "", name.lower())
        tries = [s.strip() for s in slugs.split(",") if s.strip()] or [base, base + "hq",
                                                                        base + "india"]
        out.append((name.strip(), list(dict.fromkeys(tries))))
    return out


async def probe(client: PoliteClient, ats: str, name: str, slugs: list[str]):
    mod = ADAPTERS[ats]
    for slug in slugs:
        try:
            data = await client.get_json(mod.url(slug))
        except Exception as e:  # noqa: BLE001 - report and move on
            return {"name": name, "ats": ats, "slug": slug, "error": str(e)[:80]}
        if data is None:
            continue
        jobs = mod.parse(data, name)
        ok = [j for j in jobs if j.india_ok]
        cities = Counter(j.city for j in ok if j.city)
        return {"name": name, "ats": ats, "slug": slug, "total": len(jobs), "india": len(ok),
                "city": cities.most_common(1)[0][0] if cities else ("Remote" if ok else "")}
    return None


async def main() -> None:
    cands = candidates()
    async with PoliteClient() as client:
        tasks = [probe(client, ats, name, slugs) for name, slugs in cands for ats in ADAPTERS]
        results = [r for r in await asyncio.gather(*tasks) if r]

    errors = [r for r in results if "error" in r]
    found = [r for r in results if "error" not in r]
    keep = sorted((r for r in found if r["india"] > 0), key=lambda r: -r["india"])
    with open(ROOT / "data/companies.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["name", "ats", "slug", "city"])
        for r in keep:
            w.writerow([r["name"], r["ats"], r["slug"], r["city"]])

    lines = ["| company | ats | slug | jobs | india/remote |", "| --- | --- | --- | --- | --- |"]
    lines += [f"| {r['name']} | {r['ats']} | {r['slug']} | {r['total']} | {r['india']} |"
              for r in sorted(found, key=lambda r: -r["india"])]
    lines += ["", "Errors:"] + [f"- {r['name']} {r['ats']} {r['slug']}: {r['error']}"
                                for r in errors]
    (ROOT / "data/discovery_report.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"candidates={len(cands)} boards_found={len(found)} kept={len(keep)} "
          f"india_jobs={sum(r['india'] for r in keep)} errors={len(errors)}")


if __name__ == "__main__":
    asyncio.run(main())
