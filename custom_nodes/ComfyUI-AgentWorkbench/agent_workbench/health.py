from . import VERSION


CORE_CAPABILITIES = [
    "context.read",
    "graph.inspect",
    "graph.edit",
    "workflow.write",
    "runtime.free_memory",
    "custom_node.manage",
    "service.compose",
    "service.restart",
    "sudo.print_only",
]


def build_health_payload() -> dict:
    return {
        "ok": True,
        "name": "ComfyUI Agent Workbench",
        "version": VERSION,
        "capabilities": list(CORE_CAPABILITIES),
        "sudo_policy": "print_only",
    }
