from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Callable, Mapping

from .actions import ACTION_REGISTRY, PlanValidationError, dry_run_plan


DEFAULT_OPENAI_BASE_URL = "https://api.openai.com/v1"
DEFAULT_OPENAI_MODEL = "gpt-5.5"
MAX_CONTEXT_CHARS = 8_000_000
MAX_HISTORY_ROWS = 12
MAX_HISTORY_TEXT_CHARS = 1800
MAX_TEXT_ATTACHMENT_CHARS = 12000
MAX_RELEVANT_NODE_TYPES = 80
MAX_UI_ERRORS = 20
GENERIC_NODE_QUERY_TERMS = {
    "image",
    "video",
    "save",
    "load",
    "prompt",
    "text",
    "workflow",
    "node",
}

SYSTEM_INSTRUCTIONS = """You are ComfyUI Agent Workbench, a Codex-like AI assistant embedded inside ComfyUI.
Speak Chinese by default unless the user uses another language.
You are not only a chat box: you can inspect the current ComfyUI graph, explain what you see, and help the user form executable plans for node edits, custom-node manager actions, and GB10 ComfyUI service operations.
Never claim that a ComfyUI change was applied unless the user has clicked the execution control and the backend reports success.
The deterministic planner result is only a proposed dry-run plan. It is not execution.
You are the Agent brain: decide when to propose Workbench actions from the allowed action list. The Workbench will validate those actions and render the allow/execute control.
When you propose non-read actions, tell the user what you are ready to do and that they should use the allow/execute control; do not say it is done.
Image generation should be done by operating ComfyUI workflows through Workbench actions, not by pretending the chat model directly created a file.
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


AGENT_RESPONSE_CONTRACT = {
    "name": "agent_workbench_actions_v1",
    "instructions": (
        "Return only JSON matching this contract. Put the user-facing Chinese reply in "
        "assistant_message. If you want Workbench to operate ComfyUI, put allowed actions "
        "in actions. When called through the Codex bridge schema, encode each action payload "
        "as payload_json, a JSON object string; Workbench will parse it back into payload."
    ),
}

ACTION_PAYLOAD_GUIDANCE = {
    "graph.add_node": {
        "description": "Create a node directly on the current ComfyUI canvas.",
        "payload_example": {
            "node_type": "KSampler",
            "ref": "sampler",
            "pos": [720, 360],
            "title": "Sampler",
            "widgets": {"steps": 20},
        },
    },
    "graph.connect": {
        "description": "Connect two canvas nodes by node ids or refs and slot names or indexes.",
        "payload_example": {
            "origin_node_ref": "source",
            "origin_slot": "IMAGE",
            "target_node_ref": "target",
            "target_slot": "image",
        },
    },
    "graph.set_widget": {
        "description": "Set a widget value on an existing node.",
        "payload_example": {"node_id": 4, "widget": "text", "value": "cinematic prompt"},
    },
    "graph.set_position": {
        "description": "Move a node on the current canvas.",
        "payload_example": {"node_id": 4, "pos": [320, 200]},
    },
    "graph.select_node": {
        "description": "Select and optionally focus a node after creating or editing it.",
        "payload_example": {"node_ref": "sampler", "focus": True},
    },
    "runtime.queue_prompt": {
        "description": "Queue the current browser workflow after canvas edits are applied.",
        "payload_example": {"front": False},
    },
}

AGENT_OPERATING_GUIDANCE = [
    "Prefer graph actions for fast workflow building: graph.add_node, graph.connect, graph.set_widget, then runtime.queue_prompt when the user asks to run.",
    "When current_comfyui_context.ui_errors is present, answer from those observed UI errors first; label any extra diagnosis as inference.",
    "Do not ask for a file-based workflow when registered_node_types_relevant contains the node classes needed for the request.",
    "Use exact input/output/widget names from registered_node_types_relevant; omit uncertain widgets instead of inventing parameters.",
    "Use node refs in graph.add_node payloads so later graph.connect actions can reference newly created nodes in the same plan.",
    "Leave Agnes api_key widgets empty unless the user explicitly asks to change them; Agnes can read its local saved key.",
]


def _available_workbench_actions() -> list[dict]:
    rows = []
    for action_type, (capability, risk) in sorted(ACTION_REGISTRY.items()):
        row = {"type": action_type, "capability": capability, "risk_level": risk}
        guidance = ACTION_PAYLOAD_GUIDANCE.get(action_type)
        if guidance:
            row.update(guidance)
        rows.append(row)
    return rows


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


def _search_text_parts(value: Any, *, depth: int = 0) -> list[str]:
    if depth > 3:
        return []
    if isinstance(value, str):
        return [value.lower()]
    if isinstance(value, (int, float, bool)):
        return [str(value).lower()]
    if isinstance(value, Mapping):
        parts: list[str] = []
        for key, child in value.items():
            if isinstance(key, str):
                parts.append(key.lower())
            parts.extend(_search_text_parts(child, depth=depth + 1))
        return parts
    if isinstance(value, (list, tuple)):
        parts = []
        for child in value[:40]:
            parts.extend(_search_text_parts(child, depth=depth + 1))
        return parts
    return []


def _node_type_text(row: Mapping[str, Any]) -> str:
    values = [
        row.get("type"),
        row.get("title"),
        row.get("category"),
        row.get("inputs"),
        row.get("outputs"),
        row.get("input"),
        row.get("output"),
        row.get("output_name"),
    ]
    return " ".join(
        part for value in values for part in _search_text_parts(value)
    )


def _node_type_query_terms(message: str) -> set[str]:
    lowered = message.lower()
    terms: set[str] = set()
    triggers = {
        "agnes": ["agnes"],
        "ltx": ["ltx"],
        "video": ["video", "视频", "文生视频", "图生视频"],
        "image": ["image", "图片", "图像", "文生图", "图生图"],
        "save": ["save", "保存"],
        "load": ["load", "加载"],
    }
    for canonical, aliases in triggers.items():
        if any(alias in lowered or alias in message for alias in aliases):
            terms.add(canonical)
            terms.update(alias.lower() for alias in aliases if alias.isascii())
    for token in re.findall(r"[A-Za-z][A-Za-z0-9_+-]{2,}", message):
        terms.add(token.lower())
    return terms


def _node_type_match_score(row: Mapping[str, Any], terms: set[str]) -> int:
    haystack = _node_type_text(row)
    node_type = str(row.get("type", "")).lower()
    title = str(row.get("title", "")).lower()
    category = str(row.get("category", "")).lower()
    score = 0
    matched_terms = 0
    for term in terms:
        if not term or term not in haystack:
            continue
        matched_terms += 1
        is_generic = term in GENERIC_NODE_QUERY_TERMS
        term_score = 8 if is_generic else 100
        if term in node_type:
            term_score += 5 if is_generic else 40
        if node_type.startswith(term):
            term_score += 5 if is_generic else 25
        if term in title:
            term_score += 4 if is_generic else 20
        if term in category:
            term_score += 3 if is_generic else 25
        score += term_score
    if matched_terms > 1:
        score += matched_terms * 3
    return score


def _relevant_node_types(node_types: list[Any], message: str) -> list[dict]:
    terms = _node_type_query_terms(message)
    if not terms:
        return []
    candidates: list[tuple[int, int, dict]] = []
    seen: set[str] = set()
    for index, row in enumerate(node_types):
        if not isinstance(row, Mapping):
            continue
        node_type = row.get("type")
        if not isinstance(node_type, str) or not node_type:
            continue
        score = _node_type_match_score(row, terms)
        if score <= 0:
            continue
        if node_type in seen:
            continue
        candidates.append((score, index, dict(row)))
        seen.add(node_type)
    candidates.sort(key=lambda item: (-item[0], item[1]))
    rows = [row for _, _, row in candidates[:MAX_RELEVANT_NODE_TYPES]]
    return rows


def _compact_context(context: Mapping[str, Any] | None, message: str = "") -> dict:
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
        ui_errors = graph_input.get("ui_errors")
        if isinstance(ui_errors, list):
            compact["ui_errors"] = [
                dict(row)
                for row in ui_errors[:MAX_UI_ERRORS]
                if isinstance(row, Mapping)
            ]
        node_types = graph_input.get("node_types")
        if isinstance(node_types, list):
            compact["registered_node_types_sample"] = [
                row for row in node_types[:20] if isinstance(row, Mapping)
            ]
            relevant = _relevant_node_types(node_types, message)
            if relevant:
                compact["registered_node_types_relevant"] = relevant
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
        "current_comfyui_context": _compact_context(context, message),
        "deterministic_planner_result": dry_run or {},
        "available_workbench_actions": _available_workbench_actions(),
        "agent_operating_guidance": AGENT_OPERATING_GUIDANCE,
        "response_contract": AGENT_RESPONSE_CONTRACT,
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


def _json_text_candidate(text: str) -> str:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    return cleaned.strip()


def _parse_agent_response(text: str) -> dict | None:
    try:
        decoded = json.loads(_json_text_candidate(text))
    except json.JSONDecodeError:
        return None
    if not isinstance(decoded, Mapping):
        return None
    assistant_message = decoded.get("assistant_message")
    actions = decoded.get("actions", [])
    if not isinstance(assistant_message, str) or not assistant_message.strip():
        return None
    if actions is None:
        actions = []
    if not isinstance(actions, list):
        return None
    normalized_actions: list[dict] = []
    for action in actions:
        if not isinstance(action, Mapping):
            return None
        normalized = dict(action)
        payload_json = normalized.pop("payload_json", None)
        if "payload" not in normalized and isinstance(payload_json, str):
            try:
                payload = json.loads(payload_json)
            except json.JSONDecodeError:
                return None
            if not isinstance(payload, Mapping):
                return None
            normalized["payload"] = dict(payload)
        normalized_actions.append(normalized)
    summary = decoded.get("summary")
    return {
        "assistant_message": assistant_message.strip(),
        "summary": summary.strip() if isinstance(summary, str) and summary.strip() else "Codex Workbench action plan",
        "actions": normalized_actions,
    }


def _structured_agent_reply(
    *,
    message: str,
    text: str,
    config: LLMConfig,
) -> dict | None:
    parsed = _parse_agent_response(text)
    if parsed is None:
        return None
    planned_dry_run = None
    if parsed["actions"]:
        try:
            planned_dry_run = dry_run_plan(
                {"summary": parsed["summary"], "actions": parsed["actions"]}
            )
        except PlanValidationError as exc:
            raise LLMRequestError(f"Codex returned invalid Workbench actions: {exc}") from exc
    assistant_message = _guard_unapplied_completion_claim(
        message,
        parsed["assistant_message"],
        planned_dry_run,
    )
    reply = {
        "ok": True,
        "status": "assistant_reply",
        "assistant": {
            "title": "ComfyUI Codex Agent",
            "message": assistant_message,
        },
        "provider": config.provider,
        "model": config.model,
        "agent_contract": AGENT_RESPONSE_CONTRACT["name"],
    }
    if planned_dry_run is not None:
        reply["dry_run"] = planned_dry_run
    return reply


IMAGE_GENERATION_TERMS = ("生成", "画", "绘制", "出", "generate", "draw", "create")
IMAGE_OBJECT_TERMS = ("图片", "图像", "照片", "图", "image", "picture", "photo")
UNAPPLIED_COMPLETION_TERMS = (
    "已生成",
    "已经生成",
    "生成了",
    "已完成",
    "已经完成",
    "完成了",
    "已修改",
    "已经修改",
    "修改了",
    "已执行",
    "已经执行",
    "执行了",
    "已应用",
    "已经应用",
    "应用了",
    "generated",
    "completed",
    "done",
    "applied",
    "executed",
)
UNAVAILABLE_EXECUTION_CONTROL_TERMS = (
    "允许执行",
    "允许/执行",
    "执行/允许",
    "执行控制",
    "点击执行",
    "点击 allow",
    "allow/execute",
    "allow",
    "execute",
)


def _is_actionable_dry_run(dry_run: Mapping[str, Any] | None) -> bool:
    if not isinstance(dry_run, Mapping):
        return False
    plan = dry_run.get("plan")
    if not isinstance(plan, Mapping):
        return False
    actions = plan.get("actions")
    if not isinstance(actions, list):
        return False
    return any(
        isinstance(action, Mapping) and action.get("type") != "context.collect"
        for action in actions
    )


def _dry_run_action_types(dry_run: Mapping[str, Any] | None) -> set[str]:
    if not isinstance(dry_run, Mapping):
        return set()
    plan = dry_run.get("plan")
    if not isinstance(plan, Mapping):
        return set()
    actions = plan.get("actions")
    if not isinstance(actions, list):
        return set()
    return {
        action.get("type")
        for action in actions
        if isinstance(action, Mapping) and isinstance(action.get("type"), str)
    }


def _looks_like_image_generation_request(message: str) -> bool:
    lowered = message.lower()
    return (
        any(term in lowered or term in message for term in IMAGE_GENERATION_TERMS)
        and any(term in lowered or term in message for term in IMAGE_OBJECT_TERMS)
    )


def _contains_unapplied_completion_claim(text: str) -> bool:
    lowered = text.lower()
    return any(term in lowered or term in text for term in UNAPPLIED_COMPLETION_TERMS)


def _safe_unapplied_action_message(
    message: str,
    dry_run: Mapping[str, Any] | None,
) -> str:
    plan = dry_run.get("plan") if isinstance(dry_run, Mapping) else None
    summary = plan.get("summary") if isinstance(plan, Mapping) else None
    if not isinstance(summary, str) or not summary.strip():
        summary = "操作当前 ComfyUI 工作流"
    if _is_actionable_dry_run(dry_run):
        if _looks_like_image_generation_request(message):
            if "runtime.queue_prompt" not in _dry_run_action_types(dry_run):
                return (
                    f"我准备好了一个 ComfyUI 画布计划：{summary}。"
                    "点下面的“允许执行”后，我才会创建或修改画布节点；"
                    "现在不会排队运行，也还没有真正生成图片。"
                )
            return (
                f"我准备好了一个 ComfyUI 出图计划：{summary}。"
                "点下面的“允许执行”后，我才会改提示词并运行当前工作流；现在还没有真正生成图片。"
            )
        return (
            f"我准备好了一个可执行计划：{summary}。"
            "点下面的“允许执行”后，我才会真正操作 ComfyUI；现在还没有应用任何改动。"
        )
    if _looks_like_image_generation_request(message):
        return (
            "我现在还没有生成图片，也没有可执行计划，所以侧边栏不会出现执行按钮。"
            "请先加载或创建一个带正向提示词和采样器的 ComfyUI 工作流，"
            "或者明确让我修改某个 prompt 节点后再开始生成。"
        )
    return "我现在还没有执行这个操作；需要先生成可执行计划并等待你允许。"


def _guard_unapplied_completion_claim(
    message: str,
    text: str,
    dry_run: Mapping[str, Any] | None,
) -> str:
    lowered = text.lower()
    mentions_unavailable_control = any(
        term in lowered or term in text for term in UNAVAILABLE_EXECUTION_CONTROL_TERMS
    )
    if (
        _looks_like_image_generation_request(message)
        and not _is_actionable_dry_run(dry_run)
        and mentions_unavailable_control
    ):
        return _safe_unapplied_action_message(message, dry_run)
    if not _contains_unapplied_completion_claim(text):
        return text
    if _is_actionable_dry_run(dry_run) or _looks_like_image_generation_request(message):
        return _safe_unapplied_action_message(message, dry_run)
    return text


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
            "title": "Codex CLI 未连接",
            "message": (
                "现在侧边栏已经是 ComfyUI 内的 Agent 模块，但 ComfyUI 服务还没有连到本机 Codex OAuth bridge。"
                "你要的链路不是图片 API，也不是脚本 planner；请让 AGENT_WORKBENCH_LLM_ENDPOINT "
                "指向宿主机的 Codex bridge（例如 http://172.17.0.1:8797/v1/responses）。"
                "这个 bridge 会调用已登录的 codex exec，再把 Codex 决定的 Workbench 动作交给侧边栏确认执行。"
            ),
        },
        "provider": config.provider,
        "model": config.model,
        "dry_run": dry_run or {},
        "missing": ["AGENT_WORKBENCH_LLM_ENDPOINT"],
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
        structured_reply = _structured_agent_reply(message=message, text=text, config=config)
        if structured_reply is not None:
            return structured_reply
        text = _guard_unapplied_completion_claim(message, text, dry_run)
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
