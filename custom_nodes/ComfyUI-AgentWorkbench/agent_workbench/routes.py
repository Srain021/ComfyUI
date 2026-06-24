from pathlib import Path

from aiohttp import web

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

    _REGISTERED = True
