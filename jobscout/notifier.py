"""Deliver the digest of strong leads."""

from typing import Protocol

from .models import Lead


class Notifier(Protocol):
    def send(self, leads: list[Lead]) -> None: ...


def format_digest(leads: list[Lead]) -> str:
    lines = [f"JobScout found {len(leads)} strong lead(s):", ""]
    for n, lead in enumerate(sorted(leads, key=lambda l: -l.assessment.fit_score), 1):
        job, a = lead.job, lead.assessment
        lines += [
            f"{n}. {job.title} — {job.company} ({job.location or 'location not listed'})",
            f"   Fit {a.fit_score}/100 ({a.verdict})",
            f"   Why: {'; '.join(a.matching_strengths[:4])}",
        ]
        if a.gaps:
            lines.append(f"   Gaps: {'; '.join(a.gaps[:3])}")
        if a.eligibility_concerns:
            lines.append(f"   Check: {'; '.join(a.eligibility_concerns)}")
        lines += [f"   Pitch: {a.pitch}", f"   Apply: {job.url}", ""]
    return "\n".join(lines)


class ConsoleNotifier:
    def send(self, leads: list[Lead]) -> None:
        print(format_digest(leads) if leads else "No new strong leads this run.")


class SnsNotifier:
    def __init__(self, topic_arn: str, client=None):
        if client is None:
            import boto3

            client = boto3.client("sns")
        self.client = client
        self.topic_arn = topic_arn

    def send(self, leads: list[Lead]) -> None:
        if not leads:
            return
        self.client.publish(
            TopicArn=self.topic_arn,
            Subject=f"JobScout: {len(leads)} new AI role(s) worth applying to"[:100],
            Message=format_digest(leads),
        )
