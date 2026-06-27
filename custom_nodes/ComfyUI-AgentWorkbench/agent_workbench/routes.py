import asyncio
from pathlib import Path

from aiohttp import web

from .actions import PlanValidationError, apply_deferred_action, apply_plan, dry_run_plan
from .context import collect_context
from .health import build_health_payload
from .llm import build_assistant_reply
from .planner import default_planner


_REGISTERED = False
MAX_PLANNER_GRAPH_NODES = 500
MAX_PLANNER_GRAPH_LINKS = 1000
MAX_PLANNER_NODE_TYPES = 1000
MAX_PLANNER_UI_ERRORS = 20
MAX_PLANNER_UI_ERROR_TEXT_CHARS = 1000
MAX_PLANNER_UI_ERROR_FIELD_CHARS = 200


def _bounded_string(value: object, limit: int) -> str | None:
    if not isinstance(value, str) or not value:
        return None
    if len(value) <= limit:
        return value
    return f"{value[:limit]}..."


def _bounded_ui_errors(graph: dict) -> list[dict]:
    ui_errors = graph.get("ui_errors")
    if not isinstance(ui_errors, list):
        return []
    rows = []
    for item in ui_errors[:MAX_PLANNER_UI_ERRORS]:
        if not isinstance(item, dict):
            continue
        text = _bounded_string(item.get("text"), MAX_PLANNER_UI_ERROR_TEXT_CHARS)
        if not text:
            continue
        row: dict = {"text": text}
        for key in ("source", "severity", "node_type", "title"):
            value = _bounded_string(item.get(key), MAX_PLANNER_UI_ERROR_FIELD_CHARS)
            if value:
                row[key] = value
        node_id = item.get("node_id")
        if isinstance(node_id, (int, str)):
            row["node_id"] = node_id
        rows.append(row)
    return rows


def _bounded_graph_input(graph: object) -> dict:
    if not isinstance(graph, dict):
        return {}
    nodes = graph.get("nodes")
    links = graph.get("links")
    node_types = graph.get("node_types")
    if not isinstance(nodes, list):
        nodes = []
    if not isinstance(links, list):
        links = []
    if not isinstance(node_types, list):
        node_types = []
    bounded = {
        "nodes": [node for node in nodes[:MAX_PLANNER_GRAPH_NODES] if isinstance(node, dict)],
        "links": [link for link in links[:MAX_PLANNER_GRAPH_LINKS] if isinstance(link, dict)],
        "node_types": [
            row
            for row in node_types[:MAX_PLANNER_NODE_TYPES]
            if isinstance(row, dict) and isinstance(row.get("type"), str)
        ],
    }
    ui_errors = _bounded_ui_errors(graph)
    if ui_errors:
        bounded["ui_errors"] = ui_errors
    return bounded


def _graph_from_body(body: dict) -> object:
    graph = body.get("graph")
    if isinstance(graph, dict):
        return graph
    context = body.get("context")
    if isinstance(context, dict):
        graph_input = context.get("graph_input")
        if isinstance(graph_input, dict):
            return graph_input
        context_graph = context.get("graph")
        if isinstance(context_graph, dict):
            return context_graph
    return graph


def _browser_workflow_from_body(body: dict) -> object:
    workflow = body.get("browser_workflow")
    if isinstance(workflow, dict):
        return workflow
    return None


def _context_from_message_body(body: dict) -> tuple[str, dict]:
    message = body.get("message", "")
    graph = _graph_from_body(body)
    context = collect_context(Path.cwd(), graph=graph)
    context["graph_input"] = _bounded_graph_input(graph)
    return message, context


def _list_from_body(body: dict, key: str) -> list:
    value = body.get(key)
    if not isinstance(value, list):
        return []
    return [row for row in value if isinstance(row, dict)]


def _is_context_only_dry_run(payload: dict) -> bool:
    plan = payload.get("plan")
    if not isinstance(plan, dict):
        return False
    actions = plan.get("actions")
    return (
        isinstance(actions, list)
        and len(actions) == 1
        and isinstance(actions[0], dict)
        and actions[0].get("type") == "context.collect"
    )


async def _json_request(request) -> dict:
    if not getattr(request, "can_read_body", False):
        return {}
    try:
        body = await request.json()
    except (TypeError, ValueError):
        return {}
    if not isinstance(body, dict):
        return {}
    return body


