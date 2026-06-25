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


def test_rule_planner_plans_custom_node_update_all():
    plan = RuleBasedPlanner().plan("更新全部 custom nodes", context={})

    assert plan["actions"] == [{"type": "custom_node.update_all", "payload": {}}]


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
