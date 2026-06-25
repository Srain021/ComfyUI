import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
AGENT_ROOT = REPO_ROOT / "custom_nodes" / "ComfyUI-AgentWorkbench"
sys.path.insert(0, str(AGENT_ROOT))

from agent_workbench.planner import RuleBasedPlanner, default_planner


def test_rule_planner_free_memory():
    plan = RuleBasedPlanner().plan("释放内存", context={})

    assert plan["actions"][0]["type"] == "runtime.free_memory"
    assert plan["actions"][0]["payload"] == {"unload_models": True, "free_memory": True}


def test_rule_planner_reserve_vram():
    plan = RuleBasedPlanner().plan("把 compose reserve-vram 改到 10", context={})

    assert plan["actions"][0]["type"] == "compose.set_reserve_vram"
    assert plan["actions"][0]["payload"]["value"] == "10"


def test_rule_planner_defaults_to_context_inspection():
    plan = RuleBasedPlanner().plan("看看当前工作流", context={"ignored": True})

    assert plan["actions"] == [
        {"type": "context.collect", "payload": {"message": "看看当前工作流"}}
    ]


def test_default_planner_falls_back_to_rules_for_unknown_provider(monkeypatch):
    monkeypatch.setenv("AGENT_WORKBENCH_PROVIDER", "not-yet-implemented")

    assert isinstance(default_planner(), RuleBasedPlanner)
