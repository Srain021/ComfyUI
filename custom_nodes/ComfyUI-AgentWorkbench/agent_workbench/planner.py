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
    cleaned = cleaned.strip(" \t\r\n'\"`.,，。:：;；")
    cleaned = cleaned.strip("“”‘’")
    return cleaned


VALUE_SET_DELIMITERS = (
    "替换为",
    "改成",
    "改为",
    "设置为",
    "设为",
    "变成",
    "写成",
    "写为",
    "换成",
    "换为",
    "填成",
    "填为",
    "填上",
    "输入为",
)

TEXT_APPEND_DELIMITERS = ("加上", "追加", "补上", "加入")
TEXT_REMOVE_DELIMITERS = ("去掉", "去除", "删除", "删掉", "移除")
TEXT_CLEAR_TERMS = ("清空", "清除", "清掉", "clear", "empty")
SEED_RANDOM_TERMS = ("随机", "random", "randomize")
SEED_FIXED_TERMS = ("固定", "锁定", "fixed", "fix")


def _extract_value_after_set(text: str) -> str | None:
    for delimiter in VALUE_SET_DELIMITERS:
        if delimiter in text:
            return _strip_value(text.rsplit(delimiter, 1)[1])
    match = re.search(
        r"\b(?:set|change|update|write|replace|fill)\b.+?\b(?:to|as|with)\b\s*(.+)$",
        text,
        re.IGNORECASE,
    )
    if match:
        return _strip_value(match.group(1))
    return None


def _extract_value_after_delimiters(text: str, delimiters: tuple[str, ...]) -> str | None:
    for delimiter in delimiters:
        if delimiter in text:
            value = _strip_value(text.rsplit(delimiter, 1)[1])
            return value or None
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


NODE_LABEL_ALIASES = (
    (
        ("正向提示词", "正面提示词", "正向 prompt", "正向prompt", "positive prompt", "positive"),
        ("positive prompt", "positive"),
    ),
    (
        ("负面提示词", "反向提示词", "负向提示词", "负面 prompt", "负面prompt", "negative prompt", "negative"),
        ("negative prompt", "negative"),
    ),
    (
        ("checkpoint", "ckpt", "底模", "大模型"),
        ("checkpointloader", "checkpointloadersimple", "load checkpoint", "checkpoint"),
    ),
    (
        ("vae",),
        ("vaeloader", "load vae", "vae loader"),
    ),
    (
        ("lora", "lora 模型", "lora模型"),
        ("loraloader", "load lora", "lora loader", "lora"),
    ),
    (
        ("clip skip", "clip layer", "clip 层", "clip跳层"),
        ("clipsetlastlayer", "clip set last layer"),
    ),
)


PROMPT_TEXT_WIDGET_NAMES = (
    "text",
    "prompt",
    "prompt_text",
    "positive",
    "positive_prompt",
    "negative",
    "negative_prompt",
)


def _message_mentions_generic_prompt(text: str) -> bool:
    lowered = text.lower()
    return "prompt" in lowered or "提示词" in text


def _node_has_prompt_text_widget(node: dict) -> bool:
    return _find_widget_by_name(_node_widgets(node), PROMPT_TEXT_WIDGET_NAMES) is not None


def _node_looks_like_prompt_text_node(node: dict) -> bool:
    if not _node_has_prompt_text_widget(node):
        return False
    label = _node_label(node).lower()
    compact = re.sub(r"[\s_./:-]+", "", label)
    return "prompt" in label or "提示词" in label or "cliptextencode" in compact


def _generic_prompt_text_nodes(nodes: list[dict], text: str) -> list[dict]:
    if not _message_mentions_generic_prompt(text):
        return []
    return [node for node in nodes if _node_looks_like_prompt_text_node(node)]


def _find_node_by_semantic_label(nodes: list[dict], text: str) -> dict | None:
    lowered = text.lower()
    for triggers, label_candidates in NODE_LABEL_ALIASES:
        if not any(trigger in lowered or trigger in text for trigger in triggers):
            continue
        matches = []
        for node in nodes:
            label_lower = _node_label(node).lower()
            for candidate in label_candidates:
                if candidate in label_lower:
                    matches.append((len(candidate), node))
                    break
        if matches:
            matches.sort(key=lambda item: item[0], reverse=True)
            return matches[0][1]
    generic_prompt_nodes = _generic_prompt_text_nodes(nodes, text)
    if len(generic_prompt_nodes) == 1:
        return generic_prompt_nodes[0]
    return None


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

    semantic = _find_node_by_semantic_label(nodes, text)
    if semantic is not None:
        return semantic

    labelled = _find_node_by_label(nodes, text)
    if labelled is not None:
        return labelled

    if len(selected) == 1:
        return selected[0]
    if len(nodes) == 1:
        return nodes[0]
    return None


def _message_mentions_all_nodes(text: str) -> bool:
    lowered = text.lower()
    return any(term in lowered or term in text for term in ("所有", "全部", "all", "every"))


def _message_mentions_selected_nodes(text: str) -> bool:
    lowered = text.lower()
    return any(term in lowered or term in text for term in ("选中", "选择的", "selected", "current selection"))


def _find_nodes_by_semantic_label(nodes: list[dict], text: str) -> list[dict]:
    lowered = text.lower()
    for triggers, label_candidates in NODE_LABEL_ALIASES:
        if not any(trigger in lowered or trigger in text for trigger in triggers):
            continue
        matches = []
        for node in nodes:
            label_lower = _node_label(node).lower()
            if any(candidate in label_lower for candidate in label_candidates):
                matches.append(node)
        return matches
    generic_prompt_nodes = _generic_prompt_text_nodes(nodes, text)
    if generic_prompt_nodes:
        return generic_prompt_nodes
    return []


def _find_nodes_by_label(nodes: list[dict], text: str) -> list[dict]:
    lowered = text.lower()
    matches = []
    for node in nodes:
        for key in ("title", "type"):
            value = node.get(key)
            if not isinstance(value, str) or not value:
                continue
            if value.lower() in lowered:
                matches.append(node)
                break
    return matches


def _select_all_matching_nodes(nodes: list[dict], text: str) -> list[dict]:
    if not _message_mentions_all_nodes(text):
        return []
    semantic = _find_nodes_by_semantic_label(nodes, text)
    if semantic:
        return semantic
    return _find_nodes_by_label(nodes, text)


def _select_selected_matching_nodes(nodes: list[dict], text: str) -> list[dict]:
    selected = _selected_nodes(nodes)
    if len(selected) <= 1 or not _message_mentions_selected_nodes(text):
        return []
    semantic = _find_nodes_by_semantic_label(selected, text)
    if semantic:
        return semantic
    labelled = _find_nodes_by_label(selected, text)
    if labelled:
        return labelled
    return selected


def _select_bulk_nodes(nodes: list[dict], text: str) -> list[dict]:
    selected = _select_selected_matching_nodes(nodes, text)
    if selected:
        return selected
    return _select_all_matching_nodes(nodes, text)


