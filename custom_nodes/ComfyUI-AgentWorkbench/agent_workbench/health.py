from . import VERSION
from .llm import llm_status


CORE_CAPABILITIES = [
    "context.read",
    "graph.inspect",
    "graph.edit",
    "workflow.write",
    "runtime.queue",
    "runtime.interrupt",
    "runtime.free_memory",
    "model.manage",
    "custom_node.manage",
    "service.compose",
    "service.restart",
    "sudo.print_only",
    "agent.chat",
    "agent.codex_cli",
    "agent.tool_planning",
]


def build_health_payload() -> dict:
    return {
        "ok": True,
        "name": "ComfyUI Agent Workbench",
        "version": VERSION,
        "capabilities": list(CORE_CAPABILITIES),
        "sudo_policy": "print_only",
        "llm": llm_status(),
    }
