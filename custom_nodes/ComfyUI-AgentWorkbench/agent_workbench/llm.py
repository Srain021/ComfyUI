from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Callable, Mapping


DEFAULT_OPENAI_BASE_URL = "https://api.openai.com/v1"
DEFAULT_OPENAI_MODEL = "gpt-5.5"
MAX_CONTEXT_CHARS = 8_000_000
MAX_HISTORY_ROWS = 12
MAX_HISTORY_TEXT_CHARS = 1800
MAX_TEXT_ATTACHMENT_CHARS = 12000

SYSTEM_INSTRUCTIONS = """You are ComfyUI Agent Workbench, a Codex-like AI assistant embedded inside ComfyUI.
Speak Chinese by default unless the user uses another language.
You are not only a chat box: you can inspect the current ComfyUI graph, explain what you see, and help the user form executable plans for node edits, custom-node manager actions, and GB10 ComfyUI service operations.
Never claim that a ComfyUI change was applied unless the user has clicked the execution control and the backend reports success.
For high-risk service, package, model, compose, or sudo-adjacent work, explain the risk and keep confirmation in the plan-and-apply flow.
Be concise, direct, and useful inside a narrow sidebar."""

Transport = Callable[[str, Mapping[str, str], Mapping[str, Any], float], Mapping[str, Any]]


@dataclass(frozen=True)
class LLMConfig:
    enabled: bool
    provider: str
    api_key: str | None
    model: str
    endpoint: str
    timeout: float


class LLMRequestError(RuntimeError):
    pass


def _responses_endpoint(base_url: str) -> str:
    return f"{base_url.rstrip('/')}/responses"


def config_from_env(env: Mapping[str, str] | None = None) -> LLMConfig:
    env = os.environ if env is None else env
    provider = env.get("AGENT_WORKBENCH_LLM_PROVIDER", "openai").strip().lower() or "openai"
    model = env.get("AGENT_WORKBENCH_LLM_MODEL") or env.get("OPENAI_MODEL") or DEFAULT_OPENAI_MODEL
    api_key = env.get("AGENT_WORKBENCH_OPENAI_API_KEY") or env.get("OPENAI_API_KEY")
    custom_endpoint = env.get("AGENT_WORKBENCH_LLM_ENDPOINT")
    base_url = env.get("AGENT_WORKBENCH_LLM_BASE_URL") or DEFAULT_OPENAI_BASE_URL
    endpoint = custom_endpoint or _responses_endpoint(base_url)
    try:
        timeout = float(env.get("AGENT_WORKBENCH_LLM_TIMEOUT", "30"))
    except (TypeError, ValueError):
        timeout = 30.0

    if provider in {"off", "none", "disabled", "rules"}:
        return LLMConfig(False, provider, api_key, model, endpoint, timeout)

    enabled = provider in {"openai", "responses"} and bool(api_key or custom_endpoint)
    return LLMConfig(enabled, provider, api_key, model, endpoint, timeout)


def llm_status(env: Mapping[str, str] | None = None) -> dict:
    source = os.environ if env is None else env
    config = config_from_env(env)
    return {
        "configured": config.enabled,
        "provider": config.provider,
        "model": config.model,
        "endpoint_configured": bool(source.get("AGENT_WORKBENCH_LLM_ENDPOINT")),
    }


def _bounded_json(value: Any) -> str:
    text = json.dumps(value, ensure_ascii=False, indent=2)
    if len(text) > MAX_CONTEXT_CHARS:
        return f"{text[:MAX_CONTEXT_CHARS]}\n...<truncated>"
    return text


def _bounded_text(value: Any, limit: int) -> str:
    text = value if isinstance(value, str) else ""
    if len(text) <= limit:
        return text
    return f"{text[:limit]}...<truncated>"


def _compact_context(context: Mapping[str, Any] | None) -> dict:
    if not isinstance(context, Mapping):
        return {}
    compact: dict[str, Any] = {}
    graph = context.get("graph")
    if isinstance(graph, Mapping):
        compact["graph"] = {
            "node_count": graph.get("node_count"),
            "link_count": graph.get("link_count"),
            "selected_node_ids": graph.get("selected_node_ids", []),
        }
    graph_input = context.get("graph_input")
    if isinstance(graph_input, Mapping):
        nodes = graph_input.get("nodes")
        if isinstance(nodes, list):
            selected = [node for node in nodes if isinstance(node, Mapping) and node.get("selected")][:8]
            compact["selected_nodes"] = selected
            if not selected:
                compact["sample_nodes"] = [node for node in nodes[:8] if isinstance(node, Mapping)]
        node_types = graph_input.get("node_types")
        if isinstance(node_types, list):
            compact["registered_node_types_sample"] = [
                row for row in node_types[:20] if isinstance(row, Mapping)
            ]
    custom_nodes = context.get("custom_nodes")
    if isinstance(custom_nodes, list):
        compact["custom_nodes_sample"] = [
            row for row in custom_nodes[:20] if isinstance(row, Mapping)
        ]
    workflows = context.get("workflows")
    if isinstance(workflows, list):
        compact["workflows_sample"] = [
            row for row in workflows[:10] if isinstance(row, Mapping)
        ]
    return compact


def _compact_history(history: list[Any] | None) -> list[dict]:
    if not isinstance(history, list):
        return []
    rows: list[dict] = []
    for item in history[-MAX_HISTORY_ROWS:]:
        if not isinstance(item, Mapping):
            continue
        role = item.get("role")
        if role not in {"user", "assistant", "tool"}:
            continue
        row = {
            "role": role,
            "text": _bounded_text(item.get("text"), MAX_HISTORY_TEXT_CHARS),
        }
        attachments = item.get("attachments")
        if isinstance(attachments, list):
            compact_attachments = []
            for attachment in attachments[:6]:
                if not isinstance(attachment, Mapping):
                    continue
                compact_attachments.append(
                    {
                        key: attachment.get(key)
                        for key in ("kind", "name", "mime", "size", "text", "truncated")
                        if attachment.get(key) is not None
                    }
                )
            if compact_attachments:
                row["attachments"] = compact_attachments
        rows.append(row)
    return rows


