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


def test_register_routes_adds_smoke_manifest_get_route_for_windows_manual_checks():
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

        response = asyncio.run(
            routes_by_key[("GET", "/agent/smoke_manifest")].handler(_FakeRequest())
        )
        payload = json.loads(response.text)

        assert payload["ok"] is True
        assert payload["surface"] == "windows_browser"
        assert [step["id"] for step in payload["manual_steps"]][:5] == [
            "context",
            "plan_prompt_edit",
            "confirm_elevated",
            "cancel_plan",
            "apply_prompt_edit",
        ]
        assert payload["sample_prompts"]["prompt_edit"] == "把这个 prompt 节点的文本更新成 glowing blue forest"
        assert payload["sample_prompts"]["custom_node_restart"] == "安装当前工作流缺失节点然后重启 ComfyUI"
        assert payload["sample_prompts"]["print_sudo"] == "关 swap 防止卡死"
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
            "status": "applied",
            "applied": [
                {
                    "type": "context.collect",
                    "applied": False,
                    "reason": "context action is read-only",
                }
            ],
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


def test_register_routes_adds_apply_deferred_route(monkeypatch):
    agent_routes._REGISTERED = False
    fake_prompt_server = types.SimpleNamespace(routes=web.RouteTableDef())
    calls = []

    def fake_apply_deferred_action(plan, approved_hash, action_index, root, browser_workflow=None):
        calls.append(
            {
                "plan": plan,
                "approved_hash": approved_hash,
                "action_index": action_index,
                "root": root,
                "browser_workflow": browser_workflow,
            }
        )
        return {"ok": True, "status": "applied", "applied": {"type": "service.restart_container"}}

    monkeypatch.setattr(agent_routes, "apply_deferred_action", fake_apply_deferred_action)

    try:
        agent_routes.register_routes(fake_prompt_server)

        app = web.Application()
        app.add_routes(fake_prompt_server.routes)
        routes_by_key = {
            (route.method, route.resource.canonical): route
            for route in app.router.routes()
        }

        response = asyncio.run(
            routes_by_key[("POST", "/agent/apply-deferred")].handler(
                _FakeRequest(
                    decoded_body={
                        "plan": {"summary": "restart", "actions": []},
                        "approved_hash": "hash",
                        "action_index": 1,
                    }
                )
            )
        )

        assert json.loads(response.text)["ok"] is True
        assert calls[0]["approved_hash"] == "hash"
        assert calls[0]["action_index"] == 1
    finally:
        agent_routes._REGISTERED = False


def test_apply_route_runs_blocking_dispatch_outside_event_loop(monkeypatch):
    agent_routes._REGISTERED = False
    fake_prompt_server = types.SimpleNamespace(routes=web.RouteTableDef())

    def fake_apply_plan(plan, approved_hash, root, browser_workflow=None):
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return {"ok": True, "threaded": True}
        return {"ok": False, "threaded": False}

    monkeypatch.setattr(agent_routes, "apply_plan", fake_apply_plan)

    try:
        agent_routes.register_routes(fake_prompt_server)

        app = web.Application()
        app.add_routes(fake_prompt_server.routes)
        routes_by_key = {
            (route.method, route.resource.canonical): route
            for route in app.router.routes()
        }

        response = asyncio.run(
            routes_by_key[("POST", "/agent/apply")].handler(
                _FakeRequest(
                    decoded_body={
                        "plan": {"summary": "health", "actions": []},
                        "approved_hash": "hash",
                    }
                )
            )
        )

        assert json.loads(response.text) == {"ok": True, "threaded": True}
    finally:
        agent_routes._REGISTERED = False


def test_apply_route_passes_browser_workflow_to_dispatch(monkeypatch):
    agent_routes._REGISTERED = False
    fake_prompt_server = types.SimpleNamespace(routes=web.RouteTableDef())
    calls = []

    def fake_apply_plan(plan, approved_hash, root, browser_workflow=None):
        calls.append(
            {
                "plan": plan,
                "approved_hash": approved_hash,
                "root": root,
                "browser_workflow": browser_workflow,
            }
        )
        return {"ok": True, "status": "applied", "applied": []}

    monkeypatch.setattr(agent_routes, "apply_plan", fake_apply_plan)

    try:
        agent_routes.register_routes(fake_prompt_server)

        app = web.Application()
        app.add_routes(fake_prompt_server.routes)
        routes_by_key = {
            (route.method, route.resource.canonical): route
            for route in app.router.routes()
        }

        response = asyncio.run(
            routes_by_key[("POST", "/agent/apply")].handler(
                _FakeRequest(
                    decoded_body={
                        "plan": {"summary": "save", "actions": []},
                        "approved_hash": "hash",
                        "browser_workflow": {"nodes": [{"id": 12}]},
                    }
                )
            )
        )

        assert json.loads(response.text)["ok"] is True
        assert calls[0]["browser_workflow"] == {"nodes": [{"id": 12}]}
    finally:
        agent_routes._REGISTERED = False


