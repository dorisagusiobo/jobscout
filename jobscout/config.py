import json
import os
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


@dataclass
class Settings:
    """Runtime settings. Everything can be overridden with JOBSCOUT_* env vars."""

    companies_file: Path = ROOT / "config" / "companies.json"
    profile_file: Path = ROOT / "profile" / "candidate_profile.md"
    model: str = "global.anthropic.claude-sonnet-4-6"
    effort: str = "low"
    aws_region: str = "us-east-1"
    min_score: int = 75
    max_scores_per_run: int = 25
    memory_path: Path = ROOT / ".jobscout" / "seen.json"
    dynamo_table: str | None = None
    sns_topic_arn: str | None = None
    companies: dict = field(default_factory=dict)

    @classmethod
    def from_env(cls) -> "Settings":
        s = cls()
        env = os.environ
        s.companies_file = Path(env.get("JOBSCOUT_COMPANIES_FILE", s.companies_file))
        s.profile_file = Path(env.get("JOBSCOUT_PROFILE_FILE", s.profile_file))
        s.model = env.get("JOBSCOUT_MODEL", s.model)
        s.effort = env.get("JOBSCOUT_EFFORT", s.effort)
        s.aws_region = env.get("AWS_REGION", s.aws_region)
        s.min_score = int(env.get("JOBSCOUT_MIN_SCORE", s.min_score))
        s.max_scores_per_run = int(env.get("JOBSCOUT_MAX_SCORES", s.max_scores_per_run))
        s.memory_path = Path(env.get("JOBSCOUT_MEMORY_PATH", s.memory_path))
        s.dynamo_table = env.get("JOBSCOUT_TABLE") or None
        s.sns_topic_arn = env.get("JOBSCOUT_TOPIC_ARN") or None
        s.companies = json.loads(s.companies_file.read_text())
        return s

    @property
    def profile(self) -> str:
        return self.profile_file.read_text()
