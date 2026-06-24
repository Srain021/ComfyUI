import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
AGENT_ROOT = REPO_ROOT / "custom_nodes" / "ComfyUI-AgentWorkbench"
sys.path.insert(0, str(AGENT_ROOT))

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


def test_snapshot_file_and_restore(tmp_path):
    target = tmp_path / "workflow.json"
    target.write_text('{"old": true}', encoding="utf-8")
    backup_dir = tmp_path / "backups"

    snapshot = snapshot_file(target, backup_dir, reason="workflow-save")
    target.write_text('{"old": false}', encoding="utf-8")
    restore_snapshot(snapshot, target)

    assert target.read_text(encoding="utf-8") == '{"old": true}'
    assert "workflow-save" in snapshot.name
