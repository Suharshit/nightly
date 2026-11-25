"""Ashby public job posting API.

GET https://api.ashbyhq.com/posting-api/job-board/{slug}?includeCompensation=true
Docs: https://developers.ashbyhq.com/docs/public-job-posting-api (verified 25 Nov 2026).
`isRemote` is also true for Hybrid, so use `workplaceType`. Compensation placement
differs between docs and data, so read it defensively.
"""

from datetime import datetime

from worker.models import JobIn
from worker.text import find_city, html_to_text, india_ok

SOURCE = "ashby"
_MODES = {"onsite": "onsite", "remote": "remote", "hybrid": "hybrid"}
_EMPLOYMENT = {"FullTime": "full_time", "PartTime": "part_time", "Intern": "intern",
               "Contract": "contract", "Temporary": "temporary"}


def url(slug: str) -> str:
    return f"https://api.ashbyhq.com/posting-api/job-board/{slug}?includeCompensation=true"


def _salary(j: dict) -> str | None:
    comp = j.get("compensation") or {}
    return comp.get("compensationTierSummary") or comp.get("scrapeableCompensationSalarySummary")


def parse(data: dict, company: str) -> list[JobIn]:
    jobs = []
    for j in data.get("jobs", []):
        if j.get("isListed") is False:
            continue
        loc = j.get("location")
        secondary = [s.get("location") for s in j.get("secondaryLocations") or []]
        locs = [loc, *secondary]
        country = (((j.get("address") or {}).get("postalAddress")) or {}).get("addressCountry")
        mode = _MODES.get((j.get("workplaceType") or "").lower())
        remote = mode == "remote"
        posted = j.get("publishedAt")
        jobs.append(JobIn(
            source=SOURCE,
            external_id=j["id"],
            company=company,
            title=j["title"].strip(),
            location_raw=loc,
            remote=remote,
            work_mode=mode,
            city=next((c for c in map(find_city, locs) if c), None),
            description_text=j.get("descriptionPlain") or html_to_text(j.get("descriptionHtml")),
            apply_url=j.get("jobUrl") or j.get("applyUrl"),
            posted_at=datetime.fromisoformat(posted) if posted else None,
            salary_raw=_salary(j),
            employment_type=_EMPLOYMENT.get(j.get("employmentType") or ""),
            india_ok=india_ok(locs, remote, country),
        ))
    return jobs
