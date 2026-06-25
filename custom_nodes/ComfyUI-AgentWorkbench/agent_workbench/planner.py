import os
import re


MAX_PLANNER_GRAPH_NODES = 500
MAX_PLANNER_WIDGETS_PER_NODE = 64
MAX_PLANNER_SLOTS_PER_NODE = 64


def _context_plan(message: str) -> dict:
    return {
        "summary": f"Inspect context for: {message}",
        "actions": [{"type": "context.collect", "payload": {"message": message}}],
    }


def _strip_value(value: str) -> str:
    cleaned = value.strip()
    cleaned = cleaned.strip(" \t\r\n'\"`.,，。:：")
    cleaned = cleaned.strip("“”‘’")
    return cleaned


def _extract_value_after_set(text: str) -> str | None:
    for delimiter in ("改成", "改为", "设置为", "设为", "变成"):
        if delimiter in text:
            return _strip_value(text.rsplit(delimiter, 1)[1])
    match = re.search(r"\b(?:set|change|update)\b.+?\b(?:to|as)\b\s*(.+)$", text, re.IGNORECASE)
    if match:
        return _strip_value(match.group(1))
    return None


def _coerce_widget_value(value: str, widget: dict) -> object:
    current = widget.get("value")
    lowered = value.lower()
    if isinstance(current, bool):
        if lowered in {"true", "yes", "on", "1"} or value in {"开", "开启", "是"}:
            return True
        if lowered in {"false", "no", "off", "0"} or value in {"关", "关闭", "否"}:
            return False
        return value
    if isinstance(current, int) and not isinstance(current, bool):
        try:
            return int(value)
        except ValueError:
            return value
    if isinstance(current, float):
        try:
            return float(value)
        except ValueError:
            return value
    return value


def _graph_nodes(context: dict) -> list[dict]:
    graph = context.get("graph_input") if isinstance(context, dict) else None
    if not isinstance(graph, dict):
        return []
    nodes = graph.get("nodes")
    if not isinstance(nodes, list):
        return []
    return [node for node in nodes[:MAX_PLANNER_GRAPH_NODES] if isinstance(node, dict)]


def _node_widgets(node: dict) -> list[dict]:
    widgets = node.get("widgets")
    if not isinstance(widgets, list):
        return []
    return [
        widget
        for widget in widgets[:MAX_PLANNER_WIDGETS_PER_NODE]
        if isinstance(widget, dict) and isinstance(widget.get("name"), str)
    ]


def _extract_node_id(text: str) -> str | None:
    patterns = (
        r"(\d+)\s*号?\s*节点",
        r"节点\s*#?\s*(\d+)",
        r"\bnode\s*#?\s*(\d+)\b",
        r"#(\d+)\b",
    )
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(1)
    return None


def _find_node_by_id(nodes: list[dict], node_id: str | None) -> dict | None:
    if node_id is None:
        return None
    for node in nodes:
        if str(node.get("id")) == node_id:
            return node
    return None


def _selected_nodes(nodes: list[dict]) -> list[dict]:
    return [node for node in nodes if node.get("selected") is True]


def _message_mentions_current_node(text: str) -> bool:
    lowered = text.lower()
    return any(term in text for term in ("这个", "当前", "选中", "选择")) or any(
        term in lowered for term in ("this", "selected", "current")
    )


def _node_label(node: dict) -> str:
    parts = []
    for key in ("title", "type"):
        value = node.get(key)
        if isinstance(value, str):
            parts.append(value)
    return " ".join(parts).strip()


def _find_node_by_label(nodes: list[dict], text: str) -> dict | None:
    lowered = text.lower()
    matches = []
    for node in nodes:
        label = _node_label(node)
        if not label:
            continue
        label_lower = label.lower()
        if label_lower and label_lower in lowered:
            matches.append((len(label_lower), node))
            continue
        title = node.get("title")
        if isinstance(title, str) and title.lower() in lowered:
            matches.append((len(title), node))
    if not matches:
        return None
    matches.sort(key=lambda item: item[0], reverse=True)
    return matches[0][1]


