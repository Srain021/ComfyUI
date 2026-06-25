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


def test_rule_planner_plans_service_healthcheck():
    plan = RuleBasedPlanner().plan("检查 ComfyUI 容器健康和内存", context={})

    assert plan["actions"] == [{"type": "service.healthcheck", "payload": {}}]
    assert plan["summary"] == "Check ComfyUI container health"


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


def test_rule_planner_plans_restart_container():
    plan = RuleBasedPlanner().plan("重启 ComfyUI 容器", context={})

    assert plan["actions"] == [
        {"type": "service.restart_container", "payload": {"container": "comfyui-gb10"}}
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
