import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
AGENT_ROOT = REPO_ROOT / "custom_nodes" / "ComfyUI-AgentWorkbench"
sys.path.insert(0, str(AGENT_ROOT))

from agent_workbench.actions import PlanValidationError, stable_plan_hash, validate_plan


def test_validate_plan_assigns_capabilities_and_hash_is_stable():
    raw = {
        "summary": "Change prompt text",
        "actions": [
            {
                "type": "graph.set_widget",
                "payload": {"node_id": 12, "widget": "text", "value": "cinematic lighting"},
            }
        ],
    }

    plan = validate_plan(raw)

    assert plan["risk_level"] == "canvas"
    assert plan["required_capabilities"] == ["graph.edit"]
    assert stable_plan_hash(plan) == stable_plan_hash(plan)


def test_validate_plan_rejects_unknown_action_type():
    with pytest.raises(PlanValidationError, match="Unsupported action type"):
        validate_plan({"summary": "bad", "actions": [{"type": "shell.exec", "payload": {}}]})


def test_service_actions_require_explicit_approval():
    raw = {
        "summary": "Restart ComfyUI",
        "actions": [{"type": "service.restart_container", "payload": {"container": "comfyui-gb10"}}],
    }

    plan = validate_plan(raw)

    assert plan["risk_level"] == "service"
    assert plan["requires_confirmation"] is True
