"""One parser test per ATS adapter, on saved real responses (tests/fixtures)."""

import json
from pathlib import Path

from worker.sources import ashby, greenhouse, lever
from worker.text import html_to_text, india_ok

FIX = Path(__file__).parent / "fixtures"


def load(name):
    return json.loads((FIX / name).read_text(encoding="utf-8"))


def test_greenhouse_parse():
    jobs = greenhouse.parse(load("greenhouse_razorpaysoftwareprivatelimited.json"), "Razorpay")
    assert len(jobs) == 4
    j = jobs[0]
    assert j.source == "greenhouse" and j.external_id.isdigit()
    assert j.city == "Chennai" and j.india_ok
    assert j.posted_at is not None and j.apply_url.startswith("https://")
    # entity-encoded HTML must come out as plain text
    assert "<" not in j.description_text and "&lt;" not in j.description_text
    assert j.description_text.startswith("Razorpay")


def test_lever_parse():
    jobs = lever.parse(load("lever_cred.json"), "CRED")
    assert len(jobs) == 4
    assert all(j.source == "lever" and j.india_ok for j in jobs)
    assert jobs[1].city == "Hyderabad" and jobs[1].work_mode == "onsite"
    assert jobs[0].posted_at.year >= 2024  # createdAt is epoch ms
    assert len(jobs[0].description_text) > 200


def test_ashby_parse_drops_foreign_remote():
    jobs = ashby.parse(load("ashby_ashby.json"), "Ashby")
    assert len(jobs) == 6
    assert jobs[0].work_mode == "remote" and jobs[0].remote
    assert jobs[0].salary_raw and "€" in jobs[0].salary_raw
    # Ashby's own board is EU/US/UK only, so none of it is open to India
    assert not any(j.india_ok for j in jobs)


def test_india_rules():
    assert india_ok(["Bangalore, Karnataka"], remote=False)
    assert india_ok(["Remote"], remote=True)
    assert india_ok(["Remote - APAC"], remote=True)
    assert not india_ok(["Remote - US"], remote=True)
    assert not india_ok(["San Francisco"], remote=False)
    assert india_ok(["Anywhere"], remote=False, country="IN")


def test_html_to_text():
    assert html_to_text("&lt;p&gt;Hello &amp;amp; bye&lt;/p&gt;&lt;ul&gt;&lt;li&gt;Go&lt;/li&gt;") \
        == "Hello & bye\nGo"
