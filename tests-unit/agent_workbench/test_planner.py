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


def test_rule_planner_prerender_free_memory_uses_ops_script():
    plan = RuleBasedPlanner().plan("渲染前腾内存", context={})

    assert plan["actions"] == [{"type": "service.prerender_free_memory", "payload": {}}]
    assert plan["summary"] == "Run prerender free-memory preparation"


def test_rule_planner_prerender_free_memory_then_queues_workflow():
    plan = RuleBasedPlanner().plan("渲染前腾内存然后开始生成当前工作流", context={})

    assert plan["actions"] == [
        {"type": "service.prerender_free_memory", "payload": {}},
        {"type": "runtime.queue_prompt", "payload": {"front": False}},
    ]


def test_rule_planner_prerender_free_memory_then_queues_workflow_to_front():
    plan = RuleBasedPlanner().plan("开渲前释放内存并插队生成当前工作流", context={})

    assert plan["actions"] == [
        {"type": "service.prerender_free_memory", "payload": {}},
        {"type": "runtime.queue_prompt", "payload": {"front": True}},
    ]


def test_rule_planner_saves_current_workflow_from_browser_snapshot():
    plan = RuleBasedPlanner().plan("保存当前工作流到 agent/sample.json", context={})

    assert plan["actions"] == [
        {
            "type": "workflow.save",
            "payload": {"path": "agent/sample.json", "workflow_from_browser": True},
        }
    ]


def test_rule_planner_edits_prompt_then_saves_current_workflow():
    plan = RuleBasedPlanner().plan(
        "把这个 prompt 节点改成 neon skyline 然后保存当前工作流到 agent/prompt.json",
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
            "payload": {"node_id": 12, "widget": "text", "value": "neon skyline"},
        },
        {
            "type": "workflow.save",
            "payload": {"path": "agent/prompt.json", "workflow_from_browser": True},
        },
    ]


def test_rule_planner_updates_selected_prompt_text_with_update_phrase():
    plan = RuleBasedPlanner().plan(
        "把这个 prompt 节点的文本更新成 glowing blue forest",
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
            "payload": {"node_id": 12, "widget": "text", "value": "glowing blue forest"},
        }
    ]


def test_rule_planner_copies_seed_between_named_sampler_nodes():
    plan = RuleBasedPlanner().plan(
        "把 Base KSampler 的种子复制到 Refiner KSampler",
        context={
            "graph_input": {
                "nodes": [
                    {
                        "id": 9,
                        "type": "KSampler",
                        "title": "Base KSampler",
                        "widgets": [{"name": "seed", "value": 12345}],
                    },
                    {
                        "id": 10,
                        "type": "KSampler",
                        "title": "Refiner KSampler",
                        "widgets": [{"name": "seed", "value": 999}],
                    },
                ]
            }
        },
    )

    assert plan["actions"] == [
        {
            "type": "graph.set_widget",
            "payload": {"node_id": 10, "widget": "seed", "value": 12345},
        }
    ]


def test_rule_planner_copies_seed_from_first_sampler_without_duplicating_node():
    plan = RuleBasedPlanner().plan(
        "把第一个 KSampler 的种子复制到 Refiner KSampler",
        context={
            "graph_input": {
                "nodes": [
                    {
                        "id": 9,
                        "type": "KSampler",
                        "title": "Base KSampler",
                        "widgets": [{"name": "seed", "value": 12345}],
                    },
                    {
                        "id": 10,
                        "type": "KSampler",
                        "title": "Refiner KSampler",
                        "widgets": [{"name": "seed", "value": 999}],
                    },
                ]
            }
        },
    )

    assert plan["actions"] == [
        {
            "type": "graph.set_widget",
            "payload": {"node_id": 10, "widget": "seed", "value": 12345},
        }
    ]


def test_rule_planner_copies_named_sampler_widget_to_same_widget_on_target_node():
    plan = RuleBasedPlanner().plan(
        "把 Base KSampler 的 cfg 复制到 Refiner KSampler",
        context={
            "graph_input": {
                "nodes": [
                    {
                        "id": 9,
                        "type": "KSampler",
                        "title": "Base KSampler",
                        "widgets": [
                            {"name": "seed", "value": 12345},
                            {"name": "cfg", "value": 7.5},
                        ],
                    },
                    {
                        "id": 10,
                        "type": "KSampler",
                        "title": "Refiner KSampler",
                        "widgets": [
                            {"name": "seed", "value": 999},
                            {"name": "cfg", "value": 4.0},
                        ],
                    },
                ]
            }
        },
    )

    assert plan["actions"] == [
        {
            "type": "graph.set_widget",
            "payload": {"node_id": 10, "widget": "cfg", "value": 7.5},
        }
    ]


def test_rule_planner_copies_all_common_sampler_settings_to_target_node():
    plan = RuleBasedPlanner().plan(
        "把 Base KSampler 的设置复制到 Refiner KSampler",
        context={
            "graph_input": {
                "nodes": [
                    {
                        "id": 9,
                        "type": "KSampler",
                        "title": "Base KSampler",
                        "widgets": [
                            {"name": "seed", "value": 12345},
                            {"name": "steps", "value": 28},
                            {"name": "cfg", "value": 7.5},
                            {"name": "sampler_name", "value": "dpmpp_2m"},
                            {"name": "scheduler", "value": "karras"},
                            {"name": "denoise", "value": 0.45},
                        ],
                    },
                    {
                        "id": 10,
                        "type": "KSampler",
                        "title": "Refiner KSampler",
                        "widgets": [
                            {"name": "seed", "value": 999},
                            {"name": "steps", "value": 12},
                            {"name": "cfg", "value": 4.0},
                            {"name": "sampler_name", "value": "euler"},
                            {"name": "scheduler", "value": "normal"},
                            {"name": "denoise", "value": 0.7},
                            {"name": "control_after_generate", "value": "randomize"},
                        ],
                    },
                ]
            }
        },
    )

    assert plan["actions"] == [
        {"type": "graph.set_widget", "payload": {"node_id": 10, "widget": "seed", "value": 12345}},
        {"type": "graph.set_widget", "payload": {"node_id": 10, "widget": "steps", "value": 28}},
        {"type": "graph.set_widget", "payload": {"node_id": 10, "widget": "cfg", "value": 7.5}},
        {
            "type": "graph.set_widget",
            "payload": {"node_id": 10, "widget": "sampler_name", "value": "dpmpp_2m"},
        },
        {
            "type": "graph.set_widget",
            "payload": {"node_id": 10, "widget": "scheduler", "value": "karras"},
        },
        {"type": "graph.set_widget", "payload": {"node_id": 10, "widget": "denoise", "value": 0.45}},
    ]


def test_rule_planner_plans_service_healthcheck():
    plan = RuleBasedPlanner().plan("检查 ComfyUI 容器健康和内存", context={})

    assert plan["actions"] == [{"type": "service.healthcheck", "payload": {}}]
    assert plan["summary"] == "Check ComfyUI container health"


def test_rule_planner_reserve_vram():
    plan = RuleBasedPlanner().plan("把 compose reserve-vram 改到 10", context={})

    assert plan["actions"] == [
        {
            "type": "compose.set_command_value",
            "payload": {"flag": "--reserve-vram", "value": "10"},
        }
    ]


def test_rule_planner_plans_compose_command_value_from_flag_alias():
    plan = RuleBasedPlanner().plan("把 compose reserve-vram 改成 12 并应用配置", context={})

    assert plan["actions"] == [
        {
            "type": "compose.set_command_value",
            "payload": {"flag": "--reserve-vram", "value": "12"},
        }
    ]


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


def test_rule_planner_keeps_numeric_prompt_text_after_prompt_word():
    plan = RuleBasedPlanner().plan(
        "把这个 prompt 节点的文本改成 agent live smoke prompt 2026-06-25T18:00:00.000Z",
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
            "payload": {
                "node_id": 12,
                "widget": "text",
                "value": "agent live smoke prompt 2026-06-25T18:00:00.000Z",
            },
        }
    ]


def test_rule_planner_edits_prompt_then_queues_workflow():
    plan = RuleBasedPlanner().plan(
        "把这个 prompt 节点的文本改成 cinematic lighting 然后开始生成",
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
        },
        {"type": "runtime.queue_prompt", "payload": {"front": False}},
    ]


def test_rule_planner_edits_prompt_then_queues_workflow_at_front():
    plan = RuleBasedPlanner().plan(
        "把这个 prompt 节点改成 neon skyline 并插队生成",
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
            "payload": {"node_id": 12, "widget": "text", "value": "neon skyline"},
        },
        {"type": "runtime.queue_prompt", "payload": {"front": True}},
    ]


def test_rule_planner_sets_selected_prompt_nodes_without_touching_other_selected_nodes():
    plan = RuleBasedPlanner().plan(
        "把选中的 prompt 节点改成 neon skyline",
        context={
            "graph_input": {
                "nodes": [
                    {
                        "id": 9,
                        "type": "KSampler",
                        "title": "KSampler",
                        "selected": True,
                        "widgets": [{"name": "seed", "value": 12345}],
                    },
                    {
                        "id": 12,
                        "type": "CLIPTextEncode",
                        "title": "CLIP Text Encode",
                        "selected": True,
                        "widgets": [{"name": "text", "value": "old"}],
                    },
                ]
            }
        },
    )

    assert plan["actions"] == [
        {
            "type": "graph.set_widget",
            "payload": {"node_id": 12, "widget": "text", "value": "neon skyline"},
        }
    ]


def test_rule_planner_sets_all_clip_text_prompt_nodes_by_generic_prompt_alias():
    plan = RuleBasedPlanner().plan(
        "把所有 prompt 节点改成 warm daylight",
        context={
            "graph_input": {
                "nodes": [
                    {
                        "id": 7,
                        "type": "CLIPTextEncode",
                        "title": "CLIP Text Encode",
                        "widgets": [{"name": "text", "value": "old positive"}],
                    },
                    {
                        "id": 8,
                        "type": "CLIPTextEncode",
                        "title": "CLIP Text Encode",
                        "widgets": [{"name": "text", "value": "old negative"}],
                    },
                    {
                        "id": 9,
                        "type": "KSampler",
                        "title": "KSampler",
                        "widgets": [{"name": "seed", "value": 12345}],
                    },
                ]
            }
        },
    )

    assert plan["actions"] == [
        {
            "type": "graph.set_widget",
            "payload": {"node_id": 7, "widget": "text", "value": "warm daylight"},
        },
        {
            "type": "graph.set_widget",
            "payload": {"node_id": 8, "widget": "text", "value": "warm daylight"},
        },
    ]


def test_rule_planner_sets_selected_prompt_content_with_write_synonym():
    plan = RuleBasedPlanner().plan(
        "把这个 prompt 节点的内容写成 neon skyline",
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
            "payload": {"node_id": 12, "widget": "text", "value": "neon skyline"},
        }
    ]


def test_rule_planner_sets_selected_prompt_from_colon_shorthand():
    plan = RuleBasedPlanner().plan(
        "prompt: glowing blue forest",
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
            "payload": {"node_id": 12, "widget": "text", "value": "glowing blue forest"},
        }
    ]


def test_rule_planner_fills_positive_prompt_with_natural_language():
    plan = RuleBasedPlanner().plan(
        "给正向提示词填上 warm daylight",
        context={
            "graph_input": {
                "nodes": [
                    {
                        "id": 7,
                        "type": "CLIPTextEncode",
                        "title": "Positive Prompt",
                        "widgets": [{"name": "text", "value": "old positive"}],
                    },
                    {
                        "id": 8,
                        "type": "CLIPTextEncode",
                        "title": "Negative Prompt",
                        "widgets": [{"name": "text", "value": "old negative"}],
                    },
                ]
            }
        },
    )

    assert plan["actions"] == [
        {
            "type": "graph.set_widget",
            "payload": {"node_id": 7, "widget": "text", "value": "warm daylight"},
        }
    ]


def test_rule_planner_sets_positive_prompt_with_description_phrase():
    plan = RuleBasedPlanner().plan(
        "把正向提示词描述成 glowing blue forest",
        context={
            "graph_input": {
                "nodes": [
                    {
                        "id": 7,
                        "type": "CLIPTextEncode",
                        "title": "Positive Prompt",
                        "widgets": [{"name": "text", "value": "old positive"}],
                    },
                    {
                        "id": 8,
                        "type": "CLIPTextEncode",
                        "title": "Negative Prompt",
                        "widgets": [{"name": "text", "value": "old negative"}],
                    },
                ]
            }
        },
    )

    assert plan["actions"] == [
        {
            "type": "graph.set_widget",
            "payload": {"node_id": 7, "widget": "text", "value": "glowing blue forest"},
        }
    ]


