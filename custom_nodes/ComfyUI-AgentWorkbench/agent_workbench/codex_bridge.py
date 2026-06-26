from __future__ import annotations

import argparse
import base64
import json
import os
import subprocess
import tempfile
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Mapping


DEFAULT_HOST = "172.17.0.1"
DEFAULT_PORT = 8797
DEFAULT_TIMEOUT = 180
MAX_BODY_BYTES = 12_000_000
MAX_IMAGE_ATTACHMENTS = 4
AGENT_ACTION_CONTRACT_NAME = "agent_workbench_actions_v1"


AGENT_ACTION_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "assistant_message": {
            "type": "string",
            "description": "Chinese user-facing reply for the ComfyUI sidebar.",
        },
        "summary": {
            "type": "string",
            "description": "Short English or Chinese action summary for Workbench dry-run cards.",
        },
        "actions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "type": {"type": "string"},
                    "payload_json": {
                        "type": "string",
                        "description": "A JSON object string for the Workbench action payload. Use {} when empty.",
                    },
                },
                "required": ["type", "payload_json"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["assistant_message", "summary", "actions"],
    "additionalProperties": False,
}


def responses_payload(text: str, *, model: str | None = None) -> dict:
    payload = {
        "output_text": text,
        "output": [
            {
                "content": [
                    {
                        "type": "output_text",
                        "text": text,
                    }
                ]
            }
        ],
    }
    if model:
        payload["model"] = model
    return payload


def build_codex_prompt(request_payload: Mapping[str, Any]) -> str:
    instructions = request_payload.get("instructions")
    input_payload = request_payload.get("input")
    if not isinstance(instructions, str):
        instructions = ""
    if not isinstance(input_payload, str):
        input_payload = json.dumps(input_payload, ensure_ascii=False)
    output_instruction = "只输出给用户看的最终回答。不要输出 JSON、Markdown 代码块或内部调试信息。"
    if _uses_agent_action_contract(request_payload):
        output_instruction = "只输出符合 JSON schema 的对象，不要输出 Markdown 代码块或额外文本。"
    return "\n\n".join(
        [
            "你是运行在 ComfyUI 侧边栏里的 Codex OAuth Agent bridge。",
            instructions.strip(),
            "下面是 Workbench 传来的上下文 JSON。请结合它回答用户。",
            input_payload.strip(),
            output_instruction,
        ]
    )


def codex_exec_command(
    model: str,
    output_file: Path,
    *,
    image_paths: list[Path] | None = None,
    output_schema: Path | None = None,
) -> list[str]:
    command = [
        "codex",
        "exec",
        "--ignore-user-config",
        "--ignore-rules",
        "-C",
        "/tmp",
        "--skip-git-repo-check",
        "--sandbox",
        "read-only",
        "--model",
        model,
        "--output-last-message",
        str(output_file),
    ]
    for image_path in image_paths or []:
        command.extend(["--image", str(image_path)])
    if output_schema is not None:
        command.extend(["--output-schema", str(output_schema)])
    command.append("-")
    return command


def _uses_agent_action_contract(request_payload: Mapping[str, Any]) -> bool:
    input_payload = _input_json(request_payload)
    contract = input_payload.get("response_contract")
    return isinstance(contract, Mapping) and contract.get("name") == AGENT_ACTION_CONTRACT_NAME


def _input_json(request_payload: Mapping[str, Any]) -> Mapping[str, Any]:
    input_payload = request_payload.get("input")
    if isinstance(input_payload, str):
        try:
            decoded = json.loads(input_payload)
        except json.JSONDecodeError:
            return {}
        return decoded if isinstance(decoded, Mapping) else {}
    return input_payload if isinstance(input_payload, Mapping) else {}


def _extension_for_mime(mime: str) -> str:
    return {
        "image/jpeg": ".jpg",
        "image/jpg": ".jpg",
        "image/png": ".png",
        "image/webp": ".webp",
        "image/gif": ".gif",
    }.get(mime.lower(), ".img")


