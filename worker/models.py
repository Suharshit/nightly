"""Normalised job shape shared by every source adapter."""

from datetime import datetime

from pydantic import BaseModel, Field


class JobIn(BaseModel):
    source: str  # greenhouse | lever | ashby
    external_id: str
    company: str
    title: str
    location_raw: str | None = None
    remote: bool = False
    work_mode: str | None = None  # onsite | hybrid | remote, when the source says so
    city: str | None = None  # normalised Indian city, when we can tell
    description_text: str = ""
    apply_url: str | None = None
    posted_at: datetime | None = None
    salary_raw: str | None = None
    india_ok: bool = Field(False, description="located in India, or remote and open to India")
