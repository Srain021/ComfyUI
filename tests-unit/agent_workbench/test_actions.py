import sys
from copy import deepcopy
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
AGENT_ROOT = REPO_ROOT / "custom_nodes" / "ComfyUI-AgentWorkbench"
sys.path.insert(0, str(AGENT_ROOT))

from agent_workbench.actions import (
    ACTION_REGISTRY,
    PlanValidationError,
    apply_plan,
    dry_run_plan,
    stable_plan_hash,
    validate_plan,
)
from agent_workbench.permissions import CAPABILITY_LEVELS, RISK_ORDER


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
    assert plan["plan_hash"] == stable_plan_hash(plan)


@pytest.mark.parametrize(
    ("actions", "match"),
    [
        (["bad"], r"Action 0 must be an object"),
        ([{"type": [], "payload": {}}], r"Action 0 type must be a string"),
    ],
)
def test_validate_plan_rejects_malformed_actions_with_validation_error(actions, match):
    with pytest.raises(PlanValidationError, match=match):
        validate_plan({"summary": "bad action", "actions": actions})


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


@pytest.mark.parametrize("action_type", ["service.stop_container", "service.start_container"])
def test_service_lifecycle_actions_require_explicit_approval(action_type):
    plan = validate_plan(
        {
            "summary": "Change ComfyUI service state",
            "actions": [{"type": action_type, "payload": {"container": "comfyui-gb10"}}],
        }
    )

    assert plan["risk_level"] == "service"
    assert plan["required_capabilities"] == ["service.restart"]
    assert plan["requires_confirmation"] is True


def test_compose_up_action_requires_explicit_approval():
    plan = validate_plan(
        {
            "summary": "Apply compose config",
            "actions": [{"type": "service.compose_up", "payload": {}}],
        }
    )

    assert plan["risk_level"] == "service"
    assert plan["required_capabilities"] == ["service.compose"]
    assert plan["requires_confirmation"] is True


def test_prerender_free_memory_action_requires_explicit_approval():
    plan = validate_plan(
        {
            "summary": "Prepare memory before rendering",
            "actions": [{"type": "service.prerender_free_memory", "payload": {}}],
        }
    )

    assert plan["risk_level"] == "service"
    assert plan["required_capabilities"] == ["service.restart"]
    assert plan["requires_confirmation"] is True


def test_restore_original_action_requires_explicit_approval():
    plan = validate_plan(
        {
            "summary": "Restore original ComfyUI container config",
            "actions": [{"type": "service.restore_original", "payload": {}}],
        }
    )

    assert plan["risk_level"] == "service"
    assert plan["required_capabilities"] == ["service.restart"]
    assert plan["requires_confirmation"] is True


def test_prerender_free_memory_then_queue_prompt_uses_service_risk():
    plan = validate_plan(
        {
            "summary": "Prepare memory then queue current workflow",
            "actions": [
                {"type": "service.prerender_free_memory", "payload": {}},
                {"type": "runtime.queue_prompt", "payload": {"front": False}},
            ],
        }
    )

    assert plan["risk_level"] == "service"
    assert plan["required_capabilities"] == ["service.restart", "runtime.queue"]
    assert plan["requires_confirmation"] is True


def test_service_healthcheck_is_read_only_without_extra_confirmation():
    plan = validate_plan(
        {
            "summary": "Check ComfyUI health",
            "actions": [{"type": "service.healthcheck", "payload": {}}],
        }
    )

    assert plan["risk_level"] == "read"
    assert plan["required_capabilities"] == ["context.read"]
    assert plan["requires_confirmation"] is False


def test_graph_delete_node_is_canvas_edit_without_extra_confirmation():
    plan = validate_plan(
        {
            "summary": "Delete graph node 12",
            "actions": [{"type": "graph.delete_node", "payload": {"node_id": 12}}],
        }
    )

    assert plan["risk_level"] == "canvas"
    assert plan["required_capabilities"] == ["graph.edit"]
    assert plan["requires_confirmation"] is False


def test_graph_duplicate_node_is_canvas_edit_without_extra_confirmation():
    plan = validate_plan(
        {
            "summary": "Duplicate graph node 12",
            "actions": [{"type": "graph.duplicate_node", "payload": {"node_id": 12}}],
        }
    )

    assert plan["risk_level"] == "canvas"
    assert plan["required_capabilities"] == ["graph.edit"]
    assert plan["requires_confirmation"] is False


def test_graph_set_color_is_canvas_edit_without_extra_confirmation():
    plan = validate_plan(
        {
            "summary": "Color graph node 12",
            "actions": [{"type": "graph.set_color", "payload": {"node_id": 12, "color": "#ff5555"}}],
        }
    )

    assert plan["risk_level"] == "canvas"
    assert plan["required_capabilities"] == ["graph.edit"]
    assert plan["requires_confirmation"] is False


def test_graph_set_mode_is_canvas_edit_without_extra_confirmation():
    plan = validate_plan(
        {
            "summary": "Bypass graph node 12",
            "actions": [{"type": "graph.set_mode", "payload": {"node_id": 12, "mode": "bypass"}}],
        }
    )

    assert plan["risk_level"] == "canvas"
    assert plan["required_capabilities"] == ["graph.edit"]
    assert plan["requires_confirmation"] is False


