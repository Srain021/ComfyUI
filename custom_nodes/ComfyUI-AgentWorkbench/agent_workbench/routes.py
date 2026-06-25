import asyncio
from pathlib import Path

from aiohttp import web

from .actions import PlanValidationError, apply_deferred_action, apply_plan, dry_run_plan
from .context import collect_context
from .health import build_health_payload
from .planner import default_planner


_REGISTERED = False
MAX_PLANNER_GRAPH_NODES = 500
MAX_PLANNER_GRAPH_LINKS = 1000


def _bounded_graph_input(graph: object) -> dict:
    if not isinstance(graph, dict):
        return {}
    nodes = graph.get("nodes")
    links = graph.get("links")
    if not isinstance(nodes, list):
        nodes = []
    if not isinstance(links, list):
        links = []
    return {
        "nodes": [node for node in nodes[:MAX_PLANNER_GRAPH_NODES] if isinstance(node, dict)],
        "links": [link for link in links[:MAX_PLANNER_GRAPH_LINKS] if isinstance(link, dict)],
    }


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

    @routes.post("/agent/context")
    async def agent_context(request):
        body = await _json_request(request)
        graph = _graph_from_body(body)
        context = collect_context(Path.cwd(), graph=graph)
        return web.json_response(context)

    @routes.post("/agent/plan")
    async def agent_plan(request):
        body = await _json_request(request)
        message = body.get("message", "")
        graph = _graph_from_body(body)
        context = collect_context(Path.cwd(), graph=graph)
        context["graph_input"] = _bounded_graph_input(graph)
        raw_plan = default_planner().plan(message, context=context)
        try:
            return web.json_response(dry_run_plan(raw_plan))
        except PlanValidationError as exc:
            return web.json_response(
                {"ok": False, "error": str(exc), "raw_plan": raw_plan},
                status=400,
            )

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
