"""Lever Postings API.

GET https://api.lever.co/v0/postings/{slug}?mode=json
Docs: https://github.com/lever/postings-api (verified 25 Nov 2026).
`createdAt` is epoch milliseconds (live data; not in the docs table).
`workplaceType` is on-site | remote | hybrid | unspecified (live data also shows "onsite").
"""

from datetime import UTC, datetime

from worker.models import JobIn
from worker.text import find_city, html_to_text, india_ok

SOURCE = "lever"
_MODES = {"on-site": "onsite", "onsite": "onsite", "remote": "remote", "hybrid": "hybrid"}
_COMMITMENT = {"full time": "full_time", "full-time": "full_time", "fulltime": "full_time",
               "permanent": "full_time", "part time": "part_time", "part-time": "part_time",
               "intern": "intern", "internship": "intern", "contract": "contract",
               "contractor": "contract", "temporary": "temporary", "fixed term": "contract"}


def url(slug: str) -> str:
    return f"https://api.lever.co/v0/postings/{slug}?mode=json"


def _salary(p: dict) -> str | None:
    s = p.get("salaryRange")
    if s and (s.get("min") or s.get("max")):
        cur, interval = s.get("currency", ""), s.get("interval", "")
        return f"{cur} {s.get('min')}-{s.get('max')} {interval}".strip()
    return p.get("salaryDescriptionPlain") or None


def parse(data: list, company: str) -> list[JobIn]:
    jobs = []
    for p in data:
        cats = p.get("categories") or {}
        loc = cats.get("location")
        locs = [loc, *(cats.get("allLocations") or [])]
        mode = _MODES.get((p.get("workplaceType") or "").lower())
        remote = mode == "remote" or any(x and "remote" in x.lower() for x in locs)
        parts = [p.get("openingPlain"), p.get("descriptionBodyPlain") or p.get("descriptionPlain")]
        for lst in p.get("lists") or []:
            parts.append(f"{lst.get('text', '')}\n{html_to_text(lst.get('content'))}")
        parts.append(p.get("additionalPlain"))
        created = p.get("createdAt")
        jobs.append(JobIn(
            source=SOURCE,
            external_id=p["id"],
            company=company,
            title=p["text"].strip(),
            location_raw=loc,
            remote=remote,
            work_mode="remote" if remote else mode,
            city=next((c for c in map(find_city, locs) if c), None),
            description_text="\n".join(x.strip() for x in parts if x and x.strip()),
            apply_url=p.get("hostedUrl") or p.get("applyUrl"),
            posted_at=datetime.fromtimestamp(created / 1000, tz=UTC) if created else None,
            salary_raw=_salary(p),
            employment_type=_COMMITMENT.get((cats.get("commitment") or "").strip().lower()),
            india_ok=india_ok(locs, remote, p.get("country")),
        ))
    return jobs
