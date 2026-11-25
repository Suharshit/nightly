"""Greenhouse Job Board API.

GET https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true
Docs: https://docs.greenhouse.io/job-board.html (verified 25 Nov 2026).
One call returns every job; `content` is entity-encoded HTML.
"""

from datetime import datetime

from worker.models import JobIn
from worker.text import find_city, html_to_text, india_ok

SOURCE = "greenhouse"


def url(slug: str) -> str:
    return f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true"


def parse(data: dict, company: str) -> list[JobIn]:
    jobs = []
    for j in data.get("jobs", []):
        loc = (j.get("location") or {}).get("name")
        offices = [o.get("name") for o in j.get("offices") or []]
        locs = [loc, *offices]
        remote = any(x and "remote" in x.lower() for x in locs)
        posted = j.get("first_published") or j.get("updated_at")
        city = find_city(loc) or next((c for c in map(find_city, offices) if c), None)
        jobs.append(JobIn(
            source=SOURCE,
            external_id=str(j["id"]),
            company=company,
            title=j["title"].strip(),
            location_raw=loc,
            remote=remote,
            work_mode="remote" if remote else None,
            city=city,
            description_text=html_to_text(j.get("content")),
            apply_url=j.get("absolute_url"),
            posted_at=datetime.fromisoformat(posted) if posted else None,
            india_ok=india_ok(locs, remote),
        ))
    return jobs
