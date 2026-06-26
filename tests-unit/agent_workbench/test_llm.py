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
    assert "OPENAI_API_KEY" in reply["assistant"]["message"]
    assert "Codex" in reply["assistant"]["message"]
    assert reply["dry_run"]["plan"]["actions"][0]["type"] == "context.collect"


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
