import json
from datetime import datetime, timezone
from pathlib import Path


def append_audit_event(log_path: Path, event: dict) -> dict:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    row = dict(event)
    row["created_at"] = datetime.now(timezone.utc).isoformat()
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, sort_keys=True, ensure_ascii=False) + "\n")
    return row


def read_recent_events(log_path: Path, limit: int = 50) -> list[dict]:
    if not log_path.exists():
        return []
    lines = log_path.read_text(encoding="utf-8").splitlines()
    return [json.loads(line) for line in lines[-limit:]]
