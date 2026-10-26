"""AWS Lambda entry point, triggered on a schedule by EventBridge Scheduler."""

import logging

from .config import Settings
from .memory import DynamoMemory
from .notifier import SnsNotifier
from .planner import Planner
from .scorer import ClaudeScorer

logging.getLogger().setLevel(logging.INFO)


def lambda_handler(event, context):
    settings = Settings.from_env()
    if not settings.dynamo_table or not settings.sns_topic_arn:
        raise RuntimeError("JOBSCOUT_TABLE and JOBSCOUT_TOPIC_ARN must be set")
    planner = Planner(
        settings,
        scorer=ClaudeScorer(settings.profile, settings.model, settings.aws_region, settings.effort),
        memory=DynamoMemory(settings.dynamo_table),
        notifier=SnsNotifier(settings.sns_topic_arn),
    )
    return planner.run().summary()