def _select_node(nodes: list[dict], text: str) -> dict | None:
    explicit = _find_node_by_id(nodes, _extract_node_id(text))
    if explicit is not None:
        return explicit

    selected = _selected_nodes(nodes)
    if _message_mentions_current_node(text) and len(selected) == 1:
        return selected[0]

    labelled = _find_node_by_label(nodes, text)
    if labelled is not None:
        return labelled

    if len(selected) == 1:
        return selected[0]
    if len(nodes) == 1:
        return nodes[0]
    return None


WIDGET_ALIASES = (
    (("negative", "负面", "反向"), ("negative", "negative_prompt", "neg_prompt", "text")),
    (("positive", "正向"), ("positive", "positive_prompt", "pos_prompt", "text")),
    (("prompt", "提示词", "文本", "text"), ("text", "prompt", "prompt_text", "positive")),
    (("seed", "种子"), ("seed", "noise_seed")),
    (("steps", "步数"), ("steps",)),
    (("cfg",), ("cfg", "cfg_scale")),
    (("sampler", "采样器"), ("sampler_name", "sampler")),
    (("scheduler", "调度器"), ("scheduler",)),
    (("width", "宽度"), ("width",)),
    (("height", "高度"), ("height",)),
)


def _find_widget_by_name(widgets: list[dict], candidates: tuple[str, ...]) -> dict | None:
    candidate_set = {candidate.lower() for candidate in candidates}
    for widget in widgets:
        name = widget["name"]
        if name.lower() in candidate_set:
            return widget
    return None


def _select_widget(node: dict, text: str) -> dict | None:
    widgets = _node_widgets(node)
    if not widgets:
        return None
    lowered = text.lower()

    for widget in widgets:
        name = widget["name"]
        if name.lower() in lowered:
            return widget

    for triggers, names in WIDGET_ALIASES:
        if any(trigger in lowered or trigger in text for trigger in triggers):
            widget = _find_widget_by_name(widgets, names)
            if widget is not None:
                return widget

    return _find_widget_by_name(
        widgets,
        ("text", "prompt", "positive", "negative", "seed", "steps", "cfg"),
    ) or widgets[0]


def _plan_graph_widget_edit(text: str, context: dict) -> dict | None:
    value = _extract_value_after_set(text)
    if not value:
        return None
    nodes = _graph_nodes(context)
    node = _select_node(nodes, text)
    if node is None:
        return None
    widget = _select_widget(node, text)
    if widget is None:
        return None
    return {
        "summary": f"Set {widget['name']} on node {node.get('id')}",
        "actions": [
            {
                "type": "graph.set_widget",
                "payload": {
                    "node_id": node.get("id"),
                    "widget": widget["name"],
                    "value": _coerce_widget_value(value, widget),
                },
            }
        ],
    }


def _extract_node_type_to_add(text: str) -> str | None:
    patterns = (
        r"(?:添加|新增|创建|加)(?:一个|一個|个)?\s*([A-Za-z][A-Za-z0-9_./:-]+)\s*(?:节点|node)",
        r"\b(?:add|create)\s+(?:a\s+|an\s+)?(?:node\s+)?([A-Za-z][A-Za-z0-9_./:-]+)\b",
    )
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(1).rstrip(".,，。")
    return None


def _plan_graph_add_node(text: str) -> dict | None:
    if not any(term in text.lower() or term in text for term in ("添加", "新增", "创建", "add", "create")):
        return None
    node_type = _extract_node_type_to_add(text)
    if not node_type:
        return None
    return {
        "summary": f"Add graph node {node_type}",
        "actions": [{"type": "graph.add_node", "payload": {"node_type": node_type}}],
    }


def _graph_contains_node(nodes: list[dict], node_id: int) -> bool:
    return any(str(node.get("id")) == str(node_id) for node in nodes)


def _slot_rows(node: dict, slot_key: str) -> list[dict]:
    slots = node.get(slot_key)
    if not isinstance(slots, list):
        return []
    return [
        slot
        for slot in slots[:MAX_PLANNER_SLOTS_PER_NODE]
        if isinstance(slot, dict)
    ]


def _find_node_for_phrase(nodes: list[dict], phrase: str) -> dict | None:
    cleaned = _strip_value(phrase).removesuffix("节点").removesuffix("node").strip()
    by_id = _find_node_by_id(nodes, _extract_node_id(cleaned))
    if by_id is not None:
        return by_id
    lowered = cleaned.lower()
    matches = []
    for node in nodes:
        for key in ("title", "type"):
            value = node.get(key)
            if not isinstance(value, str) or not value:
                continue
            value_lower = value.lower()
            if value_lower == lowered:
                matches.append((len(value_lower) + 1000, node))
            elif value_lower in lowered or lowered in value_lower:
                matches.append((len(value_lower), node))
    if not matches:
        return None
    matches.sort(key=lambda item: item[0], reverse=True)
    return matches[0][1]


