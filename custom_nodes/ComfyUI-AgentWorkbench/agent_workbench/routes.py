from pathlib import Path

from aiohttp import web

from .actions import PlanValidationError, apply_plan, dry_run_plan
from .context import collect_context
from .health import build_health_payload


_REGISTERED = False


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
        graph = body.get("graph")
        context = collect_context(Path.cwd(), graph=graph)
        return web.json_response(context)

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
        try:
            return web.json_response(apply_plan(plan, approved_hash=approved_hash))
        except PlanValidationError as exc:
            return web.json_response({"ok": False, "error": str(exc)}, status=400)

    _REGISTERED = True
