"""Run JobScout from a laptop.

  jobscout                 # offline keyword scoring, nothing saved (default)
  jobscout --live          # score with Claude on Bedrock, remember seen jobs locally
  jobscout --live --max 5  # cap Claude calls for a cheap first run
"""

import argparse
import json
import logging
import tempfile
from pathlib import Path

from .config import Settings
from .memory import JsonMemory
from .notifier import ConsoleNotifier
from .planner import Planner
from .scorer import ClaudeScorer, KeywordScorer


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="jobscout", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--live", action="store_true", help="score with Claude on Bedrock")
    parser.add_argument("--max", type=int, help="max postings to score this run")
    parser.add_argument("--min-score", type=int, help="alert threshold (default 75)")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO if args.verbose else logging.WARNING,
                        format="%(levelname)s %(name)s: %(message)s")
    settings = Settings.from_env()
    if args.max is not None:
        settings.max_scores_per_run = args.max
    if args.min_score is not None:
        settings.min_score = args.min_score

    if args.live:
        scorer = ClaudeScorer(settings.profile, settings.model, settings.aws_region, settings.effort)
        memory = JsonMemory(settings.memory_path)
    else:
        scorer = KeywordScorer()
        memory = JsonMemory(Path(tempfile.mkdtemp()) / "seen.json")  # throwaway

    report = Planner(settings, scorer, memory, ConsoleNotifier()).run()
    print(json.dumps(report.summary(), indent=2))


if __name__ == "__main__":
    main()
