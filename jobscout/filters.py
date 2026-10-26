"""Cheap rule filters that run before any model call.

Eligibility notes: the candidate is authorized to work in the US without
sponsorship but is not a US citizen, so roles needing a security clearance or
US citizenship are dropped. "U.S. person" (ITAR/EAR) wording is NOT dropped:
asylees count as U.S. persons under those rules.
"""

import re

from .models import Job

US_STATES = (
    "AL AK AZ AR CA CO CT DE DC FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN MS MO MT NE NV NH "
    "NJ NM NY NC ND OH OK OR PA RI SC SD TN TX UT VT VA WA WV WI WY"
).split()

US_HINTS = re.compile(
    r"\b(united states|usa|u\.s\.|us|new york|nyc|san francisco|sf|bay area|seattle|boston|austin|"
    r"chicago|denver|atlanta|washington|baltimore|los angeles|remote\s*-?\s*us)\b",
    re.I,
)
STATE_CODE = re.compile(r",\s*(" + "|".join(US_STATES) + r")\b")
NON_US = re.compile(
    r"\b(uk|united kingdom|london|canada|toronto|vancouver|europe|emea|germany|berlin|france|paris|"
    r"ireland|dublin|netherlands|amsterdam|spain|poland|india|bangalore|bengaluru|singapore|japan|"
    r"tokyo|australia|sydney|brazil|mexico|israel|apac|latam|sweden|stockholm|norway|denmark|finland|"
    r"switzerland|zurich|italy|portugal|lisbon|czech|romania|korea|seoul|china|hong kong|taiwan|"
    r"philippines|vietnam|argentina|colombia|chile|south africa|nigeria|kenya|uae|dubai|new zealand|s[aã]o paulo|middle east)\b",
    re.I,
)

INELIGIBLE = [
    re.compile(p, re.I)
    for p in (
        r"security clearance",
        r"\b(active|current|obtain|maintain)\b[^.]{0,40}\bclearance\b",
        r"\b(ts/sci|top secret|secret clearance|polygraph)\b",
        r"\bmust be (a )?u\.?s\.? citizens?\b",
        r"\bu\.?s\.? citizenship (is )?required\b",
        r"\brequires? u\.?s\.? citizenship\b",
        r"\bcitizens? (or|and) (green card holders|permanent residents) only\b",
    )
]


def title_matches(title: str, include: list[str], exclude: list[str]) -> bool:
    t = title.lower()
    return any(k in t for k in include) and not any(k in t for k in exclude)


def location_ok(location: str) -> bool:
    """Remote-in-US or a US location. Unknown or empty locations pass to the scorer."""
    loc = location.strip()
    if not loc:
        return True
    us = bool(US_HINTS.search(loc) or STATE_CODE.search(loc))
    if NON_US.search(loc) and not us:
        return False
    return us or "remote" in loc.lower() or "anywhere" in loc.lower()


def eligibility_problem(description: str) -> str | None:
    """Return the matched phrase if the posting needs clearance or citizenship."""
    for pattern in INELIGIBLE:
        m = pattern.search(description)
        if m:
            return m.group(0)
    return None


def prefilter(jobs: list[Job], include: list[str], exclude: list[str]) -> tuple[list[Job], dict[str, int]]:
    """Keep jobs that pass title, location and eligibility rules; count why others were dropped."""
    kept: list[Job] = []
    dropped = {"title": 0, "location": 0, "eligibility": 0}
    for job in jobs:
        if not title_matches(job.title, include, exclude):
            dropped["title"] += 1
        elif not location_ok(job.location):
            dropped["location"] += 1
        elif eligibility_problem(job.description):
            dropped["eligibility"] += 1
        else:
            kept.append(job)
    return kept, dropped
