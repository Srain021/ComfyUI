import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
AGENT_ROOT = REPO_ROOT / "custom_nodes" / "ComfyUI-AgentWorkbench"
sys.path.insert(0, str(AGENT_ROOT))

from agent_workbench.context import collect_context


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
