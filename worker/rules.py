"""Deterministic extraction: skills, seniority, experience, employment type, salary.

These rules run on every job for free. The LLM pass (extract.py) fills in only what they
leave unknown. Each rule is small and testable so the eval can show what they get right.
"""

import re

from pydantic import BaseModel, Field

SENIORITIES = ("intern", "fresher", "junior", "mid", "senior")


class Extraction(BaseModel):
    skills: list[str] = Field(default_factory=list, max_length=12)
    min_exp_years: int | None = Field(None, ge=0, le=30)
    max_exp_years: int | None = Field(None, ge=0, le=40)
    seniority: str | None = None  # intern | fresher | junior | mid | senior
    employment_type: str | None = None  # full_time | part_time | intern | contract | temporary
    work_mode: str | None = None  # onsite | hybrid | remote
    city: str | None = None
    salary_min_inr: int | None = None
    salary_max_inr: int | None = None


# --- skills -----------------------------------------------------------------------------
# canonical name -> regex (matched case-insensitively unless listed in CASE_SENSITIVE)
SKILLS: dict[str, str] = {
    "python": r"python", "java": r"java(?!\s*script)", "javascript": r"javascript|\bjs\b",
    "typescript": r"typescript", "go": r"golang|\bGo\b(?=[\s,/)]+(?:lang|developer|engineer|"
    r"programming|services|microservices|and|or|,|/))|(?<=[\s,(/])Go(?=\s*[,/)])",
    "rust": r"\brust\b", "c++": r"c\+\+", "c#": r"c#|\.net\b|dotnet", "kotlin": r"kotlin",
    "swift": r"\bswift\b", "scala": r"\bscala\b", "ruby": r"\bruby\b", "rails": r"rails",
    "php": r"\bphp\b", "elixir": r"elixir", "sql": r"\bsql\b", "postgresql": r"postgres",
    "mysql": r"mysql", "mongodb": r"mongo", "redis": r"\bredis\b", "cassandra": r"cassandra",
    "elasticsearch": r"elastic\s*search|opensearch", "kafka": r"kafka", "rabbitmq": r"rabbitmq",
    "spark": r"\bspark\b|pyspark", "hadoop": r"hadoop", "airflow": r"airflow",
    "dbt": r"\bdbt\b", "snowflake": r"snowflake", "bigquery": r"bigquery",
    "databricks": r"databricks", "react": r"\breact(?:\.js|js)?\b(?!\s*native)",
    "react native": r"react\s*native", "next.js": r"next\.?js", "vue": r"\bvue",
    "angular": r"angular", "node.js": r"node\.?js|\bnode\b", "express": r"express\.?js",
    "django": r"django", "flask": r"\bflask\b", "fastapi": r"fastapi",
    "spring boot": r"spring\s*boot|\bspring\b", "graphql": r"graphql",
    "rest api": r"rest(?:ful)?\s*api", "grpc": r"grpc", "microservices": r"micro-?services",
    "html": r"\bhtml", "css": r"\bcss\b|tailwind", "flutter": r"flutter", "android": r"android",
    "ios": r"\bios\b", "aws": r"\baws\b|amazon web services", "gcp": r"\bgcp\b|google cloud",
    "azure": r"azure", "docker": r"docker", "kubernetes": r"kubernetes|\bk8s\b",
    "terraform": r"terraform", "linux": r"linux", "git": r"\bgit\b|github|gitlab",
    "ci/cd": r"ci\s*/\s*cd|jenkins|github actions",
    "machine learning": r"machine learning|\bml\b", "deep learning": r"deep learning",
    "pytorch": r"pytorch", "tensorflow": r"tensorflow", "nlp": r"\bnlp\b|natural language",
    "llm": r"\bllms?\b|large language model|genai|generative ai",
    "computer vision": r"computer vision", "data analysis": r"data analy(?:sis|tics)",
    "pandas": r"pandas", "numpy": r"numpy", "statistics": r"statistic", "excel": r"\bexcel\b",
    "power bi": r"power\s*bi", "tableau": r"tableau", "figma": r"figma",
    "selenium": r"selenium", "testing": r"\bqa\b|test automation|unit test",
    # not bare "security": US boilerplate says "social security" in almost every posting
    "security": r"(?:cyber|information|application|network|cloud|product)\s*security|"
                r"\bsoc\b|\bsiem\b|appsec|infosec", "networking": r"networking|tcp/ip",
    "system design": r"system design|distributed systems", "salesforce": r"salesforce",
    "sap": r"\bsap\b", "seo": r"\bseo\b", "product management": r"product management|roadmap",
    "sales": r"\bsales\b", "marketing": r"marketing", "finance": r"\bfinance\b|accounting",
    "communication": r"communication skills",
}
_CASE_SENSITIVE = {"go"}
_SKILL_RX = {k: re.compile(v, 0 if k in _CASE_SENSITIVE else re.IGNORECASE)
             for k, v in SKILLS.items()}


