CAPABILITY_LEVELS = {
    "context.read": 0,
    "graph.inspect": 0,
    "graph.edit": 1,
    "runtime.queue": 2,
    "runtime.interrupt": 2,
    "runtime.free_memory": 2,
    "workflow.write": 3,
    "custom_node.manage": 4,
    "service.compose": 5,
    "service.restart": 5,
    "sudo.print_only": 6,
}

RISK_ORDER = ["read", "canvas", "runtime", "file", "package", "service", "human_sudo"]
RISK_REQUIRES_CONFIRMATION = {"runtime", "file", "package", "service", "human_sudo"}


def requires_confirmation(risk_level: str) -> bool:
    return risk_level in RISK_REQUIRES_CONFIRMATION


def max_risk(left: str, right: str) -> str:
    if RISK_ORDER.index(left) >= RISK_ORDER.index(right):
        return left
    return right