def test_apply_deferred_route_passes_browser_workflow_to_dispatch(monkeypatch):
    agent_routes._REGISTERED = False
    fake_prompt_server = types.SimpleNamespace(routes=web.RouteTableDef())
    calls = []

    def fake_apply_deferred_action(plan, approved_hash, action_index, root, browser_workflow=None):
        calls.append(
            {
                "plan": plan,
                "approved_hash": approved_hash,
                "action_index": action_index,
                "root": root,
                "browser_workflow": browser_workflow,
            }
        )
        return {"ok": True, "status": "applied", "applied": {"type": "workflow.save"}}

    monkeypatch.setattr(agent_routes, "apply_deferred_action", fake_apply_deferred_action)

    try:
        agent_routes.register_routes(fake_prompt_server)

        app = web.Application()
        app.add_routes(fake_prompt_server.routes)
        routes_by_key = {
            (route.method, route.resource.canonical): route
            for route in app.router.routes()
        }

        response = asyncio.run(
            routes_by_key[("POST", "/agent/apply-deferred")].handler(
                _FakeRequest(
                    decoded_body={
                        "plan": {"summary": "save", "actions": []},
                        "approved_hash": "hash",
                        "action_index": 1,
                        "browser_workflow": {"nodes": [{"id": 12, "widgets_values": ["neon"]}]},
                    }
                )
            )
        )

        assert json.loads(response.text)["ok"] is True
        assert calls[0]["browser_workflow"] == {
            "nodes": [{"id": 12, "widgets_values": ["neon"]}]
        }
    finally:
        agent_routes._REGISTERED = False


def test_register_routes_adds_agent_plan_route():
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

        response = asyncio.run(
            routes_by_key[("POST", "/agent/plan")].handler(
                _FakeRequest(decoded_body={"message": "释放内存", "graph": {"nodes": []}})
            )
        )
        payload = json.loads(response.text)

        assert payload["status"] == "dry_run"
        assert payload["plan"]["actions"][0]["type"] == "runtime.free_memory"
        assert payload["plan"]["requires_confirmation"] is True
    finally:
        agent_routes._REGISTERED = False


def test_agent_message_route_returns_plan_for_actionable_prompt():
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

        response = asyncio.run(
            routes_by_key[("POST", "/agent/message")].handler(
                _FakeRequest(decoded_body={"message": "释放内存", "graph": {"nodes": []}})
            )
        )
        payload = json.loads(response.text)

        assert payload["status"] == "dry_run"
        assert payload["plan"]["actions"][0]["type"] == "runtime.free_memory"
        assert payload["plan"]["requires_confirmation"] is True
    finally:
        agent_routes._REGISTERED = False