def test_rule_planner_does_not_treat_prompt_color_words_as_node_color():
    plan = RuleBasedPlanner().plan(
        "把这个 prompt 节点的文本改成 red apple",
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
            "payload": {"node_id": 12, "widget": "text", "value": "red apple"},
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


def test_rule_planner_sets_positive_prompt_by_semantic_alias():
    plan = RuleBasedPlanner().plan(
        "把正向提示词改成 cinematic lighting",
        context={
            "graph_input": {
                "nodes": [
                    {
                        "id": 7,
                        "type": "CLIPTextEncode",
                        "title": "Positive Prompt",
                        "widgets": [{"name": "text", "value": "old positive"}],
                    },
                    {
                        "id": 8,
                        "type": "CLIPTextEncode",
                        "title": "Negative Prompt",
                        "widgets": [{"name": "text", "value": "old negative"}],
                    },
                ]
            }
        },
    )

    assert plan["actions"] == [
        {
            "type": "graph.set_widget",
            "payload": {"node_id": 7, "widget": "text", "value": "cinematic lighting"},
        }
    ]


def test_rule_planner_sets_negative_prompt_by_semantic_alias():
    plan = RuleBasedPlanner().plan(
        "把负面提示词改成 blurry, low quality",
        context={
            "graph_input": {
                "nodes": [
                    {
                        "id": 7,
                        "type": "CLIPTextEncode",
                        "title": "Positive Prompt",
                        "widgets": [{"name": "text", "value": "old positive"}],
                    },
                    {
                        "id": 8,
                        "type": "CLIPTextEncode",
                        "title": "Negative Prompt",
                        "widgets": [{"name": "text", "value": "old negative"}],
                    },
                ]
            }
        },
    )

    assert plan["actions"] == [
        {
            "type": "graph.set_widget",
            "payload": {"node_id": 8, "widget": "text", "value": "blurry, low quality"},
        }
    ]


def test_rule_planner_sets_negative_prompt_by_semantic_alias_even_when_positive_is_selected():
    plan = RuleBasedPlanner().plan(
        "把反向 prompt 节点改成 blurry, low quality",
        context={
            "graph_input": {
                "nodes": [
                    {
                        "id": 7,
                        "type": "CLIPTextEncode",
                        "title": "Positive Prompt",
                        "selected": True,
                        "widgets": [{"name": "text", "value": "old positive"}],
                    },
                    {
                        "id": 8,
                        "type": "CLIPTextEncode",
                        "title": "Negative Prompt",
                        "widgets": [{"name": "text", "value": "old negative"}],
                    },
                ]
            }
        },
    )

    assert plan["actions"] == [
        {
            "type": "graph.set_widget",
            "payload": {"node_id": 8, "widget": "text", "value": "blurry, low quality"},
        }
    ]


def test_rule_planner_sets_positive_prompt_by_semantic_alias_even_when_negative_is_selected():
    plan = RuleBasedPlanner().plan(
        "把正向 prompt 节点改成 cinematic lighting",
        context={
            "graph_input": {
                "nodes": [
                    {
                        "id": 7,
                        "type": "CLIPTextEncode",
                        "title": "Positive Prompt",
                        "widgets": [{"name": "text", "value": "old positive"}],
                    },
                    {
                        "id": 8,
                        "type": "CLIPTextEncode",
                        "title": "Negative Prompt",
                        "selected": True,
                        "widgets": [{"name": "text", "value": "old negative"}],
                    },
                ]
            }
        },
    )

    assert plan["actions"] == [
        {
            "type": "graph.set_widget",
            "payload": {"node_id": 7, "widget": "text", "value": "cinematic lighting"},
        }
    ]


def test_rule_planner_sets_positive_and_negative_prompts_from_one_message():
    plan = RuleBasedPlanner().plan(
        "把正向提示词改成 neon skyline，负面提示词改成 blurry, watermark",
        context={
            "graph_input": {
                "nodes": [
                    {
                        "id": 7,
                        "type": "CLIPTextEncode",
                        "title": "Positive Prompt",
                        "widgets": [{"name": "text", "value": "old positive"}],
                    },
                    {
                        "id": 8,
                        "type": "CLIPTextEncode",
                        "title": "Negative Prompt",
                        "widgets": [{"name": "text", "value": "old negative"}],
                    },
                ]
            }
        },
    )

    assert plan["actions"] == [
        {
            "type": "graph.set_widget",
            "payload": {"node_id": 7, "widget": "text", "value": "neon skyline"},
        },
        {
            "type": "graph.set_widget",
            "payload": {"node_id": 8, "widget": "text", "value": "blurry, watermark"},
        },
    ]


def test_rule_planner_sets_positive_and_negative_prompts_with_polite_prefix():
    plan = RuleBasedPlanner().plan(
        "请把正向提示词改成 neon skyline，然后把负面提示词改成 blurry, watermark",
        context={
            "graph_input": {
                "nodes": [
                    {
                        "id": 7,
                        "type": "CLIPTextEncode",
                        "title": "Positive Prompt",
                        "widgets": [{"name": "text", "value": "old positive"}],
                    },
                    {
                        "id": 8,
                        "type": "CLIPTextEncode",
                        "title": "Negative Prompt",
                        "widgets": [{"name": "text", "value": "old negative"}],
                    },
                ]
            }
        },
    )

    assert plan["actions"] == [
        {
            "type": "graph.set_widget",
            "payload": {"node_id": 7, "widget": "text", "value": "neon skyline"},
        },
        {
            "type": "graph.set_widget",
            "payload": {"node_id": 8, "widget": "text", "value": "blurry, watermark"},
        },
    ]


def test_rule_planner_sets_positive_prompt_by_sampler_connection_role():
    plan = RuleBasedPlanner().plan(
        "把正向提示词改成 cinematic lighting",
        context={
            "graph_input": {
                "nodes": [
                    {
                        "id": 7,
                        "type": "CLIPTextEncode",
                        "title": "CLIP Text Encode",
                        "widgets": [{"name": "text", "value": "old positive"}],
                        "outputs": [{"name": "CONDITIONING", "type": "CONDITIONING"}],
                    },
                    {
                        "id": 8,
                        "type": "CLIPTextEncode",
                        "title": "CLIP Text Encode",
                        "widgets": [{"name": "text", "value": "old negative"}],
                        "outputs": [{"name": "CONDITIONING", "type": "CONDITIONING"}],
                    },
                    {
                        "id": 9,
                        "type": "KSampler",
                        "title": "KSampler",
                        "inputs": [
                            {"name": "model", "type": "MODEL"},
                            {"name": "positive", "type": "CONDITIONING"},
                            {"name": "negative", "type": "CONDITIONING"},
                        ],
                    },
                ],
                "links": [
                    {"id": 77, "origin_id": 7, "origin_slot": 0, "target_id": 9, "target_slot": 1},
                    {"id": 78, "origin_id": 8, "origin_slot": 0, "target_id": 9, "target_slot": 2},
                ],
            }
        },
    )

    assert plan["actions"] == [
        {
            "type": "graph.set_widget",
            "payload": {"node_id": 7, "widget": "text", "value": "cinematic lighting"},
        }
    ]


def test_rule_planner_sets_connected_positive_and_negative_prompts_from_one_message():
    plan = RuleBasedPlanner().plan(
        "把正向提示词改成 neon skyline，负面提示词改成 blurry, watermark",
        context={
            "graph_input": {
                "nodes": [
                    {
                        "id": 7,
                        "type": "CLIPTextEncode",
                        "title": "CLIP Text Encode",
                        "widgets": [{"name": "text", "value": "old positive"}],
                        "outputs": [{"name": "CONDITIONING", "type": "CONDITIONING"}],
                    },
                    {
                        "id": 8,
                        "type": "CLIPTextEncode",
                        "title": "CLIP Text Encode",
                        "widgets": [{"name": "text", "value": "old negative"}],
                        "outputs": [{"name": "CONDITIONING", "type": "CONDITIONING"}],
                    },
                    {
                        "id": 9,
                        "type": "KSampler",
                        "title": "KSampler",
                        "inputs": [
                            {"name": "model", "type": "MODEL"},
                            {"name": "positive", "type": "CONDITIONING"},
                            {"name": "negative", "type": "CONDITIONING"},
                        ],
                    },
                ],
                "links": [
                    {"id": 77, "origin_id": 7, "origin_slot": 0, "target_id": 9, "target_slot": 1},
                    {"id": 78, "origin_id": 8, "origin_slot": 0, "target_id": 9, "target_slot": 2},
                ],
            }
        },
    )

    assert plan["actions"] == [
        {
            "type": "graph.set_widget",
            "payload": {"node_id": 7, "widget": "text", "value": "neon skyline"},
        },
        {
            "type": "graph.set_widget",
            "payload": {"node_id": 8, "widget": "text", "value": "blurry, watermark"},
        },
    ]


def test_rule_planner_appends_negative_prompt_by_sampler_connection_role():
    plan = RuleBasedPlanner().plan(
        "给负面提示词加上 watermark",
        context={
            "graph_input": {
                "nodes": [
                    {
                        "id": 7,
                        "type": "CLIPTextEncode",
                        "title": "CLIP Text Encode",
                        "widgets": [{"name": "text", "value": "portrait"}],
                        "outputs": [{"name": "CONDITIONING", "type": "CONDITIONING"}],
                    },
                    {
                        "id": 8,
                        "type": "CLIPTextEncode",
                        "title": "CLIP Text Encode",
                        "widgets": [{"name": "text", "value": "blurry, low quality"}],
                        "outputs": [{"name": "CONDITIONING", "type": "CONDITIONING"}],
                    },
                    {
                        "id": 9,
                        "type": "KSampler",
                        "title": "KSampler",
                        "inputs": [
                            {"name": "model", "type": "MODEL"},
                            {"name": "positive", "type": "CONDITIONING"},
                            {"name": "negative", "type": "CONDITIONING"},
                        ],
                    },
                ],
                "links": [
                    {"id": 77, "origin_id": 7, "origin_slot": 0, "target_id": 9, "target_slot": 1},
                    {"id": 78, "origin_id": 8, "origin_slot": 0, "target_id": 9, "target_slot": 2},
                ],
            }
        },
    )

    assert plan["actions"] == [
        {
            "type": "graph.set_widget",
            "payload": {
                "node_id": 8,
                "widget": "text",
                "value": "blurry, low quality, watermark",
            },
        }
    ]


def test_rule_planner_copies_positive_prompt_text_to_negative_prompt():
    plan = RuleBasedPlanner().plan(
        "把正向提示词复制到负面提示词",
        context={
            "graph_input": {
                "nodes": [
                    {
                        "id": 7,
                        "type": "CLIPTextEncode",
                        "title": "Positive Prompt",
                        "widgets": [{"name": "text", "value": "cinematic portrait"}],
                    },
                    {
                        "id": 8,
                        "type": "CLIPTextEncode",
                        "title": "Negative Prompt",
                        "widgets": [{"name": "text", "value": "blurry"}],
                    },
                ]
            }
        },
    )

    assert plan["actions"] == [
        {
            "type": "graph.set_widget",
            "payload": {"node_id": 8, "widget": "text", "value": "cinematic portrait"},
        }
    ]


def test_rule_planner_copies_selected_prompt_text_to_named_prompt():
    plan = RuleBasedPlanner().plan(
        "copy selected prompt text to Negative Prompt",
        context={
            "graph_input": {
                "nodes": [
                    {
                        "id": 12,
                        "type": "CLIPTextEncode",
                        "title": "Prompt",
                        "selected": True,
                        "widgets": [{"name": "text", "value": "warm rim light"}],
                    },
                    {
                        "id": 8,
                        "type": "CLIPTextEncode",
                        "title": "Negative Prompt",
                        "widgets": [{"name": "text", "value": "old negative"}],
                    },
                ]
            }
        },
    )

    assert plan["actions"] == [
        {
            "type": "graph.set_widget",
            "payload": {"node_id": 8, "widget": "text", "value": "warm rim light"},
        }
    ]


def test_rule_planner_appends_text_to_positive_prompt():
    plan = RuleBasedPlanner().plan(
        "给正向提示词加上 cinematic lighting",
        context={
            "graph_input": {
                "nodes": [
                    {
                        "id": 7,
                        "type": "CLIPTextEncode",
                        "title": "Positive Prompt",
                        "widgets": [{"name": "text", "value": "portrait, shallow depth of field"}],
                    },
                    {
                        "id": 8,
                        "type": "CLIPTextEncode",
                        "title": "Negative Prompt",
                        "widgets": [{"name": "text", "value": "old negative"}],
                    },
                ]
            }
        },
    )

    assert plan["actions"] == [
        {
            "type": "graph.set_widget",
            "payload": {
                "node_id": 7,
                "widget": "text",
                "value": "portrait, shallow depth of field, cinematic lighting",
            },
        }
    ]


def test_rule_planner_removes_text_from_negative_prompt():
    plan = RuleBasedPlanner().plan(
        "从负面提示词里去掉 blurry",
        context={
            "graph_input": {
                "nodes": [
                    {
                        "id": 7,
                        "type": "CLIPTextEncode",
                        "title": "Positive Prompt",
                        "widgets": [{"name": "text", "value": "portrait"}],
                    },
                    {
                        "id": 8,
                        "type": "CLIPTextEncode",
                        "title": "Negative Prompt",
                        "widgets": [{"name": "text", "value": "blurry, low quality, watermark"}],
                    },
                ]
            }
        },
    )

    assert plan["actions"] == [
        {
            "type": "graph.set_widget",
            "payload": {
                "node_id": 8,
                "widget": "text",
                "value": "low quality, watermark",
            },
        }
    ]


def test_rule_planner_removes_text_before_delete_verb_from_positive_prompt():
    plan = RuleBasedPlanner().plan(
        "把正向提示词里的 watermark 去掉",
        context={
            "graph_input": {
                "nodes": [
                    {
                        "id": 7,
                        "type": "CLIPTextEncode",
                        "title": "Positive Prompt",
                        "widgets": [{"name": "text", "value": "portrait, watermark, cinematic"}],
                    },
                    {
                        "id": 8,
                        "type": "CLIPTextEncode",
                        "title": "Negative Prompt",
                        "widgets": [{"name": "text", "value": "blurry"}],
                    },
                ]
            }
        },
    )

    assert plan["actions"] == [
        {
            "type": "graph.set_widget",
            "payload": {
                "node_id": 7,
                "widget": "text",
                "value": "portrait, cinematic",
            },
        }
    ]


def test_rule_planner_prefers_prompt_text_removal_over_node_delete():
    plan = RuleBasedPlanner().plan(
        "从负面提示词里删除 blurry",
        context={
            "graph_input": {
                "nodes": [
                    {
                        "id": 8,
                        "type": "CLIPTextEncode",
                        "title": "Negative Prompt",
                        "widgets": [{"name": "text", "value": "blurry, low quality"}],
                    }
                ]
            }
        },
    )

    assert plan["actions"] == [
        {
            "type": "graph.set_widget",
            "payload": {
                "node_id": 8,
                "widget": "text",
                "value": "low quality",
            },
        }
    ]


def test_rule_planner_clears_selected_prompt_text():
    plan = RuleBasedPlanner().plan(
        "清空这个 prompt 节点的文本",
        context={
            "graph_input": {
                "nodes": [
                    {
                        "id": 12,
                        "type": "CLIPTextEncode",
                        "title": "Prompt",
                        "selected": True,
                        "widgets": [{"name": "text", "value": "old prompt"}],
                    }
                ]
            }
        },
    )

    assert plan["actions"] == [
        {
            "type": "graph.set_widget",
            "payload": {"node_id": 12, "widget": "text", "value": ""},
        }
    ]


def test_rule_planner_clears_negative_prompt_by_semantic_alias():
    plan = RuleBasedPlanner().plan(
        "清空负面提示词",
        context={
            "graph_input": {
                "nodes": [
                    {
                        "id": 7,
                        "type": "CLIPTextEncode",
                        "title": "Positive Prompt",
                        "widgets": [{"name": "text", "value": "portrait"}],
                    },
                    {
                        "id": 8,
                        "type": "CLIPTextEncode",
                        "title": "Negative Prompt",
                        "widgets": [{"name": "text", "value": "blurry, low quality"}],
                    },
                ]
            }
        },
    )

    assert plan["actions"] == [
        {
            "type": "graph.set_widget",
            "payload": {"node_id": 8, "widget": "text", "value": ""},
        }
    ]


def test_rule_planner_clear_queue_does_not_clear_selected_prompt():
    plan = RuleBasedPlanner().plan(
        "清空待执行队列",
        context={
            "graph_input": {
                "nodes": [
                    {
                        "id": 12,
                        "type": "CLIPTextEncode",
                        "title": "Prompt",
                        "selected": True,
                        "widgets": [{"name": "text", "value": "old prompt"}],
                    }
                ]
            }
        },
    )

    assert plan["actions"] == [{"type": "runtime.clear_queue", "payload": {}}]


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


def test_rule_planner_sets_sampler_steps_with_tune_to_synonym():
    plan = RuleBasedPlanner().plan(
        "把 KSampler 的步数调到 30",
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

    assert plan["actions"] == [
        {"type": "graph.set_widget", "payload": {"node_id": 9, "widget": "steps", "value": 30}}
    ]


def test_rule_planner_sets_sampler_steps_from_colon_shorthand():
    plan = RuleBasedPlanner().plan(
        "KSampler 步数：30",
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

    assert plan["actions"] == [
        {"type": "graph.set_widget", "payload": {"node_id": 9, "widget": "steps", "value": 30}}
    ]


def test_rule_planner_sets_sampler_steps_from_use_steps_phrase():
    plan = RuleBasedPlanner().plan(
        "让 KSampler 用 30 步",
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

    assert plan["actions"] == [
        {"type": "graph.set_widget", "payload": {"node_id": 9, "widget": "steps", "value": 30}}
    ]


def test_rule_planner_sets_sampler_steps_and_cfg_from_compact_use_phrase():
    plan = RuleBasedPlanner().plan(
        "让 KSampler 用 30 步，CFG 7.5",
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

    assert plan["actions"] == [
        {"type": "graph.set_widget", "payload": {"node_id": 9, "widget": "steps", "value": 30}},
        {"type": "graph.set_widget", "payload": {"node_id": 9, "widget": "cfg", "value": 7.5}},
    ]


def test_rule_planner_sets_sampler_method_and_scheduler_from_compact_string_phrase():
    plan = RuleBasedPlanner().plan(
        "KSampler 采样方法 dpmpp_2m，调度方式 karras",
        context={
            "graph_input": {
                "nodes": [
                    {
                        "id": 9,
                        "type": "KSampler",
                        "title": "KSampler",
                        "widgets": [
                            {"name": "sampler_name", "value": "euler"},
                            {"name": "scheduler", "value": "normal"},
                        ],
                    }
                ]
            }
        },
    )

    assert plan["actions"] == [
        {"type": "graph.set_widget", "payload": {"node_id": 9, "widget": "sampler_name", "value": "dpmpp_2m"}},
        {"type": "graph.set_widget", "payload": {"node_id": 9, "widget": "scheduler", "value": "karras"}},
    ]


def test_rule_planner_sets_selected_sampler_cfg_with_set_to_synonym():
    plan = RuleBasedPlanner().plan(
        "把这个采样器的 CFG 设成 7.5",
        context={
            "graph_input": {
                "nodes": [
                    {
                        "id": 9,
                        "type": "KSampler",
                        "title": "KSampler",
                        "selected": True,
                        "widgets": [
                            {"name": "steps", "value": 20},
                            {"name": "cfg", "value": 7.0},
                        ],
                    }
                ]
            }
        },
    )

    assert plan["actions"] == [
        {"type": "graph.set_widget", "payload": {"node_id": 9, "widget": "cfg", "value": 7.5}}
    ]


def test_rule_planner_sets_sampler_cfg_by_guidance_alias():
    plan = RuleBasedPlanner().plan(
        "把 KSampler 的引导系数改成 6.5",
        context={
            "graph_input": {
                "nodes": [
                    {
                        "id": 9,
                        "type": "KSampler",
                        "title": "KSampler",
                        "widgets": [
                            {"name": "cfg", "value": 7.0},
                            {"name": "sampler_name", "value": "euler"},
                        ],
                    }
                ]
            }
        },
    )

    assert plan["actions"] == [
        {"type": "graph.set_widget", "payload": {"node_id": 9, "widget": "cfg", "value": 6.5}}
    ]


def test_rule_planner_sets_sampler_cfg_by_prompt_relevance_alias():
    plan = RuleBasedPlanner().plan(
        "把 KSampler 的提示词相关度改成 6.5",
        context={
            "graph_input": {
                "nodes": [
                    {
                        "id": 9,
                        "type": "KSampler",
                        "title": "KSampler",
                        "widgets": [
                            {"name": "cfg", "value": 7.0},
                            {"name": "sampler_name", "value": "euler"},
                        ],
                    }
                ]
            }
        },
    )

    assert plan["actions"] == [
        {"type": "graph.set_widget", "payload": {"node_id": 9, "widget": "cfg", "value": 6.5}}
    ]


def test_rule_planner_sets_video_frame_rate_by_fps_alias_independent_of_widget_order():
    plan = RuleBasedPlanner().plan(
        "把 Video Combine 的 fps 改成 24",
        context={
            "graph_input": {
                "nodes": [
                    {
                        "id": 42,
                        "type": "VHS_VideoCombine",
                        "title": "Video Combine",
                        "widgets": [
                            {"name": "filename_prefix", "value": "ComfyUI"},
                            {"name": "frame_rate", "value": 8},
                        ],
                    }
                ]
            }
        },
    )

    assert plan["actions"] == [
        {"type": "graph.set_widget", "payload": {"node_id": 42, "widget": "frame_rate", "value": 24}}
    ]


def test_rule_planner_sets_video_frame_rate_by_chinese_alias_independent_of_widget_order():
    plan = RuleBasedPlanner().plan(
        "把 Video Combine 的帧率改成 24",
        context={
            "graph_input": {
                "nodes": [
                    {
                        "id": 42,
                        "type": "VHS_VideoCombine",
                        "title": "Video Combine",
                        "widgets": [
                            {"name": "filename_prefix", "value": "ComfyUI"},
                            {"name": "frame_rate", "value": 8},
                        ],
                    }
                ]
            }
        },
    )

    assert plan["actions"] == [
        {"type": "graph.set_widget", "payload": {"node_id": 42, "widget": "frame_rate", "value": 24}}
    ]


def test_rule_planner_sets_video_combine_loop_count_by_chinese_alias():
    plan = RuleBasedPlanner().plan(
        "把 Video Combine 的循环次数改成 2",
        context={
            "graph_input": {
                "nodes": [
                    {
                        "id": 42,
                        "type": "VHS_VideoCombine",
                        "title": "Video Combine",
                        "widgets": [
                            {"name": "frame_rate", "value": 8},
                            {"name": "loop_count", "value": 0},
                            {"name": "filename_prefix", "value": "ComfyUI"},
                        ],
                    }
                ]
            }
        },
    )

    assert plan["actions"] == [
        {"type": "graph.set_widget", "payload": {"node_id": 42, "widget": "loop_count", "value": 2}}
    ]


def test_rule_planner_sets_video_combine_loop_rate_and_prefix_together():
    plan = RuleBasedPlanner().plan(
        "把 Video Combine 的循环次数改成 2，帧率改成 24，保存前缀改成 renders/shot-a",
        context={
            "graph_input": {
                "nodes": [
                    {
                        "id": 42,
                        "type": "VHS_VideoCombine",
                        "title": "Video Combine",
                        "widgets": [
                            {"name": "frame_rate", "value": 8},
                            {"name": "loop_count", "value": 0},
                            {"name": "filename_prefix", "value": "ComfyUI"},
                        ],
                    }
                ]
            }
        },
    )

    assert plan["actions"] == [
        {"type": "graph.set_widget", "payload": {"node_id": 42, "widget": "loop_count", "value": 2}},
        {"type": "graph.set_widget", "payload": {"node_id": 42, "widget": "frame_rate", "value": 24}},
        {
            "type": "graph.set_widget",
            "payload": {"node_id": 42, "widget": "filename_prefix", "value": "renders/shot-a"},
        },
    ]


def test_rule_planner_sets_guidance_scale_widget_by_guidance_alias():
    plan = RuleBasedPlanner().plan(
        "把 LTX Conditioning 的 guidance scale 改成 4.5",
        context={
            "graph_input": {
                "nodes": [
                    {
                        "id": 43,
                        "type": "LTXVConditioning",
                        "title": "LTX Conditioning",
                        "widgets": [
                            {"name": "frame_rate", "value": 8},
                            {"name": "num_frames", "value": 97},
                            {"name": "guidance_scale", "value": 3.0},
                        ],
                    }
                ]
            }
        },
    )

    assert plan["actions"] == [
        {
            "type": "graph.set_widget",
            "payload": {"node_id": 43, "widget": "guidance_scale", "value": 4.5},
        }
    ]


def test_rule_planner_sets_save_image_filename_prefix_by_chinese_alias():
    plan = RuleBasedPlanner().plan(
        "把 Save Image 的文件名前缀改成 agent_test",
        context={
            "graph_input": {
                "nodes": [
                    {
                        "id": 30,
                        "type": "SaveImage",
                        "title": "Save Image",
                        "widgets": [
                            {"name": "quality", "value": 95},
                            {"name": "filename_prefix", "value": "ComfyUI"},
                        ],
                    },
                    {
                        "id": 42,
                        "type": "VHS_VideoCombine",
                        "title": "Video Combine",
                        "widgets": [
                            {"name": "frame_rate", "value": 8},
                            {"name": "filename_prefix", "value": "ComfyUI"},
                        ],
                    }
                ]
            }
        },
    )

    assert plan["actions"] == [
        {
            "type": "graph.set_widget",
            "payload": {"node_id": 30, "widget": "filename_prefix", "value": "agent_test"},
        }
    ]


def test_rule_planner_sets_save_image_filename_prefix_with_use_phrase():
    plan = RuleBasedPlanner().plan(
        "保存图片用 renders/shot-a 作为文件名前缀",
        context={
            "graph_input": {
                "nodes": [
                    {
                        "id": 30,
                        "type": "SaveImage",
                        "title": "Save Image",
                        "widgets": [
                            {"name": "quality", "value": 95},
                            {"name": "filename_prefix", "value": "ComfyUI"},
                        ],
                    }
                ]
            }
        },
    )

    assert plan["actions"] == [
        {
            "type": "graph.set_widget",
            "payload": {"node_id": 30, "widget": "filename_prefix", "value": "renders/shot-a"},
        }
    ]


def test_rule_planner_selects_save_image_node_by_chinese_alias_for_filename_prefix():
    plan = RuleBasedPlanner().plan(
        "把保存图片节点的文件名前缀改成 agent_test",
        context={
            "graph_input": {
                "nodes": [
                    {
                        "id": 30,
                        "type": "SaveImage",
                        "title": "Save Image",
                        "widgets": [
                            {"name": "quality", "value": 95},
                            {"name": "filename_prefix", "value": "ComfyUI"},
                        ],
                    },
                    {
                        "id": 42,
                        "type": "VHS_VideoCombine",
                        "title": "Video Combine",
                        "widgets": [
                            {"name": "frame_rate", "value": 8},
                            {"name": "filename_prefix", "value": "ComfyUI"},
                        ],
                    }
                ]
            }
        },
    )

    assert plan["actions"] == [
        {
            "type": "graph.set_widget",
            "payload": {"node_id": 30, "widget": "filename_prefix", "value": "agent_test"},
        }
    ]


def test_rule_planner_sets_video_combine_output_filename_prefix_by_chinese_alias():
    plan = RuleBasedPlanner().plan(
        "把 Video Combine 的输出文件名前缀改成 clip_001",
        context={
            "graph_input": {
                "nodes": [
                    {
                        "id": 42,
                        "type": "VHS_VideoCombine",
                        "title": "Video Combine",
                        "widgets": [
                            {"name": "frame_rate", "value": 8},
                            {"name": "filename_prefix", "value": "ComfyUI"},
                        ],
                    }
                ]
            }
        },
    )

    assert plan["actions"] == [
        {
            "type": "graph.set_widget",
            "payload": {"node_id": 42, "widget": "filename_prefix", "value": "clip_001"},
        }
    ]


def test_rule_planner_sets_save_image_quality_by_chinese_alias():
    plan = RuleBasedPlanner().plan(
        "把 Save Image 的质量改成 90",
        context={
            "graph_input": {
                "nodes": [
                    {
                        "id": 30,
                        "type": "SaveImage",
                        "title": "Save Image",
                        "widgets": [
                            {"name": "filename_prefix", "value": "ComfyUI"},
                            {"name": "quality", "value": 80},
                        ],
                    }
                ]
            }
        },
    )

    assert plan["actions"] == [
        {"type": "graph.set_widget", "payload": {"node_id": 30, "widget": "quality", "value": 90}}
    ]


def test_rule_planner_sets_save_image_output_quality_by_chinese_node_alias():
    plan = RuleBasedPlanner().plan(
        "把保存图片节点的输出质量改成 90",
        context={
            "graph_input": {
                "nodes": [
                    {
                        "id": 30,
                        "type": "SaveImage",
                        "title": "Save Image",
                        "widgets": [
                            {"name": "filename_prefix", "value": "ComfyUI"},
                            {"name": "quality", "value": 80},
                        ],
                    },
                    {
                        "id": 42,
                        "type": "VHS_VideoCombine",
                        "title": "Video Combine",
                        "widgets": [
                            {"name": "frame_rate", "value": 8},
                            {"name": "filename_prefix", "value": "ComfyUI"},
                            {"name": "quality", "value": 60},
                        ],
                    },
                ]
            }
        },
    )

    assert plan["actions"] == [
        {"type": "graph.set_widget", "payload": {"node_id": 30, "widget": "quality", "value": 90}}
    ]


def test_rule_planner_sets_save_image_format_by_chinese_alias():
    plan = RuleBasedPlanner().plan(
        "把 Save Image 的保存格式改成 webp",
        context={
            "graph_input": {
                "nodes": [
                    {
                        "id": 30,
                        "type": "SaveImage",
                        "title": "Save Image",
                        "widgets": [
                            {"name": "filename_prefix", "value": "ComfyUI"},
                            {"name": "quality", "value": 80},
                            {"name": "format", "value": "png"},
                        ],
                    }
                ]
            }
        },
    )

    assert plan["actions"] == [
        {"type": "graph.set_widget", "payload": {"node_id": 30, "widget": "format", "value": "webp"}}
    ]


def test_rule_planner_sets_save_image_output_format_by_chinese_node_alias():
    plan = RuleBasedPlanner().plan(
        "把保存图片节点的输出格式改成 webp",
        context={
            "graph_input": {
                "nodes": [
                    {
                        "id": 30,
                        "type": "SaveImage",
                        "title": "Save Image",
                        "widgets": [
                            {"name": "filename_prefix", "value": "ComfyUI"},
                            {"name": "quality", "value": 80},
                            {"name": "format", "value": "png"},
                        ],
                    },
                    {
                        "id": 42,
                        "type": "VHS_VideoCombine",
                        "title": "Video Combine",
                        "widgets": [
                            {"name": "frame_rate", "value": 8},
                            {"name": "filename_prefix", "value": "ComfyUI"},
                            {"name": "format", "value": "video/h264-mp4"},
                        ],
                    },
                ]
            }
        },
    )

    assert plan["actions"] == [
        {"type": "graph.set_widget", "payload": {"node_id": 30, "widget": "format", "value": "webp"}}
    ]


def test_rule_planner_sets_video_combine_format_by_chinese_alias():
    plan = RuleBasedPlanner().plan(
        "把 Video Combine 的视频格式改成 video/h265-mp4",
        context={
            "graph_input": {
                "nodes": [
                    {
                        "id": 42,
                        "type": "VHS_VideoCombine",
                        "title": "Video Combine",
                        "widgets": [
                            {"name": "frame_rate", "value": 8},
                            {"name": "filename_prefix", "value": "ComfyUI"},
                            {"name": "format", "value": "video/h264-mp4"},
                        ],
                    }
                ]
            }
        },
    )

    assert plan["actions"] == [
        {
            "type": "graph.set_widget",
            "payload": {"node_id": 42, "widget": "format", "value": "video/h265-mp4"},
        }
    ]


def test_rule_planner_sets_sampler_name_by_chinese_semantic_alias():
    plan = RuleBasedPlanner().plan(
        "把采样器改成 euler",
        context={
            "graph_input": {
                "nodes": [
                    {
                        "id": 9,
                        "type": "KSampler",
                        "title": "KSampler",
                        "widgets": [
                            {"name": "sampler_name", "value": "dpmpp_2m"},
                            {"name": "scheduler", "value": "karras"},
                        ],
                    },
                    {
                        "id": 12,
                        "type": "CLIPTextEncode",
                        "title": "Prompt",
                        "widgets": [{"name": "text", "value": "old"}],
                    },
                ]
            }
        },
    )

    assert plan["actions"] == [
        {"type": "graph.set_widget", "payload": {"node_id": 9, "widget": "sampler_name", "value": "euler"}}
    ]


def test_rule_planner_sets_scheduler_by_chinese_semantic_alias():
    plan = RuleBasedPlanner().plan(
        "把调度器设成 normal",
        context={
            "graph_input": {
                "nodes": [
                    {
                        "id": 9,
                        "type": "KSampler",
                        "title": "KSampler",
                        "widgets": [
                            {"name": "sampler_name", "value": "dpmpp_2m"},
                            {"name": "scheduler", "value": "karras"},
                        ],
                    },
                    {
                        "id": 12,
                        "type": "CLIPTextEncode",
                        "title": "Prompt",
                        "widgets": [{"name": "text", "value": "old"}],
                    },
                ]
            }
        },
    )

    assert plan["actions"] == [
        {"type": "graph.set_widget", "payload": {"node_id": 9, "widget": "scheduler", "value": "normal"}}
    ]


def test_rule_planner_increases_numeric_widget_from_current_value():
    plan = RuleBasedPlanner().plan(
        "把 KSampler 的 steps 提高 4",
        context={
            "graph_input": {
                "nodes": [
                    {
                        "id": 9,
                        "type": "KSampler",
                        "title": "KSampler",
                        "widgets": [{"name": "steps", "value": 20}],
                    }
                ]
            }
        },
    )

    assert plan["actions"] == [
        {"type": "graph.set_widget", "payload": {"node_id": 9, "widget": "steps", "value": 24}}
    ]


def test_rule_planner_decreases_numeric_widget_from_current_value():
    plan = RuleBasedPlanner().plan(
        "把 KSampler 的 cfg 降低 1.5",
        context={
            "graph_input": {
                "nodes": [
                    {
                        "id": 9,
                        "type": "KSampler",
                        "title": "KSampler",
                        "widgets": [{"name": "cfg", "value": 7.0}],
                    }
                ]
            }
        },
    )

    assert plan["actions"] == [
        {"type": "graph.set_widget", "payload": {"node_id": 9, "widget": "cfg", "value": 5.5}}
    ]


def test_rule_planner_treats_tune_up_to_as_absolute_value():
    plan = RuleBasedPlanner().plan(
        "把 KSampler 的 cfg 调高到 8",
        context={
            "graph_input": {
                "nodes": [
                    {
                        "id": 9,
                        "type": "KSampler",
                        "title": "KSampler",
                        "widgets": [{"name": "cfg", "value": 7.0}],
                    }
                ]
            }
        },
    )

    assert plan["actions"] == [
        {"type": "graph.set_widget", "payload": {"node_id": 9, "widget": "cfg", "value": 8.0}}
    ]


def test_rule_planner_treats_lower_to_as_absolute_value():
    plan = RuleBasedPlanner().plan(
        "把 KSampler 的步数降低到 20",
        context={
            "graph_input": {
                "nodes": [
                    {
                        "id": 9,
                        "type": "KSampler",
                        "title": "KSampler",
                        "widgets": [{"name": "steps", "value": 28}],
                    }
                ]
            }
        },
    )

    assert plan["actions"] == [
        {"type": "graph.set_widget", "payload": {"node_id": 9, "widget": "steps", "value": 20}}
    ]


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


def test_rule_planner_sets_unique_widget_by_parameter_name_without_node_name():
    plan = RuleBasedPlanner().plan(
        "把步数调到 30",
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
                    },
                    {
                        "id": 12,
                        "type": "CLIPTextEncode",
                        "title": "Prompt",
                        "widgets": [{"name": "text", "value": "old"}],
                    },
                ]
            }
        },
    )

    assert plan["actions"] == [
        {"type": "graph.set_widget", "payload": {"node_id": 9, "widget": "steps", "value": 30}}
    ]


def test_rule_planner_sets_all_matching_widgets_by_parameter_name_without_node_name():
    plan = RuleBasedPlanner().plan(
        "把所有步数调成 24",
        context={
            "graph_input": {
                "nodes": [
                    {
                        "id": 9,
                        "type": "KSampler",
                        "title": "KSampler",
                        "widgets": [{"name": "steps", "value": 20}],
                    },
                    {
                        "id": 10,
                        "type": "KSampler",
                        "title": "Refiner KSampler",
                        "widgets": [{"name": "steps", "value": 12}],
                    },
                    {
                        "id": 12,
                        "type": "CLIPTextEncode",
                        "title": "Prompt",
                        "widgets": [{"name": "text", "value": "old"}],
                    },
                ]
            }
        },
    )

    assert plan["actions"] == [
        {"type": "graph.set_widget", "payload": {"node_id": 9, "widget": "steps", "value": 24}},
        {"type": "graph.set_widget", "payload": {"node_id": 10, "widget": "steps", "value": 24}},
    ]


def test_rule_planner_increments_all_matching_steps_with_short_add_phrase():
    plan = RuleBasedPlanner().plan(
        "把所有 KSampler 的步数加 5",
        context={
            "graph_input": {
                "nodes": [
                    {
                        "id": 9,
                        "type": "KSampler",
                        "title": "KSampler",
                        "widgets": [{"name": "steps", "value": 20}],
                    },
                    {
                        "id": 10,
                        "type": "KSampler",
                        "title": "Refiner KSampler",
                        "widgets": [{"name": "steps", "value": 12}],
                    },
                ]
            }
        },
    )

    assert plan["actions"] == [
        {"type": "graph.set_widget", "payload": {"node_id": 9, "widget": "steps", "value": 25}},
        {"type": "graph.set_widget", "payload": {"node_id": 10, "widget": "steps", "value": 17}},
    ]


def test_rule_planner_sets_all_matching_denoise_with_short_down_to_phrase():
    plan = RuleBasedPlanner().plan(
        "把所有 KSampler 的 denoise 降到 0.4",
        context={
            "graph_input": {
                "nodes": [
                    {
                        "id": 9,
                        "type": "KSampler",
                        "title": "KSampler",
                        "widgets": [{"name": "denoise", "value": 1.0}],
                    },
                    {
                        "id": 10,
                        "type": "KSampler",
                        "title": "Refiner KSampler",
                        "widgets": [{"name": "denoise", "value": 0.7}],
                    },
                ]
            }
        },
    )

    assert plan["actions"] == [
        {"type": "graph.set_widget", "payload": {"node_id": 9, "widget": "denoise", "value": 0.4}},
        {"type": "graph.set_widget", "payload": {"node_id": 10, "widget": "denoise", "value": 0.4}},
    ]


def test_rule_planner_halves_all_matching_cfg_widgets():
    plan = RuleBasedPlanner().plan(
        "把所有 KSampler 的 cfg 减半",
        context={
            "graph_input": {
                "nodes": [
                    {
                        "id": 9,
                        "type": "KSampler",
                        "title": "KSampler",
                        "widgets": [{"name": "cfg", "value": 7.0}],
                    },
                    {
                        "id": 10,
                        "type": "KSampler",
                        "title": "Refiner KSampler",
                        "widgets": [{"name": "cfg", "value": 5.0}],
                    },
                ]
            }
        },
    )

    assert plan["actions"] == [
        {"type": "graph.set_widget", "payload": {"node_id": 9, "widget": "cfg", "value": 3.5}},
        {"type": "graph.set_widget", "payload": {"node_id": 10, "widget": "cfg", "value": 2.5}},
    ]


def test_rule_planner_doubles_all_matching_step_widgets():
    plan = RuleBasedPlanner().plan(
        "把所有 KSampler 的步数翻倍",
        context={
            "graph_input": {
                "nodes": [
                    {
                        "id": 9,
                        "type": "KSampler",
                        "title": "KSampler",
                        "widgets": [{"name": "steps", "value": 20}],
                    },
                    {
                        "id": 10,
                        "type": "KSampler",
                        "title": "Refiner KSampler",
                        "widgets": [{"name": "steps", "value": 12}],
                    },
                ]
            }
        },
    )

    assert plan["actions"] == [
        {"type": "graph.set_widget", "payload": {"node_id": 9, "widget": "steps", "value": 40}},
        {"type": "graph.set_widget", "payload": {"node_id": 10, "widget": "steps", "value": 24}},
    ]


def test_rule_planner_avoids_parameter_only_edit_when_multiple_nodes_match_without_all():
    plan = RuleBasedPlanner().plan(
        "把步数调到 30",
        context={
            "graph_input": {
                "nodes": [
                    {
                        "id": 9,
                        "type": "KSampler",
                        "title": "KSampler",
                        "widgets": [{"name": "steps", "value": 20}],
                    },
                    {
                        "id": 10,
                        "type": "KSampler",
                        "title": "Refiner KSampler",
                        "widgets": [{"name": "steps", "value": 12}],
                    },
                ]
            }
        },
    )

    assert plan["actions"] == [
        {"type": "context.collect", "payload": {"message": "把步数调到 30"}}
    ]


def test_rule_planner_randomizes_seed_control_on_selected_sampler():
    plan = RuleBasedPlanner().plan(
        "把这个 KSampler 的种子随机化",
        context={
            "graph_input": {
                "nodes": [
                    {
                        "id": 9,
                        "type": "KSampler",
                        "title": "KSampler",
                        "selected": True,
                        "widgets": [
                            {"name": "seed", "value": 12345},
                            {"name": "control_after_generate", "value": "fixed"},
                        ],
                    }
                ]
            }
        },
    )

    assert plan["actions"] == [
        {
            "type": "graph.set_widget",
            "payload": {
                "node_id": 9,
                "widget": "control_after_generate",
                "value": "randomize",
            },
        }
    ]


def test_rule_planner_fixes_seed_value_and_control_on_sampler():
    plan = RuleBasedPlanner().plan(
        "把 KSampler 的种子固定为 12345",
        context={
            "graph_input": {
                "nodes": [
                    {
                        "id": 9,
                        "type": "KSampler",
                        "title": "KSampler",
                        "widgets": [
                            {"name": "seed", "value": 1},
                            {"name": "control_after_generate", "value": "randomize"},
                        ],
                    }
                ]
            }
        },
    )

    assert plan["actions"] == [
        {"type": "graph.set_widget", "payload": {"node_id": 9, "widget": "seed", "value": 12345}},
        {
            "type": "graph.set_widget",
            "payload": {"node_id": 9, "widget": "control_after_generate", "value": "fixed"},
        },
    ]


def test_rule_planner_sets_widget_on_all_matching_nodes():
    plan = RuleBasedPlanner().plan(
        "把所有 KSampler 的 steps 改成 30",
        context={
            "graph_input": {
                "nodes": [
                    {
                        "id": 9,
                        "type": "KSampler",
                        "title": "KSampler",
                        "widgets": [{"name": "steps", "value": 20}],
                    },
                    {
                        "id": 10,
                        "type": "KSampler",
                        "title": "Refiner KSampler",
                        "widgets": [{"name": "steps", "value": 12}],
                    },
                    {
                        "id": 11,
                        "type": "CLIPTextEncode",
                        "title": "Prompt",
                        "widgets": [{"name": "text", "value": "old"}],
                    },
                ]
            }
        },
    )

    assert plan["actions"] == [
        {"type": "graph.set_widget", "payload": {"node_id": 9, "widget": "steps", "value": 30}},
        {"type": "graph.set_widget", "payload": {"node_id": 10, "widget": "steps", "value": 30}},
    ]


def test_rule_planner_sets_clip_skip_by_semantic_alias():
    plan = RuleBasedPlanner().plan(
        "把 clip skip 节点设置为 -2",
        context={
            "graph_input": {
                "nodes": [
                    {
                        "id": 21,
                        "type": "CLIPSetLastLayer",
                        "title": "CLIP Set Last Layer",
                        "widgets": [{"name": "stop_at_clip_layer", "value": -1}],
                    },
                    {
                        "id": 22,
                        "type": "CLIPTextEncode",
                        "title": "Prompt",
                        "widgets": [{"name": "text", "value": "old"}],
                    },
                ]
            }
        },
    )

    assert plan["actions"] == [
        {
            "type": "graph.set_widget",
            "payload": {"node_id": 21, "widget": "stop_at_clip_layer", "value": -2},
        }
    ]


def test_rule_planner_adjusts_widget_on_all_matching_nodes():
    plan = RuleBasedPlanner().plan(
        "把全部 KSampler 的 cfg 降低 1",
        context={
            "graph_input": {
                "nodes": [
                    {
                        "id": 9,
                        "type": "KSampler",
                        "title": "KSampler",
                        "widgets": [{"name": "cfg", "value": 7.0}],
                    },
                    {
                        "id": 10,
                        "type": "KSampler",
                        "title": "Refiner KSampler",
                        "widgets": [{"name": "cfg", "value": 4.5}],
                    },
                ]
            }
        },
    )

    assert plan["actions"] == [
        {"type": "graph.set_widget", "payload": {"node_id": 9, "widget": "cfg", "value": 6.0}},
        {"type": "graph.set_widget", "payload": {"node_id": 10, "widget": "cfg", "value": 3.5}},
    ]


def test_rule_planner_sets_widget_on_selected_matching_nodes():
    plan = RuleBasedPlanner().plan(
        "把选中的 KSampler 的 steps 改成 32",
        context={
            "graph_input": {
                "nodes": [
                    {
                        "id": 9,
                        "type": "KSampler",
                        "title": "KSampler",
                        "selected": True,
                        "widgets": [{"name": "steps", "value": 20}],
                    },
                    {
                        "id": 10,
                        "type": "KSampler",
                        "title": "Refiner KSampler",
                        "selected": True,
                        "widgets": [{"name": "steps", "value": 12}],
                    },
                    {
                        "id": 11,
                        "type": "KSampler",
                        "title": "Unselected KSampler",
                        "selected": False,
                        "widgets": [{"name": "steps", "value": 8}],
                    },
                    {
                        "id": 12,
                        "type": "CLIPTextEncode",
                        "title": "Prompt",
                        "selected": True,
                        "widgets": [{"name": "text", "value": "old"}],
                    },
                ]
            }
        },
    )

    assert plan["actions"] == [
        {"type": "graph.set_widget", "payload": {"node_id": 9, "widget": "steps", "value": 32}},
        {"type": "graph.set_widget", "payload": {"node_id": 10, "widget": "steps", "value": 32}},
    ]


def test_rule_planner_sets_widget_on_downstream_matching_node_by_links():
    plan = RuleBasedPlanner().plan(
        "把 KSampler 后面的 Save Image 节点的文件名前缀改成 renders/shot-a",
        context={
            "graph_input": {
                "nodes": [
                    {
                        "id": 20,
                        "type": "SaveImage",
                        "title": "Unrelated Save Image",
                        "widgets": [{"name": "filename_prefix", "value": "wrong"}],
                    },
                    {"id": 9, "type": "KSampler", "title": "KSampler"},
                    {"id": 8, "type": "VAEDecode", "title": "VAE Decode"},
                    {
                        "id": 10,
                        "type": "SaveImage",
                        "title": "Save Image",
                        "widgets": [{"name": "filename_prefix", "value": "ComfyUI"}],
                    },
                ],
                "links": [
                    {"origin_id": 9, "origin_slot": 0, "target_id": 8, "target_slot": 0},
                    {"origin_id": 8, "origin_slot": 0, "target_id": 10, "target_slot": 0},
                ],
            }
        },
    )

    assert plan["actions"] == [
        {
            "type": "graph.set_widget",
            "payload": {
                "node_id": 10,
                "widget": "filename_prefix",
                "value": "renders/shot-a",
            },
        }
    ]


def test_rule_planner_sets_widget_on_upstream_matching_node_from_selected_node():
    plan = RuleBasedPlanner().plan(
        "把这个节点上游 KSampler 的 steps 改成 24",
        context={
            "graph_input": {
                "nodes": [
                    {
                        "id": 12,
                        "type": "KSampler",
                        "title": "Unrelated KSampler",
                        "widgets": [{"name": "steps", "value": 12}],
                    },
                    {
                        "id": 9,
                        "type": "KSampler",
                        "title": "KSampler",
                        "widgets": [{"name": "steps", "value": 20}],
                    },
                    {"id": 8, "type": "VAEDecode", "title": "VAE Decode"},
                    {"id": 10, "type": "SaveImage", "title": "Save Image", "selected": True},
                ],
                "links": [
                    {"origin_id": 9, "origin_slot": 0, "target_id": 8, "target_slot": 0},
                    {"origin_id": 8, "origin_slot": 0, "target_id": 10, "target_slot": 0},
                ],
            }
        },
    )

    assert plan["actions"] == [
        {"type": "graph.set_widget", "payload": {"node_id": 9, "widget": "steps", "value": 24}}
    ]


def test_rule_planner_adds_checkpoint_node_with_initial_model_alias():
    plan = RuleBasedPlanner().plan(
        "添加一个 CheckpointLoaderSimple 节点，模型改成 dreamshaper.safetensors",
        context={"graph_input": {"nodes": []}},
    )

    assert plan["actions"] == [
        {
            "type": "graph.add_node",
            "payload": {
                "node_type": "CheckpointLoaderSimple",
                "widgets": {"ckpt_name": "dreamshaper.safetensors"},
            },
        }
    ]


def test_rule_planner_sets_checkpoint_model_by_semantic_alias():
    plan = RuleBasedPlanner().plan(
        "把底模换成 juggernaut.safetensors",
        context={
            "graph_input": {
                "nodes": [
                    {
                        "id": 31,
                        "type": "CheckpointLoaderSimple",
                        "title": "Load Checkpoint",
                        "widgets": [{"name": "ckpt_name", "value": "old.safetensors"}],
                    },
                    {
                        "id": 32,
                        "type": "CLIPTextEncode",
                        "title": "Prompt",
                        "widgets": [{"name": "text", "value": "old"}],
                    },
                ]
            }
        },
    )

    assert plan["actions"] == [
        {
            "type": "graph.set_widget",
            "payload": {
                "node_id": 31,
                "widget": "ckpt_name",
                "value": "juggernaut.safetensors",
            },
        }
    ]


def test_rule_planner_sets_checkpoint_model_with_set_to_synonym():
    plan = RuleBasedPlanner().plan(
        "把底模设成 juggernaut.safetensors",
        context={
            "graph_input": {
                "nodes": [
                    {
                        "id": 31,
                        "type": "CheckpointLoaderSimple",
                        "title": "Load Checkpoint",
                        "widgets": [{"name": "ckpt_name", "value": "old.safetensors"}],
                    }
                ]
            }
        },
    )

    assert plan["actions"] == [
        {
            "type": "graph.set_widget",
            "payload": {
                "node_id": 31,
                "widget": "ckpt_name",
                "value": "juggernaut.safetensors",
            },
        }
    ]


def test_rule_planner_sets_checkpoint_model_with_use_phrase():
    plan = RuleBasedPlanner().plan(
        "把底模用 juggernautXL.safetensors",
        context={
            "graph_input": {
                "nodes": [
                    {
                        "id": 31,
                        "type": "CheckpointLoaderSimple",
                        "title": "Load Checkpoint",
                        "widgets": [{"name": "ckpt_name", "value": "old.safetensors"}],
                    }
                ]
            }
        },
    )

    assert plan["actions"] == [
        {
            "type": "graph.set_widget",
            "payload": {
                "node_id": 31,
                "widget": "ckpt_name",
                "value": "juggernautXL.safetensors",
            },
        }
    ]


def test_rule_planner_sets_vae_model_by_semantic_alias():
    plan = RuleBasedPlanner().plan(
        "把 VAE 换成 vae-ft-mse.safetensors",
        context={
            "graph_input": {
                "nodes": [
                    {
                        "id": 33,
                        "type": "VAELoader",
                        "title": "Load VAE",
                        "widgets": [{"name": "vae_name", "value": "old.vae.safetensors"}],
                    },
                    {
                        "id": 34,
                        "type": "CLIPTextEncode",
                        "title": "Prompt",
                        "widgets": [{"name": "text", "value": "old"}],
                    },
                ]
            }
        },
    )

    assert plan["actions"] == [
        {
            "type": "graph.set_widget",
            "payload": {
                "node_id": 33,
                "widget": "vae_name",
                "value": "vae-ft-mse.safetensors",
            },
        }
    ]


def test_rule_planner_sets_load_image_file_by_chinese_node_alias():
    plan = RuleBasedPlanner().plan(
        "把加载图片节点的图片换成 input/pose-reference.png",
        context={
            "graph_input": {
                "nodes": [
                    {
                        "id": 22,
                        "type": "LoadImage",
                        "title": "Load Image",
                        "widgets": [
                            {"name": "image", "value": "old.png"},
                            {"name": "upload", "value": "image"},
                        ],
                    },
                    {
                        "id": 9,
                        "type": "KSampler",
                        "title": "KSampler",
                        "widgets": [{"name": "seed", "value": 12345}],
                    },
                ]
            }
        },
    )

    assert plan["actions"] == [
        {
            "type": "graph.set_widget",
            "payload": {
                "node_id": 22,
                "widget": "image",
                "value": "input/pose-reference.png",
            },
        }
    ]


def test_rule_planner_sets_reference_image_with_use_phrase():
    plan = RuleBasedPlanner().plan(
        "参考图用 input/pose.png",
        context={
            "graph_input": {
                "nodes": [
                    {
                        "id": 22,
                        "type": "LoadImage",
                        "title": "Load Image",
                        "widgets": [
                            {"name": "image", "value": "old.png"},
                            {"name": "upload", "value": "image"},
                        ],
                    }
                ]
            }
        },
    )

    assert plan["actions"] == [
        {
            "type": "graph.set_widget",
            "payload": {
                "node_id": 22,
                "widget": "image",
                "value": "input/pose.png",
            },
        }
    ]


def test_rule_planner_sets_image_scale_method_and_crop_by_chinese_aliases():
    plan = RuleBasedPlanner().plan(
        "把图像缩放节点的缩放算法改成 bicubic，裁剪改成 center",
        context={
            "graph_input": {
                "nodes": [
                    {
                        "id": 24,
                        "type": "ImageScale",
                        "title": "Image Scale",
                        "widgets": [
                            {"name": "upscale_method", "value": "nearest-exact"},
                            {"name": "width", "value": 512},
                            {"name": "height", "value": 512},
                            {"name": "crop", "value": "disabled"},
                        ],
                    },
                    {
                        "id": 9,
                        "type": "KSampler",
                        "title": "KSampler",
                        "widgets": [{"name": "seed", "value": 12345}],
                    },
                ]
            }
        },
    )

    assert plan["actions"] == [
        {
            "type": "graph.set_widget",
            "payload": {"node_id": 24, "widget": "upscale_method", "value": "bicubic"},
        },
        {
            "type": "graph.set_widget",
            "payload": {"node_id": 24, "widget": "crop", "value": "center"},
        },
    ]


def test_rule_planner_sets_upscale_model_loader_by_chinese_alias():
    plan = RuleBasedPlanner().plan(
        "把超分模型加载器的超分模型换成 RealESRGAN_x4plus.pth",
        context={
            "graph_input": {
                "nodes": [
                    {
                        "id": 26,
                        "type": "UpscaleModelLoader",
                        "title": "Load Upscale Model",
                        "widgets": [{"name": "model_name", "value": "old.pth"}],
                    },
                    {
                        "id": 1,
                        "type": "CheckpointLoaderSimple",
                        "title": "Checkpoint",
                        "widgets": [{"name": "ckpt_name", "value": "base.safetensors"}],
                    },
                ]
            }
        },
    )

    assert plan["actions"] == [
        {
            "type": "graph.set_widget",
            "payload": {
                "node_id": 26,
                "widget": "model_name",
                "value": "RealESRGAN_x4plus.pth",
            },
        }
    ]


def test_rule_planner_sets_denoise_widget_by_chinese_alias():
    plan = RuleBasedPlanner().plan(
        "把 KSampler 的重绘幅度改成 0.55",
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
                            {"name": "denoise", "value": 1.0},
                        ],
                    }
                ]
            }
        },
    )

    assert plan["actions"] == [
        {"type": "graph.set_widget", "payload": {"node_id": 9, "widget": "denoise", "value": 0.55}}
    ]


