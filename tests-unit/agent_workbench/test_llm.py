import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
AGENT_ROOT = REPO_ROOT / "custom_nodes" / "ComfyUI-AgentWorkbench"
sys.path.insert(0, str(AGENT_ROOT))

from agent_workbench.llm import (
    LLMConfig,
    build_assistant_reply,
    build_openai_responses_payload,
    extract_response_text,
)


def _context_only_dry_run():
    return {
        "status": "dry_run",
        "plan": {
            "summary": "Inspect context for: 介绍一下你自己",
            "actions": [
                {
                    "type": "context.collect",
                    "payload": {"message": "介绍一下你自己"},
                }
            ],
        },
    }


def _actionable_generation_dry_run():
    return {
        "status": "dry_run",
        "plan": {
            "summary": "Generate image from current ComfyUI workflow",
            "actions": [
                {
                    "type": "graph.set_widget",
                    "payload": {"node_id": 4, "widget": "text", "value": "帅气的哈士奇"},
                },
                {"type": "runtime.queue_prompt", "payload": {"front": False}},
            ],
            "requires_confirmation": True,
        },
    }


def _canvas_only_generation_dry_run():
    return {
        "status": "dry_run",
        "plan": {
            "summary": "Build Agnes image-to-video workflow",
            "actions": [
                {
                    "type": "graph.add_node",
                    "payload": {"node_type": "AgnesTextToImage", "ref": "agnes_t2i"},
                },
                {
                    "type": "graph.add_node",
                    "payload": {"node_type": "AgnesImageToVideo", "ref": "agnes_i2v"},
                },
            ],
            "requires_confirmation": True,
        },
    }


