"""Normalised job shape shared by every source adapter."""

from datetime import datetime

from pydantic import BaseModel, Field, field_validator


class JobIn(BaseModel):
    @field_validator("*", mode="before")
    @classmethod
    def _no_nul(cls, v):
        # Postgres text cannot hold NUL bytes; some boards contain them.
        return v.replace("\x00", "") if isinstance(v, str) else v

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
    employment_type: str | None = None  # full_time | part_time | intern | contract | temporary
    india_ok: bool = Field(False, description="located in India, or remote and open to India")
