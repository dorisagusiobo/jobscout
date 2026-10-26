"""Fetch postings from public job-board APIs (no keys needed) and normalize them."""

import html
import logging
import re
from datetime import datetime, timezone

import httpx

from .models import Job

log = logging.getLogger(__name__)

GREENHOUSE = "https://boards-api.greenhouse.io/v1/boards/{token}/jobs?content=true"
LEVER = "https://api.lever.co/v0/postings/{token}?mode=json"
ASHBY = "https://api.ashbyhq.com/posting-api/job-board/{token}"


def html_to_text(raw: str) -> str:
    text = html.unescape(raw or "")  # Greenhouse double-escapes its HTML
    text = re.sub(r"<(br|/p|/li|/h\d)[^>]*>", "\n", text, flags=re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    text = html.unescape(text)
    lines = (re.sub(r"[ \t]+", " ", line).strip() for line in text.splitlines())
    return "\n".join(line for line in lines if line)


def parse_greenhouse(company: str, token: str, data: dict) -> list[Job]:
    return [
        Job(
            id=f"greenhouse:{token}:{j['id']}",
            source="greenhouse",
            company=company,
            title=j["title"].strip(),
            location=(j.get("location") or {}).get("name", ""),
            url=j["absolute_url"],
            description=html_to_text(j.get("content", "")),
            posted_at=j.get("first_published") or j.get("updated_at"),
        )
        for j in data.get("jobs", [])
    ]


def parse_lever(company: str, token: str, data: list) -> list[Job]:
    jobs = []
    for j in data:
        lists = "\n".join(
            f"{section.get('text', '')}\n{html_to_text(section.get('content', ''))}"
            for section in j.get("lists", [])
        )
        created = j.get("createdAt")
        jobs.append(
            Job(
                id=f"lever:{token}:{j['id']}",
                source="lever",
                company=company,
                title=j["text"].strip(),
                location=(j.get("categories") or {}).get("location", "") or "",
                url=j["hostedUrl"],
                description=f"{j.get('descriptionPlain', '')}\n{lists}".strip(),
                posted_at=(
                    datetime.fromtimestamp(created / 1000, timezone.utc).isoformat()
                    if created
                    else None
                ),
            )
        )
    return jobs


def parse_ashby(company: str, token: str, data: dict) -> list[Job]:
    jobs = []
    for j in data.get("jobs", []):
        location = j.get("location", "") or ""
        if j.get("isRemote") and "remote" not in location.lower():
            location = f"{location} (Remote)".strip()
        jobs.append(
            Job(
                id=f"ashby:{token}:{j['id']}",
                source="ashby",
                company=company,
                title=j["title"].strip(),
                location=location,
                url=j.get("jobUrl") or j.get("applyUrl", ""),
                description=j.get("descriptionPlain") or html_to_text(j.get("descriptionHtml", "")),
                posted_at=j.get("publishedAt"),
            )
        )
    return jobs


PARSERS = {
    "greenhouse": (GREENHOUSE, parse_greenhouse),
    "lever": (LEVER, parse_lever),
    "ashby": (ASHBY, parse_ashby),
}


def fetch_all(boards: list[dict], client: httpx.Client | None = None) -> list[Job]:
    """Fetch every configured board. A broken board is logged and skipped, never fatal."""
    own_client = client is None
    client = client or httpx.Client(timeout=20, headers={"User-Agent": "JobScout/0.1"})
    jobs: list[Job] = []
    try:
        for board in boards:
            url_tpl, parse = PARSERS[board["source"]]
            try:
                resp = client.get(url_tpl.format(token=board["token"]))
                resp.raise_for_status()
                found = parse(board["company"], board["token"], resp.json())
                log.info("%s (%s): %d postings", board["company"], board["source"], len(found))
                jobs.extend(found)
            except (httpx.HTTPError, KeyError, ValueError) as exc:
                log.warning("Skipping %s (%s): %s", board["company"], board["source"], exc)
    finally:
        if own_client:
            client.close()
    return jobs