def _compact_attachments(attachments: list[Any] | None) -> list[dict]:
    if not isinstance(attachments, list):
        return []
    rows: list[dict] = []
    for item in attachments[:8]:
        if not isinstance(item, Mapping):
            continue
        row = {
            key: item.get(key)
            for key in ("kind", "name", "mime", "size", "error")
            if item.get(key) is not None
        }
        if item.get("kind") == "image" and isinstance(item.get("data_url"), str):
            row["data_url"] = item["data_url"]
        if item.get("kind") == "text" and isinstance(item.get("text"), str):
            row["text"] = _bounded_text(item.get("text"), MAX_TEXT_ATTACHMENT_CHARS)
            row["truncated"] = bool(item.get("truncated"))
        rows.append(row)
    return rows


def build_openai_responses_payload(
    message: str,
    *,
    context: Mapping[str, Any] | None,
    dry_run: Mapping[str, Any] | None,
    model: str,
    history: list[Any] | None = None,
    attachments: list[Any] | None = None,
) -> dict:
    input_payload = {
        "user_message": message,
        "chat_history": _compact_history(history),
        "attachments": _compact_attachments(attachments),
        "current_comfyui_context": _compact_context(context),
        "deterministic_planner_result": dry_run or {},
    }
    return {
        "model": model,
        "instructions": SYSTEM_INSTRUCTIONS,
        "input": _bounded_json(input_payload),
    }


def extract_response_text(payload: Mapping[str, Any]) -> str:
    output_text = payload.get("output_text")
    if isinstance(output_text, str) and output_text.strip():
        return output_text.strip()

    chunks: list[str] = []
    output = payload.get("output")
    if isinstance(output, list):
        for item in output:
            if not isinstance(item, Mapping):
                continue
            content = item.get("content")
            if not isinstance(content, list):
                continue
            for block in content:
                if not isinstance(block, Mapping):
                    continue
                text = block.get("text")
                if isinstance(text, str) and text.strip():
                    chunks.append(text.strip())
    return "\n".join(chunks)


def openai_responses_transport(
    endpoint: str,
    headers: Mapping[str, str],
    payload: Mapping[str, Any],
    timeout: float,
) -> Mapping[str, Any]:
    request = urllib.request.Request(
        endpoint,
        data=json.dumps(payload).encode("utf-8"),
        headers=dict(headers),
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise LLMRequestError(f"LLM request failed with HTTP {exc.code}: {body}") from exc
    except urllib.error.URLError as exc:
        raise LLMRequestError(f"LLM request failed: {exc.reason}") from exc

    try:
        decoded = json.loads(body)
    except json.JSONDecodeError as exc:
        raise LLMRequestError("LLM returned invalid JSON") from exc
    if not isinstance(decoded, Mapping):
        raise LLMRequestError("LLM returned a non-object JSON payload")
    return decoded


def _auth_headers(config: LLMConfig) -> dict[str, str]:
    headers = {"Content-Type": "application/json"}
    if config.api_key:
        headers["Authorization"] = f"Bearer {config.api_key}"
    return headers


def _ai_unavailable_response(dry_run: Mapping[str, Any] | None, config: LLMConfig) -> dict:
    return {
        "ok": False,
        "status": "ai_unavailable",
        "assistant": {
            "title": "AI 未连接",
            "message": (
                "现在侧边栏已经是 ComfyUI 内的 Agent 模块，但还没有接上真实 LLM。"
                "它不能直接复用你当前这个 Codex 桌面聊天线程；要像 Codex 一样自由回复，"
                "需要在 ComfyUI 服务里配置 OPENAI_API_KEY（或 AGENT_WORKBENCH_OPENAI_API_KEY），"
                "也可以配置 AGENT_WORKBENCH_LLM_ENDPOINT 指向一个 OpenAI Responses 兼容的本地/Codex bridge。"
            ),
        },
        "provider": config.provider,
        "model": config.model,
        "dry_run": dry_run or {},
        "missing": ["OPENAI_API_KEY or AGENT_WORKBENCH_LLM_ENDPOINT"],
    }


def build_assistant_reply(
    message: str,
    *,
    context: Mapping[str, Any] | None,
    dry_run: Mapping[str, Any] | None,
    history: list[Any] | None = None,
    attachments: list[Any] | None = None,
    config: LLMConfig | None = None,
    transport: Transport = openai_responses_transport,
) -> dict:
    config = config or config_from_env()
    if not config.enabled:
        return _ai_unavailable_response(dry_run, config)

    payload = build_openai_responses_payload(
        message,
        context=context,
        dry_run=dry_run,
        model=config.model,
        history=history,
        attachments=attachments,
    )
    try:
        raw = transport(config.endpoint, _auth_headers(config), payload, config.timeout)
        text = extract_response_text(raw)
        if not text:
            raise LLMRequestError("LLM returned an empty text response")
    except Exception as exc:
        return {
            "ok": False,
            "status": "ai_error",
            "assistant": {
                "title": "AI 调用失败",
                "message": str(exc),
            },
            "provider": config.provider,
            "model": config.model,
            "dry_run": dry_run or {},
        }

    return {
        "ok": True,
        "status": "assistant_reply",
        "assistant": {
            "title": "ComfyUI Codex Agent",
            "message": text,
        },
        "provider": config.provider,
        "model": config.model,
        "dry_run": dry_run or {},
    }