def extract_image_attachments(
    request_payload: Mapping[str, Any],
    tmpdir: str | Path,
) -> list[Path]:
    input_payload = _input_json(request_payload)
    attachments = input_payload.get("attachments")
    if not isinstance(attachments, list):
        return []
    output_dir = Path(tmpdir)
    paths: list[Path] = []
    for attachment in attachments:
        if len(paths) >= MAX_IMAGE_ATTACHMENTS:
            break
        if not isinstance(attachment, Mapping) or attachment.get("kind") != "image":
            continue
        data_url = attachment.get("data_url")
        mime = str(attachment.get("mime") or "image/png")
        if not isinstance(data_url, str) or "," not in data_url:
            continue
        prefix, encoded = data_url.split(",", 1)
        if ";base64" not in prefix:
            continue
        try:
            image_bytes = base64.b64decode(encoded, validate=True)
        except ValueError:
            continue
        path = output_dir / f"attachment-{len(paths)}{_extension_for_mime(mime)}"
        path.write_bytes(image_bytes)
        paths.append(path)
    return paths


def run_codex_bridge_request(
    request_payload: Mapping[str, Any],
    *,
    timeout: int = DEFAULT_TIMEOUT,
) -> dict:
    model = str(
        request_payload.get("model")
        or os.environ.get("CODEX_BRIDGE_MODEL")
        or "gpt-5.5"
    )
    prompt = build_codex_prompt(request_payload)
    with tempfile.TemporaryDirectory(prefix="comfyui-codex-bridge-") as tmpdir:
        output_file = Path(tmpdir) / "last-message.txt"
        schema_file = None
        if _uses_agent_action_contract(request_payload):
            schema_file = Path(tmpdir) / "agent-action-schema.json"
            schema_file.write_text(
                json.dumps(AGENT_ACTION_OUTPUT_SCHEMA, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        image_paths = extract_image_attachments(request_payload, tmpdir)
        completed = subprocess.run(
            codex_exec_command(
                model,
                output_file,
                image_paths=image_paths,
                output_schema=schema_file,
            ),
            input=prompt,
            text=True,
            capture_output=True,
            timeout=timeout,
            check=False,
        )
        if completed.returncode != 0:
            stderr_tail = completed.stderr[-4000:]
            raise RuntimeError(f"codex exec failed with exit {completed.returncode}: {stderr_tail}")
        text = output_file.read_text(encoding="utf-8").strip()
    return responses_payload(text, model=model)


class CodexBridgeHandler(BaseHTTPRequestHandler):
    server_version = "ComfyUICodexBridge/0.1"

    def log_message(self, format: str, *args: object) -> None:
        timestamp = time.strftime("%Y-%m-%dT%H:%M:%S")
        print(f"{timestamp} {self.address_string()} {format % args}", flush=True)

    def _send_json(self, status: int, payload: Mapping[str, Any]) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        if self.path == "/health":
            self._send_json(200, {"ok": True, "service": "comfyui-codex-bridge"})
            return
        self._send_json(404, {"ok": False, "error": "not_found"})

    def do_POST(self) -> None:
        if self.path != "/v1/responses":
            self._send_json(404, {"ok": False, "error": "not_found"})
            return
        try:
            content_length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            self._send_json(400, {"ok": False, "error": "invalid_content_length"})
            return
        if content_length <= 0 or content_length > MAX_BODY_BYTES:
            self._send_json(413, {"ok": False, "error": "invalid_body_size"})
            return
        try:
            decoded = json.loads(self.rfile.read(content_length).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            self._send_json(400, {"ok": False, "error": "invalid_json"})
            return
        if not isinstance(decoded, dict):
            self._send_json(400, {"ok": False, "error": "json_body_must_be_object"})
            return
        try:
            self._send_json(200, run_codex_bridge_request(decoded))
        except subprocess.TimeoutExpired:
            self._send_json(504, {"ok": False, "error": "codex_exec_timeout"})
        except Exception as exc:
            self._send_json(502, {"ok": False, "error": str(exc)})


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="OpenAI Responses-compatible bridge to Codex OAuth")
    parser.add_argument("--host", default=os.environ.get("CODEX_BRIDGE_HOST", DEFAULT_HOST))
    parser.add_argument("--port", type=int, default=int(os.environ.get("CODEX_BRIDGE_PORT", DEFAULT_PORT)))
    args = parser.parse_args(argv)

    server = ThreadingHTTPServer((args.host, args.port), CodexBridgeHandler)
    print(f"comfyui-codex-bridge listening on http://{args.host}:{args.port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        return 130
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
