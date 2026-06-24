import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
AGENT_ROOT = REPO_ROOT / "custom_nodes" / "ComfyUI-AgentWorkbench"
sys.path.insert(0, str(AGENT_ROOT))

from agent_workbench import snapshots as snapshot_module
from agent_workbench.audit_log import append_audit_event, read_recent_events
from agent_workbench.snapshots import restore_snapshot, snapshot_file


def test_audit_log_appends_jsonl(tmp_path):
    log_path = tmp_path / "audit.jsonl"

    append_audit_event(log_path, {"event": "dry_run", "plan_hash": "abc"})

    rows = [json.loads(line) for line in log_path.read_text().splitlines()]
    assert rows[0]["event"] == "dry_run"
    assert rows[0]["plan_hash"] == "abc"
    assert "created_at" in rows[0]
    assert read_recent_events(log_path, limit=1)[0]["event"] == "dry_run"


def test_audit_log_reads_most_recent_events_in_order(tmp_path):
    log_path = tmp_path / "audit.jsonl"

    append_audit_event(log_path, {"event": "first"})
    append_audit_event(log_path, {"event": "second"})

    assert [row["event"] for row in read_recent_events(log_path, limit=1)] == ["second"]


@pytest.mark.parametrize("limit", [0, -1])
def test_audit_log_non_positive_limit_returns_empty_list(tmp_path, limit):
    log_path = tmp_path / "audit.jsonl"
    append_audit_event(log_path, {"event": "dry_run"})

    assert read_recent_events(log_path, limit=limit) == []


def test_snapshot_file_and_restore(tmp_path):
    target = tmp_path / "workflow.json"
    target.write_text('{"old": true}', encoding="utf-8")
    backup_dir = tmp_path / "backups"

    snapshot = snapshot_file(target, backup_dir, reason="workflow-save")
    target.write_text('{"old": false}', encoding="utf-8")
    restore_snapshot(snapshot, target)

    assert target.read_text(encoding="utf-8") == '{"old": true}'
    assert "workflow-save" in snapshot.name


def test_snapshot_file_creates_distinct_files_for_same_target_reason_and_timestamp(tmp_path, monkeypatch):
    class FrozenDatetime:
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)

    monkeypatch.setattr(snapshot_module, "datetime", FrozenDatetime)
    target = tmp_path / "workflow.json"
    backup_dir = tmp_path / "backups"

    target.write_text('{"version": 1}', encoding="utf-8")
    first = snapshot_file(target, backup_dir, reason="workflow-save")
    target.write_text('{"version": 2}', encoding="utf-8")
    second = snapshot_file(target, backup_dir, reason="workflow-save")

    assert first != second
    assert first.is_file()
    assert second.is_file()
    assert first.read_text(encoding="utf-8") == '{"version": 1}'
    assert second.read_text(encoding="utf-8") == '{"version": 2}'


def test_snapshot_file_rejects_directory_targets(tmp_path):
    target = tmp_path / "workflow-dir"
    target.mkdir()

    with pytest.raises(IsADirectoryError):
        snapshot_file(target, tmp_path / "backups", reason="workflow-save")