def test_rule_planner_sets_sampler_and_scheduler_from_method_aliases():
    plan = RuleBasedPlanner().plan(
        "把 KSampler 的采样方法改成 dpmpp_2m，调度方式改成 karras",
        context={
            "graph_input": {
                "nodes": [
                    {
                        "id": 9,
                        "type": "KSampler",
                        "title": "KSampler",
                        "widgets": [
                            {"name": "sampler_name", "value": "euler"},
                            {"name": "scheduler", "value": "normal"},
                        ],
                    }
                ]
            }
        },
    )

    assert plan["actions"] == [
        {
            "type": "graph.set_widget",
            "payload": {"node_id": 9, "widget": "sampler_name", "value": "dpmpp_2m"},
        },
        {
            "type": "graph.set_widget",
            "payload": {"node_id": 9, "widget": "scheduler", "value": "karras"},
        },
    ]


def test_rule_planner_sets_widget_on_second_matching_node_by_chinese_ordinal():
    plan = RuleBasedPlanner().plan(
        "把第二个 KSampler 的 cfg 改成 4",
        context={
            "graph_input": {
                "nodes": [
                    {
                        "id": 9,
                        "type": "KSampler",
                        "title": "Base KSampler",
                        "widgets": [{"name": "cfg", "value": 7.0}],
                    },
                    {
                        "id": 10,
                        "type": "KSampler",
                        "title": "Refiner KSampler",
                        "widgets": [{"name": "cfg", "value": 5.0}],
                    },
                ]
            }
        },
    )

    assert plan["actions"] == [
        {"type": "graph.set_widget", "payload": {"node_id": 10, "widget": "cfg", "value": 4.0}}
    ]


