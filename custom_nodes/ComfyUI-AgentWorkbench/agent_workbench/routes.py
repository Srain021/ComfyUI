from aiohttp import web

from .health import build_health_payload


_REGISTERED = False


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

    _REGISTERED = True
