"""Remember which postings were already handled so each run only looks at new ones."""

import json
import time
from pathlib import Path
from typing import Protocol

SEEN_TTL_DAYS = 90


class Memory(Protocol):
    def unseen(self, ids: list[str]) -> list[str]: ...
    def remember(self, job_id: str, score: int | None, note: str) -> None: ...


class JsonMemory:
    """Local file memory for laptop runs."""

    def __init__(self, path: Path):
        self.path = path
        self.data: dict = json.loads(path.read_text()) if path.exists() else {}

    def unseen(self, ids: list[str]) -> list[str]:
        return [i for i in ids if i not in self.data]

    def remember(self, job_id: str, score: int | None, note: str) -> None:
        self.data[job_id] = {"score": score, "note": note, "seen_at": int(time.time())}
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.data, indent=1))


class DynamoMemory:
    """DynamoDB memory for Lambda runs. Items expire via the `expires_at` TTL attribute."""

    def __init__(self, table_name: str, resource=None):
        if resource is None:
            import boto3

            resource = boto3.resource("dynamodb")
        self.table = resource.Table(table_name)
        self.table_name = table_name
        self.resource = resource

    def unseen(self, ids: list[str]) -> list[str]:
        seen: set[str] = set()
        for start in range(0, len(ids), 100):  # BatchGetItem limit
            keys = [{"job_id": i} for i in ids[start : start + 100]]
            request = {self.table_name: {"Keys": keys, "ProjectionExpression": "job_id"}}
            while request:
                resp = self.resource.batch_get_item(RequestItems=request)
                seen.update(item["job_id"] for item in resp["Responses"].get(self.table_name, []))
                request = resp.get("UnprocessedKeys") or None
        return [i for i in ids if i not in seen]

    def remember(self, job_id: str, score: int | None, note: str) -> None:
        now = int(time.time())
        item = {"job_id": job_id, "note": note, "seen_at": now, "expires_at": now + SEEN_TTL_DAYS * 86400}
        if score is not None:
            item["score"] = score
        self.table.put_item(Item=item)
