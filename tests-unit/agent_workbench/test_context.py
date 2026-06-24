import asyncio
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
AGENT_ROOT = REPO_ROOT / "custom_nodes" / "ComfyUI-AgentWorkbench"
sys.path.insert(0, str(AGENT_ROOT))

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


def test_collect_context_tolerates_malformed_graph_shapes(tmp_path):
    empty_context = collect_context(tmp_path, graph=["not", "a", "dict"])

    assert empty_context["graph"] == {
        "node_count": 0,
        "link_count": 0,
        "selected_node_ids": [],
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
        "link_count": 0,
        "selected_node_ids": [1],
    }


def test_collect_context_bounds_workflow_scan_effort(tmp_path):
    workflows = tmp_path / "user" / "default" / "workflows"
    workflows.mkdir(parents=True)
    for index in range(6):
        (workflows / f"wf-{index}.json").write_text("{}", encoding="utf-8")

    context = collect_context(tmp_path, max_workflows=2, max_workflow_scan_entries=3)

    assert len(context["workflows"]) <= 2
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