def test_rule_planner_sets_scheduler_method_without_confusing_ksampler_title():
    plan = RuleBasedPlanner().plan(
        "把 KSampler 的调度方式改成 normal",
        context={
            "graph_input": {
                "nodes": [
                    {
                        "id": 9,
                        "type": "KSampler",
                        "title": "KSampler",
                        "widgets": [
                            {"name": "sampler_name", "value": "euler"},
                            {"name": "scheduler", "value": "karras"},
                        ],
                    }
                ]
            }
        },
    )

    assert plan["actions"] == [
        {
            "type": "graph.set_widget",
            "payload": {"node_id": 9, "widget": "scheduler", "value": "normal"},
        }
    ]


def test_rule_planner_sets_controlnet_start_and_end_percent_by_chinese_aliases():
    plan = RuleBasedPlanner().plan(
        "把 ControlNet 的开始百分比改成 0.2，结束百分比改成 0.8",
        context={
            "graph_input": {
                "nodes": [
                    {
                        "id": 40,
                        "type": "ControlNetApplyAdvanced",
                        "title": "Apply ControlNet",
                        "widgets": [
                            {"name": "strength", "value": 1.0},
                            {"name": "start_percent", "value": 0.0},
                            {"name": "end_percent", "value": 1.0},
                        ],
                    },
                    {
                        "id": 9,
                        "type": "KSampler",
                        "title": "KSampler",
                        "widgets": [{"name": "denoise", "value": 1.0}],
                    },
                ]
            }
        },
    )

    assert plan["actions"] == [
        {
            "type": "graph.set_widget",
            "payload": {"node_id": 40, "widget": "start_percent", "value": 0.2},
        },
        {
            "type": "graph.set_widget",
            "payload": {"node_id": 40, "widget": "end_percent", "value": 0.8},
        },
    ]


def test_rule_planner_sets_ipadapter_weight_and_timing_by_chinese_aliases():
    plan = RuleBasedPlanner().plan(
        "把 IPAdapter 的权重改成 0.7，开始时间改成 0.1，结束时间改成 0.8",
        context={
            "graph_input": {
                "nodes": [
                    {
                        "id": 50,
                        "type": "IPAdapterAdvanced",
                        "title": "IPAdapter Advanced",
                        "widgets": [
                            {"name": "weight", "value": 1.0},
                            {"name": "start_at", "value": 0.0},
                            {"name": "end_at", "value": 1.0},
                            {"name": "weight_type", "value": "linear"},
                        ],
                    }
                ]
            }
        },
    )

    assert plan["actions"] == [
        {
            "type": "graph.set_widget",
            "payload": {"node_id": 50, "widget": "weight", "value": 0.7},
        },
        {
            "type": "graph.set_widget",
            "payload": {"node_id": 50, "widget": "start_at", "value": 0.1},
        },
        {
            "type": "graph.set_widget",
            "payload": {"node_id": 50, "widget": "end_at", "value": 0.8},
        },
    ]


def test_rule_planner_sets_ipadapter_model_weight_and_timing_with_use_phrase():
    plan = RuleBasedPlanner().plan(
        "IPAdapter 用 plus-face.safetensors，权重 0.7，开始时间 0.1，结束时间 0.8",
        context={
            "graph_input": {
                "nodes": [
                    {
                        "id": 50,
                        "type": "IPAdapterAdvanced",
                        "title": "IPAdapter Advanced",
                        "widgets": [
                            {"name": "ipadapter_file", "value": "old.safetensors"},
                            {"name": "weight", "value": 1.0},
                            {"name": "start_at", "value": 0.0},
                            {"name": "end_at", "value": 1.0},
                        ],
                    }
                ]
            }
        },
    )

    assert plan["actions"] == [
        {
            "type": "graph.set_widget",
            "payload": {"node_id": 50, "widget": "ipadapter_file", "value": "plus-face.safetensors"},
        },
        {
            "type": "graph.set_widget",
            "payload": {"node_id": 50, "widget": "weight", "value": 0.7},
        },
        {
            "type": "graph.set_widget",
            "payload": {"node_id": 50, "widget": "start_at", "value": 0.1},
        },
        {
            "type": "graph.set_widget",
            "payload": {"node_id": 50, "widget": "end_at", "value": 0.8},
        },
    ]


def test_rule_planner_coerces_decimal_values_when_browser_serializes_float_widget_as_int():
    plan = RuleBasedPlanner().plan(
        "把 IPAdapter 的权重改成 0.7",
        context={
            "graph_input": {
                "nodes": [
                    {
                        "id": 50,
                        "type": "IPAdapterAdvanced",
                        "title": "IPAdapter Advanced",
                        "widgets": [
                            {"name": "weight", "value": 1},
                            {"name": "start_at", "value": 0},
                            {"name": "end_at", "value": 1},
                        ],
                    }
                ]
            }
        },
    )

    assert plan["actions"] == [
        {
            "type": "graph.set_widget",
            "payload": {"node_id": 50, "widget": "weight", "value": 0.7},
        }
    ]


def test_rule_planner_sets_controlnet_timing_when_followup_assignments_omit_operator():
    plan = RuleBasedPlanner().plan(
        "把 ControlNet 强度改成 0.65，开始时间 0.2，结束时间 0.85",
        context={
            "graph_input": {
                "nodes": [
                    {
                        "id": 40,
                        "type": "ControlNetApplyAdvanced",
                        "title": "Apply ControlNet",
                        "widgets": [
                            {"name": "strength", "value": 1.0},
                            {"name": "start_percent", "value": 0.0},
                            {"name": "end_percent", "value": 1.0},
                        ],
                    }
                ]
            }
        },
    )

    assert plan["actions"] == [
        {
            "type": "graph.set_widget",
            "payload": {"node_id": 40, "widget": "strength", "value": 0.65},
        },
        {
            "type": "graph.set_widget",
            "payload": {"node_id": 40, "widget": "start_percent", "value": 0.2},
        },
        {
            "type": "graph.set_widget",
            "payload": {"node_id": 40, "widget": "end_percent", "value": 0.85},
        },
    ]


def test_rule_planner_sets_controlnet_strength_and_timing_from_shorthand():
    plan = RuleBasedPlanner().plan(
        "ControlNet 强度 0.75，开始 0.1，结束 0.8",
        context={
            "graph_input": {
                "nodes": [
                    {
                        "id": 40,
                        "type": "ControlNetApplyAdvanced",
                        "title": "Apply ControlNet",
                        "widgets": [
                            {"name": "strength", "value": 1.0},
                            {"name": "start_percent", "value": 0.0},
                            {"name": "end_percent", "value": 1.0},
                        ],
                    }
                ]
            }
        },
    )

    assert plan["actions"] == [
        {
            "type": "graph.set_widget",
            "payload": {"node_id": 40, "widget": "strength", "value": 0.75},
        },
        {
            "type": "graph.set_widget",
            "payload": {"node_id": 40, "widget": "start_percent", "value": 0.1},
        },
        {
            "type": "graph.set_widget",
            "payload": {"node_id": 40, "widget": "end_percent", "value": 0.8},
        },
    ]


def test_rule_planner_sets_controlnet_loader_model_by_chinese_alias():
    plan = RuleBasedPlanner().plan(
        "把 ControlNet 模型加载器的模型换成 control_canny.safetensors",
        context={
            "graph_input": {
                "nodes": [
                    {
                        "id": 41,
                        "type": "ControlNetLoader",
                        "title": "Load ControlNet Model",
                        "widgets": [{"name": "control_net_name", "value": "old_controlnet.safetensors"}],
                    },
                    {
                        "id": 40,
                        "type": "ControlNetApplyAdvanced",
                        "title": "Apply ControlNet",
                        "widgets": [
                            {"name": "strength", "value": 1.0},
                            {"name": "start_percent", "value": 0.0},
                            {"name": "end_percent", "value": 1.0},
                        ],
                    },
                    {
                        "id": 1,
                        "type": "CheckpointLoaderSimple",
                        "title": "Checkpoint",
                        "widgets": [{"name": "ckpt_name", "value": "base.safetensors"}],
                    },
                ]
            }
        },
    )

    assert plan["actions"] == [
        {
            "type": "graph.set_widget",
            "payload": {
                "node_id": 41,
                "widget": "control_net_name",
                "value": "control_canny.safetensors",
            },
        }
    ]


def test_rule_planner_sets_latent_batch_widget_by_chinese_alias():
    plan = RuleBasedPlanner().plan(
        "把 Empty Latent Image 的批量改成 4",
        context={
            "graph_input": {
                "nodes": [
                    {
                        "id": 4,
                        "type": "EmptyLatentImage",
                        "title": "Empty Latent Image",
                        "widgets": [
                            {"name": "width", "value": 512},
                            {"name": "height", "value": 512},
                            {"name": "batch_size", "value": 1},
                        ],
                    }
                ]
            }
        },
    )

    assert plan["actions"] == [
        {"type": "graph.set_widget", "payload": {"node_id": 4, "widget": "batch_size", "value": 4}}
    ]


def test_rule_planner_sets_latent_size_and_batch_from_shorthand_phrase():
    plan = RuleBasedPlanner().plan(
        "Empty Latent 设成 1024x576，batch 4",
        context={
            "graph_input": {
                "nodes": [
                    {
                        "id": 4,
                        "type": "EmptyLatentImage",
                        "title": "Empty Latent Image",
                        "widgets": [
                            {"name": "width", "value": 512},
                            {"name": "height", "value": 512},
                            {"name": "batch_size", "value": 1},
                        ],
                    }
                ]
            }
        },
    )

    assert plan["actions"] == [
        {"type": "graph.set_widget", "payload": {"node_id": 4, "widget": "width", "value": 1024}},
        {"type": "graph.set_widget", "payload": {"node_id": 4, "widget": "height", "value": 576}},
        {"type": "graph.set_widget", "payload": {"node_id": 4, "widget": "batch_size", "value": 4}},
    ]


def test_rule_planner_sets_lora_model_strength_by_alias():
    plan = RuleBasedPlanner().plan(
        "把 LoRA 模型权重改成 0.8",
        context={
            "graph_input": {
                "nodes": [
                    {
                        "id": 6,
                        "type": "LoraLoader",
                        "title": "LoRA",
                        "widgets": [
                            {"name": "lora_name", "value": "old.safetensors"},
                            {"name": "strength_model", "value": 1.0},
                            {"name": "strength_clip", "value": 1.0},
                        ],
                    }
                ]
            }
        },
    )

    assert plan["actions"] == [
        {
            "type": "graph.set_widget",
            "payload": {"node_id": 6, "widget": "strength_model", "value": 0.8},
        }
    ]


def test_rule_planner_sets_both_lora_strengths_from_combined_alias():
    plan = RuleBasedPlanner().plan(
        "把 LoRA 的模型和 CLIP 权重都改成 0.75",
        context={
            "graph_input": {
                "nodes": [
                    {
                        "id": 6,
                        "type": "LoraLoader",
                        "title": "LoRA",
                        "widgets": [
                            {"name": "lora_name", "value": "old.safetensors"},
                            {"name": "strength_model", "value": 1.0},
                            {"name": "strength_clip", "value": 1.0},
                        ],
                    }
                ]
            }
        },
    )

    assert plan["actions"] == [
        {
            "type": "graph.set_widget",
            "payload": {"node_id": 6, "widget": "strength_model", "value": 0.75},
        },
        {
            "type": "graph.set_widget",
            "payload": {"node_id": 6, "widget": "strength_clip", "value": 0.75},
        },
    ]


def test_rule_planner_sets_both_lora_strengths_from_two_strengths_alias():
    plan = RuleBasedPlanner().plan(
        "把 LoRA 的两个强度都改成 0.65",
        context={
            "graph_input": {
                "nodes": [
                    {
                        "id": 6,
                        "type": "LoraLoader",
                        "title": "LoRA",
                        "widgets": [
                            {"name": "lora_name", "value": "old.safetensors"},
                            {"name": "strength_model", "value": 1.0},
                            {"name": "strength_clip", "value": 1.0},
                        ],
                    }
                ]
            }
        },
    )

    assert plan["actions"] == [
        {
            "type": "graph.set_widget",
            "payload": {"node_id": 6, "widget": "strength_model", "value": 0.65},
        },
        {
            "type": "graph.set_widget",
            "payload": {"node_id": 6, "widget": "strength_clip", "value": 0.65},
        },
    ]


def test_rule_planner_sets_lora_model_by_semantic_alias():
    plan = RuleBasedPlanner().plan(
        "把 LoRA 换成 detail.safetensors",
        context={
            "graph_input": {
                "nodes": [
                    {
                        "id": 35,
                        "type": "LoraLoader",
                        "title": "Load LoRA",
                        "widgets": [
                            {"name": "lora_name", "value": "old.safetensors"},
                            {"name": "strength_model", "value": 1.0},
                            {"name": "strength_clip", "value": 1.0},
                        ],
                    },
                    {
                        "id": 36,
                        "type": "CLIPTextEncode",
                        "title": "Prompt",
                        "widgets": [{"name": "text", "value": "old"}],
                    },
                ]
            }
        },
    )

    assert plan["actions"] == [
        {
            "type": "graph.set_widget",
            "payload": {"node_id": 35, "widget": "lora_name", "value": "detail.safetensors"},
        }
    ]


def test_rule_planner_sets_lora_model_with_use_phrase():
    plan = RuleBasedPlanner().plan(
        "让 LoRA 用 detail.safetensors",
        context={
            "graph_input": {
                "nodes": [
                    {
                        "id": 35,
                        "type": "LoraLoader",
                        "title": "Load LoRA",
                        "widgets": [
                            {"name": "lora_name", "value": "old.safetensors"},
                            {"name": "strength_model", "value": 1.0},
                            {"name": "strength_clip", "value": 1.0},
                        ],
                    }
                ]
            }
        },
    )

    assert plan["actions"] == [
        {
            "type": "graph.set_widget",
            "payload": {"node_id": 35, "widget": "lora_name", "value": "detail.safetensors"},
        }
    ]


def test_rule_planner_sets_lora_model_and_strength_with_use_phrase():
    plan = RuleBasedPlanner().plan(
        "让 LoRA 用 detail.safetensors，强度 0.7",
        context={
            "graph_input": {
                "nodes": [
                    {
                        "id": 35,
                        "type": "LoraLoader",
                        "title": "Load LoRA",
                        "widgets": [
                            {"name": "lora_name", "value": "old.safetensors"},
                            {"name": "strength_model", "value": 1.0},
                            {"name": "strength_clip", "value": 1.0},
                        ],
                    }
                ]
            }
        },
    )

    assert plan["actions"] == [
        {
            "type": "graph.set_widget",
            "payload": {"node_id": 35, "widget": "lora_name", "value": "detail.safetensors"},
        },
        {
            "type": "graph.set_widget",
            "payload": {"node_id": 35, "widget": "strength_model", "value": 0.7},
        },
    ]


def test_rule_planner_sets_lora_model_and_split_strengths_with_use_phrase():
    plan = RuleBasedPlanner().plan(
        "让 LoRA 用 detail.safetensors，模型权重 0.7，CLIP 权重 0.8",
        context={
            "graph_input": {
                "nodes": [
                    {
                        "id": 35,
                        "type": "LoraLoader",
                        "title": "Load LoRA",
                        "widgets": [
                            {"name": "lora_name", "value": "old.safetensors"},
                            {"name": "strength_model", "value": 1.0},
                            {"name": "strength_clip", "value": 1.0},
                        ],
                    }
                ]
            }
        },
    )

    assert plan["actions"] == [
        {
            "type": "graph.set_widget",
            "payload": {"node_id": 35, "widget": "lora_name", "value": "detail.safetensors"},
        },
        {
            "type": "graph.set_widget",
            "payload": {"node_id": 35, "widget": "strength_model", "value": 0.7},
        },
        {
            "type": "graph.set_widget",
            "payload": {"node_id": 35, "widget": "strength_clip", "value": 0.8},
        },
    ]


def test_rule_planner_sets_video_frame_count_by_chinese_alias():
    plan = RuleBasedPlanner().plan(
        "把 WanVideo 的帧数改成 81",
        context={
            "graph_input": {
                "nodes": [
                    {
                        "id": 10,
                        "type": "WanVideoSampler",
                        "title": "WanVideo",
                        "widgets": [
                            {"name": "width", "value": 832},
                            {"name": "height", "value": 480},
                            {"name": "num_frames", "value": 49},
                        ],
                    }
                ]
            }
        },
    )

    assert plan["actions"] == [
        {"type": "graph.set_widget", "payload": {"node_id": 10, "widget": "num_frames", "value": 81}}
    ]


def test_rule_planner_sets_image_size_from_compact_dimensions():
    plan = RuleBasedPlanner().plan(
        "把 Empty Latent Image 的尺寸改成 1024x576",
        context={
            "graph_input": {
                "nodes": [
                    {
                        "id": 4,
                        "type": "EmptyLatentImage",
                        "title": "Empty Latent Image",
                        "widgets": [
                            {"name": "width", "value": 512},
                            {"name": "height", "value": 512},
                            {"name": "batch_size", "value": 1},
                        ],
                    }
                ]
            }
        },
    )

    assert plan["actions"] == [
        {"type": "graph.set_widget", "payload": {"node_id": 4, "widget": "width", "value": 1024}},
        {"type": "graph.set_widget", "payload": {"node_id": 4, "widget": "height", "value": 576}},
    ]


def test_rule_planner_sets_image_width_height_from_compact_dimensions():
    plan = RuleBasedPlanner().plan(
        "把 Empty Latent Image 的宽高改成 1024x576",
        context={
            "graph_input": {
                "nodes": [
                    {
                        "id": 4,
                        "type": "EmptyLatentImage",
                        "title": "Empty Latent Image",
                        "widgets": [
                            {"name": "width", "value": 512},
                            {"name": "height", "value": 512},
                            {"name": "batch_size", "value": 1},
                        ],
                    }
                ]
            }
        },
    )

    assert plan["actions"] == [
        {"type": "graph.set_widget", "payload": {"node_id": 4, "widget": "width", "value": 1024}},
        {"type": "graph.set_widget", "payload": {"node_id": 4, "widget": "height", "value": 576}},
    ]


def test_rule_planner_sets_image_size_from_1080p_resolution_label():
    plan = RuleBasedPlanner().plan(
        "把 Empty Latent Image 的分辨率改成 1080p",
        context={
            "graph_input": {
                "nodes": [
                    {
                        "id": 4,
                        "type": "EmptyLatentImage",
                        "title": "Empty Latent Image",
                        "widgets": [
                            {"name": "width", "value": 512},
                            {"name": "height", "value": 512},
                        ],
                    }
                ]
            }
        },
    )

    assert plan["actions"] == [
        {"type": "graph.set_widget", "payload": {"node_id": 4, "widget": "width", "value": 1920}},
        {"type": "graph.set_widget", "payload": {"node_id": 4, "widget": "height", "value": 1080}},
    ]


def test_rule_planner_sets_vertical_1080p_resolution_with_tune_to_synonym():
    plan = RuleBasedPlanner().plan(
        "把 Empty Latent Image 的分辨率调成 1080p 竖屏",
        context={
            "graph_input": {
                "nodes": [
                    {
                        "id": 4,
                        "type": "EmptyLatentImage",
                        "title": "Empty Latent Image",
                        "widgets": [
                            {"name": "width", "value": 512},
                            {"name": "height", "value": 512},
                        ],
                    }
                ]
            }
        },
    )

    assert plan["actions"] == [
        {"type": "graph.set_widget", "payload": {"node_id": 4, "widget": "width", "value": 1080}},
        {"type": "graph.set_widget", "payload": {"node_id": 4, "widget": "height", "value": 1920}},
    ]


def test_rule_planner_sets_vertical_aspect_ratio_from_current_width():
    plan = RuleBasedPlanner().plan(
        "把 Empty Latent Image 的尺寸改成竖屏 9:16",
        context={
            "graph_input": {
                "nodes": [
                    {
                        "id": 4,
                        "type": "EmptyLatentImage",
                        "title": "Empty Latent Image",
                        "widgets": [
                            {"name": "width", "value": 720},
                            {"name": "height", "value": 720},
                        ],
                    }
                ]
            }
        },
    )

    assert plan["actions"] == [
        {"type": "graph.set_widget", "payload": {"node_id": 4, "widget": "width", "value": 720}},
        {"type": "graph.set_widget", "payload": {"node_id": 4, "widget": "height", "value": 1280}},
    ]


def test_rule_planner_sets_horizontal_aspect_ratio_from_current_height():
    plan = RuleBasedPlanner().plan(
        "把 Empty Latent Image 的分辨率改成横屏 16:9",
        context={
            "graph_input": {
                "nodes": [
                    {
                        "id": 4,
                        "type": "EmptyLatentImage",
                        "title": "Empty Latent Image",
                        "widgets": [
                            {"name": "width", "value": 720},
                            {"name": "height", "value": 720},
                        ],
                    }
                ]
            }
        },
    )

    assert plan["actions"] == [
        {"type": "graph.set_widget", "payload": {"node_id": 4, "widget": "width", "value": 1280}},
        {"type": "graph.set_widget", "payload": {"node_id": 4, "widget": "height", "value": 720}},
    ]


def test_rule_planner_adds_node_from_natural_language():
    plan = RuleBasedPlanner().plan("添加一个 KSampler 节点", context={"graph_input": {"nodes": []}})

    assert plan["actions"] == [{"type": "graph.add_node", "payload": {"node_type": "KSampler"}}]


def test_rule_planner_adds_registered_node_by_display_title():
    plan = RuleBasedPlanner().plan(
        "添加一个 Save Image 节点",
        context={
            "graph_input": {
                "nodes": [],
                "node_types": [{"type": "SaveImage", "title": "Save Image"}],
            }
        },
    )

    assert plan["actions"] == [
        {"type": "graph.add_node", "payload": {"node_type": "SaveImage"}}
    ]