def _slot_index_for_hint(node: dict, slot_key: str, hint: str | None) -> int | None:
    slots = _slot_rows(node, slot_key)
    if hint is None:
        return 0
    cleaned = _strip_value(hint)
    if cleaned.isdigit():
        return int(cleaned)
    lowered = cleaned.lower()
    for index, slot in enumerate(slots):
        name = slot.get("name")
        if isinstance(name, str) and name.lower() == lowered:
            return index
    for index, slot in enumerate(slots):
        slot_type = slot.get("type")
        if isinstance(slot_type, str) and slot_type.lower() == lowered:
            return index
    for index, slot in enumerate(slots):
        name = slot.get("name")
        if isinstance(name, str) and (name.lower() in lowered or lowered in name.lower()):
            return index
    return None


def _slot_connect_plan_from_phrases(
    nodes: list[dict],
    origin_phrase: str,
    origin_slot_hint: str,
    target_phrase: str,
    target_slot_hint: str,
) -> dict | None:
    origin = _find_node_for_phrase(nodes, origin_phrase)
    target = _find_node_for_phrase(nodes, target_phrase)
    if origin is None or target is None:
        return None
    origin_slot = _slot_index_for_hint(origin, "outputs", origin_slot_hint)
    target_slot = _slot_index_for_hint(target, "inputs", target_slot_hint)
    if origin_slot is None or target_slot is None:
        return None
    return {
        "summary": f"Connect node {origin.get('id')} to node {target.get('id')}",
        "actions": [
            {
                "type": "graph.connect",
                "payload": {
                    "origin_node_id": origin.get("id"),
                    "origin_slot": origin_slot,
                    "target_node_id": target.get("id"),
                    "target_slot": target_slot,
                },
            }
        ],
    }


def _plan_graph_connect(text: str, context: dict) -> dict | None:
    lowered = text.lower()
    if not any(term in lowered or term in text for term in ("连接", "连到", "接到", "connect")):
        return None
    nodes = _graph_nodes(context)
    slot_patterns = (
        r"把\s+(.+?)\s+的\s+([A-Za-z0-9_ -]+)\s*(?:连接到|连到|接到)\s+(.+?)\s+的\s+([A-Za-z0-9_ -]+)$",
        r"\bconnect\s+(.+?)\s+([A-Za-z0-9_ -]+)\s+(?:to|into)\s+(.+?)\s+([A-Za-z0-9_ -]+)$",
    )
    for pattern in slot_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if not match:
            continue
        plan = _slot_connect_plan_from_phrases(
            nodes,
            match.group(1),
            match.group(2),
            match.group(3),
            match.group(4),
        )
        if plan is not None:
            return plan

    patterns = (
        r"(\d+)\s*号?\s*节点.*?(?:连接|连到|接到).*?(\d+)\s*号?\s*节点",
        r"\bconnect\s+(?:node\s+)?(\d+)\s+(?:to|into)\s+(?:node\s+)?(\d+)\b",
    )
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if not match:
            continue
        origin_node_id = int(match.group(1))
        target_node_id = int(match.group(2))
        if nodes and (
            not _graph_contains_node(nodes, origin_node_id)
            or not _graph_contains_node(nodes, target_node_id)
        ):
            return None
        return {
            "summary": f"Connect node {origin_node_id} to node {target_node_id}",
            "actions": [
                {
                    "type": "graph.connect",
                    "payload": {
                        "origin_node_id": origin_node_id,
                        "origin_slot": 0,
                        "target_node_id": target_node_id,
                        "target_slot": 0,
                    },
                }
            ],
        }
    return None


def _extract_url(text: str) -> str | None:
    match = re.search(r"https?://[^\s，。]+", text)
    if match:
        return match.group(0).rstrip(".,，。")
    return None


def _extract_custom_node_id(text: str) -> str | None:
    match = re.search(
        r"(?:custom\s+node|自定义节点|节点)\s+([A-Za-z0-9_.:/-]+)",
        text,
        re.IGNORECASE,
    )
    if match:
        return match.group(1).rstrip(".,，。")
    return None