def test_assistant_reply_is_explicit_when_llm_is_not_configured(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("AGENT_WORKBENCH_OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("AGENT_WORKBENCH_LLM_ENDPOINT", raising=False)

    reply = build_assistant_reply(
        "介绍一下你自己",
        context={"graph": {"node_count": 2, "selected_node_ids": [4]}},
        dry_run=_context_only_dry_run(),
    )

    assert reply["ok"] is False
    assert reply["status"] == "ai_unavailable"
    assert "AGENT_WORKBENCH_LLM_ENDPOINT" in reply["assistant"]["message"]
    assert "Codex OAuth bridge" in reply["assistant"]["message"]
    assert "Codex" in reply["assistant"]["message"]
    assert reply["dry_run"]["plan"]["actions"][0]["type"] == "context.collect"


def test_assistant_reply_blocks_unapplied_generation_claims():
    def fake_transport(endpoint, headers, payload, timeout):
        return {"output_text": "已生成，一只雪山夕阳里的帅气哈士奇。"}

    reply = build_assistant_reply(
        "用你自己给我生成一个哈士奇的图片 要求帅",
        context={"graph": {"node_count": 6}},
        dry_run=_actionable_generation_dry_run(),
        config=LLMConfig(
            enabled=True,
            provider="openai",
            api_key="sk-test",
            model="gpt-test",
            endpoint="https://example.test/v1/responses",
            timeout=7,
        ),
        transport=fake_transport,
    )

    assert reply["ok"] is True
    assert reply["status"] == "assistant_reply"
    assert "已生成" not in reply["assistant"]["message"]
    assert "允许执行" in reply["assistant"]["message"]
    assert reply["dry_run"]["plan"]["actions"][1]["type"] == "runtime.queue_prompt"


def test_assistant_reply_does_not_claim_execute_controls_when_generation_has_no_plan():
    def fake_transport(endpoint, headers, payload, timeout):
        return {"output_text": "我已经准备好生成计划；请通过侧边栏的执行/允许控制。"}

    reply = build_assistant_reply(
        "用你自己给我生成一个哈士奇的图片 要求帅",
        context={"graph": {"node_count": 0}},
        dry_run=_context_only_dry_run(),
        config=LLMConfig(
            enabled=True,
            provider="openai",
            api_key="sk-test",
            model="gpt-test",
            endpoint="https://example.test/v1/responses",
            timeout=7,
        ),
        transport=fake_transport,
    )

    assert "执行/允许控制" not in reply["assistant"]["message"]
    assert "执行控制" not in reply["assistant"]["message"]
    assert "没有可执行计划" in reply["assistant"]["message"]


def test_assistant_reply_canvas_only_generation_plan_does_not_claim_queue_run():
    def fake_transport(endpoint, headers, payload, timeout):
        return {"output_text": "已生成一个 Agnes 工作流计划。"}

    reply = build_assistant_reply(
        "用 Agnes 节点生成一个文生图再图生视频工作流",
        context={"graph": {"node_count": 0}},
        dry_run=_canvas_only_generation_dry_run(),
        config=LLMConfig(
            enabled=True,
            provider="openai",
            api_key="sk-test",
            model="gpt-test",
            endpoint="https://example.test/v1/responses",
            timeout=7,
        ),
        transport=fake_transport,
    )

    assert reply["ok"] is True
    assert "运行当前工作流" not in reply["assistant"]["message"]
    assert "创建或修改画布节点" in reply["assistant"]["message"]


def test_openai_payload_includes_user_message_context_and_planner_result():
    payload = build_openai_responses_payload(
        "介绍一下你自己",
        context={
            "graph": {"node_count": 2, "selected_node_ids": [4]},
            "custom_nodes": [{"name": "ComfyUI-Impact-Pack", "state": "enabled"}],
        },
        dry_run=_context_only_dry_run(),
        model="gpt-test",
    )

    assert payload["model"] == "gpt-test"
    assert "ComfyUI Agent Workbench" in payload["instructions"]
    assert "介绍一下你自己" in payload["input"]
    assert "node_count" in payload["input"]
    assert "context.collect" in payload["input"]
    assert "ComfyUI-Impact-Pack" in payload["input"]


def test_openai_payload_requests_codex_agent_action_contract():
    payload = build_openai_responses_payload(
        "把正向提示词改成帅气哈士奇然后生成",
        context={"graph": {"node_count": 2}},
        dry_run=_context_only_dry_run(),
        model="gpt-test",
    )
    decoded = json.loads(payload["input"])

    assert decoded["response_contract"]["name"] == "agent_workbench_actions_v1"
    action_types = {row["type"] for row in decoded["available_workbench_actions"]}
    assert "graph.set_widget" in action_types
    assert "runtime.queue_prompt" in action_types
    assert "custom_node.install" in action_types
    graph_add = next(row for row in decoded["available_workbench_actions"] if row["type"] == "graph.add_node")
    graph_connect = next(row for row in decoded["available_workbench_actions"] if row["type"] == "graph.connect")
    assert graph_add["payload_example"]["node_type"] == "KSampler"
    assert graph_connect["payload_example"]["origin_node_ref"] == "source"
    assert "Prefer graph actions" in decoded["agent_operating_guidance"][0]
    assert any("exact input/output/widget names" in row for row in decoded["agent_operating_guidance"])


def test_openai_payload_includes_relevant_node_types_beyond_first_sample():
    node_types = [
        {"type": f"DummyNode{index}", "title": f"Dummy {index}", "category": "noise"}
        for index in range(30)
    ]
    node_types.extend(
        [
            {
                "type": "AgnesTextToImage",
                "title": "Agnes Text-to-Image",
                "category": "Agnes AI",
                "inputs": [
                    {"name": "api_key", "type": "STRING"},
                    {"name": "prompt", "type": "STRING"},
                ],
                "outputs": [{"name": "IMAGE", "type": "IMAGE"}],
            },
            {
                "type": "AgnesTextToVideo",
                "title": "Agnes Text-to-Video",
                "category": "Agnes AI",
                "inputs": [{"name": "prompt", "type": "STRING"}],
                "outputs": [{"name": "VIDEO", "type": "VIDEO"}],
            },
        ]
    )

    payload = build_openai_responses_payload(
        "用 Agnes 节点给我建一个文生视频快速工作流",
        context={"graph_input": {"nodes": [], "links": [], "node_types": node_types}},
        dry_run=_context_only_dry_run(),
        model="gpt-test",
    )
    decoded = json.loads(payload["input"])

    relevant_types = {
        row["type"]
        for row in decoded["current_comfyui_context"]["registered_node_types_relevant"]
    }
    sample_types = {
        row["type"]
        for row in decoded["current_comfyui_context"]["registered_node_types_sample"]
    }
    assert "AgnesTextToImage" in relevant_types
    assert "AgnesTextToVideo" in relevant_types
    assert "AgnesTextToImage" not in sample_types


def test_openai_payload_prioritizes_explicit_plugin_node_types_over_generic_matches():
    node_types = [
        {"type": f"GenericImageVideoNode{index}", "title": f"Generic Image Video {index}", "category": "image/video"}
        for index in range(120)
    ]
    node_types.append(
        {
            "type": "AgnesTextToVideo",
            "title": "Agnes Text-to-Video",
            "category": "Agnes AI",
            "inputs": [{"name": "prompt", "type": "STRING"}],
            "outputs": [{"name": "VIDEO", "type": "VIDEO"}],
        }
    )

    payload = build_openai_responses_payload(
        "用 Agnes 节点给我建一个文生视频快速工作流",
        context={"graph_input": {"nodes": [], "links": [], "node_types": node_types}},
        dry_run=_context_only_dry_run(),
        model="gpt-test",
    )
    decoded = json.loads(payload["input"])

    relevant_types = [
        row["type"]
        for row in decoded["current_comfyui_context"]["registered_node_types_relevant"]
    ]
    assert "AgnesTextToVideo" in relevant_types
    assert relevant_types.index("AgnesTextToVideo") < 10


def test_assistant_reply_parses_codex_json_actions_into_dry_run():
    def fake_transport(endpoint, headers, payload, timeout):
        return {
            "output_text": json.dumps(
                {
                    "assistant_message": "我会把正向提示词改成帅气哈士奇，然后运行当前工作流。",
                    "summary": "Set positive prompt then queue workflow",
                    "actions": [
                        {
                            "type": "graph.set_widget",
                            "payload": {"node_id": 4, "widget": "text", "value": "帅气的哈士奇"},
                        },
                        {"type": "runtime.queue_prompt", "payload": {"front": False}},
                    ],
                },
                ensure_ascii=False,
            )
        }

    reply = build_assistant_reply(
        "用你自己给我生成一个哈士奇的图片 要求帅",
        context={"graph": {"node_count": 6}},
        dry_run=_context_only_dry_run(),
        config=LLMConfig(
            enabled=True,
            provider="openai",
            api_key=None,
            model="gpt-test",
            endpoint="http://127.0.0.1:8797/v1/responses",
            timeout=7,
        ),
        transport=fake_transport,
    )

    assert reply["ok"] is True
    assert reply["assistant"]["message"] == "我会把正向提示词改成帅气哈士奇，然后运行当前工作流。"
    assert reply["dry_run"]["plan"]["summary"] == "Set positive prompt then queue workflow"
    assert reply["dry_run"]["plan"]["actions"][0]["type"] == "graph.set_widget"
    assert reply["dry_run"]["plan"]["actions"][1]["type"] == "runtime.queue_prompt"


def test_assistant_reply_parses_codex_schema_payload_json_actions():
    def fake_transport(endpoint, headers, payload, timeout):
        return {
            "output_text": json.dumps(
                {
                    "assistant_message": "我会改提示词，然后等你允许执行。",
                    "summary": "Set positive prompt then queue workflow",
                    "actions": [
                        {
                            "type": "graph.set_widget",
                            "payload_json": json.dumps(
                                {"node_id": 4, "widget_name": "text", "value": "帅气的哈士奇"},
                                ensure_ascii=False,
                            ),
                        }
                    ],
                },
                ensure_ascii=False,
            )
        }

    reply = build_assistant_reply(
        "用你自己给我生成一个哈士奇的图片 要求帅",
        context={"graph": {"node_count": 6}},
        dry_run=_context_only_dry_run(),
        config=LLMConfig(
            enabled=True,
            provider="openai",
            api_key=None,
            model="gpt-test",
            endpoint="http://127.0.0.1:8797/v1/responses",
            timeout=7,
        ),
        transport=fake_transport,
    )

    assert reply["ok"] is True
    assert reply["dry_run"]["plan"]["actions"][0]["payload"] == {
        "node_id": 4,
        "widget": "text",
        "value": "帅气的哈士奇",
    }


def test_openai_payload_includes_chat_history_and_current_attachments():
    payload = build_openai_responses_payload(
        "描述这张图",
        context={"graph": {"node_count": 1}},
        dry_run=_context_only_dry_run(),
        model="gpt-test",
        history=[
            {"role": "user", "text": "记住蓝色玻璃瓶"},
            {"role": "assistant", "text": "我记住了。"},
        ],
        attachments=[
            {
                "kind": "image",
                "name": "workflow.png",
                "mime": "image/png",
                "size": 3,
                "data_url": "data:image/png;base64,aW1n",
            },
            {
                "kind": "text",
                "name": "notes.txt",
                "mime": "text/plain",
                "size": 5,
                "text": "hello",
            },
        ],
    )

    decoded = json.loads(payload["input"])
    assert decoded["chat_history"][0]["text"] == "记住蓝色玻璃瓶"
    assert decoded["attachments"][0]["data_url"] == "data:image/png;base64,aW1n"
    assert decoded["attachments"][1]["text"] == "hello"


def test_extract_response_text_supports_openai_responses_shapes():
    assert extract_response_text({"output_text": "我是你的 ComfyUI Codex Agent。"}) == "我是你的 ComfyUI Codex Agent。"
    assert extract_response_text(
        {
            "output": [
                {
                    "content": [
                        {"type": "output_text", "text": "第一段"},
                        {"type": "output_text", "text": "第二段"},
                    ]
                }
            ]
        }
    ) == "第一段\n第二段"


def test_assistant_reply_uses_configured_openai_transport():
    calls = []

    def fake_transport(endpoint, headers, payload, timeout):
        calls.append(
            {
                "endpoint": endpoint,
                "headers": headers,
                "payload": payload,
                "timeout": timeout,
            }
        )
        return {"output_text": "我是你的 ComfyUI Codex Agent，可以读图、改节点、生成计划，再等你确认执行。"}

    reply = build_assistant_reply(
        "介绍一下你自己",
        context={"graph": {"node_count": 1}},
        dry_run=_context_only_dry_run(),
        history=[{"role": "user", "text": "上一轮"}],
        attachments=[{"kind": "text", "name": "a.txt", "text": "now"}],
        config=LLMConfig(
            enabled=True,
            provider="openai",
            api_key="sk-test",
            model="gpt-test",
            endpoint="https://example.test/v1/responses",
            timeout=7,
        ),
        transport=fake_transport,
    )

    assert reply["ok"] is True
    assert reply["status"] == "assistant_reply"
    assert "ComfyUI Codex Agent" in reply["assistant"]["message"]
    assert reply["provider"] == "openai"
    assert reply["model"] == "gpt-test"
    assert calls == [
        {
            "endpoint": "https://example.test/v1/responses",
            "headers": {
                "Authorization": "Bearer sk-test",
                "Content-Type": "application/json",
            },
            "payload": build_openai_responses_payload(
                "介绍一下你自己",
                context={"graph": {"node_count": 1}},
                dry_run=_context_only_dry_run(),
                model="gpt-test",
                history=[{"role": "user", "text": "上一轮"}],
                attachments=[{"kind": "text", "name": "a.txt", "text": "now"}],
            ),
            "timeout": 7,
        }
    ]
