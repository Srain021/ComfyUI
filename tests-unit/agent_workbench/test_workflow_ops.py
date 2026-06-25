import json
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
AGENT_ROOT = REPO_ROOT / "custom_nodes" / "ComfyUI-AgentWorkbench"
sys.path.insert(0, str(AGENT_ROOT))

from agent_workbench.actions import apply_plan, dry_run_plan
from agent_workbench.executor import RecordingExecutor
from agent_workbench.ops.workflows import resolve_workflow_path, save_workflow_with_snapshot


def test_save_workflow_with_snapshot(tmp_path):
    target = tmp_path / "user" / "default" / "workflows" / "sample.json"
    target.parent.mkdir(parents=True)
    target.write_text("{\"old\": true}", encoding="utf-8")

    result = save_workflow_with_snapshot(target, {"new": True}, tmp_path / "backups")

    assert json.loads(target.read_text(encoding="utf-8")) == {"new": True}
    assert Path(result["snapshot"]).exists()


def test_save_new_workflow_without_snapshot(tmp_path):
    target = tmp_path / "user" / "default" / "workflows" / "new.json"

    result = save_workflow_with_snapshot(target, {"nodes": []}, tmp_path / "backups")

    assert json.loads(target.read_text(encoding="utf-8")) == {"nodes": []}
    assert result["snapshot"] is None


def test_resolve_workflow_path_rejects_escape(tmp_path):
    with pytest.raises(ValueError, match="inside user/default/workflows"):
        resolve_workflow_path(tmp_path, "../outside.json")
    with pytest.raises(ValueError, match="inside user/default/workflows"):
        resolve_workflow_path(tmp_path, "/tmp/outside.json")


def test_apply_dispatches_confirmed_workflow_save(tmp_path):
    dry_run = dry_run_plan(
        {
            "summary": "Save workflow",
            "actions": [
                {
                    "type": "workflow.save",
                    "payload": {"path": "agent/sample.json", "workflow": {"nodes": []}},
                }
            ],
        }
    )
    plan = dict(dry_run["plan"])
    plan["confirmed"] = True

    result = apply_plan(
        plan,
        approved_hash=dry_run["plan"]["plan_hash"],
        root=tmp_path,
        executor=RecordingExecutor(),
    )

    target = tmp_path / "user" / "default" / "workflows" / "agent" / "sample.json"
    assert result["ok"] is True
    assert result["applied"][0]["type"] == "workflow.save"
    assert json.loads(target.read_text(encoding="utf-8")) == {"nodes": []}
