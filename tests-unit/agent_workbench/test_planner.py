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


def test_rule_planner_sets_selected_prompt_widget_from_natural_language():
    plan = RuleBasedPlanner().plan(
        "把这个 prompt 节点的文本改成 cinematic lighting",
        context={
            "graph_input": {
                "nodes": [
                    {
                        "id": 12,
                        "type": "CLIPTextEncode",
                        "title": "Prompt",
                        "selected": True,
                        "widgets": [{"name": "text", "value": "old"}],
                    }
                ]
            }
        },
    )

    assert plan["actions"] == [
        {
            "type": "graph.set_widget",
            "payload": {"node_id": 12, "widget": "text", "value": "cinematic lighting"},
        }
    ]


def test_rule_planner_sets_widget_by_node_id():
    plan = RuleBasedPlanner().plan(
        "把 12 号节点的 prompt 改成 hello world",
        context={
            "graph_input": {
                "nodes": [
                    {
                        "id": 12,
                        "type": "CLIPTextEncode",
                        "title": "Positive Prompt",
                        "widgets": [{"name": "text", "value": "old"}],
                    }
                ]
            }
        },
    )

    assert plan["actions"][0]["type"] == "graph.set_widget"
    assert plan["actions"][0]["payload"] == {
        "node_id": 12,
        "widget": "text",
        "value": "hello world",
    }


def test_rule_planner_sets_widget_by_node_title():
    plan = RuleBasedPlanner().plan(
        "把 Positive Prompt 的 text 设置为 soft daylight",
        context={
            "graph_input": {
                "nodes": [
                    {
                        "id": 7,
                        "type": "CLIPTextEncode",
                        "title": "Positive Prompt",
                        "widgets": [{"name": "text", "value": "old"}],
                    }
                ]
            }
        },
    )

    assert plan["actions"][0]["payload"] == {
        "node_id": 7,
        "widget": "text",
        "value": "soft daylight",
    }


def test_rule_planner_coerces_numeric_widget_values():
    plan = RuleBasedPlanner().plan(
        "把 KSampler 的 steps 改成 28",
        context={
            "graph_input": {
                "nodes": [
                    {
                        "id": 9,
                        "type": "KSampler",
                        "title": "KSampler",
                        "widgets": [
                            {"name": "steps", "value": 20},
                            {"name": "cfg", "value": 7.0},
                        ],
                    }
                ]
            }
        },
    )

    assert plan["actions"][0]["payload"] == {
        "node_id": 9,
        "widget": "steps",
        "value": 28,
    }


def test_rule_planner_sets_multiple_widgets_on_same_node():
    plan = RuleBasedPlanner().plan(
        "把 KSampler 的 steps 改成 28，cfg 改成 7.5，seed 改成 12345",
        context={
            "graph_input": {
                "nodes": [
                    {
                        "id": 9,
                        "type": "KSampler",
                        "title": "KSampler",
                        "widgets": [
                            {"name": "steps", "value": 20},
                            {"name": "cfg", "value": 7.0},
                            {"name": "seed", "value": 1},
                        ],
                    }
                ]
            }
        },
    )

    assert plan["actions"] == [
        {"type": "graph.set_widget", "payload": {"node_id": 9, "widget": "steps", "value": 28}},
        {"type": "graph.set_widget", "payload": {"node_id": 9, "widget": "cfg", "value": 7.5}},
        {"type": "graph.set_widget", "payload": {"node_id": 9, "widget": "seed", "value": 12345}},
    ]


def test_rule_planner_adds_node_from_natural_language():
    plan = RuleBasedPlanner().plan("添加一个 KSampler 节点", context={"graph_input": {"nodes": []}})

    assert plan["actions"] == [{"type": "graph.add_node", "payload": {"node_type": "KSampler"}}]


def test_rule_planner_adds_node_with_initial_prompt_widget():
    plan = RuleBasedPlanner().plan(
        "添加一个 CLIPTextEncode 节点，prompt 改成 cinematic lighting",
        context={"graph_input": {"nodes": []}},
    )

    assert plan["actions"] == [
        {
            "type": "graph.add_node",
            "payload": {
                "node_type": "CLIPTextEncode",
                "widgets": {"text": "cinematic lighting"},
            },
        }
    ]


def test_rule_planner_connects_two_nodes_by_id():
    plan = RuleBasedPlanner().plan(
        "把 1 号节点连接到 2 号节点",
        context={
            "graph_input": {
                "nodes": [
                    {"id": 1, "type": "CheckpointLoaderSimple", "title": "Checkpoint"},
                    {"id": 2, "type": "KSampler", "title": "KSampler"},
                ]
            }
        },
    )

    assert plan["actions"] == [
        {
            "type": "graph.connect",
            "payload": {
                "origin_node_id": 1,
                "origin_slot": 0,
                "target_node_id": 2,
                "target_slot": 0,
            },
        }
    ]