def test_rule_planner_adds_registered_custom_node_by_display_title_with_widget():
    plan = RuleBasedPlanner().plan(
        "添加 Video Combine 节点，文件名前缀改成 renders/shot-a",
        context={
            "graph_input": {
                "nodes": [],
                "node_types": [
                    {"type": "VHS_VideoCombine", "title": "Video Combine"},
                ],
            }
        },
    )

    assert plan["actions"] == [
        {
            "type": "graph.add_node",
            "payload": {
                "node_type": "VHS_VideoCombine",
                "widgets": {"filename_prefix": "renders/shot-a"},
            },
        }
    ]


def test_rule_planner_adds_registered_node_with_schema_input_name_widget():
    plan = RuleBasedPlanner().plan(
        "添加 Video Combine 节点，loop count 改成 2",
        context={
            "graph_input": {
                "nodes": [],
                "node_types": [
                    {
                        "type": "VHS_VideoCombine",
                        "title": "Video Combine",
                        "inputs": [
                            {"name": "images", "type": "IMAGE"},
                            {"name": "frame_rate", "type": "FLOAT"},
                            {"name": "loop_count", "type": "INT"},
                            {"name": "filename_prefix", "type": "STRING"},
                        ],
                    },
                ],
            }
        },
    )

    assert plan["actions"] == [
        {
            "type": "graph.add_node",
            "payload": {
                "node_type": "VHS_VideoCombine",
                "widgets": {"loop_count": 2},
            },
        }
    ]


def test_rule_planner_adds_quoted_node_type_with_spaces_exactly():
    plan = RuleBasedPlanner().plan(
        "添加一个 \"ACN_Advanced ControlNet Apply\" 节点",
        context={"graph_input": {"nodes": []}},
    )

    assert plan["actions"] == [
        {
            "type": "graph.add_node",
            "payload": {"node_type": "ACN_Advanced ControlNet Apply"},
        }
    ]


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


def test_rule_planner_adds_positive_prompt_node_by_natural_alias():
    plan = RuleBasedPlanner().plan(
        "添加一个正向提示词节点，内容写成 neon skyline",
        context={"graph_input": {"nodes": []}},
    )

    assert plan["actions"] == [
        {
            "type": "graph.add_node",
            "payload": {
                "node_type": "CLIPTextEncode",
                "title": "Positive Prompt",
                "widgets": {"text": "neon skyline"},
            },
        }
    ]


def test_rule_planner_adds_empty_latent_image_node_by_natural_alias_with_size():
    plan = RuleBasedPlanner().plan(
        "添加一个空 latent 图像节点，尺寸改成 1024x576",
        context={"graph_input": {"nodes": []}},
    )

    assert plan["actions"] == [
        {
            "type": "graph.add_node",
            "payload": {
                "node_type": "EmptyLatentImage",
                "widgets": {"width": 1024, "height": 576},
            },
        }
    ]


def test_rule_planner_adds_empty_latent_image_node_by_natural_alias_with_width_height():
    plan = RuleBasedPlanner().plan(
        "添加一个空 latent 图像节点，宽高改成 1024x576",
        context={"graph_input": {"nodes": []}},
    )

    assert plan["actions"] == [
        {
            "type": "graph.add_node",
            "payload": {
                "node_type": "EmptyLatentImage",
                "widgets": {"width": 1024, "height": 576},
            },
        }
    ]


def test_rule_planner_adds_vae_decode_node_by_chinese_alias():
    plan = RuleBasedPlanner().plan(
        "添加一个 VAE 解码节点",
        context={"graph_input": {"nodes": []}},
    )

    assert plan["actions"] == [
        {"type": "graph.add_node", "payload": {"node_type": "VAEDecode"}}
    ]


def test_rule_planner_adds_node_and_connects_existing_node_to_it():
    plan = RuleBasedPlanner().plan(
        "添加一个 VAE 解码节点并把 KSampler 接到它",
        context={
            "graph_input": {
                "nodes": [
                    {
                        "id": 9,
                        "type": "KSampler",
                        "title": "KSampler",
                        "outputs": [{"name": "LATENT", "type": "LATENT"}],
                    }
                ],
                "node_types": [
                    {
                        "type": "VAEDecode",
                        "title": "VAE Decode",
                        "inputs": [
                            {"name": "samples", "type": "LATENT"},
                            {"name": "vae", "type": "VAE"},
                        ],
                    }
                ],
            }
        },
    )

    assert plan["actions"] == [
        {
            "type": "graph.add_node",
            "payload": {"node_type": "VAEDecode", "ref": "new_node"},
        },
        {
            "type": "graph.connect",
            "payload": {
                "origin_node_id": 9,
                "origin_slot": 0,
                "target_node_ref": "new_node",
                "target_slot": 0,
            },
        },
    ]


def test_rule_planner_adds_node_and_connects_it_to_existing_node():
    plan = RuleBasedPlanner().plan(
        "添加一个正向提示词节点，内容写成 neon skyline，并把它接到 KSampler 的 positive",
        context={
            "graph_input": {
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
                "node_types": [
                    {
                        "type": "CLIPTextEncode",
                        "title": "CLIP Text Encode",
                        "outputs": [{"name": "CONDITIONING", "type": "CONDITIONING"}],
                    }
                ],
            }
        },
    )

    assert plan["actions"] == [
        {
            "type": "graph.add_node",
            "payload": {
                "node_type": "CLIPTextEncode",
                "title": "Positive Prompt",
                "widgets": {"text": "neon skyline"},
                "ref": "new_node",
            },
        },
        {
            "type": "graph.connect",
            "payload": {
                "origin_node_ref": "new_node",
                "origin_slot": 0,
                "target_node_id": 9,
                "target_slot": 1,
            },
        },
    ]


def test_rule_planner_adds_node_after_selected_node_by_natural_position():
    plan = RuleBasedPlanner().plan(
        "在这个节点后面添加 VAE 解码节点",
        context={
            "graph_input": {
                "nodes": [
                    {
                        "id": 9,
                        "type": "KSampler",
                        "title": "KSampler",
                        "selected": True,
                        "outputs": [{"name": "LATENT", "type": "LATENT"}],
                    }
                ],
                "node_types": [
                    {
                        "type": "VAEDecode",
                        "title": "VAE Decode",
                        "inputs": [
                            {"name": "samples", "type": "LATENT"},
                            {"name": "vae", "type": "VAE"},
                        ],
                        "outputs": [{"name": "IMAGE", "type": "IMAGE"}],
                    }
                ],
            }
        },
    )

    assert plan["actions"] == [
        {
            "type": "graph.add_node",
            "payload": {"node_type": "VAEDecode", "ref": "new_node"},
        },
        {
            "type": "graph.connect",
            "payload": {
                "origin_node_id": 9,
                "origin_slot": 0,
                "target_node_ref": "new_node",
                "target_slot": 0,
            },
        },
    ]


def test_rule_planner_adds_node_before_selected_node_by_natural_position():
    plan = RuleBasedPlanner().plan(
        "在这个节点前面添加 VAE 解码节点",
        context={
            "graph_input": {
                "nodes": [
                    {
                        "id": 11,
                        "type": "SaveImage",
                        "title": "Save Image",
                        "selected": True,
                        "inputs": [{"name": "images", "type": "IMAGE"}],
                    }
                ],
                "node_types": [
                    {
                        "type": "VAEDecode",
                        "title": "VAE Decode",
                        "inputs": [
                            {"name": "samples", "type": "LATENT"},
                            {"name": "vae", "type": "VAE"},
                        ],
                        "outputs": [{"name": "IMAGE", "type": "IMAGE"}],
                    }
                ],
            }
        },
    )

    assert plan["actions"] == [
        {
            "type": "graph.add_node",
            "payload": {"node_type": "VAEDecode", "ref": "new_node"},
        },
        {
            "type": "graph.connect",
            "payload": {
                "origin_node_ref": "new_node",
                "origin_slot": 0,
                "target_node_id": 11,
                "target_slot": 0,
            },
        },
    ]


def test_rule_planner_inserts_new_node_between_existing_nodes():
    plan = RuleBasedPlanner().plan(
        "在 KSampler 和 Save Image 之间插入 VAE 解码节点",
        context={
            "graph_input": {
                "nodes": [
                    {
                        "id": 9,
                        "type": "KSampler",
                        "title": "KSampler",
                        "outputs": [{"name": "LATENT", "type": "LATENT"}],
                    },
                    {
                        "id": 11,
                        "type": "SaveImage",
                        "title": "Save Image",
                        "inputs": [{"name": "images", "type": "IMAGE"}],
                    },
                ],
                "node_types": [
                    {
                        "type": "VAEDecode",
                        "title": "VAE Decode",
                        "inputs": [
                            {"name": "samples", "type": "LATENT"},
                            {"name": "vae", "type": "VAE"},
                        ],
                        "outputs": [{"name": "IMAGE", "type": "IMAGE"}],
                    }
                ],
            }
        },
    )

    assert plan["actions"] == [
        {
            "type": "graph.add_node",
            "payload": {"node_type": "VAEDecode", "ref": "new_node"},
        },
        {
            "type": "graph.connect",
            "payload": {
                "origin_node_id": 9,
                "origin_slot": 0,
                "target_node_ref": "new_node",
                "target_slot": 0,
            },
        },
        {
            "type": "graph.connect",
            "payload": {
                "origin_node_ref": "new_node",
                "origin_slot": 0,
                "target_node_id": 11,
                "target_slot": 0,
            },
        },
    ]


def test_rule_planner_inserts_lora_node_between_checkpoint_and_sampler_from_reversed_phrase():
    plan = RuleBasedPlanner().plan(
        "把 LoRA 插到 Checkpoint 和 KSampler 之间",
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
                        "id": 9,
                        "type": "KSampler",
                        "title": "KSampler",
                        "inputs": [{"name": "model", "type": "MODEL"}],
                    },
                ],
                "node_types": [
                    {
                        "type": "LoraLoader",
                        "title": "Load LoRA",
                        "inputs": [
                            {"name": "model", "type": "MODEL"},
                            {"name": "clip", "type": "CLIP"},
                        ],
                        "outputs": [
                            {"name": "MODEL", "type": "MODEL"},
                            {"name": "CLIP", "type": "CLIP"},
                        ],
                    }
                ],
            }
        },
    )

    assert plan["actions"] == [
        {
            "type": "graph.add_node",
            "payload": {"node_type": "LoraLoader", "ref": "new_node"},
        },
        {
            "type": "graph.connect",
            "payload": {
                "origin_node_id": 1,
                "origin_slot": 0,
                "target_node_ref": "new_node",
                "target_slot": 0,
            },
        },
        {
            "type": "graph.connect",
            "payload": {
                "origin_node_ref": "new_node",
                "origin_slot": 0,
                "target_node_id": 9,
                "target_slot": 0,
            },
        },
    ]


def test_rule_planner_inserts_lora_node_with_model_and_strength_widgets():
    plan = RuleBasedPlanner().plan(
        "在 Checkpoint 和 KSampler 之间插入 LoRA 节点，LoRA 用 detail.safetensors，强度 0.7",
        context={
            "graph_input": {
                "nodes": [
                    {
                        "id": 1,
                        "type": "CheckpointLoaderSimple",
                        "title": "Checkpoint",
                        "outputs": [{"name": "MODEL", "type": "MODEL"}],
                    },
                    {
                        "id": 9,
                        "type": "KSampler",
                        "title": "KSampler",
                        "inputs": [{"name": "model", "type": "MODEL"}],
                    },
                ],
                "node_types": [
                    {
                        "type": "LoraLoader",
                        "title": "Load LoRA",
                        "inputs": [{"name": "model", "type": "MODEL"}],
                        "outputs": [{"name": "MODEL", "type": "MODEL"}],
                        "input": {
                            "required": {
                                "lora_name": [["detail.safetensors"], {}],
                                "strength_model": ["FLOAT", {}],
                            }
                        },
                        "input_order": {"required": ["lora_name", "strength_model"]},
                    }
                ],
            }
        },
    )

    assert plan["actions"][0] == {
        "type": "graph.add_node",
        "payload": {
            "node_type": "LoraLoader",
            "widgets": {"lora_name": "detail.safetensors", "strength_model": 0.7},
            "ref": "new_node",
        },
    }


def test_rule_planner_replaces_terminal_node_preserving_incoming_links():
    plan = RuleBasedPlanner().plan(
        "把 Save Image 节点替换成 Preview Image 节点",
        context={
            "graph_input": {
                "nodes": [
                    {
                        "id": 8,
                        "type": "VAEDecode",
                        "title": "VAE Decode",
                        "outputs": [{"name": "IMAGE", "type": "IMAGE"}],
                    },
                    {
                        "id": 9,
                        "type": "SaveImage",
                        "title": "Save Image",
                        "inputs": [{"name": "images", "type": "IMAGE"}],
                    },
                ],
                "links": [
                    {
                        "id": 77,
                        "origin_id": 8,
                        "origin_slot": 0,
                        "target_id": 9,
                        "target_slot": 0,
                    }
                ],
                "node_types": [
                    {
                        "type": "PreviewImage",
                        "title": "Preview Image",
                        "inputs": [{"name": "images", "type": "IMAGE"}],
                    }
                ],
            }
        },
    )

    assert plan["actions"] == [
        {
            "type": "graph.add_node",
            "payload": {"node_type": "PreviewImage", "ref": "replacement_node"},
        },
        {
            "type": "graph.connect",
            "payload": {
                "origin_node_id": 8,
                "origin_slot": 0,
                "target_node_ref": "replacement_node",
                "target_slot": 0,
            },
        },
        {"type": "graph.delete_node", "payload": {"node_id": 9}},
    ]


def test_rule_planner_replaces_middle_node_preserving_compatible_links():
    plan = RuleBasedPlanner().plan(
        "把 VAE Decode 节点替换成 VAE Decode Tiled 节点",
        context={
            "graph_input": {
                "nodes": [
                    {
                        "id": 3,
                        "type": "KSampler",
                        "title": "KSampler",
                        "outputs": [{"name": "LATENT", "type": "LATENT"}],
                    },
                    {
                        "id": 4,
                        "type": "VAELoader",
                        "title": "VAE",
                        "outputs": [{"name": "VAE", "type": "VAE"}],
                    },
                    {
                        "id": 8,
                        "type": "VAEDecode",
                        "title": "VAE Decode",
                        "inputs": [
                            {"name": "samples", "type": "LATENT"},
                            {"name": "vae", "type": "VAE"},
                        ],
                        "outputs": [{"name": "IMAGE", "type": "IMAGE"}],
                    },
                    {
                        "id": 9,
                        "type": "SaveImage",
                        "title": "Save Image",
                        "inputs": [{"name": "images", "type": "IMAGE"}],
                    },
                ],
                "links": [
                    {
                        "id": 77,
                        "origin_id": 3,
                        "origin_slot": 0,
                        "target_id": 8,
                        "target_slot": 0,
                    },
                    {
                        "id": 78,
                        "origin_id": 4,
                        "origin_slot": 0,
                        "target_id": 8,
                        "target_slot": 1,
                    },
                    {
                        "id": 79,
                        "origin_id": 8,
                        "origin_slot": 0,
                        "target_id": 9,
                        "target_slot": 0,
                    },
                ],
                "node_types": [
                    {
                        "type": "VAEDecodeTiled",
                        "title": "VAE Decode Tiled",
                        "inputs": [
                            {"name": "samples", "type": "LATENT"},
                            {"name": "vae", "type": "VAE"},
                        ],
                        "outputs": [{"name": "IMAGE", "type": "IMAGE"}],
                    }
                ],
            }
        },
    )

    assert plan["actions"] == [
        {
            "type": "graph.add_node",
            "payload": {"node_type": "VAEDecodeTiled", "ref": "replacement_node"},
        },
        {
            "type": "graph.connect",
            "payload": {
                "origin_node_id": 3,
                "origin_slot": 0,
                "target_node_ref": "replacement_node",
                "target_slot": 0,
            },
        },
        {
            "type": "graph.connect",
            "payload": {
                "origin_node_id": 4,
                "origin_slot": 0,
                "target_node_ref": "replacement_node",
                "target_slot": 1,
            },
        },
        {
            "type": "graph.connect",
            "payload": {
                "origin_node_ref": "replacement_node",
                "origin_slot": 0,
                "target_node_id": 9,
                "target_slot": 0,
            },
        },
        {"type": "graph.delete_node", "payload": {"node_id": 8}},
    ]


def test_rule_planner_adds_vae_encode_node_by_chinese_alias():
    plan = RuleBasedPlanner().plan(
        "添加一个 VAE 编码节点",
        context={"graph_input": {"nodes": []}},
    )

    assert plan["actions"] == [
        {"type": "graph.add_node", "payload": {"node_type": "VAEEncode"}}
    ]


def test_rule_planner_adds_lora_loader_node_by_natural_alias_with_model():
    plan = RuleBasedPlanner().plan(
        "添加一个 LoRA 加载器节点，LoRA 换成 detail.safetensors",
        context={"graph_input": {"nodes": []}},
    )

    assert plan["actions"] == [
        {
            "type": "graph.add_node",
            "payload": {
                "node_type": "LoraLoader",
                "widgets": {"lora_name": "detail.safetensors"},
            },
        }
    ]


def test_rule_planner_adds_load_image_node_by_natural_alias_with_image():
    plan = RuleBasedPlanner().plan(
        "添加一个加载图片节点，图片换成 input/pose-reference.png",
        context={"graph_input": {"nodes": []}},
    )

    assert plan["actions"] == [
        {
            "type": "graph.add_node",
            "payload": {
                "node_type": "LoadImage",
                "widgets": {"image": "input/pose-reference.png"},
            },
        }
    ]


def test_rule_planner_adds_image_scale_node_by_natural_alias_with_width_height():
    plan = RuleBasedPlanner().plan(
        "添加一个图像缩放节点，宽高改成 1024x576",
        context={"graph_input": {"nodes": []}},
    )

    assert plan["actions"] == [
        {
            "type": "graph.add_node",
            "payload": {
                "node_type": "ImageScale",
                "widgets": {"width": 1024, "height": 576},
            },
        }
    ]


def test_rule_planner_adds_upscale_model_loader_by_natural_alias_with_model():
    plan = RuleBasedPlanner().plan(
        "添加一个超分模型加载器节点，超分模型换成 RealESRGAN_x4plus.pth",
        context={"graph_input": {"nodes": []}},
    )

    assert plan["actions"] == [
        {
            "type": "graph.add_node",
            "payload": {
                "node_type": "UpscaleModelLoader",
                "widgets": {"model_name": "RealESRGAN_x4plus.pth"},
            },
        }
    ]


def test_rule_planner_adds_controlnet_loader_by_natural_alias_with_model():
    plan = RuleBasedPlanner().plan(
        "添加一个 ControlNet 模型加载器节点，模型换成 control_canny.safetensors",
        context={"graph_input": {"nodes": []}},
    )

    assert plan["actions"] == [
        {
            "type": "graph.add_node",
            "payload": {
                "node_type": "ControlNetLoader",
                "widgets": {"control_net_name": "control_canny.safetensors"},
            },
        }
    ]


def test_rule_planner_deletes_selected_node():
    plan = RuleBasedPlanner().plan(
        "删除这个节点",
        context={
            "graph_input": {
                "nodes": [
                    {"id": 12, "type": "CLIPTextEncode", "title": "Prompt", "selected": True}
                ]
            }
        },
    )

    assert plan["actions"] == [{"type": "graph.delete_node", "payload": {"node_id": 12}}]


def test_rule_planner_deletes_node_by_id():
    plan = RuleBasedPlanner().plan(
        "删除 12 号节点",
        context={
            "graph_input": {
                "nodes": [
                    {"id": 7, "type": "CLIPTextEncode", "title": "Prompt"},
                    {"id": 12, "type": "KSampler", "title": "KSampler"},
                ]
            }
        },
    )

    assert plan["actions"] == [{"type": "graph.delete_node", "payload": {"node_id": 12}}]


def test_rule_planner_deletes_node_by_title():
    plan = RuleBasedPlanner().plan(
        "删除 KSampler 节点",
        context={
            "graph_input": {
                "nodes": [
                    {"id": 7, "type": "CLIPTextEncode", "title": "Prompt"},
                    {"id": 9, "type": "KSampler", "title": "KSampler"},
                ]
            }
        },
    )

    assert plan["actions"] == [{"type": "graph.delete_node", "payload": {"node_id": 9}}]


def test_rule_planner_deletes_selected_nodes():
    plan = RuleBasedPlanner().plan(
        "删除选中的节点",
        context={
            "graph_input": {
                "nodes": [
                    {"id": 12, "type": "KSampler", "title": "KSampler", "selected": True},
                    {"id": 13, "type": "CLIPTextEncode", "title": "Prompt", "selected": True},
                    {"id": 14, "type": "VAELoader", "title": "VAE", "selected": False},
                ]
            }
        },
    )

    assert plan["actions"] == [
        {"type": "graph.delete_node", "payload": {"node_id": 12}},
        {"type": "graph.delete_node", "payload": {"node_id": 13}},
    ]


def test_rule_planner_deletes_all_matching_nodes():
    plan = RuleBasedPlanner().plan(
        "删除所有 KSampler 节点",
        context={
            "graph_input": {
                "nodes": [
                    {"id": 7, "type": "CLIPTextEncode", "title": "Prompt"},
                    {"id": 9, "type": "KSampler", "title": "KSampler"},
                    {"id": 10, "type": "KSampler", "title": "Refiner KSampler"},
                ]
            }
        },
    )

    assert plan["actions"] == [
        {"type": "graph.delete_node", "payload": {"node_id": 9}},
        {"type": "graph.delete_node", "payload": {"node_id": 10}},
    ]


def test_rule_planner_deletes_downstream_nodes_by_links():
    plan = RuleBasedPlanner().plan(
        "删除 KSampler 后面的节点",
        context={
            "graph_input": {
                "nodes": [
                    {"id": 1, "type": "CheckpointLoaderSimple", "title": "Checkpoint"},
                    {"id": 9, "type": "KSampler", "title": "KSampler"},
                    {"id": 8, "type": "VAEDecode", "title": "VAE Decode"},
                    {"id": 10, "type": "SaveImage", "title": "Save Image"},
                ],
                "links": [
                    {"origin_id": 1, "origin_slot": 0, "target_id": 9, "target_slot": 0},
                    {"origin_id": 9, "origin_slot": 0, "target_id": 8, "target_slot": 0},
                    {"origin_id": 8, "origin_slot": 0, "target_id": 10, "target_slot": 0},
                ],
            }
        },
    )

    assert plan["actions"] == [
        {"type": "graph.delete_node", "payload": {"node_id": 8}},
        {"type": "graph.delete_node", "payload": {"node_id": 10}},
    ]


def test_rule_planner_duplicates_selected_node():
    plan = RuleBasedPlanner().plan(
        "复制这个节点",
        context={
            "graph_input": {
                "nodes": [
                    {"id": 12, "type": "CLIPTextEncode", "title": "Prompt", "selected": True}
                ]
            }
        },
    )

    assert plan["actions"] == [
        {"type": "graph.duplicate_node", "payload": {"node_id": 12, "offset": [40, 40], "select": True}}
    ]


