import hashlib
import json
from copy import deepcopy

from .permissions import max_risk, requires_confirmation


class PlanValidationError(ValueError):
    pass


ACTION_REGISTRY = {
    "context.collect": ("context.read", "read"),
    "graph.set_widget": ("graph.edit", "canvas"),
    "graph.add_node": ("graph.edit", "canvas"),
    "graph.connect": ("graph.edit", "canvas"),
    "workflow.save": ("workflow.write", "file"),
    "runtime.free_memory": ("runtime.free_memory", "runtime"),
    "runtime.stop_ollama_model": ("runtime.free_memory", "runtime"),
    "custom_node.install": ("custom_node.manage", "package"),
    "custom_node.disable": ("custom_node.manage", "package"),
    "custom_node.enable": ("custom_node.manage", "package"),
    "compose.set_reserve_vram": ("service.compose", "service"),
    "service.restart_container": ("service.restart", "service"),
    "sudo.print_command": ("sudo.print_only", "human_sudo"),
}


def _normalize_action(action: object, index: int) -> dict:
    if not isinstance(action, dict):
        raise PlanValidationError(f"Action {index} must be an object")
    action_type = action.get("type")
    if not isinstance(action_type, str):
        raise PlanValidationError(f"Action {index} type must be a string")
    if action_type not in ACTION_REGISTRY:
        raise PlanValidationError(f"Unsupported action type: {action_type} (action {index})")
    payload = action.get("payload", {})
    if not isinstance(payload, dict):
        raise PlanValidationError(f"Action {index} payload must be an object: {action_type}")
    capability, risk = ACTION_REGISTRY[action_type]
    return {
        "type": action_type,
        "payload": deepcopy(payload),
        "capability": capability,
        "risk_level": risk,
    }


def validate_plan(raw: dict) -> dict:
    if not isinstance(raw, dict):
        raise PlanValidationError("Plan must be an object")
    summary = raw.get("summary")
    if not isinstance(summary, str) or not summary.strip():
        raise PlanValidationError("Plan summary must be a non-empty string")
    raw_actions = raw.get("actions")
    if not isinstance(raw_actions, list) or not raw_actions:
        raise PlanValidationError("Plan actions must be a non-empty list")

    actions = [_normalize_action(action, index) for index, action in enumerate(raw_actions)]
    risk_level = "read"
    capabilities = []
    for action in actions:
        risk_level = max_risk(risk_level, action["risk_level"])
        if action["capability"] not in capabilities:
            capabilities.append(action["capability"])

    plan = {
        "summary": summary.strip(),
        "actions": actions,
        "risk_level": risk_level,
        "required_capabilities": capabilities,
        "requires_confirmation": requires_confirmation(risk_level),
    }
    plan["plan_hash"] = stable_plan_hash(plan)
    return plan


def stable_plan_hash(plan: dict) -> str:
    copy = deepcopy(plan)
    copy.pop("plan_hash", None)
    payload = json.dumps(copy, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def dry_run_plan(raw: dict) -> dict:
    plan = validate_plan(raw)
    preview = [
        {
            "type": action["type"],
            "capability": action["capability"],
            "risk_level": action["risk_level"],
            "payload": action["payload"],
        }
        for action in plan["actions"]
    ]
    return {"status": "dry_run", "plan": plan, "preview": preview}


def apply_plan(raw_plan: dict, approved_hash: str) -> dict:
    plan = validate_plan(raw_plan)
    expected_hash = stable_plan_hash(plan)
    if approved_hash != expected_hash:
        return {
            "ok": False,
            "error": "approved_hash_mismatch",
            "expected_hash": expected_hash,
        }
    if plan.get("requires_confirmation") and raw_plan.get("confirmed") is not True:
        return {"ok": False, "error": "confirmation_required"}
    return {"ok": True, "status": "accepted", "applied": []}
