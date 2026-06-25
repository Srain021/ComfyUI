import asyncio
import json
import sys
import types
from pathlib import Path

from aiohttp import web


REPO_ROOT = Path(__file__).resolve().parents[2]
AGENT_ROOT = REPO_ROOT / "custom_nodes" / "ComfyUI-AgentWorkbench"
sys.path.insert(0, str(AGENT_ROOT))

from agent_workbench import routes as agent_routes
from agent_workbench.context import collect_context
from agent_workbench.routes import _json_request


def test_collect_context_bounds_workflows_and_custom_nodes(tmp_path):
    (tmp_path / "custom_nodes" / "NodeA").mkdir(parents=True)
    (tmp_path / "custom_nodes" / "NodeB.disabled").mkdir(parents=True)
    workflows = tmp_path / "user" / "default" / "workflows"
    workflows.mkdir(parents=True)
    for index in range(3):
        (workflows / f"wf-{index}.json").write_text("{}", encoding="utf-8")

    context = collect_context(
        tmp_path,
        graph={"nodes": [{"id": 1, "type": "KSampler"}]},
        max_workflows=2,
    )

    assert context["graph"]["node_count"] == 1
    assert context["custom_nodes"][0]["name"] == "NodeA"
    assert context["custom_nodes"][0]["state"] == "enabled"
    assert context["custom_nodes"][1]["state"] == "disabled"
    assert len(context["workflows"]) == 2
    assert context["workflows_truncated"] is True
    assert context["custom_nodes_truncated"] is False


def test_collect_context_reports_disabled_node_forms_and_skips_hidden_entries(tmp_path):
    custom_nodes = tmp_path / "custom_nodes"
    (custom_nodes / "EnabledNode").mkdir(parents=True)
    (custom_nodes / "NodeB.disabled").mkdir()
    (custom_nodes / ".disabled" / "ManagerDisabled").mkdir(parents=True)
    (custom_nodes / ".hidden").mkdir()
    (custom_nodes / "__pycache__").mkdir()

    context = collect_context(tmp_path)
    rows = {row["name"]: row for row in context["custom_nodes"]}

    assert rows["EnabledNode"]["state"] == "enabled"
    assert rows["NodeB"]["state"] == "disabled"
    assert rows["ManagerDisabled"]["state"] == "disabled"
    assert rows["ManagerDisabled"]["path"] == "custom_nodes/.disabled/ManagerDisabled"
    assert ".hidden" not in rows
    assert "__pycache__" not in rows
    assert context["custom_nodes_truncated"] is False


def test_collect_context_bounds_custom_node_response(tmp_path):
    custom_nodes = tmp_path / "custom_nodes"
    custom_nodes.mkdir(parents=True)
    for index in range(5):
        (custom_nodes / f"Node{index}").mkdir()

    context = collect_context(
        tmp_path,
        max_custom_nodes=2,
        max_custom_node_scan_entries=10,
    )

    assert len(context["custom_nodes"]) == 2
    assert context["custom_nodes_truncated"] is True


def test_collect_context_counts_non_node_entries_toward_custom_node_scan_limit(tmp_path):
    custom_nodes = tmp_path / "custom_nodes"
    custom_nodes.mkdir(parents=True)
    for index in range(8):
        (custom_nodes / f"aaa-{index}.txt").write_text("noise", encoding="utf-8")
    (custom_nodes / "zzzNode").mkdir()

    context = collect_context(
        tmp_path,
        max_custom_nodes=10,
        max_custom_node_scan_entries=3,
    )

    assert context["custom_nodes"] == []
    assert context["custom_nodes_truncated"] is True


def test_collect_context_tolerates_malformed_graph_shapes(tmp_path):
    empty_context = collect_context(tmp_path, graph=["not", "a", "dict"])

    assert empty_context["graph"] == {
        "node_count": 0,
        "node_count_truncated": False,
        "link_count": 0,
        "links_truncated": False,
        "selected_node_ids": [],
        "selected_node_ids_truncated": False,
    }

    mixed_context = collect_context(
        tmp_path,
        graph={
            "nodes": [
                {"id": 1, "selected": True},
                "bad-node",
                {"id": 2, "selected": False},
            ],
            "links": "bad-links",
        },
    )

    assert mixed_context["graph"] == {
        "node_count": 2,
        "node_count_truncated": False,
        "link_count": 0,
        "links_truncated": False,
        "selected_node_ids": [1],
        "selected_node_ids_truncated": False,
    }


def test_collect_context_bounds_graph_metadata(tmp_path):
    graph = {
        "nodes": [
            {"id": index, "selected": True}
            for index in range(8)
        ],
        "links": list(range(6)),
    }

    context = collect_context(
        tmp_path,
        graph=graph,
        max_graph_nodes=4,
        max_selected_node_ids=2,
        max_graph_links=3,
    )

    assert context["graph"] == {
        "node_count": 4,
        "node_count_truncated": True,
        "link_count": 3,
        "links_truncated": True,
        "selected_node_ids": [0, 1],
        "selected_node_ids_truncated": True,
    }