def find_skills(title: str, text: str, limit: int = 12) -> list[str]:
    """Skills ranked by: in title first, then number of mentions in the description."""
    scored = []
    for name, rx in _SKILL_RX.items():
        in_title = bool(rx.search(title))
        hits = len(rx.findall(text))
        if in_title or hits:
            scored.append((not in_title, -hits, name))
    return [name for *_, name in sorted(scored)[:limit]]


# --- seniority and experience -----------------------------------------------------------
_TITLE_RULES = [
    ("intern", r"\bintern(ship)?\b|\btrainee\b|\bapprentice"),
    ("senior", r"\bsenior\b|\bsr\.?\b|\blead\b|\bstaff\b|\bprincipal\b|\bmanager\b|"
               r"\bdirector\b|\bhead of\b|\bvp\b|\barchitect\b|\b(iii|iv|v)\b|\bl[5-9]\b"),
    ("fresher", r"\bfreshers?\b|\bgraduate\b|\bnew grad\b|\bentry[- ]level\b|\bcampus\b"),
    # Level numerals only count at the end of the title or before a comma/bracket
    # ("Software Engineer I", "SDE 1, Payments"), not mid-title ("Insurance I Exp - 6 to 8").
    ("junior", r"\bjunior\b|\bjr\.?\b|\bassociate\b|\b(?:i|1)\s*(?=$|[,(|])"),
    ("mid", r"\b(?:ii|2)\s*(?=$|[,(|])"),
]
_TITLE_RX = [(s, re.compile(p, re.IGNORECASE)) for s, p in _TITLE_RULES]

_NUM = r"(\d{1,2})"
_RANGE_RX = re.compile(
    rf"{_NUM}\s*\+?\s*(?:-|–|to)\s*{_NUM}\s*\+?\s*(?:years?|yrs?)", re.IGNORECASE)
_MIN_RX = re.compile(rf"{_NUM}\s*\+?\s*(?:years?|yrs?)", re.IGNORECASE)
_EXP_CONTEXT = re.compile(r"experience|exp\b|background|track record|worked", re.IGNORECASE)
_FRESHER_TEXT = re.compile(r"\bfreshers?\b|\b0\s*(?:-|–|to)\s*1\s*years?|no prior experience|"
                           r"recent graduates?|final[- ]year students?", re.IGNORECASE)


def title_seniority(title: str) -> str | None:
    for level, rx in _TITLE_RX:
        if rx.search(title):
            return level
    return None


def experience(text: str) -> tuple[int | None, int | None]:
    """First years-of-experience mention near the word 'experience'. Returns (min, max)."""
    for sentence in re.split(r"(?<=[.!?\n])\s+", text):
        if not _EXP_CONTEXT.search(sentence):
            continue
        m = _RANGE_RX.search(sentence)
        if m:
            lo, hi = int(m.group(1)), int(m.group(2))
            if lo <= hi <= 40:
                return lo, hi
        m = _MIN_RX.search(sentence)
        if m and int(m.group(1)) <= 30:
            return int(m.group(1)), None
    if _FRESHER_TEXT.search(text):
        return 0, 1
    return None, None


_WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
          "eight": 8, "nine": 9, "ten": 10, "zero": 0}
_YEARS_RX = re.compile(r"\b(\d{1,2}|" + "|".join(_WORDS) + r")\s*\+?\s*(?:(?:-|–|to)\s*"
                       r"(\d{1,2})\s*\+?\s*)?(?:\(\d{1,2}\)\s*)?(?:years?|yrs?)",
                       re.IGNORECASE)