WIDGET_ALIASES = (
    (("negative", "负面", "反向"), ("negative", "negative_prompt", "neg_prompt", "text")),
    (("positive", "正向"), ("positive", "positive_prompt", "pos_prompt", "text")),
    (("prompt", "提示词", "文本", "内容", "text"), ("text", "prompt", "prompt_text", "positive")),
    (("模型权重", "model strength", "strength model", "strength_model"), ("strength_model",)),
    (("clip skip", "clip layer", "clip 层", "clip跳层"), ("stop_at_clip_layer",)),
    (("clip 权重", "clip强度", "clip strength", "strength_clip"), ("strength_clip",)),
    (("lora 权重", "lora强度", "权重", "强度", "strength"), ("strength_model", "strength", "weight")),
    (("lora模型", "lora 模型", "lora model", "lora"), ("lora_name", "lora", "lora_model_name")),
    (("checkpoint", "ckpt", "大模型", "底模", "模型", "model"), ("ckpt_name", "checkpoint", "model_name", "unet_name")),
    (("vae",), ("vae_name", "vae")),
    (("seed", "种子"), ("seed", "noise_seed")),
    (("steps", "步数"), ("steps",)),
    (("cfg",), ("cfg", "cfg_scale")),
    (("sampler", "采样器"), ("sampler_name", "sampler")),
    (("scheduler", "调度器"), ("scheduler",)),
    (("denoise", "重绘幅度", "降噪", "去噪"), ("denoise",)),
    (("batch", "batch size", "批量", "批次"), ("batch_size", "batch")),
    (("frames", "frame count", "num_frames", "帧数", "视频帧数"), ("num_frames", "frames", "length")),
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


def _widget_hint_map(node: dict) -> dict[str, dict]:
    widgets = _node_widgets(node)
    hints = {}
    for widget in widgets:
        hints[widget["name"].lower()] = widget
    for triggers, names in WIDGET_ALIASES:
        widget = _find_widget_by_name(widgets, names)
        if widget is None:
            continue
        for hint in (*triggers, *names):
            hints[hint.lower()] = widget
    return hints


def _widget_assignments(text: str, node: dict) -> list[tuple[dict, object]]:
    hints = _widget_hint_map(node)
    if not hints:
        return []
    hint_pattern = "|".join(re.escape(hint) for hint in sorted(hints, key=len, reverse=True))
    assignment_operators = "|".join(re.escape(operator) for operator in (*VALUE_SET_DELIMITERS, "="))
    pattern = re.compile(
        rf"(?P<hint>{hint_pattern})\s*(?:{assignment_operators})\s*",
        re.IGNORECASE,
    )
    matches = list(pattern.finditer(text))
    rows = []
    seen_widgets = set()
    for index, match in enumerate(matches):
        value_end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        raw_value = text[match.end():value_end]
        value = _strip_value(raw_value)
        if not value:
            continue
        widget = hints[match.group("hint").lower()]
        if widget["name"] in seen_widgets:
            continue
        seen_widgets.add(widget["name"])
        rows.append((widget, _coerce_widget_value(value, widget)))
    return rows


RESOLUTION_PRESETS = {
    720: (1280, 720),
    1080: (1920, 1080),
}


def _size_widgets(node: dict) -> tuple[dict | None, dict | None]:
    widgets = _node_widgets(node)
    return _find_widget_by_name(widgets, ("width",)), _find_widget_by_name(widgets, ("height",))


def _round_dimension(value: int | float) -> int:
    return int(round(float(value)))


def _current_dimension(widget: dict | None) -> int | None:
    if widget is None:
        return None
    value = widget.get("value")
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return _round_dimension(value)


def _size_assignments(text: str, node: dict) -> list[tuple[dict, object]]:
    lowered = text.lower()
    if not any(term in lowered or term in text for term in ("尺寸", "分辨率", "size", "resolution")):
        return []
    value = _extract_value_after_set(text)
    if not value:
        return []
    width, height = _size_widgets(node)
    if width is None or height is None:
        return []
    match = re.search(r"(\d+(?:\.\d+)?)\s*[xX×*]\s*(\d+(?:\.\d+)?)", value)
    if match:
        return [(width, _number_value(match.group(1))), (height, _number_value(match.group(2)))]

    preset = re.search(r"\b(720|1080)\s*p\b", value, re.IGNORECASE)
    if preset:
        preset_width, preset_height = RESOLUTION_PRESETS[int(preset.group(1))]
        if any(term in lowered or term in text for term in ("竖屏", "portrait", "vertical")):
            preset_width, preset_height = preset_height, preset_width
        return [(width, preset_width), (height, preset_height)]

    ratio = re.search(r"(\d+(?:\.\d+)?)\s*[:：]\s*(\d+(?:\.\d+)?)", value)
    if not ratio:
        return []
    ratio_width = float(ratio.group(1))
    ratio_height = float(ratio.group(2))
    if ratio_width <= 0 or ratio_height <= 0:
        return []
    mentions_vertical = any(term in lowered or term in text for term in ("竖屏", "portrait", "vertical"))
    mentions_horizontal = any(term in lowered or term in text for term in ("横屏", "landscape", "horizontal"))
    current_width = _current_dimension(width)
    current_height = _current_dimension(height)
    if mentions_vertical or (not mentions_horizontal and ratio_width < ratio_height):
        if current_width is None:
            return []
        return [(width, current_width), (height, _round_dimension(current_width * ratio_height / ratio_width))]
    if current_height is None:
        return []
    return [(width, _round_dimension(current_height * ratio_width / ratio_height)), (height, current_height)]


def _extract_widget_delta(text: str) -> int | float | None:
    lowered = text.lower()
    direction = None
    if any(
        term in lowered or term in text
        for term in ("提高", "调高", "增加", "raise", "increase", "higher")
    ):
        direction = 1
    if any(
        term in lowered or term in text
        for term in ("降低", "调低", "减少", "lower", "decrease", "down")
    ):
        direction = -1
    if direction is None:
        return None
    numbers = re.findall(r"-?\d+(?:\.\d+)?", text)
    if not numbers:
        return None
    delta = float(numbers[-1]) * direction
    return int(delta) if delta.is_integer() else delta


def _adjust_widget_value(widget: dict, delta: int | float) -> object | None:
    current = widget.get("value")
    if isinstance(current, bool) or not isinstance(current, (int, float)):
        return None
    value = current + delta
    if isinstance(current, int) and float(value).is_integer():
        return int(value)
    return value


def _mentions_seed(text: str) -> bool:
    lowered = text.lower()
    return any(term in lowered or term in text for term in ("seed", "种子"))


def _seed_control_actions_for_node(text: str, node: dict) -> list[dict]:
    if not _mentions_seed(text):
        return []
    widgets = _node_widgets(node)
    control = _find_widget_by_name(widgets, ("control_after_generate",))
    if control is None:
        return []
    lowered = text.lower()
    randomize = any(term in lowered or term in text for term in SEED_RANDOM_TERMS)
    fixed = any(term in lowered or term in text for term in SEED_FIXED_TERMS)
    if not randomize and not fixed:
        return []

    actions = []
    if fixed:
        seed = _find_widget_by_name(widgets, ("seed", "noise_seed"))
        numbers = re.findall(r"-?\d+", text)
        if seed is not None and numbers:
            actions.append(
                {
                    "type": "graph.set_widget",
                    "payload": {
                        "node_id": node.get("id"),
                        "widget": seed["name"],
                        "value": _coerce_widget_value(numbers[-1], seed),
                    },
                }
            )
    actions.append(
        {
            "type": "graph.set_widget",
            "payload": {
                "node_id": node.get("id"),
                "widget": control["name"],
                "value": "randomize" if randomize and not fixed else "fixed",
            },
        }
    )
    return actions


def _append_text_value(current: object, fragment: str) -> str | None:
    if not isinstance(current, str):
        return None
    cleaned = _strip_value(fragment)
    if not cleaned:
        return None
    base = current.strip()
    if not base:
        return cleaned
    separator = " " if base.endswith((",", "，", ";", "；")) else ", "
    return f"{base}{separator}{cleaned}"


def _remove_text_value(current: object, fragment: str) -> str | None:
    if not isinstance(current, str):
        return None
    cleaned = _strip_value(fragment)
    if not cleaned:
        return None
    parts = [part.strip() for part in re.split(r"\s*[,，]\s*", current) if part.strip()]
    lowered = cleaned.lower()
    remaining = [part for part in parts if part.lower() != lowered]
    if len(remaining) != len(parts):
        return ", ".join(remaining)
    value = re.sub(re.escape(cleaned), "", current, flags=re.IGNORECASE)
    value = re.sub(r"\s*[,，]\s*[,，]+\s*", ", ", value)
    return value.strip(" \t\r\n,，")


def _looks_like_text_clear(text: str) -> bool:
    lowered = text.lower()
    if not any(term in lowered or term in text for term in TEXT_CLEAR_TERMS):
        return False
    return any(
        term in lowered or term in text
        for term in ("prompt", "提示词", "文本", "内容", "text")
    )


def _clear_text_actions_for_node(text: str, node: dict) -> list[dict]:
    if not _looks_like_text_clear(text):
        return []
    widget = _select_widget(node, text)
    if widget is None or not isinstance(widget.get("value"), str):
        return []
    return [
        {
            "type": "graph.set_widget",
            "payload": {
                "node_id": node.get("id"),
                "widget": widget["name"],
                "value": "",
            },
        }
    ]


def _text_edit_actions_for_node(text: str, node: dict) -> list[dict]:
    clear_actions = _clear_text_actions_for_node(text, node)
    if clear_actions:
        return clear_actions

    append_value = _extract_value_after_delimiters(text, TEXT_APPEND_DELIMITERS)
    remove_value = _extract_value_after_delimiters(text, TEXT_REMOVE_DELIMITERS)
    if not append_value and not remove_value:
        return []
    widget = _select_widget(node, text)
    if widget is None:
        return []
    if append_value:
        value = _append_text_value(widget.get("value"), append_value)
    else:
        value = _remove_text_value(widget.get("value"), remove_value or "")
    if value is None:
        return []
    return [
        {
            "type": "graph.set_widget",
            "payload": {
                "node_id": node.get("id"),
                "widget": widget["name"],
                "value": value,
            },
        }
    ]


def _looks_like_widget_text_removal(text: str) -> bool:
    if not _extract_value_after_delimiters(text, TEXT_REMOVE_DELIMITERS):
        return False
    lowered = text.lower()
    return any(term in lowered or term in text for term in ("从", "里", "里面", "文本", "内容", "提示词", "prompt", "text"))


def _widget_edit_actions_for_node(text: str, node: dict) -> list[dict]:
    seed_control_actions = _seed_control_actions_for_node(text, node)
    if seed_control_actions:
        return seed_control_actions

    text_actions = _text_edit_actions_for_node(text, node)
    if text_actions:
        return text_actions

    size_assignments = _size_assignments(text, node)
    if size_assignments:
        assignments = size_assignments
    else:
        assignments = _widget_assignments(text, node)
    if assignments:
        return [
            {
                "type": "graph.set_widget",
                "payload": {
                    "node_id": node.get("id"),
                    "widget": widget["name"],
                    "value": value,
                },
            }
            for widget, value in assignments
        ]

    delta = _extract_widget_delta(text)
    if delta is not None:
        widget = _select_widget(node, text)
        if widget is None:
            return []
        value = _adjust_widget_value(widget, delta)
        if value is None:
            return []
        return [
            {
                "type": "graph.set_widget",
                "payload": {
                    "node_id": node.get("id"),
                    "widget": widget["name"],
                    "value": value,
                },
            }
        ]

    value = _extract_value_after_set(text)
    if not value:
        return []
    widget = _select_widget(node, text)
    if widget is None:
        return []
    return [
        {
            "type": "graph.set_widget",
            "payload": {
                "node_id": node.get("id"),
                "widget": widget["name"],
                "value": _coerce_widget_value(value, widget),
            },
        }
    ]


def _plan_graph_widget_edit(text: str, context: dict) -> dict | None:
    nodes = _graph_nodes(context)
    bulk_nodes = _select_bulk_nodes(nodes, text)
    if bulk_nodes:
        actions = []
        for item in bulk_nodes:
            actions.extend(_widget_edit_actions_for_node(text, item))
        if actions:
            return {
                "summary": f"Set widget(s) on {len(bulk_nodes)} matching node(s)",
                "actions": actions,
            }

    node = _select_node(nodes, text)
    if node is None:
        return None
    actions = _widget_edit_actions_for_node(text, node)
    if not actions:
        return None
    return {
        "summary": f"Set widget(s) on node {node.get('id')}",
        "actions": actions,
    }


def _copy_widget_phrases(text: str) -> tuple[str, str] | None:
    patterns = (
        r"(?:把|将)\s*(.+?)\s*(?:复制到|拷贝到|同步到)\s*(.+)$",
        r"(?:复制|拷贝|同步)\s*(.+?)\s*(?:到|至)\s*(.+)$",
        r"\bcopy\s+(.+?)\s+(?:to|into)\s+(.+)$",
        r"\bsync\s+(.+?)\s+(?:to|into)\s+(.+)$",
    )
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            source = _strip_value(match.group(1))
            target = _strip_value(match.group(2))
            if source and target:
                return source, target
    return None


def _plan_graph_copy_widget_value(text: str, context: dict) -> dict | None:
    phrases = _copy_widget_phrases(text)
    if phrases is None:
        return None
    source_phrase, target_phrase = phrases
    nodes = _graph_nodes(context)
    source = _select_node(nodes, source_phrase)
    target = _select_node(nodes, target_phrase)
    if source is None or target is None or source.get("id") == target.get("id"):
        return None
    source_widget = _select_widget(source, source_phrase)
    target_widget = _select_widget(target, target_phrase)
    if source_widget is None or target_widget is None:
        return None
    return {
        "summary": f"Copy widget from node {source.get('id')} to node {target.get('id')}",
        "actions": [
            {
                "type": "graph.set_widget",
                "payload": {
                    "node_id": target.get("id"),
                    "widget": target_widget["name"],
                    "value": source_widget.get("value"),
                },
            }
        ],
    }


def _plan_graph_delete_node(text: str, context: dict) -> dict | None:
    lowered = text.lower()
    if not any(term in lowered or term in text for term in ("删除", "删掉", "移除", "delete", "remove")):
        return None
    if _looks_like_widget_text_removal(text):
        return None
    nodes = _graph_nodes(context)
    bulk_nodes = _select_bulk_nodes(nodes, text)
    if bulk_nodes:
        return {
            "summary": f"Delete {len(bulk_nodes)} graph node(s)",
            "actions": [
                {"type": "graph.delete_node", "payload": {"node_id": node.get("id")}}
                for node in bulk_nodes
            ],
        }
    node = _select_node(nodes, text)
    if node is None:
        return None
    return {
        "summary": f"Delete graph node {node.get('id')}",
        "actions": [{"type": "graph.delete_node", "payload": {"node_id": node.get("id")}}],
    }


def _plan_graph_duplicate_node(text: str, context: dict) -> dict | None:
    lowered = text.lower()
    if not any(term in lowered or term in text for term in ("复制", "克隆", "duplicate", "clone")):
        return None
    nodes = _graph_nodes(context)
    bulk_nodes = _select_bulk_nodes(nodes, text)
    if bulk_nodes:
        return {
            "summary": f"Duplicate {len(bulk_nodes)} graph node(s)",
            "actions": [
                {
                    "type": "graph.duplicate_node",
                    "payload": {"node_id": node.get("id"), "offset": [40, 40], "select": False},
                }
                for node in bulk_nodes
            ],
        }
    node = _select_node(nodes, text)
    if node is None:
        return None
    return {
        "summary": f"Duplicate graph node {node.get('id')}",
        "actions": [
            {
                "type": "graph.duplicate_node",
                "payload": {"node_id": node.get("id"), "offset": [40, 40], "select": True},
            }
        ],
    }


NODE_COLOR_ALIASES = (
    (("红色", "标红", "red"), "#ff5555"),
    (("蓝色", "标蓝", "blue"), "#4f8cff"),
    (("绿色", "标绿", "green"), "#4caf50"),
    (("黄色", "标黄", "yellow"), "#f2c94c"),
    (("紫色", "标紫", "purple"), "#b084ff"),
    (("橙色", "标橙", "orange"), "#ff9f43"),
    (("灰色", "标灰", "gray", "grey"), "#8a8f98"),
    (("红",), "#ff5555"),
    (("蓝",), "#4f8cff"),
    (("绿",), "#4caf50"),
    (("黄",), "#f2c94c"),
    (("紫",), "#b084ff"),
    (("橙",), "#ff9f43"),
    (("灰",), "#8a8f98"),
)


def _mentions_color_action(text: str) -> bool:
    lowered = text.lower()
    return any(
        term in lowered or term in text
        for term in (
            "颜色",
            "高亮",
            "标成",
            "标为",
            "标记",
            "标红",
            "标蓝",
            "标绿",
            "标黄",
            "标紫",
            "标橙",
            "标灰",
            "highlight",
            "color",
            "mark",
        )
    )


def _extract_node_color(text: str) -> str | None:
    lowered = text.lower()
    for triggers, color in NODE_COLOR_ALIASES:
        if any(trigger in lowered or trigger in text for trigger in triggers):
            return color
    if "高亮" in text or "highlight" in lowered:
        return "#f2c94c"
    return None


def _set_color_action(node: dict, color: str) -> dict:
    return {
        "type": "graph.set_color",
        "payload": {"node_id": node.get("id"), "color": color},
    }


def _plan_graph_set_color(text: str, context: dict) -> dict | None:
    if not _mentions_color_action(text):
        return None
    color = _extract_node_color(text)
    if color is None:
        return None
    nodes = _graph_nodes(context)
    bulk_nodes = _select_bulk_nodes(nodes, text)
    if bulk_nodes:
        return {
            "summary": f"Color {len(bulk_nodes)} graph node(s)",
            "actions": [_set_color_action(node, color) for node in bulk_nodes],
        }
    node = _select_node(nodes, text)
    if node is None:
        return None
    return {
        "summary": f"Color graph node {node.get('id')}",
        "actions": [_set_color_action(node, color)],
    }


def _graph_mode_from_text(text: str) -> str | None:
    lowered = text.lower()
    if "custom node" in lowered or "自定义节点" in text:
        return None
    if any(term in lowered or term in text for term in ("取消绕过", "取消禁用", "恢复", "启用", "enable", "unmute")):
        return "always"
    if any(term in lowered or term in text for term in ("绕过", "旁路", "bypass")):
        return "bypass"
    if any(term in lowered or term in text for term in ("禁用", "停用", "mute", "disable", "关闭", "关掉")):
        return "mute"
    return None


def _plan_graph_set_mode(text: str, context: dict) -> dict | None:
    mode = _graph_mode_from_text(text)
    if mode is None:
        return None
    nodes = _graph_nodes(context)
    bulk_nodes = _select_bulk_nodes(nodes, text)
    if bulk_nodes:
        return {
            "summary": f"Set {len(bulk_nodes)} graph node(s) mode to {mode}",
            "actions": [
                {"type": "graph.set_mode", "payload": {"node_id": node.get("id"), "mode": mode}}
                for node in bulk_nodes
            ],
        }
    node = _select_node(nodes, text)
    if node is None:
        return None
    return {
        "summary": f"Set graph node {node.get('id')} mode to {mode}",
        "actions": [{"type": "graph.set_mode", "payload": {"node_id": node.get("id"), "mode": mode}}],
    }


def _extract_title_value(text: str) -> str | None:
    for delimiter in (
        "重命名为",
        "重命名成",
        "改名为",
        "改名成",
        "命名为",
        "标题改成",
        "标题改为",
        "标题设置为",
        "标题设为",
    ):
        if delimiter in text:
            return _strip_value(text.rsplit(delimiter, 1)[1])
    match = re.search(r"\brename\b.+?\bto\b\s*(.+)$", text, re.IGNORECASE)
    if match:
        return _strip_value(match.group(1))
    match = re.search(r"\btitle\b.+?\b(?:to|as)\b\s*(.+)$", text, re.IGNORECASE)
    if match:
        return _strip_value(match.group(1))
    return None


def _plan_graph_set_title(text: str, context: dict) -> dict | None:
    lowered = text.lower()
    if not any(term in lowered or term in text for term in ("标题", "重命名", "改名", "命名", "rename", "title")):
        return None
    title = _extract_title_value(text)
    if not title:
        return None
    nodes = _graph_nodes(context)
    node = _select_node(nodes, text)
    if node is None:
        return None
    return {
        "summary": f"Set graph node {node.get('id')} title",
        "actions": [{"type": "graph.set_title", "payload": {"node_id": node.get("id"), "title": title}}],
    }


def _number_value(value: str) -> int | float:
    number = float(value)
    return int(number) if number.is_integer() else number


def _position_number(value: int | float) -> int | float:
    number = float(value)
    return int(number) if number.is_integer() else number


def _node_position(node: dict) -> list[int | float]:
    pos = node.get("pos")
    if not isinstance(pos, list) or len(pos) < 2:
        return [0, 0]
    try:
        return [_number_value(str(pos[0])), _number_value(str(pos[1]))]
    except (TypeError, ValueError):
        return [0, 0]


def _extract_absolute_position(text: str) -> list[int | float] | None:
    if not any(term in text.lower() or term in text for term in ("移动到", "移到", "move to")):
        return None
    match = re.search(
        r"(?:移动到|移到|move\s+to)\s*\(?\s*(-?\d+(?:\.\d+)?)\s*[,， ]\s*(-?\d+(?:\.\d+)?)",
        text,
        re.IGNORECASE,
    )
    if not match:
        return None
    return [_number_value(match.group(1)), _number_value(match.group(2))]


def _extract_move_delta(text: str) -> list[int | float] | None:
    lowered = text.lower()
    directions = (
        (("往右", "向右", "右移", "move right", "right"), (1, 0)),
        (("往左", "向左", "左移", "move left", "left"), (-1, 0)),
        (("往下", "向下", "下移", "move down", "down"), (0, 1)),
        (("往上", "向上", "上移", "move up", "up"), (0, -1)),
    )
    direction = None
    for terms, vector in directions:
        if any(term in lowered or term in text for term in terms):
            direction = vector
            break
    if direction is None:
        return None
    numbers = re.findall(r"-?\d+(?:\.\d+)?", text)
    distance = _number_value(numbers[-1]) if numbers else 100
    return [direction[0] * distance, direction[1] * distance]


def _alignment_axis(text: str) -> str | None:
    lowered = text.lower()
    if any(term in lowered or term in text for term in ("左对齐", "align left", "left align")):
        return "left"
    if any(term in lowered or term in text for term in ("右对齐", "align right", "right align")):
        return "right"
    if any(term in lowered or term in text for term in ("上对齐", "顶端对齐", "align top", "top align")):
        return "top"
    if any(term in lowered or term in text for term in ("下对齐", "底部对齐", "align bottom", "bottom align")):
        return "bottom"
    if any(term in lowered or term in text for term in ("横向对齐", "水平对齐", "align horizontal")):
        return "horizontal"
    if any(term in lowered or term in text for term in ("纵向对齐", "垂直对齐", "align vertical")):
        return "vertical"
    return None


def _alignment_reference(axis: str, positions: list[list[int | float]]) -> int | float:
    if axis == "left":
        return min(pos[0] for pos in positions)
    if axis == "right":
        return max(pos[0] for pos in positions)
    if axis == "top":
        return min(pos[1] for pos in positions)
    if axis == "bottom":
        return max(pos[1] for pos in positions)
    if axis == "vertical":
        return positions[0][0]
    return positions[0][1]


def _aligned_position(axis: str, pos: list[int | float], reference: int | float) -> list[int | float]:
    if axis in {"left", "right", "vertical"}:
        return [reference, pos[1]]
    return [pos[0], reference]


def _plan_graph_align_nodes(text: str, context: dict) -> dict | None:
    axis = _alignment_axis(text)
    if axis is None:
        return None
    nodes = _select_bulk_nodes(_graph_nodes(context), text)
    if len(nodes) < 2:
        return None
    positions = [_node_position(node) for node in nodes]
    reference = _alignment_reference(axis, positions)
    return {
        "summary": f"Align {len(nodes)} graph node(s)",
        "actions": [
            {
                "type": "graph.set_position",
                "payload": {
                    "node_id": node.get("id"),
                    "pos": _aligned_position(axis, pos, reference),
                },
            }
            for node, pos in zip(nodes, positions)
        ],
    }


def _distribution_axis(text: str) -> str | None:
    lowered = text.lower()
    if not any(
        term in lowered or term in text
        for term in ("等间距", "均匀", "分布", "排列", "distribute", "space evenly", "spacing")
    ):
        return None
    if any(term in lowered or term in text for term in ("纵向", "垂直", "vertical", "column")):
        return "vertical"
    if any(term in lowered or term in text for term in ("横向", "水平", "horizontal", "row")):
        return "horizontal"
    return None


def _plan_graph_distribute_nodes(text: str, context: dict) -> dict | None:
    axis = _distribution_axis(text)
    if axis is None:
        return None
    nodes = _select_bulk_nodes(_graph_nodes(context), text)
    if len(nodes) < 3:
        return None
    axis_index = 0 if axis == "horizontal" else 1
    rows = sorted(((node, _node_position(node)) for node in nodes), key=lambda item: item[1][axis_index])
    first = rows[0][1][axis_index]
    last = rows[-1][1][axis_index]
    step = (last - first) / (len(rows) - 1)
    return {
        "summary": f"Distribute {len(rows)} graph node(s)",
        "actions": [
            {
                "type": "graph.set_position",
                "payload": {
                    "node_id": node.get("id"),
                    "pos": [
                        _position_number(first + step * index) if axis_index == 0 else pos[0],
                        _position_number(first + step * index) if axis_index == 1 else pos[1],
                    ],
                },
            }
            for index, (node, pos) in enumerate(rows)
        ],
    }


def _plan_graph_set_position(text: str, context: dict) -> dict | None:
    lowered = text.lower()
    if not any(term in lowered or term in text for term in ("移动", "移到", "挪", "move")):
        return None
    nodes = _graph_nodes(context)
    bulk_nodes = _select_bulk_nodes(nodes, text)
    if bulk_nodes:
        delta = _extract_move_delta(text)
        if delta is not None:
            actions = []
            for node in bulk_nodes:
                current = _node_position(node)
                actions.append(
                    {
                        "type": "graph.set_position",
                        "payload": {
                            "node_id": node.get("id"),
                            "pos": [current[0] + delta[0], current[1] + delta[1]],
                        },
                    }
                )
            return {
                "summary": f"Move {len(bulk_nodes)} graph node(s)",
                "actions": actions,
            }
    node = _select_node(nodes, text)
    if node is None:
        return None
    pos = _extract_absolute_position(text)
    if pos is None:
        delta = _extract_move_delta(text)
        if delta is None:
            return None
        current = _node_position(node)
        pos = [current[0] + delta[0], current[1] + delta[1]]
    return {
        "summary": f"Move graph node {node.get('id')}",
        "actions": [{"type": "graph.set_position", "payload": {"node_id": node.get("id"), "pos": pos}}],
    }


def _graph_select_focus(text: str) -> bool | None:
    lowered = text.lower()
    if any(term in lowered or term in text for term in ("聚焦", "定位", "居中", "focus", "center", "find")):
        return True
    if any(term in lowered or term in text for term in ("选中", "选择", "select")):
        return False
    return None


def _select_node_for_selection(nodes: list[dict], text: str) -> dict | None:
    explicit = _find_node_by_id(nodes, _extract_node_id(text))
    if explicit is not None:
        return explicit

    labelled = _find_node_by_label(nodes, text)
    if labelled is not None:
        return labelled

    return _select_node(nodes, text)


def _plan_graph_select_node(text: str, context: dict) -> dict | None:
    focus = _graph_select_focus(text)
    if focus is None:
        return None
    if focus is False and _extract_value_after_set(text):
        return None
    nodes = _graph_nodes(context)
    bulk_nodes = _select_all_matching_nodes(nodes, text)
    if len(bulk_nodes) >= 2:
        return {
            "summary": f"Select {len(bulk_nodes)} graph node(s)",
            "actions": [
                {
                    "type": "graph.select_nodes",
                    "payload": {
                        "node_ids": [node.get("id") for node in bulk_nodes],
                        "focus": focus,
                    },
                }
            ],
        }
    node = _select_node_for_selection(nodes, text)
    if node is None:
        return None
    return {
        "summary": f"Select graph node {node.get('id')}",
        "actions": [
            {"type": "graph.select_node", "payload": {"node_id": node.get("id"), "focus": focus}}
        ],
    }


def _widget_name_hint_from_text(text: str) -> str | None:
    lowered = text.lower()
    for triggers, names in WIDGET_ALIASES:
        if any(trigger in lowered or trigger in text for trigger in triggers):
            return names[0]
    return None


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
    payload = {"node_type": node_type}
    value = _extract_value_after_set(text)
    widget_name = _widget_name_hint_from_text(text)
    if value and widget_name:
        payload["widgets"] = {widget_name: value}
    return {
        "summary": f"Add graph node {node_type}",
        "actions": [{"type": "graph.add_node", "payload": payload}],
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
    if _message_mentions_current_node(cleaned):
        selected = _selected_nodes(nodes)
        if len(selected) == 1:
            return selected[0]
    semantic = _find_node_by_semantic_label(nodes, cleaned)
    if semantic is not None:
        return semantic
    labelled = _find_node_by_label(nodes, cleaned)
    if labelled is not None:
        return labelled
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


def _slot_type(slot: dict) -> str | None:
    value = slot.get("type")
    return value.lower() if isinstance(value, str) and value else None


def _slot_index_for_type(node: dict, slot_key: str, slot_type: str | None) -> int | None:
    if slot_type is None:
        return None
    for index, slot in enumerate(_slot_rows(node, slot_key)):
        if _slot_type(slot) == slot_type:
            return index
    return None


def _prompt_role_from_phrase(phrase: str, node: dict) -> str | None:
    lowered = f"{phrase} {_node_label(node)}".lower()
    if any(term in lowered or term in phrase for term in ("正向", "正面", "positive")):
        return "positive"
    if any(term in lowered or term in phrase for term in ("负面", "反向", "负向", "negative")):
        return "negative"
    return None


def _infer_connect_slots(
    origin: dict,
    target: dict,
    origin_phrase: str,
    target_phrase: str,
) -> tuple[int, int] | None:
    outputs = _slot_rows(origin, "outputs")
    inputs = _slot_rows(target, "inputs")
    if not outputs or not inputs:
        return (0, 0)

    role = _prompt_role_from_phrase(origin_phrase, origin)
    if role is not None:
        target_slot = _slot_index_for_hint(target, "inputs", role)
        if target_slot is not None:
            target_type = _slot_type(inputs[target_slot])
            origin_slot = _slot_index_for_type(origin, "outputs", target_type)
            return (origin_slot or 0, target_slot)

    for origin_index, output in enumerate(outputs):
        output_type = _slot_type(output)
        target_index = _slot_index_for_type(target, "inputs", output_type)
        if target_index is not None:
            return (origin_index, target_index)
    return (0, 0)


def _connect_plan(origin: dict, origin_slot: int, target: dict, target_slot: int) -> dict:
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
    return _connect_plan(origin, origin_slot, target, target_slot)


def _inferred_connect_plan_from_phrases(
    nodes: list[dict],
    origin_phrase: str,
    target_phrase: str,
) -> dict | None:
    origin = _find_node_for_phrase(nodes, origin_phrase)
    target = _find_node_for_phrase(nodes, target_phrase)
    if origin is None or target is None:
        return None
    slots = _infer_connect_slots(origin, target, origin_phrase, target_phrase)
    if slots is None:
        return None
    return _connect_plan(origin, slots[0], target, slots[1])


def _plan_graph_connect(text: str, context: dict) -> dict | None:
    lowered = text.lower()
    if not any(term in lowered or term in text for term in ("连接", "连到", "接到", "connect")):
        return None
    nodes = _graph_nodes(context)
    slot_patterns = (
        r"把\s*(.+?)\s*的\s*([A-Za-z0-9_ -]+)\s*(?:连接到|连到|接到)\s*(.+?)\s*的\s*([A-Za-z0-9_ -]+)$",
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

    inferred_patterns = (
        r"把\s*(.+?)\s*(?:连接到|连到|接到)\s*(.+)$",
        r"\bconnect\s+(.+?)\s+(?:to|into)\s+(.+)$",
    )
    for pattern in inferred_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if not match:
            continue
        plan = _inferred_connect_plan_from_phrases(nodes, match.group(1), match.group(2))
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


def _disconnect_input_plan(nodes: list[dict], target_phrase: str, slot_hint: str) -> dict | None:
    target = _select_node(nodes, target_phrase)
    if target is None:
        target = _find_node_for_phrase(nodes, target_phrase)
    if target is None:
        return None
    target_slot = _slot_index_for_hint(target, "inputs", slot_hint)
    if target_slot is None:
        return None
    return {
        "summary": f"Disconnect input {target_slot} on node {target.get('id')}",
        "actions": [
            {
                "type": "graph.disconnect",
                "payload": {
                    "target_node_id": target.get("id"),
                    "target_slot": target_slot,
                },
            }
        ],
    }


def _disconnect_output_plan(nodes: list[dict], origin_phrase: str, slot_hint: str) -> dict | None:
    origin = _find_node_for_phrase(nodes, origin_phrase)
    if origin is None:
        return None
    origin_slot = _slot_index_for_hint(origin, "outputs", slot_hint)
    if origin_slot is None:
        return None
    return {
        "summary": f"Disconnect output {origin_slot} on node {origin.get('id')}",
        "actions": [
            {
                "type": "graph.disconnect",
                "payload": {
                    "origin_node_id": origin.get("id"),
                    "origin_slot": origin_slot,
                },
            }
        ],
    }


def _disconnect_pair_plan(nodes: list[dict], origin_phrase: str, target_phrase: str) -> dict | None:
    origin = _find_node_for_phrase(nodes, origin_phrase)
    target = _find_node_for_phrase(nodes, target_phrase)
    if origin is None or target is None:
        return None
    return {
        "summary": f"Disconnect node {origin.get('id')} from node {target.get('id')}",
        "actions": [
            {
                "type": "graph.disconnect",
                "payload": {
                    "origin_node_id": origin.get("id"),
                    "target_node_id": target.get("id"),
                },
            }
        ],
    }


def _disconnect_all_plan(nodes: list[dict], node_phrase: str, scope: str) -> dict | None:
    node = _select_node(nodes, node_phrase)
    if node is None:
        node = _find_node_for_phrase(nodes, node_phrase)
    if node is None:
        return None
    payload_key = {
        "inputs": "target_node_id",
        "outputs": "origin_node_id",
        "all": "node_id",
    }[scope]
    return {
        "summary": f"Disconnect {scope} on node {node.get('id')}",
        "actions": [
            {
                "type": "graph.disconnect",
                "payload": {payload_key: node.get("id")},
            }
        ],
    }


def _plan_graph_disconnect(text: str, context: dict) -> dict | None:
    lowered = text.lower()
    if not any(term in lowered or term in text for term in ("断开", "清空", "移除连接", "disconnect")):
        return None
    nodes = _graph_nodes(context)
    all_patterns = (
        (r"(?:断开|清空|移除连接)\s*(.+?)\s*的\s*所有\s*(?:输入|inputs?)$", "inputs"),
        (r"\bdisconnect\s+all\s+inputs?\s+(?:on|from)\s+(.+?)$", "inputs"),
        (r"(?:断开|清空|移除连接)\s*(.+?)\s*的\s*所有\s*(?:输出|outputs?)$", "outputs"),
        (r"\bdisconnect\s+all\s+outputs?\s+(?:on|from)\s+(.+?)$", "outputs"),
        (r"(?:断开|清空|移除连接)\s*(.+?)\s*的\s*所有\s*(?:连接|links?|connections?)$", "all"),
        (r"\bdisconnect\s+all\s+(?:links?|connections?)\s+(?:on|from)\s+(.+?)$", "all"),
    )
    for pattern, scope in all_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if not match:
            continue
        plan = _disconnect_all_plan(nodes, match.group(1), scope)
        if plan is not None:
            return plan
    pair_patterns = (
        r"(?:断开|移除连接)\s*(.+?)\s*(?:到|和|与|->|to)\s*(.+?)\s*的?连接?$",
        r"\bdisconnect\s+(.+?)\s+(?:from|to)\s+(.+?)$",
    )
    for pattern in pair_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if not match:
            continue
        plan = _disconnect_pair_plan(nodes, match.group(1), match.group(2))
        if plan is not None:
            return plan
    output_patterns = (
        r"(?:断开|清空|移除连接)\s*(.+?)\s*的\s*([A-Za-z0-9_ -]+)\s*(?:输出|output)$",
        r"\bdisconnect\s+(.+?)\s+([A-Za-z0-9_ -]+)\s+output\b",
    )
    for pattern in output_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if not match:
            continue
        plan = _disconnect_output_plan(nodes, match.group(1), match.group(2))
        if plan is not None:
            return plan
    patterns = (
        r"(?:断开|清空|移除连接)\s*(.+?)\s*的\s*([A-Za-z0-9_ -]+)\s*(?:输入|input)?$",
        r"\bdisconnect\s+(.+?)\s+([A-Za-z0-9_ -]+)\s+input\b",
    )
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if not match:
            continue
        plan = _disconnect_input_plan(nodes, match.group(1), match.group(2))
        if plan is not None:
            return plan
    return None


def _extract_url(text: str) -> str | None:
    match = re.search(r"https?://[^\s，。]+", text)
    if match:
        return match.group(0).rstrip(".,，。")
    return None


CUSTOM_NODE_MARKERS = (
    "custom node",
    "custom nodes",
    "自定义节点",
    "节点管理器",
    "manager",
    "插件",
    "扩展",
)


def _extract_custom_node_id(text: str) -> str | None:
    match = re.search(
        r"(?:custom\s+nodes?|自定义节点|节点管理器|manager(?:\s+node)?|插件|扩展|节点)\s+([A-Za-z0-9_.:/-]+)",
        text,
        re.IGNORECASE,
    )
    if match:
        return match.group(1).rstrip(".,，。")
    return None


def _mentions_custom_node(text: str) -> bool:
    lowered = text.lower()
    return any(marker in lowered or marker in text for marker in CUSTOM_NODE_MARKERS)


def _plan_custom_node_manager_action(text: str) -> dict | None:
    if not _mentions_custom_node(text):
        return None
    lowered = text.lower()
    if any(term in lowered or term in text for term in ("全部", "所有", "all")) and any(
        term in lowered or term in text for term in ("update", "更新", "升级")
    ):
        return {
            "summary": "Update all custom nodes through ComfyUI-Manager",
            "actions": [{"type": "custom_node.update_all", "payload": {}}],
        }

    action_type = None
    if any(term in lowered or term in text for term in ("reinstall", "重装", "重新安装")):
        action_type = "custom_node.reinstall"
    elif any(term in lowered or term in text for term in ("fix", "修复", "repair")):
        action_type = "custom_node.fix"
    elif any(term in lowered or term in text for term in ("update", "更新", "升级")):
        action_type = "custom_node.update"

    if action_type is None:
        return None
    node_id = _extract_custom_node_id(text)
    if not node_id:
        return None
    verb = action_type.removeprefix("custom_node.")
    return {
        "summary": f"{verb.title()} custom node {node_id}",
        "actions": [{"type": action_type, "payload": {"id": node_id}}],
    }


def _restart_container_action() -> dict:
    return {"type": "service.restart_container", "payload": {"container": "comfyui-gb10"}}


def _container_lifecycle_action(action_type: str) -> dict:
    return {"type": action_type, "payload": {"container": "comfyui-gb10"}}


def _mentions_service_restart(text: str) -> bool:
    lowered = text.lower()
    return ("重启" in text or "restart" in lowered) and any(
        term in lowered or term in text for term in ("comfyui", "容器", "container", "服务")
    )


def _with_restart_followup(plan: dict, text: str) -> dict:
    if not _mentions_service_restart(text):
        return plan
    return {
        "summary": f"{plan['summary']} and restart ComfyUI",
        "actions": [*plan["actions"], _restart_container_action()],
    }


def _plan_container_lifecycle(text: str) -> dict | None:
    lowered = text.lower()
    if not any(term in lowered or term in text for term in ("comfyui", "容器", "container", "服务")):
        return None
    if "启动参数" in text or "command" in lowered or "flag" in lowered:
        return None
    if "重启" in text or "restart" in lowered:
        return {
            "summary": "Restart ComfyUI container",
            "actions": [_restart_container_action()],
        }
    if any(term in lowered or term in text for term in ("停止", "停掉", "关闭", "关掉", "stop")):
        return {
            "summary": "Stop ComfyUI container",
            "actions": [_container_lifecycle_action("service.stop_container")],
        }
    if any(term in lowered or term in text for term in ("启动", "开启", "打开", "start")):
        return {
            "summary": "Start ComfyUI container",
            "actions": [_container_lifecycle_action("service.start_container")],
        }
    return None


def _plan_custom_node_install_from_url(text: str) -> dict | None:
    lowered = text.lower()
    if not (_mentions_custom_node(text) and any(term in lowered or term in text for term in ("install", "安装"))):
        return None
    url = _extract_url(text)
    if not url:
        return None
    return {
        "summary": f"Install custom node from {url}",
        "actions": [
            {
                "type": "custom_node.install",
                "payload": {"method": "git_url", "url": url},
            }
        ],
    }


def _manager_queue_node_payload(node_id: str) -> dict:
    return {
        "id": node_id,
        "version": "unknown",
        "ui_id": node_id,
        "files": [node_id],
        "channel": "default",
        "mode": "cache",
    }


def _plan_custom_node_install_by_id(text: str) -> dict | None:
    lowered = text.lower()
    if not (_mentions_custom_node(text) and any(term in lowered or term in text for term in ("install", "安装"))):
        return None
    node_id = _extract_custom_node_id(text)
    if not node_id:
        return None
    return {
        "summary": f"Install custom node {node_id} through ComfyUI-Manager",
        "actions": [
            {
                "type": "custom_node.install",
                "payload": {"method": "manager_queue", "node": _manager_queue_node_payload(node_id)},
            }
        ],
    }


def _plan_custom_node_state_action(text: str) -> dict | None:
    lowered = text.lower()
    if not (_mentions_custom_node(text) or "节点" in text):
        return None
    action_type = None
    if any(term in lowered or term in text for term in ("disable", "禁用")):
        action_type = "custom_node.disable"
    elif any(term in lowered or term in text for term in ("enable", "启用")):
        action_type = "custom_node.enable"
    if action_type is None:
        return None
    node_id = _extract_custom_node_id(text)
    if not node_id:
        return None
    verb = action_type.removeprefix("custom_node.")
    return {
        "summary": f"{verb.title()} custom node {node_id}",
        "actions": [{"type": action_type, "payload": {"id": node_id}}],
    }


def _plan_custom_node_action(text: str) -> dict | None:
    for planner in (
        _plan_custom_node_manager_action,
        _plan_custom_node_install_from_url,
        _plan_custom_node_install_by_id,
        _plan_custom_node_state_action,
    ):
        plan = planner(text)
        if plan is not None:
            return _with_restart_followup(plan, text)
    return None


def _extract_ollama_model(text: str) -> str | None:
    match = re.search(r"(?:模型|model)\s+([A-Za-z0-9_.:/-]+)", text, re.IGNORECASE)
    if match:
        return match.group(1).rstrip(".,，。")
    match = re.search(r"ollama\s+(?:stop\s+)?([A-Za-z0-9_.:/-]+)", text, re.IGNORECASE)
    if match and match.group(1).lower() not in {"模型", "model"}:
        return match.group(1).rstrip(".,，。")
    return None


def _plan_compose_up(text: str) -> dict | None:
    lowered = text.lower()
    if "compose" not in lowered:
        return None
    if not any(term in lowered or term in text for term in ("up -d", "apply", "应用", "生效", "重读", "重建")):
        return None
    return {
        "summary": "Apply docker compose configuration",
        "actions": [{"type": "service.compose_up", "payload": {}}],
    }


def _extract_command_flag(text: str) -> str | None:
    match = re.search(r"--[A-Za-z0-9][A-Za-z0-9-]*", text)
    return match.group(0) if match else None


def _plan_compose_command_flag(text: str) -> dict | None:
    flag = _extract_command_flag(text)
    if not flag:
        return None
    lowered = text.lower()
    if not any(
        term in lowered or term in text
        for term in ("compose", "comfyui", "command", "flag", "启动参数", "参数")
    ):
        return None
    enabled = None
    if any(term in lowered or term in text for term in ("启用", "开启", "打开", "添加", "加上", "enable", "add")):
        enabled = True
    if any(
        term in lowered or term in text
        for term in ("禁用", "关闭", "移除", "删除", "去掉", "disable", "remove", "delete")
    ):
        enabled = False
    if enabled is None:
        return None
    verb = "Enable" if enabled else "Disable"
    return {
        "summary": f"{verb} compose command flag {flag}",
        "actions": [
            {"type": "compose.set_command_flag", "payload": {"flag": flag, "enabled": enabled}}
        ],
    }


QUEUE_PROMPT_TERMS = (
    "开始生成",
    "插队生成",
    "提交当前工作流",
    "运行当前工作流",
    "执行当前工作流",
    "跑当前工作流",
    "run workflow",
    "queue prompt",
    "queue workflow",
)


WORKFLOW_SAVE_PATTERNS = (
    r"(?:保存|存为|另存为)(?:当前|这个)?(?:工作流|workflow)?(?:到|为|成|至)\s*(?P<path>[^，。；;\s]+)",
    r"(?:当前|这个)?(?:工作流|workflow)(?:保存|存为|另存为)(?:到|为|成|至)\s*(?P<path>[^，。；;\s]+)",
    r"\bsave(?:\s+(?:current|this))?(?:\s+workflow)?\s+(?:to|as)\s+(?P<path>\S+)",
)


def _mentions_runtime_queue_prompt(text: str) -> bool:
    lowered = text.lower()
    return any(term in lowered or term in text for term in QUEUE_PROMPT_TERMS)


def _connector_stripped_prefix(text: str, start: int) -> str:
    prefix = text[:start].rstrip()
    for connector in ("and then", "然后", "之后", "接着", "then", "and", "并", "再"):
        if prefix.lower().endswith(connector):
            return text[: len(prefix) - len(connector)]
    return prefix


def _strip_queue_prompt_clause(text: str) -> str:
    lowered = text.lower()
    starts = [
        lowered.find(term.lower())
        for term in QUEUE_PROMPT_TERMS
        if lowered.find(term.lower()) >= 0
    ]
    if not starts:
        return text
    start = min(starts)
    if start > 0:
        prefix = _connector_stripped_prefix(text, start)
        if prefix == text[:start].rstrip():
            return text
        return _strip_value(prefix)
    return _strip_value(text[:start])


def _workflow_save_match(text: str) -> re.Match | None:
    matches = []
    for pattern in WORKFLOW_SAVE_PATTERNS:
        matches.extend(re.finditer(pattern, text, re.IGNORECASE))
    if not matches:
        return None
    return min(matches, key=lambda match: match.start())


def _strip_workflow_save_clause(text: str) -> str:
    match = _workflow_save_match(text)
    if match is None:
        return text
    if match.start() > 0:
        return _strip_value(_connector_stripped_prefix(text, match.start()))
    return _strip_value(text[: match.start()])


def _plan_workflow_save(text: str) -> dict | None:
    match = _workflow_save_match(text)
    if match is None:
        return None
    path = _strip_value(match.group("path"))
    if not path:
        return None
    return {
        "summary": f"Save current ComfyUI workflow to {path}",
        "actions": [
            {
                "type": "workflow.save",
                "payload": {"path": path, "workflow_from_browser": True},
            }
        ],
    }


def _combine_with_followup_plans(
    plan: dict,
    followup_plans: list[dict],
    graph_text: str,
    text: str,
) -> dict:
    if not followup_plans or graph_text == text:
        return plan
    return {
        "summary": f"{plan['summary']} then apply follow-up action(s)",
        "actions": [
            *plan["actions"],
            *(action for item in followup_plans for action in item["actions"]),
        ],
    }


def _combine_prerender_with_queue(
    prerender_plan: dict | None,
    queue_plan: dict | None,
) -> dict | None:
    if prerender_plan is None or queue_plan is None:
        return None
    return {
        "summary": "Prepare memory then queue current workflow",
        "actions": [*prerender_plan["actions"], *queue_plan["actions"]],
    }


def _plan_runtime_queue_prompt(text: str) -> dict | None:
    lowered = text.lower()
    if not _mentions_runtime_queue_prompt(text):
        return None
    front = any(term in lowered or term in text for term in ("插队", "队首", "front"))
    return {
        "summary": "Queue current ComfyUI workflow",
        "actions": [{"type": "runtime.queue_prompt", "payload": {"front": front}}],
    }


def _plan_runtime_interrupt(text: str) -> dict | None:
    lowered = text.lower()
    if any(
        term in lowered or term in text
        for term in (
            "停止当前生成",
            "停止生成",
            "中断当前生成",
            "中断生成",
            "停掉当前生成",
            "终止当前生成",
            "interrupt generation",
            "stop generation",
            "cancel generation",
            "interrupt current",
        )
    ):
        return {
            "summary": "Interrupt current ComfyUI generation",
            "actions": [{"type": "runtime.interrupt", "payload": {}}],
        }
    return None


def _plan_runtime_clear_queue(text: str) -> dict | None:
    lowered = text.lower()
    if any(
        term in lowered or term in text
        for term in (
            "清空待执行队列",
            "清空队列",
            "清除队列",
            "取消排队任务",
            "清掉排队任务",
            "clear queue",
            "clear pending",
            "cancel queued",
        )
    ):
        return {
            "summary": "Clear pending ComfyUI queue",
            "actions": [{"type": "runtime.clear_queue", "payload": {}}],
        }
    return None


def _plan_prerender_free_memory(text: str) -> dict | None:
    lowered = text.lower()
    mentions_prerender = any(
        term in lowered or term in text
        for term in ("渲染前", "开渲前", "出图前", "pre-render", "prerender")
    )
    mentions_memory = any(term in lowered or term in text for term in ("内存", "memory", "free"))
    if not (mentions_prerender and mentions_memory):
        return None
    return {
        "summary": "Run prerender free-memory preparation",
        "actions": [{"type": "service.prerender_free_memory", "payload": {}}],
    }


def _plan_service_healthcheck(text: str) -> dict | None:
    lowered = text.lower()
    mentions_service = any(
        term in lowered or term in text for term in ("comfyui", "容器", "container", "服务")
    )
    mentions_health = any(
        term in lowered or term in text
        for term in ("健康", "状态", "检查", "health", "status", "8188")
    )
    mentions_memory = any(term in lowered or term in text for term in ("内存", "memory", "available"))
    if mentions_service and (mentions_health or mentions_memory):
        return {
            "summary": "Check ComfyUI container health",
            "actions": [{"type": "service.healthcheck", "payload": {}}],
        }
    return None


class RuleBasedPlanner:
    def plan(self, message: str, context: dict) -> dict:
        text = message.strip() if isinstance(message, str) else ""
        lowered = text.lower()
        queue_prompt_plan = _plan_runtime_queue_prompt(text)
        workflow_save_plan = _plan_workflow_save(text)
        followup_plans = [
            plan for plan in (workflow_save_plan, queue_prompt_plan) if plan is not None
        ]
        graph_text = text
        if workflow_save_plan is not None:
            graph_text = _strip_workflow_save_clause(graph_text)
        if queue_prompt_plan is not None:
            graph_text = _strip_queue_prompt_clause(graph_text)
        graph_delete_plan = _plan_graph_delete_node(graph_text, context)
        if graph_delete_plan is not None:
            return _combine_with_followup_plans(graph_delete_plan, followup_plans, graph_text, text)
        graph_copy_widget_plan = _plan_graph_copy_widget_value(graph_text, context)
        if graph_copy_widget_plan is not None:
            return _combine_with_followup_plans(
                graph_copy_widget_plan, followup_plans, graph_text, text
            )
        graph_duplicate_plan = _plan_graph_duplicate_node(graph_text, context)
        if graph_duplicate_plan is not None:
            return _combine_with_followup_plans(
                graph_duplicate_plan, followup_plans, graph_text, text
            )
        graph_color_plan = _plan_graph_set_color(graph_text, context)
        if graph_color_plan is not None:
            return _combine_with_followup_plans(graph_color_plan, followup_plans, graph_text, text)
        graph_mode_plan = _plan_graph_set_mode(graph_text, context)
        if graph_mode_plan is not None:
            return _combine_with_followup_plans(graph_mode_plan, followup_plans, graph_text, text)
        graph_title_plan = _plan_graph_set_title(graph_text, context)
        if graph_title_plan is not None:
            return _combine_with_followup_plans(graph_title_plan, followup_plans, graph_text, text)
        graph_align_plan = _plan_graph_align_nodes(graph_text, context)
        if graph_align_plan is not None:
            return _combine_with_followup_plans(graph_align_plan, followup_plans, graph_text, text)
        graph_distribute_plan = _plan_graph_distribute_nodes(graph_text, context)
        if graph_distribute_plan is not None:
            return _combine_with_followup_plans(
                graph_distribute_plan, followup_plans, graph_text, text
            )
        graph_position_plan = _plan_graph_set_position(graph_text, context)
        if graph_position_plan is not None:
            return _combine_with_followup_plans(
                graph_position_plan, followup_plans, graph_text, text
            )
        graph_select_plan = _plan_graph_select_node(graph_text, context)
        if graph_select_plan is not None:
            return _combine_with_followup_plans(graph_select_plan, followup_plans, graph_text, text)
        graph_disconnect_plan = _plan_graph_disconnect(graph_text, context)
        if graph_disconnect_plan is not None:
            return _combine_with_followup_plans(
                graph_disconnect_plan, followup_plans, graph_text, text
            )
        graph_connect_plan = _plan_graph_connect(graph_text, context)
        if graph_connect_plan is not None:
            return _combine_with_followup_plans(graph_connect_plan, followup_plans, graph_text, text)
        graph_add_plan = _plan_graph_add_node(graph_text)
        if graph_add_plan is not None:
            return _combine_with_followup_plans(graph_add_plan, followup_plans, graph_text, text)
        graph_plan = _plan_graph_widget_edit(graph_text, context)
        if graph_plan is not None:
            return _combine_with_followup_plans(graph_plan, followup_plans, graph_text, text)
        prerender_queue_plan = _combine_prerender_with_queue(
            _plan_prerender_free_memory(text),
            queue_prompt_plan,
        )
        if prerender_queue_plan is not None:
            return prerender_queue_plan
        if workflow_save_plan is not None and queue_prompt_plan is not None:
            return {
                "summary": "Save current workflow then queue current workflow",
                "actions": [*workflow_save_plan["actions"], *queue_prompt_plan["actions"]],
            }
        if workflow_save_plan is not None:
            return workflow_save_plan
        if queue_prompt_plan is not None:
            return queue_prompt_plan
        clear_queue_plan = _plan_runtime_clear_queue(text)
        if clear_queue_plan is not None:
            return clear_queue_plan
        interrupt_plan = _plan_runtime_interrupt(text)
        if interrupt_plan is not None:
            return interrupt_plan
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
        if "锁频" in text or "lgc" in lowered or (
            "nvidia-smi" in lowered and any(term in lowered or term in text for term in ("lock", "锁"))
        ):
            return {
                "summary": "Print sudo GPU clock lock command for Srain",
                "actions": [
                    {
                        "type": "sudo.print_command",
                        "payload": {
                            "command": "sudo nvidia-smi -lgc 300,2100",
                            "why": "Lock GPU clock to reduce current spikes on GB10",
                        },
                    }
                ],
            }
        if "ollama" in lowered and any(term in lowered or term in text for term in ("服务", "systemctl", "彻底")) and any(
            term in lowered or term in text for term in ("stop", "停止", "停")
        ):
            return {
                "summary": "Print sudo Ollama service stop command for Srain",
                "actions": [
                    {
                        "type": "sudo.print_command",
                        "payload": {
                            "command": "sudo systemctl stop ollama",
                            "why": "Stop the Ollama service to fully release unified memory before heavy ComfyUI work",
                        },
                    }
                ],
            }
        custom_node_plan = _plan_custom_node_action(text)
        if custom_node_plan is not None:
            return custom_node_plan
        container_lifecycle_plan = _plan_container_lifecycle(text)
        if container_lifecycle_plan is not None:
            return container_lifecycle_plan
        if "ollama" in lowered and any(term in lowered or term in text for term in ("stop", "停止", "驱逐")):
            model = _extract_ollama_model(text)
            if model:
                return {
                    "summary": f"Stop Ollama model {model}",
                    "actions": [{"type": "runtime.stop_ollama_model", "payload": {"model": model}}],
                }
        if _mentions_custom_node(text) and any(
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
        if (_mentions_custom_node(text) or "节点" in text) and any(
            term in lowered or term in text for term in ("disable", "禁用")
        ):
            node_id = _extract_custom_node_id(text)
            if node_id:
                return {
                    "summary": f"Disable custom node {node_id}",
                    "actions": [{"type": "custom_node.disable", "payload": {"id": node_id}}],
                }
        if (_mentions_custom_node(text) or "节点" in text) and any(
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
        compose_flag_plan = _plan_compose_command_flag(text)
        if compose_flag_plan is not None:
            return compose_flag_plan
        compose_up_plan = _plan_compose_up(text)
        if compose_up_plan is not None:
            return compose_up_plan
        prerender_free_memory_plan = _plan_prerender_free_memory(text)
        if prerender_free_memory_plan is not None:
            return prerender_free_memory_plan
        service_healthcheck_plan = _plan_service_healthcheck(text)
        if service_healthcheck_plan is not None:
            return service_healthcheck_plan
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
