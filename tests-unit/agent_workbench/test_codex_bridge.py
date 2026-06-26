import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
AGENT_ROOT = REPO_ROOT / "custom_nodes" / "ComfyUI-AgentWorkbench"
sys.path.insert(0, str(AGENT_ROOT))

from agent_workbench.codex_bridge import (
    AGENT_ACTION_OUTPUT_SCHEMA,
    build_codex_prompt,
    codex_exec_command,
    extract_image_attachments,
    responses_payload,
)


def test_codex_bridge_builds_openai_compatible_response():
    payload = responses_payload("你好，我是 Codex OAuth bridge。")

    assert payload["output_text"] == "你好，我是 Codex OAuth bridge。"
    assert payload["output"][0]["content"][0] == {
        "type": "output_text",
        "text": "你好，我是 Codex OAuth bridge。",
    }


def test_codex_bridge_prompt_preserves_instructions_and_input():
    prompt = build_codex_prompt(
        {
            "instructions": "You are ComfyUI Agent Workbench.",
            "input": json.dumps({"user_message": "介绍一下你自己"}, ensure_ascii=False),
        }
    )

    assert "You are ComfyUI Agent Workbench." in prompt
    assert "介绍一下你自己" in prompt
    assert "只输出给用户看的最终回答" in prompt


def test_codex_exec_command_uses_oauth_safe_noninteractive_mode(tmp_path):
    output_file = tmp_path / "last.txt"
    command = codex_exec_command("gpt-5.5", output_file)

    assert command[:2] == ["codex", "exec"]
    assert "--ignore-user-config" in command
    assert "--ignore-rules" in command
    assert "--skip-git-repo-check" in command
    assert "--sandbox" in command
    assert "read-only" in command
    assert "--output-last-message" in command
    assert str(output_file) in command


def test_codex_exec_command_adds_image_arguments(tmp_path):
    output_file = tmp_path / "last.txt"
    image_file = tmp_path / "workflow.png"
    image_file.write_bytes(b"img")

    command = codex_exec_command("gpt-5.5", output_file, image_paths=[image_file])

    image_index = command.index("--image")
    assert command[image_index + 1] == str(image_file)


def test_codex_exec_command_adds_output_schema(tmp_path):
    output_file = tmp_path / "last.txt"
    schema_file = tmp_path / "schema.json"

    command = codex_exec_command("gpt-5.5", output_file, output_schema=schema_file)

    schema_index = command.index("--output-schema")
    assert command[schema_index + 1] == str(schema_file)


def test_codex_bridge_prompt_switches_to_json_contract_for_agent_mode():
    prompt = build_codex_prompt(
        {
            "instructions": "You are ComfyUI Agent Workbench.",
            "input": json.dumps(
                {
                    "user_message": "用你自己生成一张哈士奇图",
                    "response_contract": {"name": "agent_workbench_actions_v1"},
                },
                ensure_ascii=False,
            ),
        }
    )

    assert "只输出符合 JSON schema 的对象" in prompt
    assert "不要输出 JSON" not in prompt


def test_agent_action_output_schema_uses_string_payload_for_strict_codex_schema():
    action_schema = AGENT_ACTION_OUTPUT_SCHEMA["properties"]["actions"]["items"]

    assert action_schema["additionalProperties"] is False
    assert action_schema["properties"]["payload_json"]["type"] == "string"
    assert "payload" not in action_schema["properties"]


def test_extract_image_attachments_decodes_data_urls(tmp_path):
    paths = extract_image_attachments(
        {
            "input": json.dumps(
                {
                    "attachments": [
                        {
                            "kind": "image",
                            "name": "workflow.png",
                            "mime": "image/png",
                            "data_url": "data:image/png;base64,aW1n",
                        }
                    ]
                }
            )
        },
        tmp_path,
    )

    assert len(paths) == 1
    assert paths[0].name == "attachment-0.png"
    assert paths[0].read_bytes() == b"img"
