"""Score job fit with Claude on Amazon Bedrock using structured output."""

from typing import Protocol

from .models import FitAssessment, Job

SYSTEM = """You screen job postings for one candidate and judge fit honestly.

Rules:
- Use only facts in the candidate profile. Never invent experience, employers or skills.
- Course and certificate projects count as projects, not paid work experience.
- Score 0-100: 80+ strong (apply this week), 60-79 possible, below 60 weak.
- Weigh hard requirements (years, must-have stack, degree) above nice-to-haves.
- The candidate is authorized to work in the US without sponsorship but is NOT a US citizen
  and cannot hold a security clearance. Put any citizenship, clearance, relocation or
  on-site requirement outside the Baltimore/DC area in eligibility_concerns and cap the score
  at 40 if it is mandatory. eligibility_concerns lists real blockers only: leave it empty when
  there are none, and never add notes like "no sponsorship concern".
- The pitch must be one truthful sentence grounded in the profile.

<candidate_profile>
{profile}
</candidate_profile>"""

MAX_DESCRIPTION_CHARS = 12_000


class Scorer(Protocol):
    def score(self, job: Job) -> FitAssessment: ...


def job_prompt(job: Job) -> str:
    return (
        f"Company: {job.company}\nTitle: {job.title}\nLocation: {job.location}\n\n"
        f"<job_description>\n{job.description[:MAX_DESCRIPTION_CHARS]}\n</job_description>\n\n"
        "Assess the candidate's fit for this job."
    )


INFERENCE_PROFILE_PREFIXES = {"global", "us", "eu", "jp", "apac", "au"}


def bedrock_api(model: str) -> str:
    """'invoke' for inference-profile IDs (global./us./...), else 'mantle' (Messages API endpoint)."""
    return "invoke" if model.split(".", 1)[0] in INFERENCE_PROFILE_PREFIXES else "mantle"


def bedrock_client(model: str, aws_region: str):
    if bedrock_api(model) == "invoke":
        from anthropic import AnthropicBedrock

        return AnthropicBedrock(aws_region=aws_region)
    from anthropic import AnthropicBedrockMantle

    return AnthropicBedrockMantle(aws_region=aws_region)


class ClaudeScorer:
    def __init__(self, profile: str, model: str, aws_region: str, effort: str = "low", client=None):
        self.client = client or bedrock_client(model, aws_region)
        self.model = model
        self.effort = effort  # empty string = don't send (older models reject effort)
        self.system = SYSTEM.format(profile=profile)

    def score(self, job: Job) -> FitAssessment:
        extra = {"output_config": {"effort": self.effort}} if self.effort else {}
        if bedrock_api(self.model) == "invoke":
            # InvokeModel rejects the SDK's newest API version; pin Bedrock's own.
            extra["extra_body"] = {"anthropic_version": "bedrock-2023-05-31"}
        response = self.client.messages.parse(
            model=self.model,
            max_tokens=4000,
            system=self.system,
            messages=[{"role": "user", "content": job_prompt(job)}],
            output_format=FitAssessment,
            **extra,
        )
        if response.parsed_output is None:
            raise RuntimeError(f"No structured output for {job.id} (stop_reason={response.stop_reason})")
        return response.parsed_output


class KeywordScorer:
    """Offline stand-in for dry runs and tests: scores by skill-keyword overlap."""

    SKILLS = ("python", "llm", "rag", "agent", "fastapi", "aws", "bedrock", "terraform",
              "docker", "prompt", "embedding", "evaluation", "next.js", "react", "mcp")

    def score(self, job: Job) -> FitAssessment:
        text = f"{job.title} {job.description}".lower()
        hits = [s for s in self.SKILLS if s in text]
        score = min(100, 30 + 7 * len(hits))
        verdict = "strong" if score >= 80 else "possible" if score >= 60 else "weak"
        return FitAssessment(
            fit_score=score,
            verdict=verdict,
            matching_strengths=hits,
            gaps=[],
            eligibility_concerns=[],
            pitch=f"(dry run) keyword overlap: {', '.join(hits) or 'none'}",
        )
