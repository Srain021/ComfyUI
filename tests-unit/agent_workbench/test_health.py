import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
AGENT_ROOT = REPO_ROOT / "custom_nodes" / "ComfyUI-AgentWorkbench"
sys.path.insert(0, str(AGENT_ROOT))

from agent_workbench.health import build_health_payload


def test_health_payload_names_core_capabilities():
    payload = build_health_payload()

    assert payload["ok"] is True
    assert payload["name"] == "ComfyUI Agent Workbench"
    assert payload["version"] == "0.1.0"
    assert "graph.edit" in payload["capabilities"]
    assert "custom_node.manage" in payload["capabilities"]
    assert "service.compose" in payload["capabilities"]
    assert payload["sudo_policy"] == "print_only"