def test_collect_context_bounds_workflow_scan_effort(tmp_path):
    workflows = tmp_path / "user" / "default" / "workflows"
    workflows.mkdir(parents=True)
    for index in range(6):
        (workflows / f"wf-{index}.json").write_text("{}", encoding="utf-8")

    context = collect_context(tmp_path, max_workflows=2, max_workflow_scan_entries=3)

    assert len(context["workflows"]) <= 2
    assert context["workflows_truncated"] is True


def test_collect_context_counts_non_json_entries_toward_scan_limit(tmp_path):
    workflows = tmp_path / "user" / "default" / "workflows"
    workflows.mkdir(parents=True)
    for index in range(8):
        (workflows / f"aaa-{index}.txt").write_text("noise", encoding="utf-8")
    (workflows / "zzz-workflow.json").write_text("{}", encoding="utf-8")

    context = collect_context(tmp_path, max_workflows=5, max_workflow_scan_entries=3)

    assert context["workflows"] == []
    assert context["workflows_truncated"] is True


def test_collect_context_skips_workflow_stat_failures(tmp_path):
    workflows = tmp_path / "user" / "default" / "workflows"
    workflows.mkdir(parents=True)
    (workflows / "ok.json").write_text("{}", encoding="utf-8")
    (workflows / "broken.json").symlink_to(workflows / "missing.json")

    context = collect_context(tmp_path, max_workflows=5)

    assert context["workflows"] == [
        {"path": "user/default/workflows/ok.json", "bytes": 2}
    ]


class _FakeRequest:
    def __init__(self, decoded_body=None, error=None, can_read_body=True):
        self._decoded_body = decoded_body
        self._error = error
        self.can_read_body = can_read_body

    async def json(self):
        if self._error:
            raise self._error
        return self._decoded_body


def test_json_request_normalizes_invalid_and_non_object_bodies():
    assert asyncio.run(_json_request(_FakeRequest(decoded_body=["not", "dict"]))) == {}
    assert asyncio.run(_json_request(_FakeRequest(error=ValueError("bad json")))) == {}
    assert asyncio.run(_json_request(_FakeRequest(can_read_body=False))) == {}


def test_register_routes_adds_agent_context_post_route():
    agent_routes._REGISTERED = False
    fake_prompt_server = types.SimpleNamespace(routes=web.RouteTableDef())

    try:
        agent_routes.register_routes(fake_prompt_server)

        app = web.Application()
        app.add_routes(fake_prompt_server.routes)
        matches = [
            route
            for route in app.router.routes()
            if route.method == "POST" and route.resource.canonical == "/agent/context"
        ]

        assert len(matches) == 1
        response = asyncio.run(
            matches[0].handler(
                _FakeRequest(decoded_body={"graph": {"nodes": [{"id": 1}]}})
            )
        )
        payload = json.loads(response.text)
        assert payload["graph"]["node_count"] == 1
        assert "custom_nodes" in payload
        assert "custom_nodes_truncated" in payload

        malformed_response = asyncio.run(
            matches[0].handler(_FakeRequest(decoded_body=["not", "a", "dict"]))
        )
        malformed_payload = json.loads(malformed_response.text)
        assert malformed_payload["graph"] == {
            "node_count": 0,
            "node_count_truncated": False,
            "link_count": 0,
            "links_truncated": False,
            "selected_node_ids": [],
            "selected_node_ids_truncated": False,
        }
    finally:
        agent_routes._REGISTERED = False


def test_register_routes_adds_dry_run_and_apply_routes():
    agent_routes._REGISTERED = False
    fake_prompt_server = types.SimpleNamespace(routes=web.RouteTableDef())

    try:
        agent_routes.register_routes(fake_prompt_server)

        app = web.Application()
        app.add_routes(fake_prompt_server.routes)
        routes_by_key = {
            (route.method, route.resource.canonical): route
            for route in app.router.routes()
        }

        dry_run_response = asyncio.run(
            routes_by_key[("POST", "/agent/dry-run")].handler(
                _FakeRequest(
                    decoded_body={
                        "summary": "inspect",
                        "actions": [{"type": "context.collect", "payload": {}}],
                    }
                )
            )
        )
        dry_run_payload = json.loads(dry_run_response.text)

        assert dry_run_payload["status"] == "dry_run"
        assert dry_run_payload["plan"]["plan_hash"]

        apply_response = asyncio.run(
            routes_by_key[("POST", "/agent/apply")].handler(
                _FakeRequest(
                    decoded_body={
                        "plan": dry_run_payload["plan"],
                        "approved_hash": dry_run_payload["plan"]["plan_hash"],
                    }
                )
            )
        )

        assert json.loads(apply_response.text) == {
            "ok": True,
            "status": "accepted",
            "applied": [],
        }

        invalid_response = asyncio.run(
            routes_by_key[("POST", "/agent/dry-run")].handler(
                _FakeRequest(decoded_body={"summary": "", "actions": []})
            )
        )

        assert invalid_response.status == 400
        assert json.loads(invalid_response.text)["ok"] is False
    finally:
        agent_routes._REGISTERED = False