def test_graph_title_and_position_are_canvas_edits_without_extra_confirmation():
    plan = validate_plan(
        {
            "summary": "Organize graph node 12",
            "actions": [
                {"type": "graph.set_title", "payload": {"node_id": 12, "title": "Main Prompt"}},
                {"type": "graph.set_position", "payload": {"node_id": 12, "pos": [100, 200]}},
            ],
        }
    )

    assert plan["risk_level"] == "canvas"
    assert plan["required_capabilities"] == ["graph.edit"]
    assert plan["requires_confirmation"] is False


def test_graph_disconnect_is_canvas_edit_without_extra_confirmation():
    plan = validate_plan(
        {
            "summary": "Disconnect KSampler positive input",
            "actions": [
                {"type": "graph.disconnect", "payload": {"target_node_id": 2, "target_slot": 1}},
                {"type": "graph.disconnect", "payload": {"origin_node_id": 1, "origin_slot": 0}},
                {"type": "graph.disconnect", "payload": {"origin_node_id": 1, "target_node_id": 2}},
            ],
        }
    )

    assert plan["risk_level"] == "canvas"
    assert plan["required_capabilities"] == ["graph.edit"]
    assert plan["requires_confirmation"] is False


def test_graph_select_node_is_canvas_edit_without_extra_confirmation():
    plan = validate_plan(
        {
            "summary": "Select KSampler",
            "actions": [{"type": "graph.select_node", "payload": {"node_id": 9, "focus": True}}],
        }
    )

    assert plan["risk_level"] == "canvas"
    assert plan["required_capabilities"] == ["graph.edit"]
    assert plan["requires_confirmation"] is False


def test_graph_select_nodes_is_canvas_edit_without_extra_confirmation():
    plan = validate_plan(
        {
            "summary": "Select KSamplers",
            "actions": [{"type": "graph.select_nodes", "payload": {"node_ids": [9, 10]}}],
        }
    )

    assert plan["risk_level"] == "canvas"
    assert plan["required_capabilities"] == ["graph.edit"]
    assert plan["requires_confirmation"] is False


def test_queue_prompt_requires_runtime_confirmation():
    plan = validate_plan(
        {
            "summary": "Queue current workflow",
            "actions": [{"type": "runtime.queue_prompt", "payload": {"front": False}}],
        }
    )

    assert plan["risk_level"] == "runtime"
    assert plan["required_capabilities"] == ["runtime.queue"]
    assert plan["requires_confirmation"] is True


def test_graph_edit_then_queue_prompt_requires_runtime_confirmation():
    plan = validate_plan(
        {
            "summary": "Edit prompt then queue workflow",
            "actions": [
                {
                    "type": "graph.set_widget",
                    "payload": {"node_id": 12, "widget": "text", "value": "cinematic lighting"},
                },
                {"type": "runtime.queue_prompt", "payload": {"front": False}},
            ],
        }
    )

    assert plan["risk_level"] == "runtime"
    assert plan["required_capabilities"] == ["graph.edit", "runtime.queue"]
    assert plan["requires_confirmation"] is True


def test_clear_queue_requires_runtime_confirmation():
    plan = validate_plan(
        {
            "summary": "Clear pending queue",
            "actions": [{"type": "runtime.clear_queue", "payload": {}}],
        }
    )

    assert plan["risk_level"] == "runtime"
    assert plan["required_capabilities"] == ["runtime.queue"]
    assert plan["requires_confirmation"] is True


def test_interrupt_generation_requires_runtime_confirmation():
    plan = validate_plan(
        {
            "summary": "Interrupt current generation",
            "actions": [{"type": "runtime.interrupt", "payload": {}}],
        }
    )

    assert plan["risk_level"] == "runtime"
    assert plan["required_capabilities"] == ["runtime.interrupt"]
    assert plan["requires_confirmation"] is True


def test_stable_plan_hash_ignores_top_level_plan_hash():
    plan = validate_plan(
        {
            "summary": "Change prompt text",
            "actions": [{"type": "graph.set_widget", "payload": {"value": "cinematic lighting"}}],
        }
    )
    changed_hash_field = deepcopy(plan)
    changed_hash_field["plan_hash"] = "not-the-original-hash"

    assert stable_plan_hash(changed_hash_field) == stable_plan_hash(plan)


def test_stable_plan_hash_changes_when_real_field_changes():
    plan = validate_plan(
        {
            "summary": "Change prompt text",
            "actions": [{"type": "graph.set_widget", "payload": {"value": "cinematic lighting"}}],
        }
    )
    changed_summary = deepcopy(plan)
    changed_summary["summary"] = "Change prompt text again"

    assert stable_plan_hash(changed_summary) != stable_plan_hash(plan)