def _smoke_manifest() -> dict:
    prompt_edit = "把这个 prompt 节点的文本更新成 glowing blue forest"
    elevated = "关 swap 防止卡死"
    return {
        "ok": True,
        "surface": "windows_browser",
        "workbench_url": "http://<spark-host>:8188/",
        "agent_routes": [
            "/agent/context",
            "/agent/message",
            "/agent/plan",
            "/agent/apply",
            "/agent/apply-deferred",
            "/agent/smoke_manifest",
        ],
        "sample_prompts": {
            "prompt_edit": prompt_edit,
            "custom_node_restart": "安装当前工作流缺失节点然后重启 ComfyUI",
            "manager_queue": "查看 Manager 安装队列状态",
            "compose_apply": "应用 compose 配置并重建 ComfyUI 服务",
            "service_logs": "查看 ComfyUI 最近日志",
            "print_sudo": elevated,
        },
        "manual_steps": [
            {
                "id": "context",
                "control": "Context",
                "prompt": None,
                "expect": "Output JSON includes graph, custom_nodes, workflows, and selected_node_ids.",
            },
            {
                "id": "plan_prompt_edit",
                "control": "Plan",
                "prompt": prompt_edit,
                "expect": "Dry run contains graph.set_widget for the selected prompt/text widget.",
            },
            {
                "id": "confirm_elevated",
                "control": "Plan",
                "prompt": elevated,
                "expect": "Confirm elevated action appears; Apply stays disabled until checked.",
            },
            {
                "id": "cancel_plan",
                "control": "Cancel",
                "prompt": None,
                "expect": "Output reports user_cancelled and Apply becomes disabled.",
            },
            {
                "id": "apply_prompt_edit",
                "control": "Apply",
                "prompt": prompt_edit,
                "expect": "After planning the prompt edit, Apply updates the selected node in the browser graph.",
            },
            {
                "id": "plan_custom_node_restart",
                "control": "Plan only",
                "prompt": "安装当前工作流缺失节点然后重启 ComfyUI",
                "expect": "Plan shows Manager/custom-node action plus ComfyUI restart as elevated or deferred work.",
            },
        ],
        "safety": {
            "sudo": "print_only",
            "manifest": "read_only",
            "destructive_ops": "plan_and_confirm_before_apply",
        },
    }


def register_routes(prompt_server=None) -> None:
    global _REGISTERED
    if _REGISTERED:
        return

    if prompt_server is None:
        from server import PromptServer

        prompt_server = PromptServer.instance

    routes = prompt_server.routes

    @routes.get("/agent/health")
    async def agent_health(request):
        return web.json_response(build_health_payload())

    @routes.get("/agent/smoke_manifest")
    async def agent_smoke_manifest(request):
        return web.json_response(_smoke_manifest())

    @routes.post("/agent/context")
    async def agent_context(request):
        body = await _json_request(request)
        graph = _graph_from_body(body)
        context = collect_context(Path.cwd(), graph=graph)
        return web.json_response(context)

    @routes.post("/agent/plan")
    async def agent_plan(request):
        body = await _json_request(request)
        message, context = _context_from_message_body(body)
        raw_plan = default_planner().plan(message, context=context)
        try:
            return web.json_response(dry_run_plan(raw_plan))
        except PlanValidationError as exc:
            return web.json_response(
                {"ok": False, "error": str(exc), "raw_plan": raw_plan},
                status=400,
            )

    @routes.post("/agent/message")
    async def agent_message(request):
        body = await _json_request(request)
        message, context = _context_from_message_body(body)
        raw_plan = default_planner().plan(message, context=context)
        try:
            dry_run = dry_run_plan(raw_plan)
        except PlanValidationError as exc:
            return web.json_response(
                {"ok": False, "error": str(exc), "raw_plan": raw_plan},
                status=400,
            )
        reply = await asyncio.to_thread(
            build_assistant_reply,
            message,
            context=context,
            dry_run=dry_run,
            history=_list_from_body(body, "history"),
            attachments=_list_from_body(body, "attachments"),
        )
        return web.json_response(reply)

    @routes.post("/agent/dry-run")
    async def agent_dry_run(request):
        body = await _json_request(request)
        try:
            return web.json_response(dry_run_plan(body))
        except PlanValidationError as exc:
            return web.json_response({"ok": False, "error": str(exc)}, status=400)

    @routes.post("/agent/apply")
    async def agent_apply(request):
        body = await _json_request(request)
        plan = body.get("plan", {})
        approved_hash = body.get("approved_hash", "")
        browser_workflow = _browser_workflow_from_body(body)
        try:
            result = await asyncio.to_thread(
                apply_plan,
                plan,
                approved_hash=approved_hash,
                root=Path.cwd(),
                browser_workflow=browser_workflow,
            )
            return web.json_response(result)
        except PlanValidationError as exc:
            return web.json_response({"ok": False, "error": str(exc)}, status=400)

    @routes.post("/agent/apply-deferred")
    async def agent_apply_deferred(request):
        body = await _json_request(request)
        plan = body.get("plan", {})
        approved_hash = body.get("approved_hash", "")
        action_index = body.get("action_index")
        browser_workflow = _browser_workflow_from_body(body)
        try:
            result = await asyncio.to_thread(
                apply_deferred_action,
                plan,
                approved_hash=approved_hash,
                action_index=action_index,
                root=Path.cwd(),
                browser_workflow=browser_workflow,
            )
            return web.json_response(result)
        except PlanValidationError as exc:
            return web.json_response({"ok": False, "error": str(exc)}, status=400)

    _REGISTERED = True
