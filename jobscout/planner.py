"""The agent loop: scan -> filter -> skip seen -> score -> remember -> alert."""

import logging
from dataclasses import dataclass, field

from .filters import prefilter
from .memory import Memory
from .models import Job, Lead
from .notifier import Notifier
from .scorer import Scorer
from .sources import fetch_all

log = logging.getLogger(__name__)


@dataclass
class RunReport:
    fetched: int = 0
    dropped: dict[str, int] = field(default_factory=dict)
    already_seen: int = 0
    scored: int = 0
    deferred: int = 0
    errors: int = 0
    leads: list[Lead] = field(default_factory=list)

    def summary(self) -> dict:
        return {
            "fetched": self.fetched,
            "dropped": self.dropped,
            "already_seen": self.already_seen,
            "scored": self.scored,
            "deferred_to_next_run": self.deferred,
            "errors": self.errors,
            "leads": len(self.leads),
        }


class Planner:
    def __init__(self, settings, scorer: Scorer, memory: Memory, notifier: Notifier, fetch=fetch_all):
        self.settings = settings
        self.scorer = scorer
        self.memory = memory
        self.notifier = notifier
        self.fetch = fetch

    def run(self) -> RunReport:
        cfg = self.settings.companies
        report = RunReport()

        jobs: list[Job] = self.fetch(cfg["boards"])
        report.fetched = len(jobs)

        candidates, report.dropped = prefilter(jobs, cfg["title_include"], cfg["title_exclude"])
        by_id = {j.id: j for j in candidates}
        fresh = self.memory.unseen(list(by_id))
        report.already_seen = len(by_id) - len(fresh)

        # Cap model calls per run; the rest stay unseen and are scored next run.
        batch = fresh[: self.settings.max_scores_per_run]
        report.deferred = len(fresh) - len(batch)

        for job_id in batch:
            job = by_id[job_id]
            try:
                assessment = self.scorer.score(job)
            except Exception:  # one bad posting must not sink the run
                log.exception("Scoring failed for %s", job_id)
                report.errors += 1
                continue
            report.scored += 1
            self.memory.remember(job_id, assessment.fit_score, assessment.verdict)
            if assessment.fit_score >= self.settings.min_score and not assessment.eligibility_concerns:
                report.leads.append(Lead(job=job, assessment=assessment))

        self.notifier.send(report.leads)
        log.info("Run summary: %s", report.summary())
        return report
