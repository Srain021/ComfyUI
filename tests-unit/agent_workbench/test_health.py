import asyncio
import importlib.util
import json
import sys
import types
from pathlib import Path

from aiohttp import web

REPO_ROOT = Path(__file__).resolve().parents[2]
AGENT_ROOT = REPO_ROOT / "custom_nodes" / "ComfyUI-AgentWorkbench"
sys.path.insert(0, str(AGENT_ROOT))

from agent_workbench import routes as agent_routes
from agent_workbench.health import CORE_CAPABILITIES, build_health_payload

def test_health_payload_names_core_capabilities():
    payload = build_health_payload()

    assert payload["ok"] is True
    assert payload["name"] == "ComfyUI Agent Workbench"
    assert payload["version"] == "0.1.0"
    assert "graph.edit" in payload["capabilities"]
    assert "custom_node.manage" in payload["capabilities"]
    assert "service.compose" in payload["capabilities"]
    assert payload["sudo_policy"] == "print_only"

def test_health_payload_capabilities_are_isolated_from_module_constant():
    payload = build_health_payload()

    assert payload["capabilities"] is not CORE_CAPABILITIES
    payload["capabilities"].append("mutated")
    assert "mutated" not in build_health_payload()["capabilities"]

def test_register_routes_adds_agent_health_get_route():
    agent_routes._REGISTERED = False
    fake_prompt_server = types.SimpleNamespace(routes=web.RouteTableDef())

    try:
        agent_routes.register_routes(fake_prompt_server)

        app = web.Application()
        app.add_routes(fake_prompt_server.routes)
        matches = [
            route
            for route in app.router.routes()
            if route.method == "GET" and route.resource.canonical == "/agent/health"
        ]

        assert len(matches) == 1
        response = asyncio.run(matches[0].handler(None))
        assert json.loads(response.text)["ok"] is True
    finally:
        agent_routes._REGISTERED = False

def test_custom_node_entrypoint_exposes_frontend_extension(monkeypatch):
    module_name = "agent_workbench_custom_node_entrypoint"
    for loaded_name in list(sys.modules):
        if loaded_name == module_name or loaded_name.startswith(f"{module_name}."):
            del sys.modules[loaded_name]

    fake_prompt_server = types.SimpleNamespace(routes=web.RouteTableDef())
    fake_server = types.ModuleType("server")
    fake_server.PromptServer = types.SimpleNamespace(instance=fake_prompt_server)
    monkeypatch.setitem(sys.modules, "server", fake_server)

    spec = importlib.util.spec_from_file_location(
        module_name,
        AGENT_ROOT / "__init__.py",
        submodule_search_locations=[str(AGENT_ROOT)],
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)

    assert module.NODE_CLASS_MAPPINGS == {}
    assert module.NODE_DISPLAY_NAME_MAPPINGS == {}
    assert module.WEB_DIRECTORY == "js"

    web_root = AGENT_ROOT / module.WEB_DIRECTORY
    assert (web_root / "agent-workbench.js").is_file()
    assert (web_root / "agent-workbench.css").is_file()

def test_frontend_loads_stylesheet_without_css_module_import():
    script = (AGENT_ROOT / "js" / "agent-workbench.js").read_text()

    assert 'import "./agent-workbench.css";' not in script
    assert "/extensions/ComfyUI-AgentWorkbench/agent-workbench.css" in script
    assert 'document.createElement("link")' in script

def test_frontend_panel_creation_is_idempotent():
    script = (AGENT_ROOT / "js" / "agent-workbench.js").read_text()

    assert 'document.getElementById("agent-workbench-panel")' in script

def test_frontend_exposes_plan_first_operator_controls():
    script = (AGENT_ROOT / "js" / "agent-workbench.js").read_text()

    assert "/agent/context" in script
    assert "/agent/plan" in script
    assert "/agent/apply" in script
    assert "currentGraphSnapshot" in script
    assert "agent-workbench-confirm" in script
    assert "agent-workbench-cancel" in script
    assert "user_cancelled" in script
    assert "requires_confirmation" in script
    assert "plan.confirmed" in script


def test_frontend_graph_snapshot_includes_slots_for_connection_planning():
    script = (AGENT_ROOT / "js" / "agent-workbench.js").read_text()

    assert "slotRows" in script
    assert "mode: node.mode" in script
    assert "inputs: slotRows(node.inputs)" in script
    assert "outputs: slotRows(node.outputs)" in script
    assert "type: slot.type" in script


def test_frontend_styles_plan_apply_and_confirmation_states():
    stylesheet = (AGENT_ROOT / "js" / "agent-workbench.css").read_text()

    assert ".agent-workbench-actions" in stylesheet
    assert "#agent-workbench-panel button:disabled" in stylesheet
    assert ".agent-workbench-confirm[hidden]" in stylesheet
    assert "#agent-workbench-cancel:not([hidden])" in stylesheet


def test_frontend_wires_graph_actions_after_server_approval():
    script = (AGENT_ROOT / "js" / "agent-workbench.js").read_text()
    graph_actions = (AGENT_ROOT / "js" / "graph-actions.js").read_text()

    assert 'import { applyGraphActions } from "./graph-actions.js";' in script
    assert "if (result.ok)" in script
    assert "result.browser_applied = applyGraphActions(lastDryRun.plan.actions)" in script
    assert "browser_error" in script
    assert "executeFrontendRequest" in script
    assert "manager_request" in script
    assert "http_request" in script
    assert 'action.type === "graph.set_widget"' in graph_actions
    assert 'action.type === "graph.add_node"' in graph_actions
    assert 'action.type === "graph.connect"' in graph_actions
    assert 'action.type === "graph.delete_node"' in graph_actions
    assert 'action.type === "graph.set_mode"' in graph_actions
    assert 'action.type === "graph.set_title"' in graph_actions
    assert 'action.type === "graph.set_position"' in graph_actions
    assert 'action.type === "graph.disconnect"' in graph_actions
    assert "app.graph.getNodeById" in graph_actions
    assert "globalThis.LiteGraph.createNode" in graph_actions
    assert ".connect(" in graph_actions
    assert ".disconnectInput(" in graph_actions
    assert "matchingLinks(" in graph_actions
    assert "graph.remove(node)" in graph_actions
    assert "node.mode =" in graph_actions
    assert "node.title =" in graph_actions
    assert "node.pos =" in graph_actions
    assert "globalThis.LiteGraph.BYPASS" in graph_actions
    assert "app.graph.setDirtyCanvas(true, true)" in graph_actions