def test_rule_planner_clones_node_by_title():
    plan = RuleBasedPlanner().plan(
        "克隆 KSampler 节点",
        context={
            "graph_input": {
                "nodes": [
                    {"id": 7, "type": "CLIPTextEncode", "title": "Prompt"},
                    {"id": 9, "type": "KSampler", "title": "KSampler"},
                ]
            }
        },
    )

    assert plan["actions"] == [
        {"type": "graph.duplicate_node", "payload": {"node_id": 9, "offset": [40, 40], "select": True}}
    ]


def test_rule_planner_duplicates_selected_nodes():
    plan = RuleBasedPlanner().plan(
        "复制选中的节点",
        context={
            "graph_input": {
                "nodes": [
                    {"id": 12, "type": "KSampler", "title": "KSampler", "selected": True},
                    {"id": 13, "type": "CLIPTextEncode", "title": "Prompt", "selected": True},
                    {"id": 14, "type": "VAELoader", "title": "VAE", "selected": False},
                ]
            }
        },
    )

    assert plan["actions"] == [
        {"type": "graph.duplicate_node", "payload": {"node_id": 12, "offset": [40, 40], "select": False}},
        {"type": "graph.duplicate_node", "payload": {"node_id": 13, "offset": [40, 40], "select": False}},
    ]


def test_rule_planner_duplicates_all_matching_nodes():
    plan = RuleBasedPlanner().plan(
        "复制所有 KSampler 节点",
        context={
            "graph_input": {
                "nodes": [
                    {"id": 7, "type": "CLIPTextEncode", "title": "Prompt"},
                    {"id": 9, "type": "KSampler", "title": "KSampler"},
                    {"id": 10, "type": "KSampler", "title": "Refiner KSampler"},
                ]
            }
        },
    )

    assert plan["actions"] == [
        {"type": "graph.duplicate_node", "payload": {"node_id": 9, "offset": [40, 40], "select": False}},
        {"type": "graph.duplicate_node", "payload": {"node_id": 10, "offset": [40, 40], "select": False}},
    ]


def test_rule_planner_duplicates_upstream_nodes_by_links():
    plan = RuleBasedPlanner().plan(
        "复制这个节点上游节点",
        context={
            "graph_input": {
                "nodes": [
                    {"id": 1, "type": "CheckpointLoaderSimple", "title": "Checkpoint"},
                    {"id": 9, "type": "KSampler", "title": "KSampler"},
                    {"id": 8, "type": "VAEDecode", "title": "VAE Decode"},
                    {"id": 10, "type": "SaveImage", "title": "Save Image", "selected": True},
                ],
                "links": [
                    {"origin_id": 1, "origin_slot": 0, "target_id": 9, "target_slot": 0},
                    {"origin_id": 9, "origin_slot": 0, "target_id": 8, "target_slot": 0},
                    {"origin_id": 8, "origin_slot": 0, "target_id": 10, "target_slot": 0},
                ],
            }
        },
    )

    assert plan["actions"] == [
        {"type": "graph.duplicate_node", "payload": {"node_id": 1, "offset": [40, 40], "select": False}},
        {"type": "graph.duplicate_node", "payload": {"node_id": 9, "offset": [40, 40], "select": False}},
        {"type": "graph.duplicate_node", "payload": {"node_id": 8, "offset": [40, 40], "select": False}},
    ]


def test_rule_planner_marks_selected_node_red():
    plan = RuleBasedPlanner().plan(
        "把这个节点标红",
        context={
            "graph_input": {
                "nodes": [
                    {"id": 12, "type": "CLIPTextEncode", "title": "Prompt", "selected": True}
                ]
            }
        },
    )

    assert plan["actions"] == [
        {"type": "graph.set_color", "payload": {"node_id": 12, "color": "#ff5555"}}
    ]


def test_rule_planner_highlights_all_matching_nodes_yellow():
    plan = RuleBasedPlanner().plan(
        "把所有 KSampler 节点高亮",
        context={
            "graph_input": {
                "nodes": [
                    {"id": 7, "type": "CLIPTextEncode", "title": "Prompt"},
                    {"id": 9, "type": "KSampler", "title": "KSampler"},
                    {"id": 10, "type": "KSampler", "title": "Refiner KSampler"},
                ]
            }
        },
    )

    assert plan["actions"] == [
        {"type": "graph.set_color", "payload": {"node_id": 9, "color": "#f2c94c"}},
        {"type": "graph.set_color", "payload": {"node_id": 10, "color": "#f2c94c"}},
    ]


def test_rule_planner_bypasses_selected_node():
    plan = RuleBasedPlanner().plan(
        "绕过这个节点",
        context={
            "graph_input": {
                "nodes": [
                    {"id": 12, "type": "CLIPTextEncode", "title": "Prompt", "selected": True}
                ]
            }
        },
    )

    assert plan["actions"] == [
        {"type": "graph.set_mode", "payload": {"node_id": 12, "mode": "bypass"}}
    ]


def test_rule_planner_mutes_node_by_title():
    plan = RuleBasedPlanner().plan(
        "禁用 KSampler 节点",
        context={
            "graph_input": {
                "nodes": [
                    {"id": 7, "type": "CLIPTextEncode", "title": "Prompt"},
                    {"id": 9, "type": "KSampler", "title": "KSampler"},
                ]
            }
        },
    )

    assert plan["actions"] == [
        {"type": "graph.set_mode", "payload": {"node_id": 9, "mode": "mute"}}
    ]


def test_rule_planner_mutes_second_matching_node_by_chinese_ordinal():
    plan = RuleBasedPlanner().plan(
        "禁用第二个 KSampler 节点",
        context={
            "graph_input": {
                "nodes": [
                    {"id": 9, "type": "KSampler", "title": "Base KSampler"},
                    {"id": 10, "type": "KSampler", "title": "Refiner KSampler"},
                ]
            }
        },
    )

    assert plan["actions"] == [
        {"type": "graph.set_mode", "payload": {"node_id": 10, "mode": "mute"}}
    ]


def test_rule_planner_enables_node_by_id():
    plan = RuleBasedPlanner().plan(
        "启用 12 号节点",
        context={
            "graph_input": {
                "nodes": [
                    {"id": 12, "type": "KSampler", "title": "KSampler", "mode": 4},
                ]
            }
        },
    )

    assert plan["actions"] == [
        {"type": "graph.set_mode", "payload": {"node_id": 12, "mode": "always"}}
    ]


def test_rule_planner_sets_mode_on_selected_nodes():
    plan = RuleBasedPlanner().plan(
        "禁用选中的节点",
        context={
            "graph_input": {
                "nodes": [
                    {"id": 12, "type": "KSampler", "title": "KSampler", "selected": True},
                    {"id": 13, "type": "CLIPTextEncode", "title": "Prompt", "selected": True},
                    {"id": 14, "type": "VAELoader", "title": "VAE", "selected": False},
                ]
            }
        },
    )

    assert plan["actions"] == [
        {"type": "graph.set_mode", "payload": {"node_id": 12, "mode": "mute"}},
        {"type": "graph.set_mode", "payload": {"node_id": 13, "mode": "mute"}},
    ]


def test_rule_planner_mutes_downstream_nodes_by_links():
    plan = RuleBasedPlanner().plan(
        "禁用 KSampler 后面的节点",
        context={
            "graph_input": {
                "nodes": [
                    {"id": 1, "type": "CheckpointLoaderSimple", "title": "Checkpoint"},
                    {"id": 9, "type": "KSampler", "title": "KSampler"},
                    {"id": 8, "type": "VAEDecode", "title": "VAE Decode"},
                    {"id": 10, "type": "SaveImage", "title": "Save Image"},
                ],
                "links": [
                    {"origin_id": 1, "origin_slot": 0, "target_id": 9, "target_slot": 0},
                    {"origin_id": 9, "origin_slot": 0, "target_id": 8, "target_slot": 0},
                    {"origin_id": 8, "origin_slot": 0, "target_id": 10, "target_slot": 0},
                ],
            }
        },
    )

    assert plan["actions"] == [
        {"type": "graph.set_mode", "payload": {"node_id": 8, "mode": "mute"}},
        {"type": "graph.set_mode", "payload": {"node_id": 10, "mode": "mute"}},
    ]


def test_rule_planner_colors_downstream_nodes_by_links():
    plan = RuleBasedPlanner().plan(
        "把 KSampler 后面的节点标黄",
        context={
            "graph_input": {
                "nodes": [
                    {"id": 1, "type": "CheckpointLoaderSimple", "title": "Checkpoint"},
                    {"id": 9, "type": "KSampler", "title": "KSampler"},
                    {"id": 8, "type": "VAEDecode", "title": "VAE Decode"},
                    {"id": 10, "type": "SaveImage", "title": "Save Image"},
                ],
                "links": [
                    {"origin_id": 1, "origin_slot": 0, "target_id": 9, "target_slot": 0},
                    {"origin_id": 9, "origin_slot": 0, "target_id": 8, "target_slot": 0},
                    {"origin_id": 8, "origin_slot": 0, "target_id": 10, "target_slot": 0},
                ],
            }
        },
    )

    assert plan["actions"] == [
        {"type": "graph.set_color", "payload": {"node_id": 8, "color": "#f2c94c"}},
        {"type": "graph.set_color", "payload": {"node_id": 10, "color": "#f2c94c"}},
    ]


def test_rule_planner_selects_upstream_nodes_from_selected_node():
    plan = RuleBasedPlanner().plan(
        "选中这个节点上游节点",
        context={
            "graph_input": {
                "nodes": [
                    {"id": 1, "type": "CheckpointLoaderSimple", "title": "Checkpoint"},
                    {"id": 3, "type": "CLIPTextEncode", "title": "Positive Prompt"},
                    {"id": 4, "type": "CLIPTextEncode", "title": "Negative Prompt"},
                    {"id": 9, "type": "KSampler", "title": "KSampler"},
                    {"id": 8, "type": "VAEDecode", "title": "VAE Decode"},
                    {"id": 10, "type": "SaveImage", "title": "Save Image", "selected": True},
                ],
                "links": [
                    {"origin_id": 1, "origin_slot": 0, "target_id": 9, "target_slot": 0},
                    {"origin_id": 3, "origin_slot": 0, "target_id": 9, "target_slot": 1},
                    {"origin_id": 4, "origin_slot": 0, "target_id": 9, "target_slot": 2},
                    {"origin_id": 9, "origin_slot": 0, "target_id": 8, "target_slot": 0},
                    {"origin_id": 8, "origin_slot": 0, "target_id": 10, "target_slot": 0},
                ],
            }
        },
    )

    assert plan["actions"] == [
        {"type": "graph.select_nodes", "payload": {"node_ids": [1, 3, 4, 9, 8], "focus": False}}
    ]


def test_rule_planner_colors_upstream_nodes_from_selected_node():
    plan = RuleBasedPlanner().plan(
        "把这个节点上游节点标蓝",
        context={
            "graph_input": {
                "nodes": [
                    {"id": 1, "type": "CheckpointLoaderSimple", "title": "Checkpoint"},
                    {"id": 3, "type": "CLIPTextEncode", "title": "Positive Prompt"},
                    {"id": 4, "type": "CLIPTextEncode", "title": "Negative Prompt"},
                    {"id": 9, "type": "KSampler", "title": "KSampler"},
                    {"id": 8, "type": "VAEDecode", "title": "VAE Decode"},
                    {"id": 10, "type": "SaveImage", "title": "Save Image", "selected": True},
                ],
                "links": [
                    {"origin_id": 1, "origin_slot": 0, "target_id": 9, "target_slot": 0},
                    {"origin_id": 3, "origin_slot": 0, "target_id": 9, "target_slot": 1},
                    {"origin_id": 4, "origin_slot": 0, "target_id": 9, "target_slot": 2},
                    {"origin_id": 9, "origin_slot": 0, "target_id": 8, "target_slot": 0},
                    {"origin_id": 8, "origin_slot": 0, "target_id": 10, "target_slot": 0},
                ],
            }
        },
    )

    assert plan["actions"] == [
        {"type": "graph.set_color", "payload": {"node_id": 1, "color": "#4f8cff"}},
        {"type": "graph.set_color", "payload": {"node_id": 3, "color": "#4f8cff"}},
        {"type": "graph.set_color", "payload": {"node_id": 4, "color": "#4f8cff"}},
        {"type": "graph.set_color", "payload": {"node_id": 9, "color": "#4f8cff"}},
        {"type": "graph.set_color", "payload": {"node_id": 8, "color": "#4f8cff"}},
    ]


def test_rule_planner_moves_downstream_nodes_by_delta():
    plan = RuleBasedPlanner().plan(
        "把 KSampler 后面的节点往右移动 100",
        context={
            "graph_input": {
                "nodes": [
                    {"id": 1, "type": "CheckpointLoaderSimple", "title": "Checkpoint", "pos": [0, 0]},
                    {"id": 9, "type": "KSampler", "title": "KSampler", "pos": [100, 20]},
                    {"id": 8, "type": "VAEDecode", "title": "VAE Decode", "pos": [300, 20]},
                    {"id": 10, "type": "SaveImage", "title": "Save Image", "pos": [520, 20]},
                ],
                "links": [
                    {"origin_id": 1, "origin_slot": 0, "target_id": 9, "target_slot": 0},
                    {"origin_id": 9, "origin_slot": 0, "target_id": 8, "target_slot": 0},
                    {"origin_id": 8, "origin_slot": 0, "target_id": 10, "target_slot": 0},
                ],
            }
        },
    )

    assert plan["actions"] == [
        {"type": "graph.set_position", "payload": {"node_id": 8, "pos": [400, 20]}},
        {"type": "graph.set_position", "payload": {"node_id": 10, "pos": [620, 20]}},
    ]


def test_rule_planner_moves_upstream_nodes_by_delta_from_selected_node():
    plan = RuleBasedPlanner().plan(
        "把这个节点上游节点往上移动 40",
        context={
            "graph_input": {
                "nodes": [
                    {"id": 1, "type": "CheckpointLoaderSimple", "title": "Checkpoint", "pos": [0, 100]},
                    {"id": 9, "type": "KSampler", "title": "KSampler", "pos": [200, 120]},
                    {"id": 8, "type": "VAEDecode", "title": "VAE Decode", "pos": [420, 140]},
                    {"id": 10, "type": "SaveImage", "title": "Save Image", "selected": True, "pos": [640, 160]},
                ],
                "links": [
                    {"origin_id": 1, "origin_slot": 0, "target_id": 9, "target_slot": 0},
                    {"origin_id": 9, "origin_slot": 0, "target_id": 8, "target_slot": 0},
                    {"origin_id": 8, "origin_slot": 0, "target_id": 10, "target_slot": 0},
                ],
            }
        },
    )

    assert plan["actions"] == [
        {"type": "graph.set_position", "payload": {"node_id": 1, "pos": [0, 60]}},
        {"type": "graph.set_position", "payload": {"node_id": 9, "pos": [200, 80]}},
        {"type": "graph.set_position", "payload": {"node_id": 8, "pos": [420, 100]}},
    ]


def test_rule_planner_horizontally_aligns_downstream_nodes_by_links():
    plan = RuleBasedPlanner().plan(
        "把 KSampler 后面的节点横向对齐",
        context={
            "graph_input": {
                "nodes": [
                    {"id": 1, "type": "CheckpointLoaderSimple", "title": "Checkpoint", "pos": [0, 120]},
                    {"id": 9, "type": "KSampler", "title": "KSampler", "pos": [220, 160]},
                    {"id": 8, "type": "VAEDecode", "title": "VAE Decode", "pos": [440, 220]},
                    {"id": 10, "type": "SaveImage", "title": "Save Image", "pos": [660, 100]},
                ],
                "links": [
                    {"origin_id": 1, "origin_slot": 0, "target_id": 9, "target_slot": 0},
                    {"origin_id": 9, "origin_slot": 0, "target_id": 8, "target_slot": 0},
                    {"origin_id": 8, "origin_slot": 0, "target_id": 10, "target_slot": 0},
                ],
            }
        },
    )

    assert plan["actions"] == [
        {"type": "graph.set_position", "payload": {"node_id": 8, "pos": [440, 220]}},
        {"type": "graph.set_position", "payload": {"node_id": 10, "pos": [660, 220]}},
    ]


def test_rule_planner_vertically_distributes_upstream_nodes_from_selected_node():
    plan = RuleBasedPlanner().plan(
        "把这个节点上游节点纵向等间距排列",
        context={
            "graph_input": {
                "nodes": [
                    {"id": 1, "type": "CheckpointLoaderSimple", "title": "Checkpoint", "pos": [0, 0]},
                    {"id": 3, "type": "CLIPTextEncode", "title": "Positive Prompt", "pos": [40, 120]},
                    {"id": 4, "type": "CLIPTextEncode", "title": "Negative Prompt", "pos": [80, 420]},
                    {"id": 9, "type": "KSampler", "title": "KSampler", "pos": [220, 240]},
                    {"id": 8, "type": "VAEDecode", "title": "VAE Decode", "pos": [440, 360]},
                    {"id": 10, "type": "SaveImage", "title": "Save Image", "selected": True, "pos": [660, 540]},
                ],
                "links": [
                    {"origin_id": 1, "origin_slot": 0, "target_id": 9, "target_slot": 0},
                    {"origin_id": 3, "origin_slot": 0, "target_id": 9, "target_slot": 1},
                    {"origin_id": 4, "origin_slot": 0, "target_id": 9, "target_slot": 2},
                    {"origin_id": 9, "origin_slot": 0, "target_id": 8, "target_slot": 0},
                    {"origin_id": 8, "origin_slot": 0, "target_id": 10, "target_slot": 0},
                ],
            }
        },
    )

    assert plan["actions"] == [
        {"type": "graph.set_position", "payload": {"node_id": 1, "pos": [0, 0]}},
        {"type": "graph.set_position", "payload": {"node_id": 3, "pos": [40, 105]}},
        {"type": "graph.set_position", "payload": {"node_id": 9, "pos": [220, 210]}},
        {"type": "graph.set_position", "payload": {"node_id": 8, "pos": [440, 315]}},
        {"type": "graph.set_position", "payload": {"node_id": 4, "pos": [80, 420]}},
    ]


def test_rule_planner_collapses_selected_node():
    plan = RuleBasedPlanner().plan(
        "折叠这个节点",
        context={
            "graph_input": {
                "nodes": [
                    {"id": 12, "type": "CLIPTextEncode", "title": "Prompt", "selected": True}
                ]
            }
        },
    )

    assert plan["actions"] == [
        {"type": "graph.set_collapsed", "payload": {"node_id": 12, "collapsed": True}}
    ]


def test_rule_planner_expands_all_matching_nodes():
    plan = RuleBasedPlanner().plan(
        "展开所有 KSampler 节点",
        context={
            "graph_input": {
                "nodes": [
                    {"id": 7, "type": "CLIPTextEncode", "title": "Prompt", "collapsed": True},
                    {"id": 9, "type": "KSampler", "title": "KSampler", "collapsed": True},
                    {"id": 10, "type": "KSampler", "title": "Refiner KSampler", "collapsed": True},
                ]
            }
        },
    )

    assert plan["actions"] == [
        {"type": "graph.set_collapsed", "payload": {"node_id": 9, "collapsed": False}},
        {"type": "graph.set_collapsed", "payload": {"node_id": 10, "collapsed": False}},
    ]


def test_rule_planner_resizes_selected_node_box():
    plan = RuleBasedPlanner().plan(
        "把这个节点框大小改成 420x260",
        context={
            "graph_input": {
                "nodes": [
                    {"id": 12, "type": "CLIPTextEncode", "title": "Prompt", "selected": True}
                ]
            }
        },
    )

    assert plan["actions"] == [
        {"type": "graph.set_size", "payload": {"node_id": 12, "size": [420, 260]}}
    ]


def test_rule_planner_resizes_node_box_by_title_in_english():
    plan = RuleBasedPlanner().plan(
        "resize KSampler node box to 360 x 180",
        context={
            "graph_input": {
                "nodes": [
                    {"id": 7, "type": "CLIPTextEncode", "title": "Prompt"},
                    {"id": 9, "type": "KSampler", "title": "KSampler"},
                ]
            }
        },
    )

    assert plan["actions"] == [
        {"type": "graph.set_size", "payload": {"node_id": 9, "size": [360, 180]}}
    ]


def test_rule_planner_does_not_treat_image_resize_as_node_box_resize():
    plan = RuleBasedPlanner().plan(
        "resize ImageScale node to 1024x576",
        context={
            "graph_input": {
                "nodes": [
                    {
                        "id": 4,
                        "type": "ImageScale",
                        "title": "ImageScale",
                        "widgets": [
                            {"name": "width", "value": 512},
                            {"name": "height", "value": 512},
                        ],
                    }
                ]
            }
        },
    )

    assert plan["actions"] == [
        {"type": "graph.set_widget", "payload": {"node_id": 4, "widget": "width", "value": 1024}},
        {"type": "graph.set_widget", "payload": {"node_id": 4, "widget": "height", "value": 576}},
    ]


def test_rule_planner_renames_selected_node_title():
    plan = RuleBasedPlanner().plan(
        "把这个节点标题改成 Main Prompt",
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
        {"type": "graph.set_title", "payload": {"node_id": 12, "title": "Main Prompt"}}
    ]


def test_rule_planner_renames_node_by_title():
    plan = RuleBasedPlanner().plan(
        "把 KSampler 节点重命名为 Final Sampler",
        context={
            "graph_input": {
                "nodes": [
                    {"id": 7, "type": "CLIPTextEncode", "title": "Prompt"},
                    {"id": 9, "type": "KSampler", "title": "KSampler"},
                ]
            }
        },
    )

    assert plan["actions"] == [
        {"type": "graph.set_title", "payload": {"node_id": 9, "title": "Final Sampler"}}
    ]


def test_rule_planner_moves_selected_node_to_absolute_position():
    plan = RuleBasedPlanner().plan(
        "把这个节点移动到 100, 200",
        context={
            "graph_input": {
                "nodes": [
                    {"id": 12, "type": "CLIPTextEncode", "title": "Prompt", "selected": True}
                ]
            }
        },
    )

    assert plan["actions"] == [
        {"type": "graph.set_position", "payload": {"node_id": 12, "pos": [100, 200]}}
    ]


def test_rule_planner_moves_node_right_by_delta():
    plan = RuleBasedPlanner().plan(
        "把 KSampler 往右移动 300",
        context={
            "graph_input": {
                "nodes": [
                    {"id": 7, "type": "CLIPTextEncode", "title": "Prompt", "pos": [0, 0]},
                    {"id": 9, "type": "KSampler", "title": "KSampler", "pos": [10, 20]},
                ]
            }
        },
    )

    assert plan["actions"] == [
        {"type": "graph.set_position", "payload": {"node_id": 9, "pos": [310, 20]}}
    ]


def test_rule_planner_moves_node_to_right_of_named_reference_node():
    plan = RuleBasedPlanner().plan(
        "把 Base KSampler 移到 Refiner KSampler 右边",
        context={
            "graph_input": {
                "nodes": [
                    {"id": 9, "type": "KSampler", "title": "Base KSampler", "pos": [10, 20]},
                    {"id": 10, "type": "KSampler", "title": "Refiner KSampler", "pos": [400, 80]},
                ]
            }
        },
    )

    assert plan["actions"] == [
        {"type": "graph.set_position", "payload": {"node_id": 9, "pos": [620, 80]}}
    ]