def _extract_ollama_model(text: str) -> str | None:
    match = re.search(r"(?:模型|model)\s+([A-Za-z0-9_.:/-]+)", text, re.IGNORECASE)
    if match:
        return match.group(1).rstrip(".,，。")
    match = re.search(r"ollama\s+(?:stop\s+)?([A-Za-z0-9_.:/-]+)", text, re.IGNORECASE)
    if match and match.group(1).lower() not in {"模型", "model"}:
        return match.group(1).rstrip(".,，。")
    return None


class RuleBasedPlanner:
    def plan(self, message: str, context: dict) -> dict:
        text = message.strip() if isinstance(message, str) else ""
        lowered = text.lower()
        graph_connect_plan = _plan_graph_connect(text, context)
        if graph_connect_plan is not None:
            return graph_connect_plan
        graph_add_plan = _plan_graph_add_node(text)
        if graph_add_plan is not None:
            return graph_add_plan
        graph_plan = _plan_graph_widget_edit(text, context)
        if graph_plan is not None:
            return graph_plan
        if "swapoff" in lowered or (
            "swap" in lowered and any(term in text for term in ("关", "关闭", "禁用"))
        ):
            return {
                "summary": "Print sudo swapoff command for Srain",
                "actions": [
                    {
                        "type": "sudo.print_command",
                        "payload": {
                            "command": "sudo swapoff -a",
                            "why": "Disable swap to avoid unified-memory paging and machine stalls",
                        },
                    }
                ],
            }
        if ("重启" in text or "restart" in lowered) and any(
            term in lowered or term in text for term in ("comfyui", "容器", "container", "服务")
        ):
            return {
                "summary": "Restart ComfyUI container",
                "actions": [
                    {"type": "service.restart_container", "payload": {"container": "comfyui-gb10"}}
                ],
            }
        if "ollama" in lowered and any(term in lowered or term in text for term in ("stop", "停止", "驱逐")):
            model = _extract_ollama_model(text)
            if model:
                return {
                    "summary": f"Stop Ollama model {model}",
                    "actions": [{"type": "runtime.stop_ollama_model", "payload": {"model": model}}],
                }
        if ("custom node" in lowered or "自定义节点" in text) and any(
            term in lowered or term in text for term in ("install", "安装")
        ):
            url = _extract_url(text)
            if url:
                return {
                    "summary": f"Install custom node from {url}",
                    "actions": [
                        {
                            "type": "custom_node.install",
                            "payload": {"method": "git_url", "url": url},
                        }
                    ],
                }
        if ("custom node" in lowered or "自定义节点" in text or "节点" in text) and any(
            term in lowered or term in text for term in ("disable", "禁用")
        ):
            node_id = _extract_custom_node_id(text)
            if node_id:
                return {
                    "summary": f"Disable custom node {node_id}",
                    "actions": [{"type": "custom_node.disable", "payload": {"id": node_id}}],
                }
        if ("custom node" in lowered or "自定义节点" in text or "节点" in text) and any(
            term in lowered or term in text for term in ("enable", "启用")
        ):
            node_id = _extract_custom_node_id(text)
            if node_id:
                return {
                    "summary": f"Enable custom node {node_id}",
                    "actions": [{"type": "custom_node.enable", "payload": {"id": node_id}}],
                }
        if "reserve-vram" in lowered or "reserve vram" in lowered:
            match = re.search(r"(\d+)", text)
            value = match.group(1) if match else "8"
            return {
                "summary": f"Set compose reserve-vram to {value}",
                "actions": [{"type": "compose.set_reserve_vram", "payload": {"value": value}}],
            }
        if "free" in lowered or "释放" in text or "腾内存" in text or "内存" in text:
            return {
                "summary": "Free ComfyUI memory",
                "actions": [
                    {
                        "type": "runtime.free_memory",
                        "payload": {"unload_models": True, "free_memory": True},
                    }
                ],
            }
        return _context_plan(text)


def default_planner() -> RuleBasedPlanner:
    provider = os.environ.get("AGENT_WORKBENCH_PROVIDER", "rules")
    if provider != "rules":
        return RuleBasedPlanner()
    return RuleBasedPlanner()