def stated_years(text: str) -> set[int]:
    """Every number the posting itself gives as years ("3+ years", "2-4 yrs", "five years"),
    plus 0 and 1 when it says fresher / 0-1 years. Used to check an LLM's years."""
    out: set[int] = set()
    for m in _YEARS_RX.finditer(text):
        a = m.group(1).lower()
        out.add(_WORDS[a] if a in _WORDS else int(a))
        if m.group(2):
            out.add(int(m.group(2)))
    if _FRESHER_TEXT.search(text):
        out |= {0, 1}
    return out


def seniority_from_years(lo: int | None) -> str | None:
    if lo is None:
        return None
    if lo == 0:
        return "fresher"
    if lo <= 2:
        return "junior"
    if lo <= 5:
        return "mid"
    return "senior"


# --- employment type, work mode, salary -------------------------------------------------
def employment_from_title(title: str) -> str | None:
    t = title.lower()
    if re.search(r"\bintern(ship)?\b", t):
        return "intern"
    if re.search(r"\bcontract(or)?\b|\bfreelance", t):
        return "contract"
    if re.search(r"\bpart[- ]time\b", t):
        return "part_time"
    return None


def work_mode_from_text(text: str) -> str | None:
    t = text.lower()
    if re.search(r"\bhybrid\b", t):
        return "hybrid"
    if re.search(r"\b(fully remote|remote[- ]first|work from home|100% remote)\b", t):
        return "remote"
    if re.search(r"\b(on-?site|in-?office|work from office|wfo)\b", t):
        return "onsite"
    return None


_LPA_RX = re.compile(r"(\d+(?:\.\d+)?)\s*(?:-|–|to)\s*(\d+(?:\.\d+)?)\s*(?:lpa|lakhs?|l\b)",
                     re.IGNORECASE)
_INR_RX = re.compile(r"(?:₹|inr|rs\.?)\s*(\d[\d,.]*)\s*([kml]|lakh|lac|cr)?\s*(?:-|–|to)\s*"
                     r"(?:₹|inr|rs\.?)?\s*(\d[\d,.]*)\s*([kml]|lakh|lac|cr)?", re.IGNORECASE)
_MULT = {"k": 1e3, "m": 1e6, "l": 1e5, "lakh": 1e5, "lac": 1e5, "cr": 1e7}


def _amount(num: str, unit: str | None) -> int:
    return int(float(num.replace(",", "")) * _MULT.get((unit or "").lower(), 1))


def salary_inr(*texts: str | None) -> tuple[int | None, int | None]:
    """Yearly INR range from salary_raw or the description. Non-INR salaries stay unknown."""
    for t in texts:
        if not t:
            continue
        m = _LPA_RX.search(t)
        if m:
            return int(float(m.group(1)) * 1e5), int(float(m.group(2)) * 1e5)
        m = _INR_RX.search(t)
        if m:
            lo = _amount(m.group(1), m.group(2))
            hi = _amount(m.group(3), m.group(4) or m.group(2))
            if 50_000 <= lo <= hi <= 50_000_000:  # yearly-looking numbers only
                return lo, hi
    return None, None


# --- combine ---------------------------------------------------------------------------
def rule_extract(title: str, description: str, *, salary_raw: str | None = None,
                 employment_type: str | None = None, work_mode: str | None = None,
                 city: str | None = None) -> Extraction:
    lo, hi = experience(description)
    by_title, by_years = title_seniority(title), seniority_from_years(lo)
    seniority = by_title or by_years
    # A "junior"/"mid" title numeral loses to a clear senior experience ask (e.g. 6+ years).
    if by_title in ("junior", "mid") and by_years == "senior":
        seniority = "senior"
    s_lo, s_hi = salary_inr(salary_raw, description)
    return Extraction(
        skills=find_skills(title, description),
        min_exp_years=lo, max_exp_years=hi,
        seniority=seniority,
        employment_type=employment_type or employment_from_title(title) or "full_time",
        work_mode=work_mode or work_mode_from_text(description),
        city=city,
        salary_min_inr=s_lo, salary_max_inr=s_hi,
    )


def needs_llm(x: Extraction) -> bool:
    """The LLM pass is worth a call only when the rules missed the fields search relies on."""
    return (x.seniority is None
            or (x.min_exp_years is None and x.seniority != "intern")
            or len(x.skills) < 3)