def test_rule_planner_connects_nodes_by_title_and_slot_names():
    plan = RuleBasedPlanner().plan(
        "把 Checkpoint 的 MODEL 连接到 KSampler 的 model",
        context={
            "graph_input": {
                "nodes": [
                    {
                        "id": 1,
                        "type": "CheckpointLoaderSimple",
                        "title": "Checkpoint",
                        "outputs": [
                            {"name": "MODEL", "type": "MODEL"},
                            {"name": "CLIP", "type": "CLIP"},
                            {"name": "VAE", "type": "VAE"},
                        ],
                    },
                    {
                        "id": 2,
                        "type": "KSampler",
                        "title": "KSampler",
                        "inputs": [
                            {"name": "model", "type": "MODEL"},
                            {"name": "positive", "type": "CONDITIONING"},
                            {"name": "negative", "type": "CONDITIONING"},
                        ],
                    },
                ]
            }
        },
    )

    assert plan["actions"] == [
        {
            "type": "graph.connect",
            "payload": {
                "origin_node_id": 1,
                "origin_slot": 0,
                "target_node_id": 2,
                "target_slot": 0,
            },
        }
    ]


def test_rule_planner_connects_clip_to_prompt_by_slot_names():
    plan = RuleBasedPlanner().plan(
        "把 Checkpoint 的 CLIP 连到 Positive Prompt 的 clip",
        context={
            "graph_input": {
                "nodes": [
                    {
                        "id": 1,
                        "type": "CheckpointLoaderSimple",
                        "title": "Checkpoint",
                        "outputs": [
                            {"name": "MODEL", "type": "MODEL"},
                            {"name": "CLIP", "type": "CLIP"},
                        ],
                    },
                    {
                        "id": 3,
                        "type": "CLIPTextEncode",
                        "title": "Positive Prompt",
                        "inputs": [{"name": "clip", "type": "CLIP"}],
                    },
                ]
            }
        },
    )

    assert plan["actions"][0]["payload"] == {
        "origin_node_id": 1,
        "origin_slot": 1,
        "target_node_id": 3,
        "target_slot": 0,
    }


def test_rule_planner_plans_restart_container():
    plan = RuleBasedPlanner().plan("重启 ComfyUI 容器", context={})

    assert plan["actions"] == [
        {"type": "service.restart_container", "payload": {"container": "comfyui-gb10"}}
    ]


def test_rule_planner_plans_stop_ollama_model():
    plan = RuleBasedPlanner().plan("停止 ollama 模型 nemotron-3-nano:30b", context={})

    assert plan["actions"] == [
        {"type": "runtime.stop_ollama_model", "payload": {"model": "nemotron-3-nano:30b"}}
    ]


def test_rule_planner_prints_sudo_for_ollama_service_stop():
    plan = RuleBasedPlanner().plan("彻底停止 ollama 服务", context={})

    assert plan["actions"][0]["type"] == "sudo.print_command"
    assert plan["actions"][0]["payload"]["command"] == "sudo systemctl stop ollama"
    assert "ollama" in plan["actions"][0]["payload"]["why"].lower()


def test_rule_planner_prints_sudo_for_gpu_clock_lock():
    plan = RuleBasedPlanner().plan("锁频防止断电", context={})

    assert plan["actions"][0]["type"] == "sudo.print_command"
    assert plan["actions"][0]["payload"]["command"] == "sudo nvidia-smi -lgc 300,2100"
    assert "clock" in plan["actions"][0]["payload"]["why"].lower()


def test_rule_planner_plans_compose_up_to_apply_config():
    plan = RuleBasedPlanner().plan("应用 compose 配置并重建 ComfyUI 服务", context={})

    assert plan["actions"] == [{"type": "service.compose_up", "payload": {}}]


def test_rule_planner_plans_custom_node_install_from_git_url():
    plan = RuleBasedPlanner().plan(
        "安装 custom node https://github.com/example/ComfyUI-TestNode.git",
        context={},
    )

    assert plan["actions"] == [
        {
            "type": "custom_node.install",
            "payload": {
                "method": "git_url",
                "url": "https://github.com/example/ComfyUI-TestNode.git",
            },
        }
    ]


def test_rule_planner_plans_custom_node_disable_and_enable():
    disable_plan = RuleBasedPlanner().plan("禁用 custom node ComfyUI-TestNode", context={})
    enable_plan = RuleBasedPlanner().plan("启用 custom node ComfyUI-TestNode", context={})

    assert disable_plan["actions"] == [
        {"type": "custom_node.disable", "payload": {"id": "ComfyUI-TestNode"}}
    ]
    assert enable_plan["actions"] == [
        {"type": "custom_node.enable", "payload": {"id": "ComfyUI-TestNode"}}
    ]


def test_rule_planner_prints_sudo_swapoff_instead_of_executing():
    plan = RuleBasedPlanner().plan("关 swap 防止卡死", context={})

    assert plan["actions"][0]["type"] == "sudo.print_command"
    assert plan["actions"][0]["payload"]["command"] == "sudo swapoff -a"
    assert "swap" in plan["actions"][0]["payload"]["why"].lower()


def test_rule_planner_defaults_to_context_inspection():
    plan = RuleBasedPlanner().plan("看看当前工作流", context={"ignored": True})

    assert plan["actions"] == [
        {"type": "context.collect", "payload": {"message": "看看当前工作流"}}
    ]


def test_default_planner_falls_back_to_rules_for_unknown_provider(monkeypatch):
    monkeypatch.setenv("AGENT_WORKBENCH_PROVIDER", "not-yet-implemented")

    assert isinstance(default_planner(), RuleBasedPlanner)