def test_rule_planner_moves_first_matching_node_right_of_second_matching_node_by_ordinal():
    plan = RuleBasedPlanner().plan(
        "把第一个 KSampler 移到第二个 KSampler 右边",
        context={
            "graph_input": {
                "nodes": [
                    {"id": 9, "type": "KSampler", "title": "Base KSampler", "pos": [10, 20]},
                    {"id": 10, "type": "KSampler", "title": "Refiner KSampler", "pos": [400, 80]},
                ]
            }
        },
    )

    assert plan["actions"] == [
        {"type": "graph.set_position", "payload": {"node_id": 9, "pos": [620, 80]}}
    ]


def test_rule_planner_moves_node_below_named_reference_node():
    plan = RuleBasedPlanner().plan(
        "把 Base KSampler 放到 Refiner KSampler 下面",
        context={
            "graph_input": {
                "nodes": [
                    {"id": 9, "type": "KSampler", "title": "Base KSampler", "pos": [10, 20]},
                    {"id": 10, "type": "KSampler", "title": "Refiner KSampler", "pos": [400, 80]},
                ]
            }
        },
    )

    assert plan["actions"] == [
        {"type": "graph.set_position", "payload": {"node_id": 9, "pos": [400, 260]}}
    ]


def test_rule_planner_moves_node_to_right_of_named_reference_node_in_english():
    plan = RuleBasedPlanner().plan(
        "move Base KSampler to the right of Refiner KSampler",
        context={
            "graph_input": {
                "nodes": [
                    {"id": 9, "type": "KSampler", "title": "Base KSampler", "pos": [10, 20]},
                    {"id": 10, "type": "KSampler", "title": "Refiner KSampler", "pos": [400, 80]},
                ]
            }
        },
    )

    assert plan["actions"] == [
        {"type": "graph.set_position", "payload": {"node_id": 9, "pos": [620, 80]}}
    ]


def test_rule_planner_moves_selected_nodes_by_delta():
    plan = RuleBasedPlanner().plan(
        "把选中的节点往右移动 100",
        context={
            "graph_input": {
                "nodes": [
                    {"id": 7, "type": "CLIPTextEncode", "title": "Prompt", "selected": True, "pos": [0, 0]},
                    {"id": 9, "type": "KSampler", "title": "KSampler", "selected": True, "pos": [10, 20]},
                    {"id": 10, "type": "VAELoader", "title": "VAE", "selected": False, "pos": [50, 60]},
                ]
            }
        },
    )

    assert plan["actions"] == [
        {"type": "graph.set_position", "payload": {"node_id": 7, "pos": [100, 0]}},
        {"type": "graph.set_position", "payload": {"node_id": 9, "pos": [110, 20]}},
    ]


def test_rule_planner_moves_all_matching_nodes_by_delta():
    plan = RuleBasedPlanner().plan(
        "把所有 KSampler 往下移动 80",
        context={
            "graph_input": {
                "nodes": [
                    {"id": 7, "type": "CLIPTextEncode", "title": "Prompt", "pos": [0, 0]},
                    {"id": 9, "type": "KSampler", "title": "KSampler", "pos": [10, 20]},
                    {"id": 10, "type": "KSampler", "title": "Refiner KSampler", "pos": [50, 60]},
                ]
            }
        },
    )

    assert plan["actions"] == [
        {"type": "graph.set_position", "payload": {"node_id": 9, "pos": [10, 100]}},
        {"type": "graph.set_position", "payload": {"node_id": 10, "pos": [50, 140]}},
    ]


def test_rule_planner_left_aligns_selected_nodes():
    plan = RuleBasedPlanner().plan(
        "把选中的节点左对齐",
        context={
            "graph_input": {
                "nodes": [
                    {"id": 7, "type": "CLIPTextEncode", "title": "Prompt", "selected": True, "pos": [120, 0]},
                    {"id": 9, "type": "KSampler", "title": "KSampler", "selected": True, "pos": [80, 40]},
                    {"id": 10, "type": "VAELoader", "title": "VAE", "selected": False, "pos": [10, 20]},
                ]
            }
        },
    )

    assert plan["actions"] == [
        {"type": "graph.set_position", "payload": {"node_id": 7, "pos": [80, 0]}},
        {"type": "graph.set_position", "payload": {"node_id": 9, "pos": [80, 40]}},
    ]


def test_rule_planner_horizontally_aligns_all_matching_nodes():
    plan = RuleBasedPlanner().plan(
        "把所有 KSampler 节点横向对齐",
        context={
            "graph_input": {
                "nodes": [
                    {"id": 7, "type": "CLIPTextEncode", "title": "Prompt", "pos": [0, 0]},
                    {"id": 9, "type": "KSampler", "title": "KSampler", "pos": [10, 20]},
                    {"id": 10, "type": "KSampler", "title": "Refiner KSampler", "pos": [50, 60]},
                ]
            }
        },
    )

    assert plan["actions"] == [
        {"type": "graph.set_position", "payload": {"node_id": 9, "pos": [10, 20]}},
        {"type": "graph.set_position", "payload": {"node_id": 10, "pos": [50, 20]}},
    ]


def test_rule_planner_distributes_selected_nodes_horizontally():
    plan = RuleBasedPlanner().plan(
        "把选中的节点横向等间距排列",
        context={
            "graph_input": {
                "nodes": [
                    {"id": 7, "type": "CLIPTextEncode", "title": "Prompt", "selected": True, "pos": [10, 0]},
                    {"id": 9, "type": "KSampler", "title": "KSampler", "selected": True, "pos": [70, 40]},
                    {"id": 11, "type": "VAEDecode", "title": "Decode", "selected": True, "pos": [250, 80]},
                    {"id": 12, "type": "VAELoader", "title": "VAE", "selected": False, "pos": [400, 100]},
                ]
            }
        },
    )

    assert plan["actions"] == [
        {"type": "graph.set_position", "payload": {"node_id": 7, "pos": [10, 0]}},
        {"type": "graph.set_position", "payload": {"node_id": 9, "pos": [130, 40]}},
        {"type": "graph.set_position", "payload": {"node_id": 11, "pos": [250, 80]}},
    ]


def test_rule_planner_distributes_all_matching_nodes_vertically():
    plan = RuleBasedPlanner().plan(
        "把所有 KSampler 节点纵向等间距排列",
        context={
            "graph_input": {
                "nodes": [
                    {"id": 7, "type": "CLIPTextEncode", "title": "Prompt", "pos": [0, 0]},
                    {"id": 9, "type": "KSampler", "title": "KSampler", "pos": [10, 20]},
                    {"id": 10, "type": "KSampler", "title": "Refiner KSampler", "pos": [50, 50]},
                    {"id": 11, "type": "KSampler", "title": "Final KSampler", "pos": [90, 200]},
                ]
            }
        },
    )

    assert plan["actions"] == [
        {"type": "graph.set_position", "payload": {"node_id": 9, "pos": [10, 20]}},
        {"type": "graph.set_position", "payload": {"node_id": 10, "pos": [50, 110]}},
        {"type": "graph.set_position", "payload": {"node_id": 11, "pos": [90, 200]}},
    ]


def test_rule_planner_auto_layouts_workflow_by_links():
    plan = RuleBasedPlanner().plan(
        "整理这个工作流",
        context={
            "graph_input": {
                "nodes": [
                    {"id": 1, "type": "CheckpointLoaderSimple", "title": "Checkpoint", "pos": [500, 100]},
                    {"id": 3, "type": "CLIPTextEncode", "title": "Positive Prompt", "pos": [100, 220]},
                    {"id": 4, "type": "CLIPTextEncode", "title": "Negative Prompt", "pos": [160, 360]},
                    {"id": 9, "type": "KSampler", "title": "KSampler", "pos": [700, 260]},
                    {"id": 8, "type": "VAEDecode", "title": "VAE Decode", "pos": [40, 80]},
                    {"id": 10, "type": "SaveImage", "title": "Save Image", "pos": [900, 420]},
                ],
                "links": [
                    {"origin_id": 1, "origin_slot": 0, "target_id": 9, "target_slot": 0},
                    {"origin_id": 3, "origin_slot": 0, "target_id": 9, "target_slot": 1},
                    {"origin_id": 4, "origin_slot": 0, "target_id": 9, "target_slot": 2},
                    {"origin_id": 9, "origin_slot": 0, "target_id": 8, "target_slot": 0},
                    {"origin_id": 8, "origin_slot": 0, "target_id": 10, "target_slot": 0},
                ],
            }
        },
    )

    assert plan["actions"] == [
        {"type": "graph.set_position", "payload": {"node_id": 1, "pos": [40, 80]}},
        {"type": "graph.set_position", "payload": {"node_id": 3, "pos": [40, 260]}},
        {"type": "graph.set_position", "payload": {"node_id": 4, "pos": [40, 440]}},
        {"type": "graph.set_position", "payload": {"node_id": 9, "pos": [260, 80]}},
        {"type": "graph.set_position", "payload": {"node_id": 8, "pos": [480, 80]}},
        {"type": "graph.set_position", "payload": {"node_id": 10, "pos": [700, 80]}},
    ]


def test_rule_planner_selects_node_by_title():
    plan = RuleBasedPlanner().plan(
        "选中 KSampler 节点",
        context={
            "graph_input": {
                "nodes": [
                    {"id": 7, "type": "CLIPTextEncode", "title": "Prompt"},
                    {"id": 9, "type": "KSampler", "title": "KSampler"},
                ]
            }
        },
    )

    assert plan["actions"] == [
        {"type": "graph.select_node", "payload": {"node_id": 9, "focus": False}}
    ]


def test_rule_planner_selects_all_matching_nodes():
    plan = RuleBasedPlanner().plan(
        "选中所有 KSampler 节点",
        context={
            "graph_input": {
                "nodes": [
                    {"id": 7, "type": "CLIPTextEncode", "title": "Prompt"},
                    {"id": 9, "type": "KSampler", "title": "KSampler"},
                    {"id": 10, "type": "KSampler", "title": "Refiner KSampler"},
                ]
            }
        },
    )

    assert plan["actions"] == [
        {"type": "graph.select_nodes", "payload": {"node_ids": [9, 10], "focus": False}}
    ]


