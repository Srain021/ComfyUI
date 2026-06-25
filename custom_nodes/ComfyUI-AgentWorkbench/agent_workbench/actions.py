import hashlib
import json
from copy import deepcopy
from pathlib import Path

from .executor import DefaultExecutor
from .ops.compose import DEFAULT_COMPOSE_PATH, apply_reserve_vram
from .ops.manager import manager_request_for_action
from .ops.workflows import resolve_workflow_path, save_workflow_with_snapshot
from .permissions import max_risk, requires_confirmation


class PlanValidationError(ValueError):
    pass


ACTION_REGISTRY = {
    "context.collect": ("context.read", "read"),
    "graph.set_widget": ("graph.edit", "canvas"),
    "graph.add_node": ("graph.edit", "canvas"),
    "graph.connect": ("graph.edit", "canvas"),
    "graph.disconnect": ("graph.edit", "canvas"),
    "graph.delete_node": ("graph.edit", "canvas"),
    "graph.duplicate_node": ("graph.edit", "canvas"),
    "graph.set_mode": ("graph.edit", "canvas"),
    "graph.set_title": ("graph.edit", "canvas"),
    "graph.set_position": ("graph.edit", "canvas"),
    "graph.select_node": ("graph.edit", "canvas"),
    "workflow.save": ("workflow.write", "file"),
    "runtime.queue_prompt": ("runtime.queue", "runtime"),
    "runtime.clear_queue": ("runtime.queue", "runtime"),
    "runtime.interrupt": ("runtime.interrupt", "runtime"),
    "runtime.free_memory": ("runtime.free_memory", "runtime"),
    "runtime.stop_ollama_model": ("runtime.free_memory", "runtime"),
    "custom_node.install": ("custom_node.manage", "package"),
    "custom_node.disable": ("custom_node.manage", "package"),
    "custom_node.enable": ("custom_node.manage", "package"),
    "custom_node.update": ("custom_node.manage", "package"),
    "custom_node.update_all": ("custom_node.manage", "package"),
    "custom_node.reinstall": ("custom_node.manage", "package"),
    "custom_node.fix": ("custom_node.manage", "package"),
    "compose.set_reserve_vram": ("service.compose", "service"),
    "service.compose_up": ("service.compose", "service"),
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
    copy.pop("confirmed", None)
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


def _agent_backup_dir(root: Path) -> Path:
    return root / "user" / "default" / "agent_workbench" / "backups"


def _required_payload(payload: dict, key: str, action_type: str) -> object:
    if key not in payload:
        raise PlanValidationError(f"{action_type} payload requires {key}")
    return payload[key]


def _dispatch_action(action: dict, root: Path, executor) -> dict:
    action_type = action["type"]
    payload = action.get("payload", {})
    if action_type.startswith("graph."):
        return {"type": action_type, "browser_required": True, "payload": payload}
    if action_type == "runtime.queue_prompt":
        return {"type": action_type, "browser_required": True, "payload": payload}
    if action_type == "context.collect":
        return {"type": action_type, "applied": False, "reason": "context action is read-only"}
    if action_type == "workflow.save":
        path = str(_required_payload(payload, "path", action_type))
        workflow = _required_payload(payload, "workflow", action_type)
        target = resolve_workflow_path(root, path)
        result = save_workflow_with_snapshot(target, workflow, _agent_backup_dir(root))
        return {"type": action_type, "workflow": result}
    if action_type == "compose.set_reserve_vram":
        value = str(_required_payload(payload, "value", action_type))
        compose_path = root / DEFAULT_COMPOSE_PATH
        result = apply_reserve_vram(compose_path, value, _agent_backup_dir(root))
        command_result = executor.run_command(
            ["docker", "compose", "-f", str(DEFAULT_COMPOSE_PATH), "up", "-d"]
        )
        return {"type": action_type, "compose": result, "command": command_result}
    if action_type == "service.compose_up":
        command_result = executor.run_command(
            ["docker", "compose", "-f", str(DEFAULT_COMPOSE_PATH), "up", "-d"]
        )
        return {"type": action_type, "command": command_result}
    if action_type == "service.restart_container":
        container = payload.get("container", "comfyui-gb10")
        return {"type": action_type, "command": executor.run_command(["docker", "restart", container])}
    if action_type == "runtime.stop_ollama_model":
        model = str(_required_payload(payload, "model", action_type))
        return {"type": action_type, "command": executor.run_command(["ollama", "stop", model])}
    if action_type == "runtime.interrupt":
        return {"type": action_type, "http_request": {"path": "/interrupt", "json": payload}}
    if action_type == "runtime.clear_queue":
        return {"type": action_type, "http_request": {"path": "/queue", "json": {"clear": True}}}
    if action_type == "runtime.free_memory":
        return {"type": action_type, "http_request": {"path": "/free", "json": payload}}
    if action_type.startswith("custom_node."):
        request = manager_request_for_action(action)
        executor.manager_request(request)
        return {"type": action_type, "manager_request": request}
    if action_type == "sudo.print_command":
        command = str(_required_payload(payload, "command", action_type))
        return {"type": action_type, "command": command, "executed": False}
    raise PlanValidationError(f"No dispatcher for action type: {action_type}")


def apply_plan(raw_plan: dict, approved_hash: str, root: Path | None = None, executor=None) -> dict:
    root = root or Path.cwd()
    executor = executor or DefaultExecutor()
    confirmed = isinstance(raw_plan, dict) and raw_plan.get("confirmed") is True
    plan = validate_plan(raw_plan)
    expected_hash = stable_plan_hash(plan)
    if approved_hash != expected_hash:
        return {"ok": False, "error": "approved_hash_mismatch", "expected_hash": expected_hash}
    if plan.get("requires_confirmation") and not confirmed:
        return {"ok": False, "error": "confirmation_required"}
    try:
        applied = [_dispatch_action(action, root, executor) for action in plan["actions"]]
    except (OSError, ValueError) as exc:
        raise PlanValidationError(str(exc)) from exc
    return {"ok": True, "status": "applied", "applied": applied}
