from typing import Literal

from pydantic import BaseModel, Field


class Job(BaseModel):
    """A job posting normalized across job-board sources."""

    id: str  # "<source>:<company>:<posting id>", stable across runs
    source: Literal["greenhouse", "lever", "ashby"]
    company: str
    title: str
    location: str
    url: str
    description: str = ""
    posted_at: str | None = None


class FitAssessment(BaseModel):
    """Claude's structured judgement of how well a job fits the candidate."""

    fit_score: int = Field(description="0-100. 80+ means apply this week.")
    verdict: Literal["strong", "possible", "weak"]
    matching_strengths: list[str] = Field(
        description="Specific profile facts that match the job's requirements."
    )
    gaps: list[str] = Field(description="Requirements the profile does not show.")
    eligibility_concerns: list[str] = Field(
        description="Anything suggesting citizenship, clearance or on-site rules the candidate cannot meet."
    )
    pitch: str = Field(description="One sentence the candidate could open a cover letter with.")


class Lead(BaseModel):
    job: Job
    assessment: FitAssessment