def test_rule_planner_focuses_node_by_id():
    plan = RuleBasedPlanner().plan(
        "聚焦 12 号节点",
        context={
            "graph_input": {
                "nodes": [
                    {"id": 12, "type": "KSampler", "title": "KSampler"},
                ]
            }
        },
    )

    assert plan["actions"] == [
        {"type": "graph.select_node", "payload": {"node_id": 12, "focus": True}}
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


def test_rule_planner_connects_sampler_to_vae_decode_by_chinese_alias():
    plan = RuleBasedPlanner().plan(
        "把 KSampler 接到 VAE 解码节点",
        context={
            "graph_input": {
                "nodes": [
                    {
                        "id": 9,
                        "type": "KSampler",
                        "title": "KSampler",
                        "outputs": [{"name": "LATENT", "type": "LATENT"}],
                    },
                    {
                        "id": 4,
                        "type": "VAEDecode",
                        "title": "Decode",
                        "inputs": [
                            {"name": "samples", "type": "LATENT"},
                            {"name": "vae", "type": "VAE"},
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
                "origin_node_id": 9,
                "origin_slot": 0,
                "target_node_id": 4,
                "target_slot": 0,
            },
        }
    ]


def test_rule_planner_connects_load_image_to_vae_encode_by_chinese_alias():
    plan = RuleBasedPlanner().plan(
        "把加载图片接到 VAE 编码节点",
        context={
            "graph_input": {
                "nodes": [
                    {
                        "id": 6,
                        "type": "LoadImage",
                        "title": "Load Image",
                        "outputs": [{"name": "IMAGE", "type": "IMAGE"}],
                    },
                    {
                        "id": 5,
                        "type": "VAEEncode",
                        "title": "Encode",
                        "inputs": [
                            {"name": "pixels", "type": "IMAGE"},
                            {"name": "vae", "type": "VAE"},
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
                "origin_node_id": 6,
                "origin_slot": 0,
                "target_node_id": 5,
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


def test_rule_planner_connects_selected_node_to_named_target_slot():
    plan = RuleBasedPlanner().plan(
        "把这个节点的 CONDITIONING 接到 KSampler 的 positive",
        context={
            "graph_input": {
                "nodes": [
                    {
                        "id": 7,
                        "type": "CLIPTextEncode",
                        "title": "Prompt",
                        "selected": True,
                        "outputs": [{"name": "CONDITIONING", "type": "CONDITIONING"}],
                    },
                    {
                        "id": 9,
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
                "origin_node_id": 7,
                "origin_slot": 0,
                "target_node_id": 9,
                "target_slot": 1,
            },
        }
    ]


def test_rule_planner_connects_semantic_prompt_node_to_sampler_slot():
    plan = RuleBasedPlanner().plan(
        "把正向提示词的 CONDITIONING 连到 KSampler 的 positive",
        context={
            "graph_input": {
                "nodes": [
                    {
                        "id": 7,
                        "type": "CLIPTextEncode",
                        "title": "Positive Prompt",
                        "outputs": [{"name": "CONDITIONING", "type": "CONDITIONING"}],
                    },
                    {
                        "id": 8,
                        "type": "CLIPTextEncode",
                        "title": "Negative Prompt",
                        "outputs": [{"name": "CONDITIONING", "type": "CONDITIONING"}],
                    },
                    {
                        "id": 9,
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
                "origin_node_id": 7,
                "origin_slot": 0,
                "target_node_id": 9,
                "target_slot": 1,
            },
        }
    ]


def test_rule_planner_infers_positive_sampler_slot_when_connecting_positive_prompt():
    plan = RuleBasedPlanner().plan(
        "把正向提示词接到 KSampler",
        context={
            "graph_input": {
                "nodes": [
                    {
                        "id": 7,
                        "type": "CLIPTextEncode",
                        "title": "Positive Prompt",
                        "outputs": [{"name": "CONDITIONING", "type": "CONDITIONING"}],
                    },
                    {
                        "id": 9,
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
                "origin_node_id": 7,
                "origin_slot": 0,
                "target_node_id": 9,
                "target_slot": 1,
            },
        }
    ]


def test_rule_planner_infers_negative_sampler_slot_when_connecting_negative_prompt():
    plan = RuleBasedPlanner().plan(
        "把负面提示词接到 KSampler",
        context={
            "graph_input": {
                "nodes": [
                    {
                        "id": 8,
                        "type": "CLIPTextEncode",
                        "title": "Negative Prompt",
                        "outputs": [{"name": "CONDITIONING", "type": "CONDITIONING"}],
                    },
                    {
                        "id": 9,
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
                "origin_node_id": 8,
                "origin_slot": 0,
                "target_node_id": 9,
                "target_slot": 2,
            },
        }
    ]


def test_rule_planner_reroutes_node_output_to_new_target():
    plan = RuleBasedPlanner().plan(
        "把 VAE Decode 改接到 Preview Image",
        context={
            "graph_input": {
                "nodes": [
                    {
                        "id": 8,
                        "type": "VAEDecode",
                        "title": "VAE Decode",
                        "outputs": [{"name": "IMAGE", "type": "IMAGE"}],
                    },
                    {
                        "id": 9,
                        "type": "SaveImage",
                        "title": "Save Image",
                        "inputs": [{"name": "images", "type": "IMAGE"}],
                    },
                    {
                        "id": 10,
                        "type": "PreviewImage",
                        "title": "Preview Image",
                        "inputs": [{"name": "images", "type": "IMAGE"}],
                    },
                ],
                "links": [
                    {
                        "id": 77,
                        "origin_id": 8,
                        "origin_slot": 0,
                        "target_id": 9,
                        "target_slot": 0,
                    }
                ],
            }
        },
    )

    assert plan["actions"] == [
        {"type": "graph.disconnect", "payload": {"origin_node_id": 8, "origin_slot": 0}},
        {
            "type": "graph.connect",
            "payload": {
                "origin_node_id": 8,
                "origin_slot": 0,
                "target_node_id": 10,
                "target_slot": 0,
            },
        },
    ]


def test_rule_planner_reroutes_semantic_prompt_to_sampler_slot():
    plan = RuleBasedPlanner().plan(
        "把正向提示词重新接到 Refiner KSampler 的 positive",
        context={
            "graph_input": {
                "nodes": [
                    {
                        "id": 7,
                        "type": "CLIPTextEncode",
                        "title": "Positive Prompt",
                        "outputs": [{"name": "CONDITIONING", "type": "CONDITIONING"}],
                    },
                    {
                        "id": 9,
                        "type": "KSampler",
                        "title": "KSampler",
                        "inputs": [
                            {"name": "model", "type": "MODEL"},
                            {"name": "positive", "type": "CONDITIONING"},
                            {"name": "negative", "type": "CONDITIONING"},
                        ],
                    },
                    {
                        "id": 10,
                        "type": "KSampler",
                        "title": "Refiner KSampler",
                        "inputs": [
                            {"name": "model", "type": "MODEL"},
                            {"name": "positive", "type": "CONDITIONING"},
                            {"name": "negative", "type": "CONDITIONING"},
                        ],
                    },
                ],
                "links": [
                    {
                        "id": 77,
                        "origin_id": 7,
                        "origin_slot": 0,
                        "target_id": 9,
                        "target_slot": 1,
                    }
                ],
            }
        },
    )

    assert plan["actions"] == [
        {"type": "graph.disconnect", "payload": {"origin_node_id": 7, "origin_slot": 0}},
        {
            "type": "graph.connect",
            "payload": {
                "origin_node_id": 7,
                "origin_slot": 0,
                "target_node_id": 10,
                "target_slot": 1,
            },
        },
    ]


def test_rule_planner_reroutes_target_input_to_new_origin():
    plan = RuleBasedPlanner().plan(
        "把 KSampler 的 positive 输入改接到 Refiner Positive Prompt",
        context={
            "graph_input": {
                "nodes": [
                    {
                        "id": 7,
                        "type": "CLIPTextEncode",
                        "title": "Positive Prompt",
                        "outputs": [{"name": "CONDITIONING", "type": "CONDITIONING"}],
                    },
                    {
                        "id": 9,
                        "type": "KSampler",
                        "title": "KSampler",
                        "inputs": [
                            {"name": "model", "type": "MODEL"},
                            {"name": "positive", "type": "CONDITIONING"},
                            {"name": "negative", "type": "CONDITIONING"},
                        ],
                    },
                    {
                        "id": 10,
                        "type": "CLIPTextEncode",
                        "title": "Refiner Positive Prompt",
                        "outputs": [{"name": "CONDITIONING", "type": "CONDITIONING"}],
                    },
                ],
                "links": [
                    {
                        "id": 77,
                        "origin_id": 7,
                        "origin_slot": 0,
                        "target_id": 9,
                        "target_slot": 1,
                    }
                ],
            }
        },
    )

    assert plan["actions"] == [
        {"type": "graph.disconnect", "payload": {"target_node_id": 9, "target_slot": 1}},
        {
            "type": "graph.connect",
            "payload": {
                "origin_node_id": 10,
                "origin_slot": 0,
                "target_node_id": 9,
                "target_slot": 1,
            },
        },
    ]


def test_rule_planner_reroutes_selected_target_input_to_new_origin():
    plan = RuleBasedPlanner().plan(
        "把这个节点的 images 输入重新接到 VAE Decode",
        context={
            "graph_input": {
                "nodes": [
                    {
                        "id": 8,
                        "type": "VAEDecode",
                        "title": "VAE Decode",
                        "outputs": [{"name": "IMAGE", "type": "IMAGE"}],
                    },
                    {
                        "id": 9,
                        "type": "PreviewImage",
                        "title": "Preview Image",
                        "selected": True,
                        "inputs": [{"name": "images", "type": "IMAGE"}],
                    },
                    {
                        "id": 10,
                        "type": "LoadImage",
                        "title": "Old Image",
                        "outputs": [{"name": "IMAGE", "type": "IMAGE"}],
                    },
                ],
                "links": [
                    {
                        "id": 77,
                        "origin_id": 10,
                        "origin_slot": 0,
                        "target_id": 9,
                        "target_slot": 0,
                    }
                ],
            }
        },
    )

    assert plan["actions"] == [
        {"type": "graph.disconnect", "payload": {"target_node_id": 9, "target_slot": 0}},
        {
            "type": "graph.connect",
            "payload": {
                "origin_node_id": 8,
                "origin_slot": 0,
                "target_node_id": 9,
                "target_slot": 0,
            },
        },
    ]


def test_rule_planner_disconnects_target_input_by_title_and_slot_name():
    plan = RuleBasedPlanner().plan(
        "断开 KSampler 的 positive 输入",
        context={
            "graph_input": {
                "nodes": [
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
            "type": "graph.disconnect",
            "payload": {"target_node_id": 2, "target_slot": 1},
        }
    ]


def test_rule_planner_disconnects_selected_node_input():
    plan = RuleBasedPlanner().plan(
        "断开这个节点的 model 输入",
        context={
            "graph_input": {
                "nodes": [
                    {
                        "id": 2,
                        "type": "KSampler",
                        "title": "KSampler",
                        "selected": True,
                        "inputs": [
                            {"name": "model", "type": "MODEL"},
                            {"name": "positive", "type": "CONDITIONING"},
                        ],
                    },
                ]
            }
        },
    )

    assert plan["actions"] == [
        {
            "type": "graph.disconnect",
            "payload": {"target_node_id": 2, "target_slot": 0},
        }
    ]


def test_rule_planner_disconnects_origin_output_by_title_and_slot_name():
    plan = RuleBasedPlanner().plan(
        "断开 Checkpoint 的 MODEL 输出",
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
                        "id": 2,
                        "type": "KSampler",
                        "title": "KSampler",
                        "inputs": [{"name": "model", "type": "MODEL"}],
                    },
                ],
                "links": [
                    {
                        "id": 77,
                        "origin_id": 1,
                        "origin_slot": 0,
                        "target_id": 2,
                        "target_slot": 0,
                    }
                ],
            }
        },
    )

    assert plan["actions"] == [
        {
            "type": "graph.disconnect",
            "payload": {"origin_node_id": 1, "origin_slot": 0},
        }
    ]


def test_rule_planner_disconnects_nodes_by_title_pair():
    plan = RuleBasedPlanner().plan(
        "断开 Checkpoint 到 KSampler 的连接",
        context={
            "graph_input": {
                "nodes": [
                    {"id": 1, "type": "CheckpointLoaderSimple", "title": "Checkpoint"},
                    {"id": 2, "type": "KSampler", "title": "KSampler"},
                ],
                "links": [
                    {
                        "id": 77,
                        "origin_id": 1,
                        "origin_slot": 0,
                        "target_id": 2,
                        "target_slot": 0,
                    }
                ],
            }
        },
    )

    assert plan["actions"] == [
        {
            "type": "graph.disconnect",
            "payload": {"origin_node_id": 1, "target_node_id": 2},
        }
    ]


def test_rule_planner_disconnects_all_inputs_on_selected_node():
    plan = RuleBasedPlanner().plan(
        "断开这个节点的所有输入",
        context={
            "graph_input": {
                "nodes": [
                    {"id": 2, "type": "KSampler", "title": "KSampler", "selected": True}
                ],
                "links": [
                    {"id": 77, "origin_id": 1, "origin_slot": 0, "target_id": 2, "target_slot": 0},
                    {"id": 78, "origin_id": 3, "origin_slot": 0, "target_id": 2, "target_slot": 1},
                    {"id": 79, "origin_id": 2, "origin_slot": 0, "target_id": 4, "target_slot": 0},
                ],
            }
        },
    )

    assert plan["actions"] == [
        {"type": "graph.disconnect", "payload": {"target_node_id": 2}}
    ]


def test_rule_planner_disconnects_all_outputs_on_node_by_title():
    plan = RuleBasedPlanner().plan(
        "断开 KSampler 的所有输出",
        context={
            "graph_input": {
                "nodes": [
                    {"id": 2, "type": "KSampler", "title": "KSampler"},
                    {"id": 4, "type": "VAEDecode", "title": "Decode"},
                ],
                "links": [
                    {"id": 77, "origin_id": 1, "origin_slot": 0, "target_id": 2, "target_slot": 0},
                    {"id": 79, "origin_id": 2, "origin_slot": 0, "target_id": 4, "target_slot": 0},
                ],
            }
        },
    )

    assert plan["actions"] == [
        {"type": "graph.disconnect", "payload": {"origin_node_id": 2}}
    ]


def test_rule_planner_disconnects_all_links_on_selected_node():
    plan = RuleBasedPlanner().plan(
        "断开这个节点的所有连接",
        context={
            "graph_input": {
                "nodes": [
                    {"id": 2, "type": "KSampler", "title": "KSampler", "selected": True}
                ],
                "links": [
                    {"id": 77, "origin_id": 1, "origin_slot": 0, "target_id": 2, "target_slot": 0},
                    {"id": 79, "origin_id": 2, "origin_slot": 0, "target_id": 4, "target_slot": 0},
                ],
            }
        },
    )

    assert plan["actions"] == [
        {"type": "graph.disconnect", "payload": {"node_id": 2}}
    ]


def test_rule_planner_disconnects_downstream_node_inputs_by_links():
    plan = RuleBasedPlanner().plan(
        "断开 KSampler 后面的节点的所有输入",
        context={
            "graph_input": {
                "nodes": [
                    {"id": 1, "type": "CheckpointLoaderSimple", "title": "Checkpoint"},
                    {"id": 9, "type": "KSampler", "title": "KSampler"},
                    {"id": 8, "type": "VAEDecode", "title": "VAE Decode"},
                    {"id": 10, "type": "SaveImage", "title": "Save Image"},
                ],
                "links": [
                    {"id": 77, "origin_id": 1, "origin_slot": 0, "target_id": 9, "target_slot": 0},
                    {"id": 78, "origin_id": 9, "origin_slot": 0, "target_id": 8, "target_slot": 0},
                    {"id": 79, "origin_id": 8, "origin_slot": 0, "target_id": 10, "target_slot": 0},
                ],
            }
        },
    )

    assert plan["actions"] == [
        {"type": "graph.disconnect", "payload": {"target_node_id": 8}},
        {"type": "graph.disconnect", "payload": {"target_node_id": 10}},
    ]


def test_rule_planner_disconnects_upstream_node_outputs_from_selected_node():
    plan = RuleBasedPlanner().plan(
        "断开这个节点上游节点的所有输出",
        context={
            "graph_input": {
                "nodes": [
                    {"id": 1, "type": "CheckpointLoaderSimple", "title": "Checkpoint"},
                    {"id": 3, "type": "CLIPTextEncode", "title": "Positive Prompt"},
                    {"id": 4, "type": "CLIPTextEncode", "title": "Negative Prompt"},
                    {"id": 9, "type": "KSampler", "title": "KSampler"},
                    {"id": 8, "type": "VAEDecode", "title": "VAE Decode"},
                    {"id": 10, "type": "SaveImage", "title": "Save Image", "selected": True},
                ],
                "links": [
                    {"id": 77, "origin_id": 1, "origin_slot": 0, "target_id": 9, "target_slot": 0},
                    {"id": 78, "origin_id": 3, "origin_slot": 0, "target_id": 9, "target_slot": 1},
                    {"id": 79, "origin_id": 4, "origin_slot": 0, "target_id": 9, "target_slot": 2},
                    {"id": 80, "origin_id": 9, "origin_slot": 0, "target_id": 8, "target_slot": 0},
                    {"id": 81, "origin_id": 8, "origin_slot": 0, "target_id": 10, "target_slot": 0},
                ],
            }
        },
    )

    assert plan["actions"] == [
        {"type": "graph.disconnect", "payload": {"origin_node_id": 1}},
        {"type": "graph.disconnect", "payload": {"origin_node_id": 3}},
        {"type": "graph.disconnect", "payload": {"origin_node_id": 4}},
        {"type": "graph.disconnect", "payload": {"origin_node_id": 9}},
        {"type": "graph.disconnect", "payload": {"origin_node_id": 8}},
    ]


def test_rule_planner_plans_restart_container():
    plan = RuleBasedPlanner().plan("重启 ComfyUI 容器", context={})

    assert plan["actions"] == [
        {"type": "service.restart_container", "payload": {"container": "comfyui-gb10"}}
    ]


def test_rule_planner_plans_recent_comfyui_logs():
    plan = RuleBasedPlanner().plan("查看 ComfyUI 最近日志", context={})

    assert plan["actions"] == [
        {"type": "service.logs", "payload": {"container": "comfyui-gb10", "tail": 80}}
    ]


def test_rule_planner_plans_stop_container():
    plan = RuleBasedPlanner().plan("停止 ComfyUI 容器", context={})

    assert plan["actions"] == [
        {"type": "service.stop_container", "payload": {"container": "comfyui-gb10"}}
    ]


def test_rule_planner_plans_start_container():
    plan = RuleBasedPlanner().plan("启动 ComfyUI 容器", context={})

    assert plan["actions"] == [
        {"type": "service.start_container", "payload": {"container": "comfyui-gb10"}}
    ]


def test_rule_planner_plans_update_comfyui_then_restart():
    plan = RuleBasedPlanner().plan("更新 ComfyUI 本体然后重启 ComfyUI", context={})

    assert plan["actions"] == [
        {"type": "service.update_comfyui", "payload": {}},
        {"type": "service.restart_container", "payload": {"container": "comfyui-gb10"}},
    ]


def test_rule_planner_plans_restore_original_container_config():
    plan = RuleBasedPlanner().plan("回滚到原始 ComfyUI 容器配置", context={})

    assert plan["summary"] == "Restore original ComfyUI container configuration"
    assert plan["actions"] == [{"type": "service.restore_original", "payload": {}}]


def test_rule_planner_plans_stop_ollama_model():
    plan = RuleBasedPlanner().plan("停止 ollama 模型 nemotron-3-nano:30b", context={})

    assert plan["actions"] == [
        {"type": "runtime.stop_ollama_model", "payload": {"model": "nemotron-3-nano:30b"}}
    ]


def test_rule_planner_plans_queue_current_workflow():
    plan = RuleBasedPlanner().plan("开始生成当前工作流", context={})

    assert plan["actions"] == [{"type": "runtime.queue_prompt", "payload": {"front": False}}]


def test_rule_planner_plans_queue_current_workflow_to_front():
    plan = RuleBasedPlanner().plan("插队生成当前工作流", context={})

    assert plan["actions"] == [{"type": "runtime.queue_prompt", "payload": {"front": True}}]


def test_rule_planner_plans_clear_pending_queue():
    plan = RuleBasedPlanner().plan("清空待执行队列", context={})

    assert plan["actions"] == [{"type": "runtime.clear_queue", "payload": {}}]


def test_rule_planner_plans_interrupt_current_generation():
    plan = RuleBasedPlanner().plan("停止当前生成", context={})

    assert plan["actions"] == [{"type": "runtime.interrupt", "payload": {}}]


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


def test_rule_planner_plans_compose_command_flag_enable_and_disable():
    enable_plan = RuleBasedPlanner().plan("给 ComfyUI 启用 compose flag --bf16-vae 并应用配置", context={})
    disable_plan = RuleBasedPlanner().plan("从 compose 里移除 --bf16-vae 并应用配置", context={})

    assert enable_plan["actions"] == [
        {
            "type": "compose.set_command_flag",
            "payload": {"flag": "--bf16-vae", "enabled": True},
        }
    ]
    assert disable_plan["actions"] == [
        {
            "type": "compose.set_command_flag",
            "payload": {"flag": "--bf16-vae", "enabled": False},
        }
    ]


def test_rule_planner_plans_compose_command_flag_from_natural_aliases():
    enable_plan = RuleBasedPlanner().plan("打开 ComfyUI 的 bf16 vae 启动参数并应用配置", context={})
    disable_plan = RuleBasedPlanner().plan("关掉 ComfyUI 的 cuda malloc 启动参数", context={})

    assert enable_plan["actions"] == [
        {
            "type": "compose.set_command_flag",
            "payload": {"flag": "--bf16-vae", "enabled": True},
        }
    ]
    assert disable_plan["actions"] == [
        {
            "type": "compose.set_command_flag",
            "payload": {"flag": "--disable-cuda-malloc", "enabled": False},
        }
    ]


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


def test_rule_planner_plans_plugin_install_from_git_url():
    plan = RuleBasedPlanner().plan(
        "安装插件 https://github.com/example/ComfyUI-TestNode.git",
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


def test_rule_planner_plans_custom_node_install_by_manager_id():
    plan = RuleBasedPlanner().plan("安装 custom node ComfyUI-Impact-Pack", context={})

    assert plan["actions"] == [
        {
            "type": "custom_node.install",
            "payload": {
                "method": "manager_queue",
                "node": {
                    "id": "ComfyUI-Impact-Pack",
                    "version": "unknown",
                    "ui_id": "ComfyUI-Impact-Pack",
                    "files": ["ComfyUI-Impact-Pack"],
                    "channel": "default",
                    "mode": "cache",
                },
            },
        }
    ]


def test_rule_planner_plans_plugin_install_when_id_precedes_marker():
    plan = RuleBasedPlanner().plan("安装 ComfyUI-Impact-Pack 插件", context={})

    assert plan["actions"] == [
        {
            "type": "custom_node.install",
            "payload": {
                "method": "manager_queue",
                "node": {
                    "id": "ComfyUI-Impact-Pack",
                    "version": "unknown",
                    "ui_id": "ComfyUI-Impact-Pack",
                    "files": ["ComfyUI-Impact-Pack"],
                    "channel": "default",
                    "mode": "cache",
                },
            },
        }
    ]


def test_rule_planner_plans_plugin_install_by_manager_id_then_restart():
    plan = RuleBasedPlanner().plan("安装插件 ComfyUI-Impact-Pack 然后重启 ComfyUI", context={})

    assert plan["actions"] == [
        {
            "type": "custom_node.install",
            "payload": {
                "method": "manager_queue",
                "node": {
                    "id": "ComfyUI-Impact-Pack",
                    "version": "unknown",
                    "ui_id": "ComfyUI-Impact-Pack",
                    "files": ["ComfyUI-Impact-Pack"],
                    "channel": "default",
                    "mode": "cache",
                },
            },
        },
        {"type": "service.restart_container", "payload": {"container": "comfyui-gb10"}},
    ]


def test_rule_planner_plans_plugin_install_then_bare_restart():
    plan = RuleBasedPlanner().plan("安装 Impact-Pack 插件然后重启", context={})

    assert plan["actions"] == [
        {
            "type": "custom_node.install",
            "payload": {
                "method": "manager_queue",
                "node": {
                    "id": "Impact-Pack",
                    "version": "unknown",
                    "ui_id": "Impact-Pack",
                    "files": ["Impact-Pack"],
                    "channel": "default",
                    "mode": "cache",
                },
            },
        },
        {"type": "service.restart_container", "payload": {"container": "comfyui-gb10"}},
    ]


def test_rule_planner_installs_missing_workflow_nodes_from_graph_types_then_restart():
    plan = RuleBasedPlanner().plan(
        "安装当前工作流缺失节点然后重启 ComfyUI",
        context={
            "graph_input": {
                "nodes": [
                    {"id": 1, "type": "SaveImage", "title": "Save Image"},
                    {"id": 2, "type": "ImpactWildcard", "title": "Impact Wildcard"},
                    {"id": 3, "type": "ImpactWildcard", "title": "Impact Wildcard Copy"},
                ],
                "node_types": [{"type": "SaveImage", "title": "Save Image"}],
            }
        },
    )

    assert plan["actions"] == [
        {
            "type": "custom_node.install",
            "payload": {
                "method": "manager_queue",
                "node": {
                    "id": "ImpactWildcard",
                    "version": "unknown",
                    "ui_id": "ImpactWildcard",
                    "files": ["ImpactWildcard"],
                    "channel": "default",
                    "mode": "cache",
                },
            },
        },
        {"type": "service.restart_container", "payload": {"container": "comfyui-gb10"}},
    ]


def test_rule_planner_prefers_manager_metadata_for_missing_workflow_nodes():
    plan = RuleBasedPlanner().plan(
        "修复这个工作流里的 missing nodes",
        context={
            "graph_input": {
                "nodes": [
                    {
                        "id": 4,
                        "type": "ImpactWildcard",
                        "title": "Impact Wildcard",
                        "properties": {"cnr_id": "ComfyUI-Impact-Pack"},
                    }
                ],
                "node_types": [{"type": "SaveImage", "title": "Save Image"}],
            }
        },
    )

    assert plan["actions"] == [
        {
            "type": "custom_node.install",
            "payload": {
                "method": "manager_queue",
                "node": {
                    "id": "ComfyUI-Impact-Pack",
                    "version": "unknown",
                    "ui_id": "ComfyUI-Impact-Pack",
                    "files": ["ComfyUI-Impact-Pack"],
                    "channel": "default",
                    "mode": "cache",
                },
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


def test_rule_planner_plans_plugin_disable():
    plan = RuleBasedPlanner().plan("禁用插件 ComfyUI-TestNode", context={})

    assert plan["actions"] == [
        {"type": "custom_node.disable", "payload": {"id": "ComfyUI-TestNode"}}
    ]


def test_rule_planner_plans_plugin_disable_when_id_precedes_marker():
    plan = RuleBasedPlanner().plan("禁用 ComfyUI-TestNode 插件", context={})

    assert plan["actions"] == [
        {"type": "custom_node.disable", "payload": {"id": "ComfyUI-TestNode"}}
    ]


def test_rule_planner_plans_plugin_close_then_restart_from_natural_phrase():
    plan = RuleBasedPlanner().plan("把 ComfyUI-Impact-Pack 插件关掉然后重启服务", context={})

    assert plan["actions"] == [
        {"type": "custom_node.disable", "payload": {"id": "ComfyUI-Impact-Pack"}},
        {"type": "service.restart_container", "payload": {"container": "comfyui-gb10"}},
    ]


def test_rule_planner_plans_plugin_open_then_restart_from_natural_phrase():
    plan = RuleBasedPlanner().plan("打开 ComfyUI-Impact-Pack 插件并重启", context={})

    assert plan["actions"] == [
        {"type": "custom_node.enable", "payload": {"id": "ComfyUI-Impact-Pack"}},
        {"type": "service.restart_container", "payload": {"container": "comfyui-gb10"}},
    ]


def test_rule_planner_plans_extension_enable_then_restart_when_id_precedes_marker():
    plan = RuleBasedPlanner().plan("启用 ComfyUI-TestNode 扩展然后重启 ComfyUI", context={})

    assert plan["actions"] == [
        {"type": "custom_node.enable", "payload": {"id": "ComfyUI-TestNode"}},
        {"type": "service.restart_container", "payload": {"container": "comfyui-gb10"}},
    ]


def test_rule_planner_plans_custom_node_uninstall_and_plugin_remove():
    uninstall_plan = RuleBasedPlanner().plan("卸载 custom node ComfyUI-TestNode", context={})
    remove_plan = RuleBasedPlanner().plan("移除 ComfyUI-OldNode 插件然后重启 ComfyUI", context={})

    assert uninstall_plan["actions"] == [
        {"type": "custom_node.uninstall", "payload": {"id": "ComfyUI-TestNode"}}
    ]
    assert remove_plan["actions"] == [
        {"type": "custom_node.uninstall", "payload": {"id": "ComfyUI-OldNode"}},
        {"type": "service.restart_container", "payload": {"container": "comfyui-gb10"}},
    ]


def test_rule_planner_plans_custom_node_version_switch():
    plan = RuleBasedPlanner().plan(
        "把 ComfyUI-Impact-Pack 插件切换到版本 1.2.3 然后重启 ComfyUI",
        context={},
    )

    assert plan["actions"] == [
        {
            "type": "custom_node.switch_version",
            "payload": {"id": "ComfyUI-Impact-Pack", "version": "1.2.3"},
        },
        {"type": "service.restart_container", "payload": {"container": "comfyui-gb10"}},
    ]


def test_rule_planner_plans_custom_node_update_reinstall_and_fix():
    update_plan = RuleBasedPlanner().plan("更新 custom node ComfyUI-TestNode", context={})
    reinstall_plan = RuleBasedPlanner().plan("重装 custom node ComfyUI-TestNode", context={})
    fix_plan = RuleBasedPlanner().plan("修复 custom node ComfyUI-BrokenNode", context={})

    assert update_plan["actions"] == [
        {"type": "custom_node.update", "payload": {"id": "ComfyUI-TestNode"}}
    ]
    assert reinstall_plan["actions"] == [
        {"type": "custom_node.reinstall", "payload": {"id": "ComfyUI-TestNode"}}
    ]
    assert fix_plan["actions"] == [
        {"type": "custom_node.fix", "payload": {"id": "ComfyUI-BrokenNode"}}
    ]


def test_rule_planner_plans_extension_fix():
    plan = RuleBasedPlanner().plan("修复扩展 ComfyUI-BrokenNode", context={})

    assert plan["actions"] == [
        {"type": "custom_node.fix", "payload": {"id": "ComfyUI-BrokenNode"}}
    ]


def test_rule_planner_plans_custom_node_update_all():
    plan = RuleBasedPlanner().plan("更新全部 custom nodes", context={})

    assert plan["actions"] == [{"type": "custom_node.update_all", "payload": {}}]


def test_rule_planner_plans_plugin_update_all():
    plan = RuleBasedPlanner().plan("更新全部插件", context={})

    assert plan["actions"] == [{"type": "custom_node.update_all", "payload": {}}]


def test_rule_planner_plans_plugin_update_all_then_bare_restart():
    plan = RuleBasedPlanner().plan("更新全部插件后重启", context={})

    assert plan["actions"] == [
        {"type": "custom_node.update_all", "payload": {}},
        {"type": "service.restart_container", "payload": {"container": "comfyui-gb10"}},
    ]


def test_rule_planner_plans_installed_plugin_update_all_then_restart():
    plan = RuleBasedPlanner().plan("更新已安装插件然后重启服务", context={})

    assert plan["actions"] == [
        {"type": "custom_node.update_all", "payload": {}},
        {"type": "service.restart_container", "payload": {"container": "comfyui-gb10"}},
    ]


def test_rule_planner_plans_manager_queue_status_for_install_progress():
    plan = RuleBasedPlanner().plan("查看 Manager 安装队列状态", context={})

    assert plan["actions"] == [{"type": "manager.queue_status", "payload": {}}]


def test_rule_planner_plans_manager_queue_start():
    plan = RuleBasedPlanner().plan("开始 Manager 安装队列", context={})

    assert plan["actions"] == [{"type": "manager.queue_start", "payload": {}}]


def test_rule_planner_plans_manager_queue_reset():
    plan = RuleBasedPlanner().plan("清空 Manager 安装队列", context={})

    assert plan["actions"] == [{"type": "manager.queue_reset", "payload": {}}]


def test_rule_planner_does_not_invent_manager_queue_pause_endpoint():
    plan = RuleBasedPlanner().plan("暂停 Manager 安装队列", context={})

    assert plan["actions"] == [
        {"type": "context.collect", "payload": {"message": "暂停 Manager 安装队列"}}
    ]


def test_rule_planner_plans_manager_queue_status_for_model_download_progress():
    plan = RuleBasedPlanner().plan("看看模型下载进度", context={})

    assert plan["actions"] == [{"type": "manager.queue_status", "payload": {}}]


def test_rule_planner_plans_installed_custom_node_list_read():
    plan = RuleBasedPlanner().plan("列出已安装插件", context={})

    assert plan["actions"] == [
        {"type": "custom_node.list", "payload": {"scope": "installed"}}
    ]


def test_rule_planner_plans_installed_custom_nodes_read_from_english_phrase():
    plan = RuleBasedPlanner().plan("show installed custom nodes", context={})

    assert plan["actions"] == [
        {"type": "custom_node.list", "payload": {"scope": "installed"}}
    ]


def test_rule_planner_plans_custom_node_search_read():
    plan = RuleBasedPlanner().plan("搜索 custom node Impact Pack", context={})

    assert plan["actions"] == [
        {"type": "custom_node.search", "payload": {"query": "Impact Pack"}}
    ]


def test_rule_planner_plans_custom_node_disable_then_restart():
    plan = RuleBasedPlanner().plan("禁用 custom node ComfyUI-TestNode 然后重启 ComfyUI", context={})

    assert plan["actions"] == [
        {"type": "custom_node.disable", "payload": {"id": "ComfyUI-TestNode"}},
        {"type": "service.restart_container", "payload": {"container": "comfyui-gb10"}},
    ]


def test_rule_planner_plans_custom_node_install_then_restart():
    plan = RuleBasedPlanner().plan(
        "安装 custom node https://github.com/example/ComfyUI-TestNode.git 并重启服务",
        context={},
    )

    assert plan["actions"] == [
        {
            "type": "custom_node.install",
            "payload": {
                "method": "git_url",
                "url": "https://github.com/example/ComfyUI-TestNode.git",
            },
        },
        {"type": "service.restart_container", "payload": {"container": "comfyui-gb10"}},
    ]


def test_rule_planner_plans_model_install_from_url_with_explicit_target():
    plan = RuleBasedPlanner().plan(
        "安装模型 https://example.com/models/hero.safetensors 到 checkpoints，base SDXL",
        context={},
    )

    assert plan["actions"] == [
        {
            "type": "model.install",
            "payload": {
                "model": {
                    "name": "hero.safetensors",
                    "type": "checkpoints",
                    "base": "SDXL",
                    "save_path": "checkpoints",
                    "url": "https://example.com/models/hero.safetensors",
                    "filename": "hero.safetensors",
                    "ui_id": "hero.safetensors",
                }
            },
        }
    ]


def test_rule_planner_plans_model_install_with_explicit_filename_and_restart():
    plan = RuleBasedPlanner().plan(
        "安装模型 https://example.com/models/download 到 loras，文件名 detail.safetensors，base SDXL 然后重启 ComfyUI",
        context={},
    )

    assert plan["actions"] == [
        {
            "type": "model.install",
            "payload": {
                "model": {
                    "name": "detail.safetensors",
                    "type": "lora",
                    "base": "SDXL",
                    "save_path": "loras",
                    "url": "https://example.com/models/download",
                    "filename": "detail.safetensors",
                    "ui_id": "detail.safetensors",
                }
            },
        },
        {"type": "service.restart_container", "payload": {"container": "comfyui-gb10"}},
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