def test_stable_plan_hash_changes_when_nested_payload_changes():
    plan = validate_plan(
        {
            "summary": "Change prompt text",
            "actions": [{"type": "graph.set_widget", "payload": {"value": "cinematic lighting"}}],
        }
    )
    changed_payload = deepcopy(plan)
    changed_payload["actions"][0]["payload"]["value"] = "soft daylight"

    assert stable_plan_hash(changed_payload) != stable_plan_hash(plan)


@pytest.mark.parametrize(
    ("action_type", "payload", "risk_level"),
    [
        ("runtime.free_memory", {}, "runtime"),
        ("runtime.interrupt", {}, "runtime"),
        ("workflow.save", {"path": "workflow.json"}, "file"),
        ("custom_node.install", {"repo": "example/custom-node"}, "package"),
        ("custom_node.update", {"id": "ComfyUI-TestNode"}, "package"),
        ("custom_node.update_all", {}, "package"),
        ("custom_node.reinstall", {"id": "ComfyUI-TestNode"}, "package"),
        ("custom_node.fix", {"id": "ComfyUI-TestNode"}, "package"),
        ("custom_node.uninstall", {"id": "ComfyUI-TestNode"}, "package"),
        ("service.restart_container", {"container": "comfyui-gb10"}, "service"),
        ("service.stop_container", {"container": "comfyui-gb10"}, "service"),
        ("service.start_container", {"container": "comfyui-gb10"}, "service"),
        ("service.prerender_free_memory", {}, "service"),
        ("service.restore_original", {}, "service"),
        ("sudo.print_command", {"command": "sudo swapoff -a"}, "human_sudo"),
    ],
)
def test_confirmation_required_for_elevated_risk_actions(action_type, payload, risk_level):
    plan = validate_plan({"summary": "Requires confirmation", "actions": [{"type": action_type, "payload": payload}]})

    assert plan["risk_level"] == risk_level
    assert plan["requires_confirmation"] is True


def test_mixed_action_plan_uses_highest_risk_level():
    plan = validate_plan(
        {
            "summary": "Mixed plan",
            "actions": [
                {"type": "context.collect", "payload": {}},
                {"type": "graph.set_widget", "payload": {"node_id": 12, "widget": "text", "value": "noir"}},
                {"type": "workflow.save", "payload": {"path": "workflow.json"}},
                {"type": "service.restart_container", "payload": {"container": "comfyui-gb10"}},
            ],
        }
    )

    assert plan["risk_level"] == "service"
    assert plan["requires_confirmation"] is True


def test_action_registry_references_known_capabilities_and_risks():
    for capability, risk_level in ACTION_REGISTRY.values():
        assert capability in CAPABILITY_LEVELS
        assert risk_level in RISK_ORDER


def test_dry_run_returns_plan_hash_and_preview():
    result = dry_run_plan(
        {"summary": "inspect", "actions": [{"type": "context.collect", "payload": {}}]}
    )

    assert result["status"] == "dry_run"
    assert result["plan"]["plan_hash"]
    assert result["preview"][0]["type"] == "context.collect"
    assert result["preview"][0]["capability"] == "context.read"


def test_apply_rejects_changed_hash():
    dry_run = dry_run_plan(
        {"summary": "inspect", "actions": [{"type": "context.collect", "payload": {}}]}
    )

    result = apply_plan(dry_run["plan"], approved_hash="wrong")

    assert result["ok"] is False
    assert result["error"] == "approved_hash_mismatch"


def test_apply_revalidates_submitted_plan_before_hash_comparison():
    dry_run = dry_run_plan(
        {"summary": "inspect", "actions": [{"type": "context.collect", "payload": {}}]}
    )
    tampered = deepcopy(dry_run["plan"])
    tampered["actions"][0]["payload"]["extra"] = "changed after approval"

    result = apply_plan(tampered, approved_hash=dry_run["plan"]["plan_hash"])

    assert result["ok"] is False
    assert result["error"] == "approved_hash_mismatch"
    assert result["expected_hash"] != dry_run["plan"]["plan_hash"]


def test_apply_does_not_trust_client_supplied_confirmation_fields():
    dry_run = dry_run_plan(
        {"summary": "free memory", "actions": [{"type": "runtime.free_memory", "payload": {}}]}
    )
    tampered = deepcopy(dry_run["plan"])
    tampered["requires_confirmation"] = False
    tampered["risk_level"] = "read"
    tampered["actions"][0]["risk_level"] = "read"
    tampered["actions"][0]["capability"] = "context.read"

    result = apply_plan(tampered, approved_hash=dry_run["plan"]["plan_hash"])

    assert result == {"ok": False, "error": "confirmation_required"}


def test_apply_accepts_confirmed_matching_plan():
    dry_run = dry_run_plan(
        {"summary": "free memory", "actions": [{"type": "runtime.free_memory", "payload": {}}]}
    )
    confirmed = deepcopy(dry_run["plan"])
    confirmed["confirmed"] = True

    result = apply_plan(confirmed, approved_hash=dry_run["plan"]["plan_hash"])

    assert result == {
        "ok": True,
        "status": "applied",
        "applied": [
            {"type": "runtime.free_memory", "http_request": {"path": "/free", "json": {}}}
        ],
    }