def test_agent_message_route_returns_ai_status_for_conversation(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("AGENT_WORKBENCH_OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("AGENT_WORKBENCH_LLM_ENDPOINT", raising=False)
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

        response = asyncio.run(
            routes_by_key[("POST", "/agent/message")].handler(
                _FakeRequest(
                    decoded_body={
                        "message": "介绍一下你自己",
                        "graph": {"nodes": [{"id": 1, "type": "KSampler"}]},
                    }
                )
            )
        )
        payload = json.loads(response.text)

        assert payload["status"] == "ai_unavailable"
        assert payload["ok"] is False
        assert "Codex" in payload["assistant"]["message"]
        assert payload["dry_run"]["plan"]["actions"][0]["type"] == "context.collect"
    finally:
        agent_routes._REGISTERED = False


def test_agent_message_route_passes_history_and_attachments_to_llm(monkeypatch):
    agent_routes._REGISTERED = False
    fake_prompt_server = types.SimpleNamespace(routes=web.RouteTableDef())
    calls = []

    def fake_build_assistant_reply(message, context, dry_run, history=None, attachments=None):
        calls.append(
            {
                "message": message,
                "history": history,
                "attachments": attachments,
                "dry_run": dry_run,
                "context": context,
            }
        )
        return {
            "ok": True,
            "status": "assistant_reply",
            "assistant": {"title": "ComfyUI Codex Agent", "message": "我看到了附件。"},
        }

    monkeypatch.setattr(agent_routes, "build_assistant_reply", fake_build_assistant_reply)

    try:
        agent_routes.register_routes(fake_prompt_server)

        app = web.Application()
        app.add_routes(fake_prompt_server.routes)
        routes_by_key = {
            (route.method, route.resource.canonical): route
            for route in app.router.routes()
        }

        response = asyncio.run(
            routes_by_key[("POST", "/agent/message")].handler(
                _FakeRequest(
                    decoded_body={
                        "message": "描述这张图",
                        "graph": {"nodes": [{"id": 1, "type": "KSampler"}]},
                        "history": [{"role": "user", "text": "上一轮"}],
                        "attachments": [
                            {
                                "kind": "image",
                                "name": "workflow.png",
                                "mime": "image/png",
                                "data_url": "data:image/png;base64,aW1n",
                            }
                        ],
                    }
                )
            )
        )
        payload = json.loads(response.text)

        assert payload["status"] == "assistant_reply"
        assert calls[0]["message"] == "描述这张图"
        assert calls[0]["history"] == [{"role": "user", "text": "上一轮"}]
        assert calls[0]["attachments"][0]["name"] == "workflow.png"
        assert calls[0]["dry_run"]["plan"]["actions"][0]["type"] == "context.collect"
    finally:
        agent_routes._REGISTERED = False


def test_agent_plan_route_passes_graph_snapshot_to_planner():
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

        response = asyncio.run(
            routes_by_key[("POST", "/agent/plan")].handler(
                _FakeRequest(
                    decoded_body={
                        "message": "把这个 prompt 节点的文本改成 cinematic lighting",
                        "graph": {
                            "nodes": [
                                {
                                    "id": 12,
                                    "type": "CLIPTextEncode",
                                    "title": "Prompt",
                                    "selected": True,
                                    "widgets": [{"name": "text", "value": "old"}],
                                }
                            ],
                            "links": [],
                        },
                    }
                )
            )
        )
        payload = json.loads(response.text)

        assert payload["status"] == "dry_run"
        assert payload["plan"]["actions"][0]["type"] == "graph.set_widget"
        assert payload["plan"]["actions"][0]["payload"] == {
            "node_id": 12,
            "widget": "text",
            "value": "cinematic lighting",
        }
        assert payload["plan"]["requires_confirmation"] is False
    finally:
        agent_routes._REGISTERED = False


def test_agent_plan_route_preserves_registered_node_types_for_planner():
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

        response = asyncio.run(
            routes_by_key[("POST", "/agent/plan")].handler(
                _FakeRequest(
                    decoded_body={
                        "message": "添加一个 Save Image 节点",
                        "graph": {
                            "nodes": [],
                            "links": [],
                            "node_types": [{"type": "SaveImage", "title": "Save Image"}],
                        },
                    }
                )
            )
        )
        payload = json.loads(response.text)

        assert payload["status"] == "dry_run"
        assert payload["plan"]["actions"][0]["type"] == "graph.add_node"
        assert payload["plan"]["actions"][0]["payload"] == {"node_type": "SaveImage"}
    finally:
        agent_routes._REGISTERED = False


def test_agent_plan_route_preserves_registered_node_type_outputs_for_new_node_connections():
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

        response = asyncio.run(
            routes_by_key[("POST", "/agent/plan")].handler(
                _FakeRequest(
                    decoded_body={
                        "message": "添加一个正向提示词节点，内容写成 neon skyline，并把它接到 KSampler 的 positive",
                        "graph": {
                            "nodes": [
                                {
                                    "id": 9,
                                    "type": "KSampler",
                                    "title": "KSampler",
                                    "inputs": [
                                        {"name": "model", "type": "MODEL"},
                                        {"name": "positive", "type": "CONDITIONING"},
                                        {"name": "negative", "type": "CONDITIONING"},
                                    ],
                                }
                            ],
                            "links": [],
                            "node_types": [
                                {
                                    "type": "CLIPTextEncode",
                                    "title": "CLIP Text Encode",
                                    "outputs": [
                                        {"name": "CONDITIONING", "type": "CONDITIONING"}
                                    ],
                                }
                            ],
                        },
                    }
                )
            )
        )
        payload = json.loads(response.text)

        assert payload["status"] == "dry_run"
        assert payload["plan"]["actions"] == [
            {
                "type": "graph.add_node",
                "payload": {
                    "node_type": "CLIPTextEncode",
                    "title": "Positive Prompt",
                    "widgets": {"text": "neon skyline"},
                    "ref": "new_node",
                },
                "capability": "graph.edit",
                "risk_level": "canvas",
            },
            {
                "type": "graph.connect",
                "payload": {
                    "origin_node_ref": "new_node",
                    "origin_slot": 0,
                    "target_node_id": 9,
                    "target_slot": 1,
                },
                "capability": "graph.edit",
                "risk_level": "canvas",
            },
        ]
    finally:
        agent_routes._REGISTERED = False


def test_agent_plan_route_accepts_context_graph_input_for_agent_callers():
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

        response = asyncio.run(
            routes_by_key[("POST", "/agent/plan")].handler(
                _FakeRequest(
                    decoded_body={
                        "message": "把 KSampler 的重绘幅度改成 0.55",
                        "context": {
                            "graph_input": {
                                "nodes": [
                                    {
                                        "id": 9,
                                        "type": "KSampler",
                                        "title": "KSampler",
                                        "widgets": [
                                            {"name": "steps", "value": 20},
                                            {"name": "cfg", "value": 7.0},
                                            {"name": "denoise", "value": 1.0},
                                        ],
                                    }
                                ],
                                "links": [],
                            }
                        },
                    }
                )
            )
        )
        payload = json.loads(response.text)

        assert payload["status"] == "dry_run"
        assert payload["plan"]["actions"][0]["type"] == "graph.set_widget"
        assert payload["plan"]["actions"][0]["payload"] == {
            "node_id": 9,
            "widget": "denoise",
            "value": 0.55,
        }
    finally:
        agent_routes._REGISTERED = False
