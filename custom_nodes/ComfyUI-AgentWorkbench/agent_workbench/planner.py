import os
import re
from urllib.parse import unquote, urlparse


MAX_PLANNER_GRAPH_NODES = 500
MAX_PLANNER_GRAPH_LINKS = 1000
MAX_PLANNER_WIDGETS_PER_NODE = 64
MAX_PLANNER_SLOTS_PER_NODE = 64
MAX_PLANNER_NODE_TYPES = 1000
MAX_PLANNER_NODE_TYPE_INPUTS = 128
RELATIVE_NODE_X_GAP = 220
RELATIVE_NODE_Y_GAP = 180


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
    "更新成",
    "更新为",
    "更新到",
    "设置为",
    "设置成",
    "设为",
    "设成",
    "调整到",
    "调整为",
    "提高到",
    "提高为",
    "提高成",
    "调高到",
    "调高为",
    "调高成",
    "增加到",
    "增加为",
    "增加成",
    "降低到",
    "降低为",
    "降低成",
    "降到",
    "降为",
    "降成",
    "调低到",
    "调低为",
    "调低成",
    "减少到",
    "减少为",
    "减少成",
    "调到",
    "调成",
    "调为",
    "变成",
    "写成",
    "写为",
    "描述成",
    "描述为",
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
WIDGET_ASSIGNMENT_OPERATORS = (*VALUE_SET_DELIMITERS, "=", ":", "：", "是")


def _extract_value_after_set(text: str) -> str | None:
    for delimiter in VALUE_SET_DELIMITERS:
        if delimiter in text:
            return _strip_value(text.rsplit(delimiter, 1)[1])
    match = re.search(
        r"\b(?:set|change|update|write|replace|fill|resize)\b.+?\b(?:to|as|with)\b\s*(.+)$",
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


def _looks_like_question_assignment(text: str, value: str) -> bool:
    value = _strip_value(value)
    if not value:
        return True
    if any(term in value for term in ("什么", "哪个", "哪一个", "哪些", "多少", "吗", "？")):
        return True
    if "?" in value or "?" in text or "？" in text:
        return True
    if any(term in text for term in ("推荐", "能用", "可以用", "可用")):
        return True
    if "最好" in text and any(term in text for term in ("什么", "哪个", "哪一个", "哪些", "推荐")):
        return True
    lowered = text.lower()
    value_lowered = value.lower()
    if any(term in value_lowered for term in ("what", "which", "recommend")):
        return True
    if any(term in lowered for term in ("what model", "which model", "recommend", "can use")):
        return True
    return False


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
            try:
                return float(value)
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


def _graph_links(context: dict) -> list[dict]:
    graph = context.get("graph_input") if isinstance(context, dict) else None
    if not isinstance(graph, dict):
        return []
    links = graph.get("links")
    if not isinstance(links, list):
        return []
    return [link for link in links[:MAX_PLANNER_GRAPH_LINKS] if isinstance(link, dict)]


def _graph_node_types(context: dict) -> list[dict]:
    graph = context.get("graph_input") if isinstance(context, dict) else None
    if not isinstance(graph, dict):
        return []
    node_types = graph.get("node_types")
    if not isinstance(node_types, list):
        return []
    rows = []
    for row in node_types[:MAX_PLANNER_NODE_TYPES]:
        if not isinstance(row, dict) or not isinstance(row.get("type"), str):
            continue
        rows.append(row)
    return rows


def _graph_registered_node_type_names(context: dict) -> set[str]:
    return {row["type"] for row in _graph_node_types(context)}


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


CHINESE_ORDINAL_INDEXES = {
    "一": 0,
    "二": 1,
    "两": 1,
    "三": 2,
    "四": 3,
    "五": 4,
    "六": 5,
    "七": 6,
    "八": 7,
    "九": 8,
    "十": 9,
}

ENGLISH_ORDINAL_INDEXES = {
    "first": 0,
    "1st": 0,
    "second": 1,
    "2nd": 1,
    "third": 2,
    "3rd": 2,
    "fourth": 3,
    "4th": 3,
    "fifth": 4,
    "5th": 4,
    "sixth": 5,
    "6th": 5,
    "seventh": 6,
    "7th": 6,
    "eighth": 7,
    "8th": 7,
    "ninth": 8,
    "9th": 8,
    "tenth": 9,
    "10th": 9,
}


def _extract_ordinal_index(text: str) -> int | None:
    match = re.search(r"第\s*(?P<ordinal>\d+|[一二两三四五六七八九十])\s*(?:个|個)", text)
    if match:
        ordinal = match.group("ordinal")
        if ordinal.isdigit():
            index = int(ordinal) - 1
            return index if index >= 0 else None
        return CHINESE_ORDINAL_INDEXES.get(ordinal)
    match = re.search(
        r"\b(?P<ordinal>first|1st|second|2nd|third|3rd|fourth|4th|fifth|5th|"
        r"sixth|6th|seventh|7th|eighth|8th|ninth|9th|tenth|10th)\b",
        text,
        re.IGNORECASE,
    )
    if match is None:
        return None
    return ENGLISH_ORDINAL_INDEXES.get(match.group("ordinal").lower())


def _find_node_by_id(nodes: list[dict], node_id: str | None) -> dict | None:
    if node_id is None:
        return None
    for node in nodes:
        if str(node.get("id")) == node_id:
            return node
    return None


def _find_node_by_ordinal(
    nodes: list[dict],
    text: str,
    links: list[dict] | None = None,
) -> dict | None:
    index = _extract_ordinal_index(text)
    if index is None:
        return None
    matches = _find_nodes_by_semantic_label(nodes, text, links)
    if not matches:
        matches = _find_nodes_by_label(nodes, text)
    if not matches and ("节点" in text or "node" in text.lower()):
        matches = nodes
    if index >= len(matches):
        return None
    return matches[index]


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
        (
            "负面提示词",
            "反向提示词",
            "负向提示词",
            "负面 prompt",
            "负面prompt",
            "反向 prompt",
            "反向prompt",
            "负向 prompt",
            "负向prompt",
            "negative prompt",
            "negative",
        ),
        ("negative prompt", "negative"),
    ),
    (
        ("checkpoint", "ckpt", "底模", "大模型"),
        ("checkpointloader", "checkpointloadersimple", "load checkpoint", "checkpoint"),
    ),
    (
        ("vae 解码", "vae解码", "vae decode", "decode vae", "latent 转图像", "latent to image"),
        ("vaedecode", "vae decode", "decode"),
    ),
    (
        ("vae 编码", "vae编码", "vae encode", "encode vae", "图像转 latent", "image to latent"),
        ("vaeencode", "vae encode", "encode"),
    ),
    (
        ("vae",),
        ("vaeloader", "load vae", "vae loader"),
    ),
    (
        ("加载图片", "导入图片", "输入图片", "输入图像", "参考图", "参考图片", "load image", "image input"),
        ("loadimage", "load image"),
    ),
    (
        ("图像缩放", "图片缩放", "缩放节点", "image scale", "image resize", "resize image"),
        ("imagescale", "image scale", "image resize", "resize image"),
    ),
    (
        ("超分模型", "放大模型", "upscale model", "upscaler model"),
        ("upscalemodelloader", "upscale model", "load upscale model"),
    ),
    (
        ("lora", "lora 模型", "lora模型"),
        ("loraloader", "load lora", "lora loader", "lora"),
    ),
    (
        ("保存图片", "保存图像", "save image", "saveimage"),
        ("saveimage", "save image"),
    ),
    (
        ("采样器", "采样节点", "调度器", "sampler", "scheduler"),
        ("ksampler", "sampler"),
    ),
    (
        ("clip skip", "clip layer", "clip 层", "clip跳层"),
        ("clipsetlastlayer", "clip set last layer"),
    ),
    (
        ("controlnet 模型加载器", "controlnet loader", "load controlnet model", "控制网模型加载器"),
        ("controlnetloader", "load controlnet model", "controlnet loader"),
    ),
    (
        ("controlnet", "control net", "控制网", "控制网络"),
        ("controlnet", "control net"),
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


def _prompt_role_from_text(text: str) -> str | None:
    lowered = text.lower()
    if any(term in lowered or term in text for term in ("正向", "正面", "positive")):
        return "positive"
    if any(term in lowered or term in text for term in ("负面", "反向", "负向", "negative")):
        return "negative"
    return None


PROMPT_ROLE_ASSIGNMENT_TERMS = (
    (
        "positive",
        "正向提示词",
        ("正向提示词", "正面提示词", "正向 prompt", "正向prompt", "positive prompt"),
    ),
    (
        "negative",
        "负面提示词",
        ("负面提示词", "反向提示词", "负向提示词", "负面 prompt", "负面prompt", "negative prompt"),
    ),
)


def _prompt_role_assignment_matches(text: str) -> list[tuple[str, str, str]]:
    role_lookup = {}
    role_terms = []
    for role, canonical_phrase, terms in PROMPT_ROLE_ASSIGNMENT_TERMS:
        for term in terms:
            role_lookup[term.lower()] = (role, canonical_phrase)
            role_terms.append(term)

    role_pattern = "|".join(re.escape(term) for term in sorted(role_terms, key=len, reverse=True))
    operator_pattern = "|".join(
        re.escape(operator)
        for operator in sorted((*WIDGET_ASSIGNMENT_OPERATORS, "to", "as", "with"), key=len, reverse=True)
    )
    prefix_pattern = (
        r"(?:然后把|然后将|接着把|接着将|并且把|并且将|并把|并将|再把|再将|把|将|给|and\s+)?"
    )
    pattern = re.compile(
        rf"(?:^|[\s,，;；。]+)?{prefix_pattern}\s*"
        rf"(?P<role>{role_pattern})\s*(?:的)?\s*(?:文本|内容|prompt|text)?\s*"
        rf"(?:{operator_pattern})\s*",
        re.IGNORECASE,
    )
    matches = list(pattern.finditer(text))
    if len(matches) < 2:
        return []

    rows = []
    seen_roles = set()
    for index, match in enumerate(matches):
        role, canonical_phrase = role_lookup[match.group("role").lower()]
        if role in seen_roles:
            return []
        value_end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        value = _strip_value(text[match.end():value_end])
        if not value:
            return []
        seen_roles.add(role)
        rows.append((role, canonical_phrase, value))
    return rows


def _nodes_by_id(nodes: list[dict]) -> dict[str, dict]:
    return {str(node.get("id")): node for node in nodes if node.get("id") is not None}


def _link_slot_index(link: dict, key: str) -> int | None:
    value = link.get(key)
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.isdigit():
        return int(value)
    return None


def _input_slot_role(node: dict, slot_index: int | None) -> str | None:
    if slot_index is None:
        return None
    slots = node.get("inputs")
    if not isinstance(slots, list) or slot_index < 0 or slot_index >= len(slots):
        return None
    slot = slots[slot_index]
    if not isinstance(slot, dict):
        return None
    name = slot.get("name")
    if not isinstance(name, str):
        return None
    lowered = name.lower()
    if "positive" in lowered or "正向" in name or "正面" in name:
        return "positive"
    if "negative" in lowered or "负面" in name or "反向" in name or "负向" in name:
        return "negative"
    return None


def _prompt_nodes_by_connection_role(
    nodes: list[dict],
    links: list[dict],
    role: str,
) -> list[dict]:
    by_id = _nodes_by_id(nodes)
    rows = []
    seen = set()
    for link in links:
        target = by_id.get(str(link.get("target_id")))
        origin = by_id.get(str(link.get("origin_id")))
        if target is None or origin is None:
            continue
        if _input_slot_role(target, _link_slot_index(link, "target_slot")) != role:
            continue
        if not _node_looks_like_prompt_text_node(origin):
            continue
        origin_id = origin.get("id")
        if origin_id in seen:
            continue
        seen.add(origin_id)
        rows.append(origin)
    return rows


def _generic_prompt_text_nodes(nodes: list[dict], text: str) -> list[dict]:
    if not _message_mentions_generic_prompt(text):
        return []
    return [node for node in nodes if _node_looks_like_prompt_text_node(node)]


def _find_node_by_semantic_label(
    nodes: list[dict],
    text: str,
    links: list[dict] | None = None,
) -> dict | None:
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
    role = _prompt_role_from_text(text)
    if role is not None:
        linked_prompt_nodes = _prompt_nodes_by_connection_role(nodes, links or [], role)
        if len(linked_prompt_nodes) == 1:
            return linked_prompt_nodes[0]
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


def _select_node(nodes: list[dict], text: str, links: list[dict] | None = None) -> dict | None:
    explicit = _find_node_by_id(nodes, _extract_node_id(text))
    if explicit is not None:
        return explicit

    ordinal = _find_node_by_ordinal(nodes, text, links)
    if ordinal is not None:
        return ordinal

    selected = _selected_nodes(nodes)
    if _message_mentions_current_node(text) and len(selected) == 1:
        return selected[0]

    semantic = _find_node_by_semantic_label(nodes, text, links)
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


def _select_node_preferring_label(
    nodes: list[dict],
    text: str,
    links: list[dict] | None = None,
) -> dict | None:
    explicit = _find_node_by_id(nodes, _extract_node_id(text))
    if explicit is not None:
        return explicit

    ordinal = _find_node_by_ordinal(nodes, text, links)
    if ordinal is not None:
        return ordinal

    selected = _selected_nodes(nodes)
    if _message_mentions_current_node(text) and len(selected) == 1:
        return selected[0]

    labelled = _find_node_by_label(nodes, text)
    if labelled is not None:
        return labelled

    semantic = _find_node_by_semantic_label(nodes, text, links)
    if semantic is not None:
        return semantic

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


def _find_nodes_by_semantic_label(
    nodes: list[dict],
    text: str,
    links: list[dict] | None = None,
) -> list[dict]:
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
    role = _prompt_role_from_text(text)
    if role is not None:
        linked_prompt_nodes = _prompt_nodes_by_connection_role(nodes, links or [], role)
        if linked_prompt_nodes:
            return linked_prompt_nodes
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


def _select_all_matching_nodes(
    nodes: list[dict],
    text: str,
    links: list[dict] | None = None,
) -> list[dict]:
    if not _message_mentions_all_nodes(text):
        return []
    semantic = _find_nodes_by_semantic_label(nodes, text, links)
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


def _select_bulk_nodes(
    nodes: list[dict],
    text: str,
    links: list[dict] | None = None,
) -> list[dict]:
    selected = _select_selected_matching_nodes(nodes, text)
    if selected:
        return selected
    return _select_all_matching_nodes(nodes, text, links)


WIDGET_ALIASES = (
    (("negative", "负面", "反向"), ("negative", "negative_prompt", "neg_prompt", "text")),
    (("positive", "正向"), ("positive", "positive_prompt", "pos_prompt", "text")),
    (("prompt", "提示词", "文本", "内容", "text"), ("text", "prompt", "prompt_text", "positive")),
    (
        (
            "filename prefix",
            "file name prefix",
            "文件名前缀",
            "输出文件名前缀",
            "保存文件名前缀",
            "保存前缀",
            "输出前缀",
        ),
        ("filename_prefix", "filename", "file_prefix", "output_prefix"),
    ),
    (
        ("quality", "image quality", "jpeg quality", "webp quality", "质量", "图片质量", "输出质量", "压缩质量"),
        ("quality", "image_quality", "jpeg_quality", "webp_quality"),
    ),
    (
        ("format", "file format", "image format", "video format", "格式", "保存格式", "输出格式", "图片格式", "视频格式"),
        ("format", "image_format", "video_format", "file_format"),
    ),
    (
        ("image", "input image", "source image", "reference image", "图片", "图像", "输入图", "输入图片", "参考图", "参考图片"),
        ("image", "image_path", "input_image", "reference_image"),
    ),
    (
        ("upscale method", "upscale_method", "scale method", "resize method", "缩放算法", "放大算法", "插值算法"),
        ("upscale_method", "method", "resize_method", "interpolation"),
    ),
    (
        ("crop", "crop mode", "裁剪", "裁剪模式"),
        ("crop", "crop_mode"),
    ),
    (
        ("超分模型", "放大模型", "upscale model", "upscaler model"),
        ("model_name", "upscale_model_name", "model"),
    ),
    (
        ("controlnet 模型", "control net model", "controlnet model", "控制网模型", "控制网络模型"),
        ("control_net_name", "controlnet_name", "model_name"),
    ),
    (("模型权重", "model strength", "strength model", "strength_model"), ("strength_model",)),
    (("clip skip", "clip layer", "clip 层", "clip跳层"), ("stop_at_clip_layer",)),
    (("clip 权重", "clip强度", "clip strength", "strength_clip"), ("strength_clip",)),
    (("lora 权重", "lora强度", "权重", "强度", "strength"), ("strength_model", "strength", "weight")),
    (("lora模型", "lora 模型", "lora model", "lora"), ("lora_name", "lora", "lora_model_name")),
    (("checkpoint", "ckpt", "大模型", "底模", "模型", "model"), ("ckpt_name", "checkpoint", "model_name", "unet_name")),
    (("vae",), ("vae_name", "vae")),
    (
        ("ipadapter 模型", "ipadapter model", "ipadapter", "ip adapter"),
        ("ipadapter_file", "ipadapter_name", "ipadapter", "model_name"),
    ),
    (("seed", "种子"), ("seed", "noise_seed")),
    (("steps", "步数"), ("steps",)),
    (
        ("cfg", "guidance", "guidance scale", "引导系数", "引导强度", "提示词相关度", "提示词引导"),
        ("cfg", "cfg_scale", "guidance_scale"),
    ),
    (
        ("sampler", "sampler method", "sampling method", "sampling algorithm", "采样器", "采样方法", "采样算法", "采样方式"),
        ("sampler_name", "sampler"),
    ),
    (
        ("scheduler", "scheduler method", "schedule method", "调度器", "调度方式", "调度方法", "调度策略"),
        ("scheduler",),
    ),
    (("denoise", "重绘幅度", "降噪", "去噪"), ("denoise",)),
    (
        (
            "start percent",
            "start_percent",
            "start time",
            "start_at",
            "开始百分比",
            "开始",
            "起始百分比",
            "起始",
            "开始比例",
            "起始比例",
            "开始时间",
            "起始时间",
        ),
        ("start_percent", "start", "start_at"),
    ),
    (
        (
            "end percent",
            "end_percent",
            "end time",
            "end_at",
            "结束百分比",
            "结束",
            "终止百分比",
            "终止",
            "结束比例",
            "终止比例",
            "结束时间",
            "终止时间",
        ),
        ("end_percent", "end", "end_at"),
    ),
    (("batch", "batch size", "批量", "批次"), ("batch_size", "batch")),
    (("fps", "frame rate", "帧率", "视频帧率"), ("frame_rate", "fps")),
    (
        ("loop count", "loop_count", "loops", "repeat count", "循环次数", "循环数", "重复次数", "重复播放次数"),
        ("loop_count", "loops"),
    ),
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


def _widget_accepts_implicit_number(widget: dict) -> bool:
    value = widget.get("value")
    if isinstance(value, bool):
        return False
    if isinstance(value, (int, float)):
        return True
    return widget.get("name", "").lower() in {
        "batch",
        "batch_size",
        "cfg",
        "cfg_scale",
        "denoise",
        "end",
        "end_at",
        "end_percent",
        "fps",
        "frame_rate",
        "frames",
        "guidance_scale",
        "height",
        "length",
        "loop_count",
        "loops",
        "noise_seed",
        "num_frames",
        "quality",
        "seed",
        "start",
        "start_at",
        "start_percent",
        "steps",
        "strength",
        "strength_clip",
        "strength_model",
        "weight",
        "width",
    }


def _widget_accepts_implicit_string(widget: dict) -> bool:
    value = widget.get("value")
    if isinstance(value, bool) or isinstance(value, (int, float)):
        return False
    return widget.get("name", "").lower() in {
        "checkpoint",
        "ckpt_name",
        "control_net_name",
        "controlnet_name",
        "crop",
        "crop_mode",
        "file_format",
        "file_prefix",
        "filename",
        "filename_prefix",
        "format",
        "image",
        "image_format",
        "image_path",
        "input_image",
        "interpolation",
        "ipadapter",
        "ipadapter_file",
        "ipadapter_name",
        "lora",
        "lora_model_name",
        "lora_name",
        "method",
        "model",
        "model_name",
        "output_prefix",
        "reference_image",
        "resize_method",
        "sampler",
        "sampler_name",
        "scheduler",
        "unet_name",
        "upscale_method",
        "upscale_model_name",
        "vae",
        "vae_name",
        "video_format",
    }


def _looks_like_explicit_assignment_fragment(value: str) -> bool:
    return any(operator in value for operator in VALUE_SET_DELIMITERS)


def _node_mentions_widget_hint(node: dict, text: str) -> bool:
    lowered = text.lower()
    for hint in _widget_hint_map(node):
        if hint in {"text", "文本", "内容"}:
            continue
        if hint in lowered or hint in text:
            return True
    return False


def _nodes_matching_widget_hint(nodes: list[dict], text: str) -> list[dict]:
    return [node for node in nodes if _node_mentions_widget_hint(node, text)]


def _select_mentioned_widget(node: dict, text: str) -> dict | None:
    lowered = text.lower()
    hints = _widget_hint_map(node)
    for hint in sorted(hints, key=len, reverse=True):
        if hint in {"text", "文本", "内容"}:
            continue
        if hint in lowered or hint in text:
            return hints[hint]
    return None


def _combined_strength_assignments(text: str, node: dict) -> list[tuple[dict, object]]:
    lowered = text.lower()
    if not any(term in lowered or term in text for term in ("权重", "强度", "strength")):
        return []
    mentions_model_and_clip = (
        any(term in lowered or term in text for term in ("模型", "model"))
        and "clip" in lowered
    )
    mentions_both_strengths = any(
        term in lowered or term in text
        for term in ("两个", "兩個", "两种", "兩種", "两边", "兩邊", "both", "dual")
    )
    if not mentions_model_and_clip and not mentions_both_strengths:
        return []
    value = _extract_value_after_set(text)
    if not value:
        return []
    widgets = _node_widgets(node)
    model_strength = _find_widget_by_name(widgets, ("strength_model",))
    clip_strength = _find_widget_by_name(widgets, ("strength_clip",))
    if model_strength is None or clip_strength is None:
        return []
    return [
        (model_strength, _coerce_widget_value(value, model_strength)),
        (clip_strength, _coerce_widget_value(value, clip_strength)),
    ]


def _step_count_assignment(text: str, node: dict) -> list[tuple[dict, object]]:
    lowered = text.lower()
    if "步" not in text and "steps" not in lowered:
        return []
    if not any(term in lowered or term in text for term in ("用", "使用", "with")):
        return []
    match = re.search(r"(?:用|使用|with)\s*(\d+)\s*(?:步|steps?)", text, re.IGNORECASE)
    if not match:
        return []
    widget = _find_widget_by_name(_node_widgets(node), ("steps",))
    if widget is None:
        return []
    return [(widget, _coerce_widget_value(match.group(1), widget))]


def _strip_use_assignment_suffix(value: str) -> str:
    cleaned = re.sub(
        r"\s*(?:作为|当作|as)\s*(?:文件名前缀|输出文件名前缀|输出前缀|保存前缀|filename prefix|file name prefix|output prefix)\s*$",
        "",
        value,
        flags=re.IGNORECASE,
    )
    return _strip_value(cleaned)


def _use_value_before_followup_assignment(value: str, node: dict) -> str:
    for match in re.finditer(r"[，,;；]", value):
        tail = value[match.end():]
        if _select_mentioned_widget(node, tail) is not None:
            return value[: match.start()]
    return value


def _use_widget_assignment(text: str, node: dict) -> list[tuple[dict, object]]:
    if _step_count_assignment(text, node):
        return []
    match = re.search(r"(?:用|使用)\s*(.+)$", text, re.IGNORECASE)
    if match is None:
        match = re.search(r"\bwith\b\s*(.+)$", text, re.IGNORECASE)
    if match is None:
        return []
    prefix = text[: match.start()]
    widget = _select_mentioned_widget(node, prefix) or _select_mentioned_widget(node, text)
    if widget is None:
        return []
    raw_value = match.group(1)
    if _looks_like_question_assignment(text, raw_value):
        return []
    value = _strip_use_assignment_suffix(_use_value_before_followup_assignment(raw_value, node))
    if not value:
        return []
    return [(widget, _coerce_widget_value(value, widget))]


def _merge_widget_assignments(*assignment_groups: list[tuple[dict, object]]) -> list[tuple[dict, object]]:
    rows = []
    seen = set()
    for group in assignment_groups:
        for widget, value in group:
            name = widget.get("name")
            if name in seen:
                continue
            seen.add(name)
            rows.append((widget, value))
    return rows


def _widget_assignments(text: str, node: dict) -> list[tuple[dict, object]]:
    hints = _widget_hint_map(node)
    if not hints:
        return []
    hint_pattern = "|".join(re.escape(hint) for hint in sorted(hints, key=len, reverse=True))
    assignment_operators = "|".join(
        re.escape(operator) for operator in sorted(WIDGET_ASSIGNMENT_OPERATORS, key=len, reverse=True)
    )
    explicit_pattern = re.compile(
        rf"(?P<hint>{hint_pattern})\s*(?:{assignment_operators})\s*",
        re.IGNORECASE,
    )
    implicit_number_pattern = re.compile(
        rf"(?:^|[\s，,;；])\s*(?P<hint>{hint_pattern})\s*(?P<value>-?\d+(?:\.\d+)?)",
        re.IGNORECASE,
    )
    implicit_string_pattern = re.compile(
        rf"(?:^|[\s，,;；])\s*(?P<hint>{hint_pattern})\s+(?P<value>[^，,;；]+)",
        re.IGNORECASE,
    )
    matches = [
        {
            "start": match.start(),
            "end": match.end(),
            "hint": match.group("hint").lower(),
            "value_start": match.end(),
            "value": None,
        }
        for match in explicit_pattern.finditer(text)
    ]
    for match in implicit_number_pattern.finditer(text):
        hint = match.group("hint").lower()
        widget = hints[hint]
        if not _widget_accepts_implicit_number(widget):
            continue
        matches.append(
            {
                "start": match.start("hint"),
                "end": match.end(),
                "hint": hint,
                "value_start": match.start("value"),
                "value": match.group("value"),
            }
        )
    for match in implicit_string_pattern.finditer(text):
        hint = match.group("hint").lower()
        widget = hints[hint]
        if not _widget_accepts_implicit_string(widget):
            continue
        if _looks_like_explicit_assignment_fragment(match.group("value")):
            continue
        matches.append(
            {
                "start": match.start("hint"),
                "end": match.end(),
                "hint": hint,
                "value_start": match.start("value"),
                "value": match.group("value"),
            }
        )
    matches.sort(key=lambda row: (row["start"], row["end"]))
    rows = []
    seen_widgets = set()
    for index, match in enumerate(matches):
        value_end = matches[index + 1]["start"] if index + 1 < len(matches) else len(text)
        raw_value = match["value"] if match["value"] is not None else text[match["value_start"]:value_end]
        value = _strip_value(raw_value)
        if not value or _looks_like_question_assignment(text, value):
            continue
        widget = hints[match["hint"]]
        if widget["name"] in seen_widgets:
            continue
        seen_widgets.add(widget["name"])
        rows.append((widget, _coerce_widget_value(value, widget)))
    return rows


RESOLUTION_PRESETS = {
    720: (1280, 720),
    1080: (1920, 1080),
}


def _mentions_size(text: str) -> bool:
    lowered = text.lower()
    return any(
        term in lowered or term in text
        for term in (
            "尺寸",
            "分辨率",
            "宽高",
            "高宽",
            "宽和高",
            "高和宽",
            "宽度和高度",
            "高度和宽度",
            "size",
            "resolution",
            "resize",
            "width height",
            "height width",
            "width/height",
            "w/h",
        )
    )


def _looks_like_size_value(value: str) -> bool:
    return bool(
        re.search(r"\d+(?:\.\d+)?\s*[xX×*]\s*\d+(?:\.\d+)?", value)
        or re.search(r"\b(?:720|1080)\s*p\b", value, re.IGNORECASE)
        or re.search(r"\d+(?:\.\d+)?\s*[:：]\s*\d+(?:\.\d+)?", value)
    )


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
    value = _extract_value_after_set(text)
    if not value:
        return []
    if not _mentions_size(text) and not _looks_like_size_value(value):
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
        for term in ("提高", "调高", "增加", "加", "raise", "increase", "higher")
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


def _extract_widget_multiplier(text: str) -> int | float | None:
    lowered = text.lower()
    if any(term in lowered or term in text for term in ("减半", "half", "halve")):
        return 0.5
    if any(term in lowered or term in text for term in ("翻倍", "加倍", "double")):
        return 2
    match = re.search(r"(?:乘以|乘|×|\*)\s*(\d+(?:\.\d+)?)", text, re.IGNORECASE)
    if match:
        value = float(match.group(1))
        return int(value) if value.is_integer() else value
    return None


def _adjust_widget_value(widget: dict, delta: int | float) -> object | None:
    current = widget.get("value")
    if isinstance(current, bool) or not isinstance(current, (int, float)):
        return None
    value = current + delta
    if isinstance(current, int) and float(value).is_integer():
        return int(value)
    return value


def _scale_widget_value(widget: dict, multiplier: int | float) -> object | None:
    current = widget.get("value")
    if isinstance(current, bool) or not isinstance(current, (int, float)):
        return None
    value = current * multiplier
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


def _extract_text_remove_value(text: str) -> str | None:
    value = _extract_value_after_delimiters(text, TEXT_REMOVE_DELIMITERS)
    if value:
        return value
    for delimiter in TEXT_REMOVE_DELIMITERS:
        if delimiter not in text:
            continue
        before = text.rsplit(delimiter, 1)[0]
        match = re.search(r"(?:里面|里的|里|中的|中|from)\s*([^,，;；]+?)\s*$", before, re.IGNORECASE)
        if match:
            return _strip_value(match.group(1))
    return None


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
    remove_value = _extract_text_remove_value(text)
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
    if not _extract_text_remove_value(text):
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
        assignments = _merge_widget_assignments(
            size_assignments,
            _widget_assignments(text, node),
        )
    else:
        assignments = _step_count_assignment(text, node)
        if assignments:
            assignments = _merge_widget_assignments(
                assignments,
                _widget_assignments(text, node),
            )
        if not assignments:
            use_assignments = _use_widget_assignment(text, node)
            if use_assignments:
                assignments = _merge_widget_assignments(
                    use_assignments,
                    _widget_assignments(text, node),
                )
        if not assignments:
            assignments = _combined_strength_assignments(text, node)
        if not assignments:
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

    multiplier = _extract_widget_multiplier(text)
    if multiplier is not None:
        widget = _select_widget(node, text)
        if widget is None:
            return []
        value = _scale_widget_value(widget, multiplier)
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
    links = _graph_links(context)
    bulk_nodes = _select_bulk_nodes(nodes, text, links)
    if bulk_nodes:
        actions = []
        for item in bulk_nodes:
            actions.extend(_widget_edit_actions_for_node(text, item))
        if actions:
            return {
                "summary": f"Set widget(s) on {len(bulk_nodes)} matching node(s)",
                "actions": actions,
            }

    if _message_mentions_all_nodes(text):
        widget_hint_nodes = _nodes_matching_widget_hint(nodes, text)
        if widget_hint_nodes:
            actions = []
            for item in widget_hint_nodes:
                actions.extend(_widget_edit_actions_for_node(text, item))
            if actions:
                return {
                    "summary": f"Set widget(s) on {len(widget_hint_nodes)} matching node(s)",
                    "actions": actions,
                }

    node = _select_node(nodes, text, links)
    if node is None:
        widget_hint_nodes = _nodes_matching_widget_hint(nodes, text)
        if len(widget_hint_nodes) != 1:
            return None
        node = widget_hint_nodes[0]
    actions = _widget_edit_actions_for_node(text, node)
    if not actions:
        return None
    return {
        "summary": f"Set widget(s) on node {node.get('id')}",
        "actions": actions,
    }


def _plan_prompt_role_assignments(text: str, context: dict) -> dict | None:
    assignments = _prompt_role_assignment_matches(text)
    if not assignments:
        return None

    nodes = _graph_nodes(context)
    links = _graph_links(context)
    actions = []
    seen_targets = set()
    for _, role_phrase, value in assignments:
        node = _find_node_by_semantic_label(nodes, role_phrase, links)
        if node is None:
            return None
        widget = _select_widget(node, f"{role_phrase} text")
        if widget is None:
            return None
        target = (node.get("id"), widget["name"])
        if target in seen_targets:
            return None
        seen_targets.add(target)
        actions.append(
            {
                "type": "graph.set_widget",
                "payload": {
                    "node_id": node.get("id"),
                    "widget": widget["name"],
                    "value": _coerce_widget_value(value, widget),
                },
            }
        )
    return {
        "summary": f"Set prompt role widget(s) on {len(actions)} node(s)",
        "actions": actions,
    }


IMAGE_GENERATION_STOP_TERMS = (
    "停止生成",
    "中断生成",
    "终止生成",
    "取消生成",
    "stop generation",
    "cancel generation",
    "interrupt generation",
)

IMAGE_GENERATION_PATTERNS = (
    r"(?:帮我|给我|请|麻烦|用你自己|你自己|直接|现在|我想要|我要)?\s*"
    r"(?:生成|画|绘制|做|出)\s*(?:一张|一个|一幅|一副|一只|张|个|幅|副|只)?\s*"
    r"(?P<subject>.+?)(?:的)?(?:图片|图像|照片|图)\s*(?P<tail>.*)$",
    r"\b(?:generate|draw|create|make)\s+(?:an?|the)?\s*(?P<subject>.+?)\s*"
    r"(?:image|picture|photo)\s*(?P<tail>.*)$",
)


def _image_generation_prompt(text: str) -> str | None:
    if not isinstance(text, str):
        return None
    lowered = text.lower()
    if any(term in lowered or term in text for term in IMAGE_GENERATION_STOP_TERMS):
        return None
    if any(
        term in lowered or term in text
        for term in ("你自己", "你来", "背后的", "背后", "codex", "openai", "chatgpt", "不是comfyui", "不要comfyui", "直接生成")
    ) and not any(
        term in lowered or term in text
        for term in ("当前 comfyui", "当前工作流", "comfyui 工作流", "current workflow")
    ):
        return None
    if not any(term in lowered or term in text for term in ("图片", "图像", "照片", "图", "image", "picture", "photo")):
        return None
    if not any(term in lowered or term in text for term in ("生成", "画", "绘制", "做", "出", "generate", "draw", "create", "make")):
        return None

    for pattern in IMAGE_GENERATION_PATTERNS:
        match = re.search(pattern, text, re.IGNORECASE)
        if match is None:
            continue
        subject = _strip_value(match.group("subject"))
        tail = _strip_value(match.group("tail"))
        tail = re.sub(r"^(?:要求|要|需要|必须|风格|style|with)\s*", "", tail, flags=re.IGNORECASE)
        tail = _strip_value(tail)
        if not subject:
            continue
        if tail and re.fullmatch(r"帅(?:气)?(?:一点|一些)?", tail):
            return subject if "帅" in subject else f"帅气的{subject}"
        return f"{subject}, {tail}" if tail else subject
    return None


def _positive_prompt_node(nodes: list[dict], links: list[dict]) -> dict | None:
    linked = _prompt_nodes_by_connection_role(nodes, links, "positive")
    if len(linked) == 1:
        return linked[0]

    labelled = []
    for node in nodes:
        if not _node_looks_like_prompt_text_node(node):
            continue
        label = _node_label(node).lower()
        if ("positive" in label or "正向" in label or "正面" in label) and not any(
            term in label for term in ("negative", "负面", "反向", "负向")
        ):
            labelled.append(node)
    if len(labelled) == 1:
        return labelled[0]

    selected = [node for node in _selected_nodes(nodes) if _node_looks_like_prompt_text_node(node)]
    if len(selected) == 1:
        return selected[0]

    generic = [node for node in nodes if _node_looks_like_prompt_text_node(node)]
    if len(generic) == 1:
        return generic[0]
    return None


def _plan_image_generation_request(text: str, context: dict) -> dict | None:
    prompt = _image_generation_prompt(text)
    if not prompt:
        return None
    nodes = _graph_nodes(context)
    node = _positive_prompt_node(nodes, _graph_links(context))
    if node is None:
        return None
    widget = _select_widget(node, "正向提示词 text")
    if widget is None:
        return None
    lowered = text.lower()
    front = any(term in lowered or term in text for term in ("插队", "队首", "front"))
    return {
        "summary": "Generate image with current ComfyUI workflow",
        "actions": [
            {
                "type": "graph.set_widget",
                "payload": {
                    "node_id": node.get("id"),
                    "widget": widget["name"],
                    "value": _coerce_widget_value(prompt, widget),
                },
            },
            {"type": "runtime.queue_prompt", "payload": {"front": front}},
        ],
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


def _copy_all_widget_settings_requested(text: str) -> bool:
    lowered = text.lower()
    return any(
        term in lowered or term in text
        for term in (
            "所有设置",
            "全部设置",
            "所有参数",
            "全部参数",
            "整组设置",
            "整套设置",
            "设置",
            "参数",
            "配置",
            "all settings",
            "all parameters",
            "all params",
            "all widgets",
            "settings",
            "parameters",
            "params",
            "configuration",
        )
    )


def _copy_common_widget_actions(source: dict, target: dict) -> list[dict]:
    target_widgets = {widget["name"].lower(): widget for widget in _node_widgets(target)}
    actions = []
    seen = set()
    for source_widget in _node_widgets(source):
        source_name = source_widget["name"].lower()
        if source_name in seen:
            continue
        target_widget = target_widgets.get(source_name)
        if target_widget is None:
            continue
        seen.add(source_name)
        actions.append(
            {
                "type": "graph.set_widget",
                "payload": {
                    "node_id": target.get("id"),
                    "widget": target_widget["name"],
                    "value": source_widget.get("value"),
                },
            }
        )
    return actions


def _plan_graph_copy_widget_value(text: str, context: dict) -> dict | None:
    phrases = _copy_widget_phrases(text)
    if phrases is None:
        return None
    source_phrase, target_phrase = phrases
    nodes = _graph_nodes(context)
    links = _graph_links(context)
    source = _select_node_preferring_label(nodes, source_phrase, links)
    target = _select_node_preferring_label(nodes, target_phrase, links)
    if source is None or target is None or source.get("id") == target.get("id"):
        return None
    if _copy_all_widget_settings_requested(source_phrase):
        actions = _copy_common_widget_actions(source, target)
        if not actions:
            return None
        return {
            "summary": f"Copy {len(actions)} widget setting(s) from node {source.get('id')} to node {target.get('id')}",
            "actions": actions,
        }
    source_widget = _select_widget(source, source_phrase)
    if source_widget is None:
        return None
    target_widget = _find_widget_by_name(_node_widgets(target), (source_widget["name"],))
    if target_widget is None:
        target_widget = _select_widget(target, target_phrase)
    if target_widget is None:
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
    links = _graph_links(context)
    bulk_nodes = _select_bulk_nodes(nodes, text, links)
    if bulk_nodes:
        return {
            "summary": f"Delete {len(bulk_nodes)} graph node(s)",
            "actions": [
                {"type": "graph.delete_node", "payload": {"node_id": node.get("id")}}
                for node in bulk_nodes
            ],
        }
    node = _select_node(nodes, text, links)
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
    links = _graph_links(context)
    bulk_nodes = _select_bulk_nodes(nodes, text, links)
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
    node = _select_node(nodes, text, links)
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
    links = _graph_links(context)
    bulk_nodes = _select_bulk_nodes(nodes, text, links)
    if bulk_nodes:
        return {
            "summary": f"Color {len(bulk_nodes)} graph node(s)",
            "actions": [_set_color_action(node, color) for node in bulk_nodes],
        }
    node = _select_node(nodes, text, links)
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
    links = _graph_links(context)
    bulk_nodes = _select_bulk_nodes(nodes, text, links)
    if bulk_nodes:
        return {
            "summary": f"Set {len(bulk_nodes)} graph node(s) mode to {mode}",
            "actions": [
                {"type": "graph.set_mode", "payload": {"node_id": node.get("id"), "mode": mode}}
                for node in bulk_nodes
            ],
        }
    node = _select_node(nodes, text, links)
    if node is None:
        return None
    return {
        "summary": f"Set graph node {node.get('id')} mode to {mode}",
        "actions": [{"type": "graph.set_mode", "payload": {"node_id": node.get("id"), "mode": mode}}],
    }


def _collapsed_state_from_text(text: str) -> bool | None:
    lowered = text.lower()
    if any(term in lowered or term in text for term in ("取消折叠", "展开", "expand", "unfold")):
        return False
    if any(term in lowered or term in text for term in ("折叠", "收起", "collapse", "fold")):
        return True
    return None


def _plan_graph_set_collapsed(text: str, context: dict) -> dict | None:
    collapsed = _collapsed_state_from_text(text)
    if collapsed is None:
        return None
    nodes = _graph_nodes(context)
    links = _graph_links(context)
    bulk_nodes = _select_bulk_nodes(nodes, text, links)
    if bulk_nodes:
        return {
            "summary": f"{'Collapse' if collapsed else 'Expand'} {len(bulk_nodes)} graph node(s)",
            "actions": [
                {
                    "type": "graph.set_collapsed",
                    "payload": {"node_id": node.get("id"), "collapsed": collapsed},
                }
                for node in bulk_nodes
            ],
        }
    node = _select_node(nodes, text, links)
    if node is None:
        return None
    return {
        "summary": f"{'Collapse' if collapsed else 'Expand'} graph node {node.get('id')}",
        "actions": [
            {
                "type": "graph.set_collapsed",
                "payload": {"node_id": node.get("id"), "collapsed": collapsed},
            }
        ],
    }


def _graph_neighborhood_direction(text: str) -> str | None:
    lowered = text.lower()
    if any(
        term in lowered or term in text
        for term in (
            "下游",
            "后续节点",
            "后面的节点",
            "后面的所有节点",
            "后面所有节点",
            "后面的",
            "后面",
            "之后的节点",
            "之后所有节点",
            "之后",
            "downstream",
            "following nodes",
            "nodes after",
            "after this node",
            "after the node",
        )
    ):
        return "downstream"
    if any(
        term in lowered or term in text
        for term in (
            "上游",
            "前面的节点",
            "前面的所有节点",
            "前面所有节点",
            "前面的",
            "前面",
            "之前的节点",
            "之前所有节点",
            "之前",
            "upstream",
            "previous nodes",
            "nodes before",
            "before this node",
            "before the node",
        )
    ):
        return "upstream"
    return None


def _reachable_graph_node_ids(
    anchor_id: object,
    links: list[dict],
    direction: str,
) -> set[object]:
    adjacency: dict[object, list[object]] = {}
    for link in links:
        origin_id = link.get("origin_id")
        target_id = link.get("target_id")
        if origin_id is None or target_id is None:
            continue
        if direction == "upstream":
            origin_id, target_id = target_id, origin_id
        adjacency.setdefault(origin_id, []).append(target_id)

    seen = set()
    queue = list(adjacency.get(anchor_id, []))
    while queue:
        node_id = queue.pop(0)
        if node_id == anchor_id or node_id in seen:
            continue
        seen.add(node_id)
        queue.extend(adjacency.get(node_id, []))
    return seen


GRAPH_NEIGHBORHOOD_ANCHOR_MARKERS = {
    "downstream": (
        "后面的所有节点",
        "后面所有节点",
        "后面的节点",
        "后续节点",
        "之后的节点",
        "之后所有节点",
        "下游节点",
        "后面的",
        "后面",
        "之后",
        "下游",
        "downstream",
        "following nodes",
        "after this node",
        "after the node",
    ),
    "upstream": (
        "前面的所有节点",
        "前面所有节点",
        "前面的节点",
        "之前的节点",
        "之前所有节点",
        "上游节点",
        "前面的",
        "前面",
        "之前",
        "上游",
        "upstream",
        "previous nodes",
        "before this node",
        "before the node",
    ),
}


def _graph_neighborhood_anchor_phrase(text: str, direction: str) -> str | None:
    lowered = text.lower()
    candidates = []
    for marker in GRAPH_NEIGHBORHOOD_ANCHOR_MARKERS[direction]:
        haystack = lowered if marker.isascii() else text
        needle = marker.lower() if marker.isascii() else marker
        index = haystack.find(needle)
        if index > 0:
            candidates.append(index)
    if not candidates:
        return None
    phrase = text[: min(candidates)].strip(" ，,。:：")
    return phrase or None


def _select_graph_neighborhood_nodes(
    text: str,
    context: dict,
) -> tuple[str, list[dict]] | None:
    direction = _graph_neighborhood_direction(text)
    if direction is None:
        return None
    nodes = _graph_nodes(context)
    links = _graph_links(context)
    anchor_phrase = _graph_neighborhood_anchor_phrase(text, direction)
    anchor = None
    if anchor_phrase is not None:
        anchor = _select_node_preferring_label(nodes, anchor_phrase, links)
    if anchor is None:
        anchor = _select_node_preferring_label(nodes, text, links)
    if anchor is None:
        return None
    reachable_ids = _reachable_graph_node_ids(anchor.get("id"), links, direction)
    if not reachable_ids:
        return None
    return direction, [node for node in nodes if node.get("id") in reachable_ids]


def _disconnect_all_scope_from_text(text: str) -> str | None:
    lowered = text.lower()
    if not any(term in lowered or term in text for term in ("断开", "清空", "移除连接", "disconnect")):
        return None
    if any(term in lowered or term in text for term in ("所有输入", "all inputs", "all input")):
        return "inputs"
    if any(term in lowered or term in text for term in ("所有输出", "all outputs", "all output")):
        return "outputs"
    if any(
        term in lowered or term in text
        for term in ("所有连接", "所有连线", "全部连接", "all links", "all connections")
    ):
        return "all"
    return None


def _disconnect_payload_key_for_scope(scope: str) -> str:
    return {
        "inputs": "target_node_id",
        "outputs": "origin_node_id",
        "all": "node_id",
    }[scope]


def _plan_graph_neighborhood_action(text: str, context: dict) -> dict | None:
    selected = _select_graph_neighborhood_nodes(text, context)
    if selected is None:
        return None
    direction, nodes = selected
    lowered = text.lower()

    if any(term in lowered or term in text for term in ("删除", "删掉", "移除", "delete", "remove")):
        if _looks_like_widget_text_removal(text):
            return None
        return {
            "summary": f"Delete {len(nodes)} {direction} graph node(s)",
            "actions": [
                {"type": "graph.delete_node", "payload": {"node_id": node.get("id")}}
                for node in nodes
            ],
        }

    if any(term in lowered or term in text for term in ("复制", "克隆", "duplicate", "clone")):
        return {
            "summary": f"Duplicate {len(nodes)} {direction} graph node(s)",
            "actions": [
                {
                    "type": "graph.duplicate_node",
                    "payload": {"node_id": node.get("id"), "offset": [40, 40], "select": False},
                }
                for node in nodes
            ],
        }

    disconnect_scope = _disconnect_all_scope_from_text(text)
    if disconnect_scope is not None:
        payload_key = _disconnect_payload_key_for_scope(disconnect_scope)
        return {
            "summary": f"Disconnect {disconnect_scope} on {len(nodes)} {direction} graph node(s)",
            "actions": [
                {"type": "graph.disconnect", "payload": {payload_key: node.get("id")}}
                for node in nodes
            ],
        }

    widget_actions = []
    for node in nodes:
        widget_actions.extend(_widget_edit_actions_for_node(text, node))
    if widget_actions:
        return {
            "summary": f"Set widget(s) on {len(nodes)} {direction} graph node(s)",
            "actions": widget_actions,
        }

    if _mentions_color_action(text):
        color = _extract_node_color(text)
        if color is not None:
            return {
                "summary": f"Color {len(nodes)} {direction} graph node(s)",
                "actions": [_set_color_action(node, color) for node in nodes],
            }

    mode = _graph_mode_from_text(text)
    if mode is not None:
        return {
            "summary": f"Set {len(nodes)} {direction} graph node(s) mode to {mode}",
            "actions": [
                {"type": "graph.set_mode", "payload": {"node_id": node.get("id"), "mode": mode}}
                for node in nodes
            ],
        }

    collapsed = _collapsed_state_from_text(text)
    if collapsed is not None:
        return {
            "summary": f"{'Collapse' if collapsed else 'Expand'} {len(nodes)} {direction} graph node(s)",
            "actions": [
                {
                    "type": "graph.set_collapsed",
                    "payload": {"node_id": node.get("id"), "collapsed": collapsed},
                }
                for node in nodes
            ],
        }

    alignment_axis = _alignment_axis(text)
    if alignment_axis is not None:
        actions = _align_graph_node_actions(nodes, alignment_axis)
        if actions:
            return {
                "summary": f"Align {len(nodes)} {direction} graph node(s)",
                "actions": actions,
            }

    distribution_axis = _distribution_axis(text)
    if distribution_axis is not None:
        actions = _distribute_graph_node_actions(nodes, distribution_axis)
        if actions:
            return {
                "summary": f"Distribute {len(nodes)} {direction} graph node(s)",
                "actions": actions,
            }

    delta = _extract_move_delta(text)
    if delta is not None:
        actions = []
        for node in nodes:
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
            "summary": f"Move {len(nodes)} {direction} graph node(s)",
            "actions": actions,
        }

    focus = _graph_select_focus(text)
    if focus is not None:
        return {
            "summary": f"{'Focus' if focus else 'Select'} {len(nodes)} {direction} graph node(s)",
            "actions": [
                {
                    "type": "graph.select_nodes",
                    "payload": {"node_ids": [node.get("id") for node in nodes], "focus": focus},
                }
            ],
        }
    return None


def _mentions_node_box_size(text: str) -> bool:
    lowered = text.lower()
    return any(
        term in lowered or term in text
        for term in (
            "节点框",
            "节点面板",
            "节点窗口",
            "node box",
            "node panel",
            "node size",
            "graph node size",
            "canvas node size",
        )
    )


def _extract_node_box_size(text: str) -> list[int | float] | None:
    if not _mentions_node_box_size(text):
        return None
    matches = re.findall(r"(\d+(?:\.\d+)?)\s*[xX×*]\s*(\d+(?:\.\d+)?)", text)
    if not matches:
        return None
    width, height = matches[-1]
    return [_number_value(width), _number_value(height)]


def _plan_graph_set_size(text: str, context: dict) -> dict | None:
    size = _extract_node_box_size(text)
    if size is None:
        return None
    nodes = _graph_nodes(context)
    links = _graph_links(context)
    bulk_nodes = _select_bulk_nodes(nodes, text, links)
    if bulk_nodes:
        return {
            "summary": f"Resize {len(bulk_nodes)} graph node box(es)",
            "actions": [
                {"type": "graph.set_size", "payload": {"node_id": node.get("id"), "size": size}}
                for node in bulk_nodes
            ],
        }
    node = _select_node(nodes, text, links)
    if node is None:
        return None
    return {
        "summary": f"Resize graph node {node.get('id')} box",
        "actions": [{"type": "graph.set_size", "payload": {"node_id": node.get("id"), "size": size}}],
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
    links = _graph_links(context)
    node = _select_node(nodes, text, links)
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


def _relative_position_relation(value: str) -> str | None:
    lowered = value.lower()
    if any(term in lowered or term in value for term in ("右边", "右侧", "右面", "右方", "right of")):
        return "right"
    if any(term in lowered or term in value for term in ("左边", "左侧", "左面", "左方", "left of")):
        return "left"
    if any(
        term in lowered or term in value
        for term in ("下面", "下方", "下边", "below", "under", "beneath")
    ):
        return "below"
    if any(term in lowered or term in value for term in ("上面", "上方", "上边", "above", "over")):
        return "above"
    return None


def _clean_relative_node_phrase(value: str) -> str:
    cleaned = _strip_value(value)
    cleaned = re.sub(r"^(?:the\s+)", "", cleaned, flags=re.IGNORECASE).strip()
    cleaned = re.sub(r"\s*(?:的)?(?:节点|node)\s*$", "", cleaned, flags=re.IGNORECASE).strip()
    return _strip_value(cleaned)


def _extract_relative_position_request(text: str) -> tuple[str, str, str] | None:
    relation_terms = (
        "右边",
        "右侧",
        "右面",
        "右方",
        "左边",
        "左侧",
        "左面",
        "左方",
        "下面",
        "下方",
        "下边",
        "上面",
        "上方",
        "上边",
    )
    relation_pattern = "|".join(re.escape(term) for term in relation_terms)
    chinese_pattern = re.compile(
        rf"^\s*(?:请|帮我)?\s*(?:把|将)?\s*"
        rf"(?P<source>.+?)\s*(?:移动到|移到|挪到|放到|放在)\s*"
        rf"(?P<target>.+?)\s*(?:的)?\s*(?P<relation>{relation_pattern})\s*$"
    )
    match = chinese_pattern.search(text)
    if match:
        relation = _relative_position_relation(match.group("relation"))
        source = _clean_relative_node_phrase(match.group("source"))
        target = _clean_relative_node_phrase(match.group("target"))
        if relation and source and target:
            return source, target, relation

    english_pattern = re.compile(
        r"^\s*(?:please\s+)?(?:move|put|place)\s+"
        r"(?P<source>.+?)\s+(?:to\s+|on\s+|at\s+)?(?:the\s+)?"
        r"(?P<relation>right of|left of|below|under|beneath|above|over)\s+"
        r"(?P<target>.+?)\s*$",
        re.IGNORECASE,
    )
    match = english_pattern.search(text)
    if not match:
        return None
    relation = _relative_position_relation(match.group("relation"))
    source = _clean_relative_node_phrase(match.group("source"))
    target = _clean_relative_node_phrase(match.group("target"))
    if not relation or not source or not target:
        return None
    return source, target, relation


def _relative_position(anchor: list[int | float], relation: str) -> list[int | float]:
    if relation == "right":
        return [_position_number(anchor[0] + RELATIVE_NODE_X_GAP), anchor[1]]
    if relation == "left":
        return [_position_number(anchor[0] - RELATIVE_NODE_X_GAP), anchor[1]]
    if relation == "below":
        return [anchor[0], _position_number(anchor[1] + RELATIVE_NODE_Y_GAP)]
    return [anchor[0], _position_number(anchor[1] - RELATIVE_NODE_Y_GAP)]


def _plan_relative_graph_position(text: str, nodes: list[dict], links: list[dict]) -> dict | None:
    request = _extract_relative_position_request(text)
    if request is None:
        return None
    source_phrase, target_phrase, relation = request
    source = _select_node_preferring_label(nodes, source_phrase, links)
    target = _select_node_preferring_label(nodes, target_phrase, links)
    if source is None or target is None or source.get("id") == target.get("id"):
        return None
    pos = _relative_position(_node_position(target), relation)
    return {
        "summary": f"Move graph node {source.get('id')} {relation} of node {target.get('id')}",
        "actions": [
            {"type": "graph.set_position", "payload": {"node_id": source.get("id"), "pos": pos}}
        ],
    }


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


def _align_graph_node_actions(nodes: list[dict], axis: str) -> list[dict] | None:
    if len(nodes) < 2:
        return None
    positions = [_node_position(node) for node in nodes]
    reference = _alignment_reference(axis, positions)
    return [
        {
            "type": "graph.set_position",
            "payload": {
                "node_id": node.get("id"),
                "pos": _aligned_position(axis, pos, reference),
            },
        }
        for node, pos in zip(nodes, positions)
    ]


def _plan_graph_align_nodes(text: str, context: dict) -> dict | None:
    axis = _alignment_axis(text)
    if axis is None:
        return None
    nodes = _select_bulk_nodes(_graph_nodes(context), text, _graph_links(context))
    actions = _align_graph_node_actions(nodes, axis)
    if actions is None:
        return None
    return {
        "summary": f"Align {len(nodes)} graph node(s)",
        "actions": actions,
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


def _distribute_graph_node_actions(nodes: list[dict], axis: str) -> list[dict] | None:
    if len(nodes) < 3:
        return None
    axis_index = 0 if axis == "horizontal" else 1
    rows = sorted(((node, _node_position(node)) for node in nodes), key=lambda item: item[1][axis_index])
    first = rows[0][1][axis_index]
    last = rows[-1][1][axis_index]
    step = (last - first) / (len(rows) - 1)
    return [
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
    ]


def _plan_graph_distribute_nodes(text: str, context: dict) -> dict | None:
    axis = _distribution_axis(text)
    if axis is None:
        return None
    nodes = _select_bulk_nodes(_graph_nodes(context), text, _graph_links(context))
    actions = _distribute_graph_node_actions(nodes, axis)
    if actions is None:
        return None
    return {
        "summary": f"Distribute {len(nodes)} graph node(s)",
        "actions": actions,
    }


def _mentions_auto_layout(text: str) -> bool:
    lowered = text.lower()
    return any(
        term in lowered or term in text
        for term in (
            "整理",
            "自动排版",
            "自动布局",
            "重新布局",
            "排版一下",
            "布局一下",
            "tidy",
            "auto layout",
            "arrange workflow",
            "layout workflow",
            "organize workflow",
            "clean up workflow",
        )
    )


def _auto_layout_depths(nodes: list[dict], links: list[dict]) -> dict[object, int]:
    node_ids = {node.get("id") for node in nodes if node.get("id") is not None}
    incoming_counts = {node_id: 0 for node_id in node_ids}
    outgoing: dict[object, list[object]] = {node_id: [] for node_id in node_ids}
    for link in links:
        origin_id = link.get("origin_id")
        target_id = link.get("target_id")
        if origin_id not in node_ids or target_id not in node_ids or origin_id == target_id:
            continue
        outgoing[origin_id].append(target_id)
        incoming_counts[target_id] += 1

    depths = {node_id: 0 for node_id, count in incoming_counts.items() if count == 0}
    queue = [node.get("id") for node in nodes if node.get("id") in depths]
    remaining_incoming = dict(incoming_counts)
    while queue:
        origin_id = queue.pop(0)
        origin_depth = depths.get(origin_id, 0)
        for target_id in outgoing.get(origin_id, []):
            depths[target_id] = max(depths.get(target_id, 0), origin_depth + 1)
            remaining_incoming[target_id] -= 1
            if remaining_incoming[target_id] == 0:
                queue.append(target_id)

    for node_id in node_ids:
        depths.setdefault(node_id, 0)
    return depths


def _plan_graph_auto_layout(text: str, context: dict) -> dict | None:
    if not _mentions_auto_layout(text):
        return None
    nodes = [node for node in _graph_nodes(context) if node.get("id") is not None]
    if len(nodes) < 2:
        return None
    positions = [_node_position(node) for node in nodes]
    origin_x = min(pos[0] for pos in positions)
    origin_y = min(pos[1] for pos in positions)
    depths = _auto_layout_depths(nodes, _graph_links(context))
    layer_counts: dict[int, int] = {}
    actions = []
    for node in nodes:
        depth = depths.get(node.get("id"), 0)
        row = layer_counts.get(depth, 0)
        layer_counts[depth] = row + 1
        actions.append(
            {
                "type": "graph.set_position",
                "payload": {
                    "node_id": node.get("id"),
                    "pos": [
                        _position_number(origin_x + RELATIVE_NODE_X_GAP * depth),
                        _position_number(origin_y + RELATIVE_NODE_Y_GAP * row),
                    ],
                },
            }
        )
    return {
        "summary": f"Auto layout {len(nodes)} graph node(s)",
        "actions": actions,
    }


def _plan_graph_set_position(text: str, context: dict) -> dict | None:
    lowered = text.lower()
    if not any(
        term in lowered or term in text
        for term in ("移动", "移到", "挪", "放到", "放在", "move", "put", "place")
    ):
        return None
    nodes = _graph_nodes(context)
    links = _graph_links(context)
    relative_plan = _plan_relative_graph_position(text, nodes, links)
    if relative_plan is not None:
        return relative_plan
    bulk_nodes = _select_bulk_nodes(nodes, text, links)
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
    node = _select_node(nodes, text, links)
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


def _select_node_for_selection(
    nodes: list[dict],
    text: str,
    links: list[dict] | None = None,
) -> dict | None:
    explicit = _find_node_by_id(nodes, _extract_node_id(text))
    if explicit is not None:
        return explicit

    labelled = _find_node_by_label(nodes, text)
    if labelled is not None:
        return labelled

    return _select_node(nodes, text, links)


def _plan_graph_select_node(text: str, context: dict) -> dict | None:
    focus = _graph_select_focus(text)
    if focus is None:
        return None
    if _extract_value_after_set(text):
        return None
    nodes = _graph_nodes(context)
    links = _graph_links(context)
    bulk_nodes = _select_all_matching_nodes(nodes, text, links)
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
    node = _select_node_for_selection(nodes, text, links)
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


ADD_NODE_ALIASES = (
    (
        ("正向提示词", "正面提示词", "正向 prompt", "positive prompt"),
        "CLIPTextEncode",
        "Positive Prompt",
    ),
    (
        ("负面提示词", "反向提示词", "负向提示词", "负面 prompt", "negative prompt"),
        "CLIPTextEncode",
        "Negative Prompt",
    ),
    (
        ("提示词", "prompt node", "clip text encode", "cliptextencode"),
        "CLIPTextEncode",
        None,
    ),
    (
        ("空 latent 图像", "空latent图像", "empty latent image", "latent image"),
        "EmptyLatentImage",
        None,
    ),
    (
        ("lora 加载器", "lora加载器", "lora loader", "load lora", "lora 节点"),
        "LoraLoader",
        None,
    ),
    (
        ("checkpoint 加载器", "checkpoint loader", "load checkpoint", "底模加载器"),
        "CheckpointLoaderSimple",
        None,
    ),
    (
        ("vae 解码", "vae解码", "vae decode", "decode vae", "latent 转图像", "latent to image"),
        "VAEDecode",
        None,
    ),
    (
        ("vae 编码", "vae编码", "vae encode", "encode vae", "图像转 latent", "image to latent"),
        "VAEEncode",
        None,
    ),
    (
        ("vae 加载器", "vae加载器", "vae loader", "load vae"),
        "VAELoader",
        None,
    ),
    (
        ("加载图片", "导入图片", "输入图片", "输入图像", "load image", "image input"),
        "LoadImage",
        None,
    ),
    (
        ("图像缩放", "图片缩放", "缩放节点", "image scale", "image resize", "resize image"),
        "ImageScale",
        None,
    ),
    (
        ("超分模型加载器", "超分模型", "放大模型加载器", "upscale model loader", "load upscale model"),
        "UpscaleModelLoader",
        None,
    ),
    (
        ("controlnet 模型加载器", "controlnet 加载器", "controlnet loader", "load controlnet model", "控制网模型加载器"),
        "ControlNetLoader",
        None,
    ),
)


def _node_type_alias_to_add(text: str) -> tuple[str, str | None] | None:
    lowered = text.lower()
    for triggers, node_type, title in ADD_NODE_ALIASES:
        if any(trigger in lowered or trigger in text for trigger in triggers):
            return node_type, title
    return None


def _normalize_node_type_phrase(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.lower())


def _registered_node_type_for_phrase(context: dict, phrase: str) -> str | None:
    cleaned = _strip_value(phrase)
    if not cleaned:
        return None
    lowered = cleaned.lower()
    compact = _normalize_node_type_phrase(cleaned)
    if not compact:
        return None
    for row in _graph_node_types(context):
        labels = [row.get("type"), row.get("title"), row.get("name"), row.get("display_name")]
        for label in labels:
            if not isinstance(label, str) or not label:
                continue
            if label.lower() == lowered or _normalize_node_type_phrase(label) == compact:
                return row["type"]
    return None


def _node_type_row(context: dict, node_type: str) -> dict | None:
    for row in _graph_node_types(context):
        if row.get("type") == node_type:
            return row
    return None


def _schema_input_type(raw: object) -> object:
    if isinstance(raw, dict):
        return raw.get("type")
    if not isinstance(raw, list) or not raw:
        return None
    first = raw[0]
    if isinstance(first, list):
        return "COMBO"
    if isinstance(first, str):
        return first
    return None


def _input_rows_from_schema_mapping(row: dict) -> list[dict]:
    node_input = row.get("input")
    if not isinstance(node_input, dict):
        return []
    input_order = row.get("input_order")
    rows = []
    for section in ("required", "optional"):
        section_inputs = node_input.get(section)
        if not isinstance(section_inputs, dict):
            continue
        if isinstance(input_order, dict) and isinstance(input_order.get(section), list):
            names = input_order[section]
        else:
            names = list(section_inputs.keys())
        for name in names:
            if not isinstance(name, str):
                continue
            rows.append({"name": name, "type": _schema_input_type(section_inputs.get(name))})
    return rows


def _node_type_input_rows(context: dict, node_type: str) -> list[dict]:
    row = _node_type_row(context, node_type)
    if row is None:
        return []
    explicit_inputs = row.get("inputs")
    if isinstance(explicit_inputs, list):
        return [
            item
            for item in explicit_inputs[:MAX_PLANNER_NODE_TYPE_INPUTS]
            if isinstance(item, dict) and isinstance(item.get("name"), str)
        ]
    rows = _input_rows_from_schema_mapping(row)
    if rows:
        return rows[:MAX_PLANNER_NODE_TYPE_INPUTS]
    input_order = row.get("input_order")
    if not isinstance(input_order, dict):
        return []
    names = []
    for section in ("required", "optional"):
        values = input_order.get(section)
        if isinstance(values, list):
            names.extend(value for value in values if isinstance(value, str))
    return [{"name": name} for name in names[:MAX_PLANNER_NODE_TYPE_INPUTS]]


def _node_type_output_rows(context: dict, node_type: str) -> list[dict]:
    row = _node_type_row(context, node_type)
    if row is None:
        return []
    explicit_outputs = row.get("outputs")
    if isinstance(explicit_outputs, list):
        return [
            item
            for item in explicit_outputs[:MAX_PLANNER_NODE_TYPE_INPUTS]
            if isinstance(item, dict) and isinstance(item.get("name"), str)
        ]
    output_types = row.get("output")
    if not isinstance(output_types, list):
        return []
    output_names = row.get("output_name")
    rows = []
    for index, output_type in enumerate(output_types[:MAX_PLANNER_NODE_TYPE_INPUTS]):
        if not isinstance(output_type, str) or not output_type:
            continue
        name = output_type
        if isinstance(output_names, list) and index < len(output_names):
            candidate = output_names[index]
            if isinstance(candidate, str) and candidate:
                name = candidate
        rows.append({"name": name, "type": output_type})
    return rows


def _node_type_input_looks_like_widget(row: dict) -> bool:
    input_type = row.get("type")
    if isinstance(input_type, str):
        return input_type.upper() in {"STRING", "INT", "FLOAT", "BOOLEAN", "COMBO"}
    return input_type is None


def _node_type_widget_input_rows(context: dict, node_type: str) -> list[dict]:
    row = _node_type_row(context, node_type) or {}
    rows = []
    seen = set()
    for candidate in (*_node_type_input_rows(context, node_type), *_input_rows_from_schema_mapping(row)):
        name = candidate.get("name")
        if not isinstance(name, str) or name in seen:
            continue
        if not _node_type_input_looks_like_widget(candidate):
            continue
        seen.add(name)
        rows.append(candidate)
    return rows


def _node_type_widget_name_hint_from_text(context: dict, node_type: str, text: str) -> tuple[str, dict] | None:
    normalized_text = _normalize_node_type_phrase(text)
    matches = []
    for row in _node_type_widget_input_rows(context, node_type):
        name = row["name"]
        lowered = name.lower()
        normalized_name = _normalize_node_type_phrase(name)
        spaced_name = name.replace("_", " ").lower()
        if lowered in text.lower() or spaced_name in text.lower() or normalized_name in normalized_text:
            matches.append((len(normalized_name), name, row))
    if not matches:
        return None
    matches.sort(key=lambda item: item[0], reverse=True)
    return matches[0][1], matches[0][2]


def _node_type_input_row_by_name(context: dict, node_type: str, name: str) -> dict | None:
    lowered = name.lower()
    for row in _node_type_widget_input_rows(context, node_type):
        row_name = row.get("name")
        if isinstance(row_name, str) and row_name.lower() == lowered:
            return row
    return None


def _coerce_new_node_widget_value(value: str, input_row: dict | None) -> object:
    input_type = input_row.get("type") if isinstance(input_row, dict) else None
    input_type = input_type.upper() if isinstance(input_type, str) else None
    lowered = value.lower()
    if input_type == "BOOLEAN":
        if lowered in {"true", "yes", "on", "1"} or value in {"开", "开启", "是"}:
            return True
        if lowered in {"false", "no", "off", "0"} or value in {"关", "关闭", "否"}:
            return False
    if input_type == "INT":
        try:
            return int(value)
        except ValueError:
            return value
    if input_type == "FLOAT":
        try:
            return float(value)
        except ValueError:
            return value
    return value


def _default_new_node_widget_value(input_row: dict) -> object:
    input_type = input_row.get("type")
    input_type = input_type.upper() if isinstance(input_type, str) else None
    if input_type == "BOOLEAN":
        return False
    if input_type == "INT":
        return 0
    if input_type == "FLOAT":
        return 0.0
    return ""


def _synthetic_widget_node_for_type(context: dict, node_type: str) -> dict:
    return {
        "type": node_type,
        "title": node_type,
        "widgets": [
            {"name": row["name"], "value": _default_new_node_widget_value(row)}
            for row in _node_type_widget_input_rows(context, node_type)
        ],
    }


def _extract_quoted_node_type_phrase(text: str) -> str | None:
    for opener, closer in (('"', '"'), ("'", "'"), ("`", "`"), ("“", "”"), ("「", "」"), ("『", "』")):
        pattern = (
            rf"(?:添加|新增|创建|加|add|create)(?:一个|一個|个|\s+a|\s+an)?\s*"
            rf"{re.escape(opener)}(?P<node_type>.+?){re.escape(closer)}"
        )
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return _strip_value(match.group("node_type"))
    return None


def _extract_unquoted_node_type_phrase(text: str) -> str | None:
    patterns = (
        r"(?:添加|新增|创建|加)(?:一个|一個|个)?\s*(?P<node_type>.+?)\s*(?:节点|node)(?:[\s,，。；;]|$)",
        r"\b(?:add|create)\s+(?:a\s+|an\s+)?(?:node\s+)?(?P<node_type>.+?)(?:\s+node)?(?:[\s,，。；;]|$)",
    )
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return _strip_value(match.group("node_type"))
    return None


def _looks_like_exact_node_type_phrase(phrase: str) -> bool:
    return re.fullmatch(r"[A-Za-z][A-Za-z0-9_./:-]*(?:\s+[A-Za-z][A-Za-z0-9_./:-]*)*", phrase) is not None


def _node_type_from_exact_phrase(phrase: str) -> str | None:
    cleaned = _strip_value(phrase)
    if not _looks_like_exact_node_type_phrase(cleaned):
        return None
    if " " in cleaned:
        return "".join(cleaned.split())
    return cleaned.rstrip(".,，。")


def _extract_node_type_to_add(text: str, context: dict) -> str | None:
    alias = _node_type_alias_to_add(text)
    if alias is not None:
        return alias[0]
    quoted = _extract_quoted_node_type_phrase(text)
    if quoted:
        return _registered_node_type_for_phrase(context, quoted) or quoted
    phrase = _extract_unquoted_node_type_phrase(text)
    if not phrase:
        return None
    return _registered_node_type_for_phrase(context, phrase) or _node_type_from_exact_phrase(phrase)


def _extract_new_node_size_widgets(text: str) -> dict[str, object]:
    if not _mentions_size(text):
        return {}
    value = _extract_value_after_set(text)
    if not value:
        return {}
    match = re.search(r"(\d+(?:\.\d+)?)\s*[xX×*]\s*(\d+(?:\.\d+)?)", value)
    if not match:
        return {}
    return {
        "width": _number_value(match.group(1)),
        "height": _number_value(match.group(2)),
    }


def _new_node_widget_name(node_type: str, widget_name: str) -> str:
    if node_type == "CLIPTextEncode" and widget_name in {"positive", "negative"}:
        return "text"
    return widget_name


def _initial_widgets_for_new_node(node_type: str, text: str, context: dict) -> dict[str, object]:
    widgets = {}
    widgets.update(_extract_new_node_size_widgets(text))
    value = _extract_value_after_set(text)
    widget_name = _widget_name_hint_from_text(text)
    schema_widget = None
    if widget_name is None:
        schema_widget = _node_type_widget_name_hint_from_text(context, node_type, text)
        if schema_widget is not None:
            widget_name = schema_widget[0]
    if value and widget_name:
        widget_name = _new_node_widget_name(node_type, widget_name)
        if widget_name == "image" and node_type != "LoadImage":
            return widgets
        if widget_name not in widgets:
            if schema_widget is None:
                input_row = _node_type_input_row_by_name(context, node_type, widget_name)
            else:
                input_row = schema_widget[1]
            widgets[widget_name] = _coerce_new_node_widget_value(value, input_row)
    synthetic_node = _synthetic_widget_node_for_type(context, node_type)
    assignments = _merge_widget_assignments(
        _use_widget_assignment(text, synthetic_node),
        _widget_assignments(text, synthetic_node),
    )
    for widget, assignment_value in assignments:
        widget_name = _new_node_widget_name(node_type, widget["name"])
        if widget_name == "image" and node_type != "LoadImage":
            continue
        widgets.setdefault(widget_name, assignment_value)
    return widgets


def _plan_graph_add_node(text: str, context: dict) -> dict | None:
    if not any(term in text.lower() or term in text for term in ("添加", "新增", "创建", "add", "create")):
        return None
    node_type = _extract_node_type_to_add(text, context)
    if not node_type:
        return None
    payload = {"node_type": node_type}
    alias = _node_type_alias_to_add(text)
    if alias is not None and alias[1]:
        payload["title"] = alias[1]
    widgets = _initial_widgets_for_new_node(node_type, text, context)
    if widgets:
        payload["widgets"] = widgets
    return {
        "summary": f"Add graph node {node_type}",
        "actions": [{"type": "graph.add_node", "payload": payload}],
    }


def _existing_to_new_node_origin_phrase(text: str) -> str | None:
    patterns = (
        r"(?:并把|并将|然后把|然后将|接着把|接着将|再把|再将|，把|,)\s*(?P<origin>.+?)\s*(?:连接到|连到|接到)\s*(?:它|这个节点|新节点|该节点)\s*$",
        r"\band\s+connect\s+(?P<origin>.+?)\s+(?:to|into)\s+(?:it|the\s+new\s+node)\s*$",
    )
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            origin = _strip_value(match.group("origin"))
            if origin:
                return origin
    return None


def _new_node_to_existing_target_phrase(text: str) -> str | None:
    patterns = (
        r"(?:并把|并将|然后把|然后将|接着把|接着将|再把|再将|，把|,)\s*(?:它|这个节点|新节点|该节点)\s*(?:连接到|连到|接到)\s*(?P<target>.+?)\s*$",
        r"\band\s+connect\s+(?:it|the\s+new\s+node)\s+(?:to|into)\s+(?P<target>.+?)\s*$",
    )
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            target = _strip_value(match.group("target"))
            if target:
                return target
    return None


def _strip_new_node_connect_clause(text: str) -> str:
    patterns = (
        r"\s*(?:，|,)?\s*(?:并把|并将|然后把|然后将|接着把|接着将|再把|再将)\s*(?:它|这个节点|新节点|该节点)\s*(?:连接到|连到|接到)\s*.+$",
        r"\s*(?:，|,)?\s*(?:并把|并将|然后把|然后将|接着把|接着将|再把|再将)\s*.+?\s*(?:连接到|连到|接到)\s*(?:它|这个节点|新节点|该节点)\s*$",
        r"\s+and\s+connect\s+(?:it|the\s+new\s+node)\s+(?:to|into)\s+.+$",
        r"\s+and\s+connect\s+.+?\s+(?:to|into)\s+(?:it|the\s+new\s+node)\s*$",
    )
    stripped = text
    for pattern in patterns:
        stripped = re.sub(pattern, "", stripped, flags=re.IGNORECASE)
    return _strip_value(stripped)


def _synthetic_node_for_type(context: dict, node_type: str) -> dict:
    row = _node_type_row(context, node_type) or {}
    title = row.get("title") if isinstance(row.get("title"), str) else node_type
    return {
        "type": node_type,
        "title": title,
        "inputs": _node_type_input_rows(context, node_type),
        "outputs": _node_type_output_rows(context, node_type),
    }


def _plan_graph_add_node_and_connect(text: str, context: dict) -> dict | None:
    origin_phrase = _existing_to_new_node_origin_phrase(text)
    target_phrase = _new_node_to_existing_target_phrase(text)
    if origin_phrase is None and target_phrase is None:
        return None
    add_text = _strip_new_node_connect_clause(text)
    add_plan = _plan_graph_add_node(add_text, context)
    if add_plan is None or len(add_plan.get("actions", [])) != 1:
        return None
    add_action = add_plan["actions"][0]
    add_payload = dict(add_action.get("payload", {}))
    node_type = add_payload.get("node_type")
    if not isinstance(node_type, str) or not node_type:
        return None
    nodes = _graph_nodes(context)
    links = _graph_links(context)
    node_ref = "new_node"
    add_payload["ref"] = node_ref
    if target_phrase is not None:
        target = _find_node_for_phrase(nodes, target_phrase, links)
        if target is None:
            return None
        origin = _synthetic_node_for_type(context, node_type)
        slots = _infer_connect_slots(origin, target, node_type, target_phrase)
        if slots is None:
            return None
        return {
            "summary": f"Add graph node {node_type} and connect to node {target.get('id')}",
            "actions": [
                {"type": "graph.add_node", "payload": add_payload},
                {
                    "type": "graph.connect",
                    "payload": {
                        "origin_node_ref": node_ref,
                        "origin_slot": slots[0],
                        "target_node_id": target.get("id"),
                        "target_slot": slots[1],
                    },
                },
            ],
        }
    origin = _find_node_for_phrase(nodes, origin_phrase or "", links)
    if origin is None:
        return None
    target = _synthetic_node_for_type(context, node_type)
    slots = _infer_connect_slots(origin, target, origin_phrase or "", node_type)
    if slots is None:
        return None
    return {
        "summary": f"Add graph node {node_type} and connect node {origin.get('id')}",
        "actions": [
            {"type": "graph.add_node", "payload": add_payload},
            {
                "type": "graph.connect",
                "payload": {
                    "origin_node_id": origin.get("id"),
                    "origin_slot": slots[0],
                    "target_node_ref": node_ref,
                    "target_slot": slots[1],
                },
            },
        ],
    }


def _adjacent_new_node_parts(text: str) -> tuple[str, str, str] | None:
    patterns = (
        r"(?:在|给)?\s*(?P<anchor>.+?)\s*(?P<position>后面|后边|之后|前面|前边|之前)\s*(?:添加|新增|创建|加|插入)\s*(?:一个|一個|个)?\s*(?P<node>.+?)\s*(?:节点)?$",
        r"\b(?:add|create|insert)\s+(?:a\s+|an\s+)?(?P<node>.+?)\s+(?:node\s+)?(?P<position>after|behind|before)\s+(?P<anchor>.+)$",
    )
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if not match:
            continue
        anchor = _strip_value(match.group("anchor"))
        node = _strip_value(match.group("node"))
        position = match.group("position").lower()
        if not anchor or not node:
            continue
        if position in {"后面", "后边", "之后", "after", "behind"}:
            return anchor, "after", node
        return anchor, "before", node
    return None


def _plan_graph_add_adjacent_node(text: str, context: dict) -> dict | None:
    parts = _adjacent_new_node_parts(text)
    if parts is None:
        return None
    anchor_phrase, position, node_phrase = parts
    add_plan = _plan_graph_add_node(f"添加 {node_phrase} 节点", context)
    if add_plan is None or len(add_plan.get("actions", [])) != 1:
        return None
    add_payload = dict(add_plan["actions"][0].get("payload", {}))
    node_type = add_payload.get("node_type")
    if not isinstance(node_type, str) or not node_type:
        return None

    nodes = _graph_nodes(context)
    links = _graph_links(context)
    anchor = _find_node_for_phrase(nodes, anchor_phrase, links)
    if anchor is None:
        return None
    new_node = _synthetic_node_for_type(context, node_type)
    node_ref = "new_node"
    add_payload["ref"] = node_ref

    if position == "after":
        slots = _infer_connect_slots(anchor, new_node, anchor_phrase, node_type)
        if slots is None:
            return None
        connect_payload = {
            "origin_node_id": anchor.get("id"),
            "origin_slot": slots[0],
            "target_node_ref": node_ref,
            "target_slot": slots[1],
        }
    else:
        slots = _infer_connect_slots(new_node, anchor, node_type, anchor_phrase)
        if slots is None:
            return None
        connect_payload = {
            "origin_node_ref": node_ref,
            "origin_slot": slots[0],
            "target_node_id": anchor.get("id"),
            "target_slot": slots[1],
        }

    return {
        "summary": f"Add graph node {node_type} {position} node {anchor.get('id')}",
        "actions": [
            {"type": "graph.add_node", "payload": add_payload},
            {"type": "graph.connect", "payload": connect_payload},
        ],
    }


def _insert_node_between_parts(text: str) -> tuple[str, str, str] | None:
    patterns = (
        r"(?:在|把|将)?\s*(?P<origin>.+?)\s*(?:和|与|到|->)\s*(?P<target>.+?)\s*之间\s*(?:插入|加入|添加|新增)\s*(?:一个|一個|个)?\s*(?P<node>.+?)\s*(?:节点)?$",
        r"(?:把|将)?\s*(?P<node>.+?)\s*(?:插到|插入到|加入到|加到|放到)\s*(?P<origin>.+?)\s*(?:和|与|到|->)\s*(?P<target>.+?)\s*之间\s*$",
        r"\binsert\s+(?:a\s+|an\s+)?(?P<node>.+?)\s+between\s+(?P<origin>.+?)\s+and\s+(?P<target>.+?)$",
        r"\badd\s+(?:a\s+|an\s+)?(?P<node>.+?)\s+between\s+(?P<origin>.+?)\s+and\s+(?P<target>.+?)$",
    )
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if not match:
            continue
        origin = _strip_value(match.group("origin"))
        target = _strip_value(match.group("target"))
        node = _strip_value(match.group("node"))
        if origin and target and node:
            return origin, target, node
    return None


def _plan_graph_insert_node_between(text: str, context: dict) -> dict | None:
    parts = _insert_node_between_parts(text)
    if parts is None:
        return None
    origin_phrase, target_phrase, node_phrase = parts
    add_plan = _plan_graph_add_node(f"添加 {node_phrase} 节点", context)
    if add_plan is None or len(add_plan.get("actions", [])) != 1:
        return None
    add_payload = dict(add_plan["actions"][0].get("payload", {}))
    node_type = add_payload.get("node_type")
    if not isinstance(node_type, str) or not node_type:
        return None
    widgets = dict(add_payload.get("widgets", {})) if isinstance(add_payload.get("widgets"), dict) else {}
    widgets.update(
        {
            key: value
            for key, value in _initial_widgets_for_new_node(node_type, text, context).items()
            if key not in widgets
        }
    )
    if widgets:
        add_payload["widgets"] = widgets

    nodes = _graph_nodes(context)
    links = _graph_links(context)
    origin = _find_node_for_phrase(nodes, origin_phrase, links)
    target = _find_node_for_phrase(nodes, target_phrase, links)
    if origin is None or target is None:
        return None
    inserted = _synthetic_node_for_type(context, node_type)
    incoming_slots = _infer_connect_slots(origin, inserted, origin_phrase, node_type)
    outgoing_slots = _infer_connect_slots(inserted, target, node_type, target_phrase)
    if incoming_slots is None or outgoing_slots is None:
        return None

    node_ref = "new_node"
    add_payload["ref"] = node_ref
    return {
        "summary": (
            f"Insert graph node {node_type} between node {origin.get('id')} "
            f"and node {target.get('id')}"
        ),
        "actions": [
            {"type": "graph.add_node", "payload": add_payload},
            {
                "type": "graph.connect",
                "payload": {
                    "origin_node_id": origin.get("id"),
                    "origin_slot": incoming_slots[0],
                    "target_node_ref": node_ref,
                    "target_slot": incoming_slots[1],
                },
            },
            {
                "type": "graph.connect",
                "payload": {
                    "origin_node_ref": node_ref,
                    "origin_slot": outgoing_slots[0],
                    "target_node_id": target.get("id"),
                    "target_slot": outgoing_slots[1],
                },
            },
        ],
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


def _find_node_for_phrase(
    nodes: list[dict],
    phrase: str,
    links: list[dict] | None = None,
) -> dict | None:
    cleaned = _strip_value(phrase).removesuffix("节点").removesuffix("node").strip()
    by_id = _find_node_by_id(nodes, _extract_node_id(cleaned))
    if by_id is not None:
        return by_id
    if _message_mentions_current_node(cleaned):
        selected = _selected_nodes(nodes)
        if len(selected) == 1:
            return selected[0]
    semantic = _find_node_by_semantic_label(nodes, cleaned, links)
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


def _replacement_parts(text: str) -> tuple[str, str] | None:
    lowered = text.lower()
    if not any(term in lowered or term in text for term in ("节点", "node")):
        return None
    patterns = (
        r"(?:把|将)?\s*(?P<old>.+?)\s*(?P<operator>替换成|替换为|换成|换为)\s*(?P<new>.+?)$",
        r"\breplace\s+(?P<old>.+?)\s+(?P<operator>with)\s+(?P<new>.+)$",
    )
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if not match:
            continue
        old_phrase = _strip_value(match.group("old"))
        new_phrase = _strip_value(match.group("new"))
        old_lowered = old_phrase.lower()
        old_is_node = (
            old_phrase.endswith("节点")
            or old_lowered.endswith("node")
            or _message_mentions_current_node(old_phrase)
        )
        if old_phrase and new_phrase and old_is_node:
            return old_phrase, new_phrase
    return None


def _node_type_for_replacement(context: dict, phrase: str) -> str | None:
    cleaned = _strip_value(phrase).removesuffix("节点").removesuffix("node").strip()
    registered = _registered_node_type_for_phrase(context, cleaned)
    if registered:
        return registered
    alias = _node_type_alias_to_add(cleaned)
    if alias is not None:
        return alias[0]
    if "/" in cleaned or "\\" in cleaned or re.search(r"\.[A-Za-z0-9]{2,6}$", cleaned):
        return None
    return (
        _node_type_from_exact_phrase(cleaned)
        or _extract_node_type_to_add(f"添加 {cleaned} 节点", context)
    )


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


def _slot_index_for_replacement(
    replacement: dict,
    replacement_slot_key: str,
    old_node: dict,
    old_slot_key: str,
    old_index: object,
) -> int | None:
    try:
        index = int(old_index)
    except (TypeError, ValueError):
        return None
    old_slots = _slot_rows(old_node, old_slot_key)
    if index < 0 or index >= len(old_slots):
        return None
    old_slot = old_slots[index]
    old_name = old_slot.get("name")
    if isinstance(old_name, str) and old_name:
        matched_by_name = _slot_index_for_hint(replacement, replacement_slot_key, old_name)
        if matched_by_name is not None:
            return matched_by_name
    matched_by_type = _slot_index_for_type(replacement, replacement_slot_key, _slot_type(old_slot))
    if matched_by_type is not None:
        return matched_by_type
    replacement_slots = _slot_rows(replacement, replacement_slot_key)
    if index < len(replacement_slots):
        return index
    return None


def _plan_graph_replace_node(text: str, context: dict) -> dict | None:
    parts = _replacement_parts(text)
    if parts is None:
        return None
    old_phrase, new_phrase = parts
    nodes = _graph_nodes(context)
    links = _graph_links(context)
    old_node = _find_node_for_phrase(nodes, old_phrase, links)
    if old_node is None:
        return None
    node_type = _node_type_for_replacement(context, new_phrase)
    if not node_type:
        return None

    replacement = _synthetic_node_for_type(context, node_type)
    node_ref = "replacement_node"
    add_payload = {"node_type": node_type, "ref": node_ref}
    pos = old_node.get("pos")
    if isinstance(pos, list) and len(pos) >= 2:
        add_payload["pos"] = [pos[0], pos[1]]

    old_node_id = old_node.get("id")
    actions = [{"type": "graph.add_node", "payload": add_payload}]
    for link in links:
        if str(link.get("target_id")) != str(old_node_id):
            continue
        target_slot = _slot_index_for_replacement(
            replacement,
            "inputs",
            old_node,
            "inputs",
            link.get("target_slot"),
        )
        if target_slot is None:
            continue
        actions.append(
            {
                "type": "graph.connect",
                "payload": {
                    "origin_node_id": link.get("origin_id"),
                    "origin_slot": link.get("origin_slot", 0),
                    "target_node_ref": node_ref,
                    "target_slot": target_slot,
                },
            }
        )
    for link in links:
        if str(link.get("origin_id")) != str(old_node_id):
            continue
        origin_slot = _slot_index_for_replacement(
            replacement,
            "outputs",
            old_node,
            "outputs",
            link.get("origin_slot"),
        )
        if origin_slot is None:
            continue
        actions.append(
            {
                "type": "graph.connect",
                "payload": {
                    "origin_node_ref": node_ref,
                    "origin_slot": origin_slot,
                    "target_node_id": link.get("target_id"),
                    "target_slot": link.get("target_slot", 0),
                },
            }
        )
    actions.append({"type": "graph.delete_node", "payload": {"node_id": old_node_id}})
    return {
        "summary": f"Replace graph node {old_node_id} with {node_type}",
        "actions": actions,
    }


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


def _reroute_connection_parts(text: str) -> tuple[str, str] | None:
    patterns = (
        r"(?:把|将)?\s*(?P<origin>.+?)\s*(?:重新接到|重新连接到|重接到|重连到|改接到|改连到)\s*(?P<target>.+)$",
        r"\b(?:reroute|reconnect)\s+(?P<origin>.+?)\s+(?:to|into)\s+(?P<target>.+)$",
    )
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if not match:
            continue
        origin = _strip_value(match.group("origin"))
        target = _strip_value(match.group("target"))
        if origin and target:
            return origin, target
    return None


def _split_node_phrase_and_slot_hint(phrase: str) -> tuple[str, str | None]:
    patterns = (
        r"(?P<node>.+?)\s*的\s*(?P<slot>[A-Za-z0-9_ -]+)(?:\s*(?:输入|输出|input|output))?$",
        r"(?P<node>.+?)\s+(?:slot|input|output)\s+(?P<slot>[A-Za-z0-9_ -]+)$",
    )
    for pattern in patterns:
        match = re.search(pattern, phrase, re.IGNORECASE)
        if not match:
            continue
        node_phrase = _strip_value(match.group("node"))
        slot_hint = _strip_value(match.group("slot"))
        if node_phrase and slot_hint:
            return node_phrase, slot_hint
    return phrase, None


def _find_reroute_target_node(
    nodes: list[dict],
    phrase: str,
    links: list[dict] | None = None,
) -> dict | None:
    explicit = _find_node_by_id(nodes, _extract_node_id(phrase))
    if explicit is not None:
        return explicit
    labelled = _find_node_by_label(nodes, phrase)
    if labelled is not None:
        return labelled
    return _find_node_for_phrase(nodes, phrase, links)


def _input_reroute_parts(text: str) -> tuple[str, str, str] | None:
    patterns = (
        r"(?:把|将)?\s*(?P<target>.+?)\s*的\s*(?P<slot>[A-Za-z0-9_ -]+)\s*(?:输入|input)\s*(?:重新接到|重新连接到|重接到|重连到|改接到|改连到)\s*(?P<origin>.+)$",
        r"\b(?:reroute|reconnect)\s+(?P<target>.+?)\s+(?P<slot>[A-Za-z0-9_ -]+)\s+input\s+(?:to|from)\s+(?P<origin>.+)$",
    )
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if not match:
            continue
        target = _strip_value(match.group("target"))
        slot = _strip_value(match.group("slot"))
        origin = _strip_value(match.group("origin"))
        if target and slot and origin:
            return target, slot, origin
    return None


def _plan_graph_reroute_input(text: str, context: dict) -> dict | None:
    parts = _input_reroute_parts(text)
    if parts is None:
        return None
    target_phrase, target_slot_hint, origin_phrase = parts
    nodes = _graph_nodes(context)
    links = _graph_links(context)
    target = _find_reroute_target_node(nodes, target_phrase, links)
    origin = _find_reroute_target_node(nodes, origin_phrase, links)
    if target is None or origin is None or target.get("id") == origin.get("id"):
        return None
    target_slot = _slot_index_for_hint(target, "inputs", target_slot_hint)
    if target_slot is None:
        return None
    target_inputs = _slot_rows(target, "inputs")
    target_type = _slot_type(target_inputs[target_slot]) if target_slot < len(target_inputs) else None
    origin_slot = _slot_index_for_type(origin, "outputs", target_type)
    if origin_slot is None:
        inferred = _infer_connect_slots(origin, target, origin_phrase, target_phrase)
        if inferred is None:
            return None
        origin_slot = inferred[0]
    return {
        "summary": f"Reroute input {target_slot} on node {target.get('id')}",
        "actions": [
            {
                "type": "graph.disconnect",
                "payload": {"target_node_id": target.get("id"), "target_slot": target_slot},
            },
            {
                "type": "graph.connect",
                "payload": {
                    "origin_node_id": origin.get("id"),
                    "origin_slot": origin_slot,
                    "target_node_id": target.get("id"),
                    "target_slot": target_slot,
                },
            },
        ],
    }


def _plan_graph_reroute_connection(text: str, context: dict) -> dict | None:
    parts = _reroute_connection_parts(text)
    if parts is None:
        return None
    origin_phrase_raw, target_phrase_raw = parts
    origin_phrase, origin_slot_hint = _split_node_phrase_and_slot_hint(origin_phrase_raw)
    target_phrase, target_slot_hint = _split_node_phrase_and_slot_hint(target_phrase_raw)

    nodes = _graph_nodes(context)
    links = _graph_links(context)
    origin = _find_node_for_phrase(nodes, origin_phrase, links)
    target = _find_reroute_target_node(nodes, target_phrase, links)
    if origin is None or target is None or origin.get("id") == target.get("id"):
        return None

    slots = _infer_connect_slots(origin, target, origin_phrase_raw, target_phrase_raw)
    if slots is None:
        return None
    origin_slot, target_slot = slots
    if origin_slot_hint is not None:
        explicit_origin_slot = _slot_index_for_hint(origin, "outputs", origin_slot_hint)
        if explicit_origin_slot is None:
            return None
        origin_slot = explicit_origin_slot
    if target_slot_hint is not None:
        explicit_target_slot = _slot_index_for_hint(target, "inputs", target_slot_hint)
        if explicit_target_slot is None:
            return None
        target_slot = explicit_target_slot

    return {
        "summary": f"Reroute node {origin.get('id')} to node {target.get('id')}",
        "actions": [
            {
                "type": "graph.disconnect",
                "payload": {"origin_node_id": origin.get("id"), "origin_slot": origin_slot},
            },
            {
                "type": "graph.connect",
                "payload": {
                    "origin_node_id": origin.get("id"),
                    "origin_slot": origin_slot,
                    "target_node_id": target.get("id"),
                    "target_slot": target_slot,
                },
            },
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


def _disconnect_input_plan(
    nodes: list[dict],
    links: list[dict],
    target_phrase: str,
    slot_hint: str,
) -> dict | None:
    target = _select_node(nodes, target_phrase, links)
    if target is None:
        target = _find_node_for_phrase(nodes, target_phrase, links)
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


def _disconnect_output_plan(
    nodes: list[dict],
    links: list[dict],
    origin_phrase: str,
    slot_hint: str,
) -> dict | None:
    origin = _find_node_for_phrase(nodes, origin_phrase, links)
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


def _disconnect_pair_plan(
    nodes: list[dict],
    links: list[dict],
    origin_phrase: str,
    target_phrase: str,
) -> dict | None:
    origin = _find_node_for_phrase(nodes, origin_phrase, links)
    target = _find_node_for_phrase(nodes, target_phrase, links)
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


def _disconnect_all_plan(
    nodes: list[dict],
    links: list[dict],
    node_phrase: str,
    scope: str,
) -> dict | None:
    node = _select_node(nodes, node_phrase, links)
    if node is None:
        node = _find_node_for_phrase(nodes, node_phrase, links)
    if node is None:
        return None
    payload_key = _disconnect_payload_key_for_scope(scope)
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
    links = _graph_links(context)
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
        plan = _disconnect_all_plan(nodes, links, match.group(1), scope)
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
        plan = _disconnect_pair_plan(nodes, links, match.group(1), match.group(2))
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
        plan = _disconnect_output_plan(nodes, links, match.group(1), match.group(2))
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
        plan = _disconnect_input_plan(nodes, links, match.group(1), match.group(2))
        if plan is not None:
            return plan
    return None


def _extract_url(text: str) -> str | None:
    match = re.search(r"https?://[^\s，。]+", text)
    if match:
        return match.group(0).rstrip(".,，。")
    return None


MODEL_SAVE_PATH_TYPES = {
    "checkpoints": "checkpoints",
    "checkpoint": "checkpoints",
    "loras": "lora",
    "lora": "lora",
    "vae": "vae",
    "text_encoders": "clip",
    "text_encoder": "clip",
    "clip": "clip",
    "controlnet": "controlnet",
    "controlnets": "controlnet",
    "upscale_models": "upscale",
    "upscalers": "upscale",
    "embeddings": "embedding",
    "diffusion_models": "diffusion_model",
    "unet": "diffusion_model",
}


def _url_basename(url: str) -> str | None:
    basename = os.path.basename(unquote(urlparse(url).path).rstrip("/"))
    return basename or None


def _extract_model_save_path(text: str, url: str) -> str | None:
    tail = text[text.find(url) + len(url):] if url in text else text
    match = re.search(
        r"(?:保存到|存到|下载到|放到|放进|到|save_path|save path|into|to)\s*([A-Za-z0-9_./-]+)",
        tail,
        re.IGNORECASE,
    )
    if match:
        return match.group(1).rstrip(".,，。")
    return None


def _extract_model_filename(text: str, url: str) -> str | None:
    match = re.search(
        r"(?:文件名|保存为|存为|(?<![A-Za-z0-9_])(?:filename|file name|save as|as)(?![A-Za-z0-9_]))\s*[:：=]?\s*([A-Za-z0-9_.-]+)",
        text,
        re.IGNORECASE,
    )
    if match:
        return match.group(1).rstrip(".,，。")
    return _url_basename(url)


def _extract_model_base(text: str) -> str | None:
    match = re.search(r"(?:base|基础模型)\s*[:：=]?\s*([A-Za-z0-9_.-]+)", text, re.IGNORECASE)
    if match:
        return match.group(1).rstrip(".,，。")
    return None


def _plan_model_install(text: str) -> dict | None:
    lowered = text.lower()
    if not any(term in lowered or term in text for term in ("安装", "下载", "install", "download")):
        return None
    if not any(term in lowered or term in text for term in ("模型", "model")):
        return None
    url = _extract_url(text)
    if not url:
        return None
    save_path = _extract_model_save_path(text, url)
    filename = _extract_model_filename(text, url)
    base = _extract_model_base(text)
    if not save_path or not filename or not base:
        return None
    model_type = MODEL_SAVE_PATH_TYPES.get(save_path.lower(), save_path)
    model = {
        "name": filename,
        "type": model_type,
        "base": base,
        "save_path": save_path,
        "url": url,
        "filename": filename,
        "ui_id": filename,
    }
    return {
        "summary": f"Install model {filename} through ComfyUI-Manager",
        "actions": [{"type": "model.install", "payload": {"model": model}}],
    }


def _plan_manager_queue_status(text: str) -> dict | None:
    lowered = text.lower()
    mentions_queue_or_progress = any(
        term in lowered or term in text for term in ("queue", "progress", "队列", "进度")
    )
    mentions_status = any(term in lowered or term in text for term in ("status", "状态"))
    mentions_manager = any(
        term in lowered or term in text
        for term in ("manager", "comfyui-manager", "节点管理器", "管理器")
    )
    mentions_install_download = any(
        term in lowered or term in text for term in ("install", "download", "安装", "下载")
    )
    mentions_package_domain = any(
        term in lowered or term in text
        for term in ("model", "custom node", "custom nodes", "模型", "自定义节点", "插件", "扩展")
    )
    mentions_read = any(
        term in lowered or term in text
        for term in ("查看", "看看", "检查", "查询", "read", "check", "status", "状态", "progress", "进度")
    )
    if not (mentions_queue_or_progress or mentions_status):
        return None
    if not mentions_read:
        return None
    if not (mentions_manager or mentions_install_download or mentions_package_domain):
        return None
    if mentions_status and not (mentions_queue_or_progress or mentions_manager or mentions_install_download):
        return None
    return {
        "summary": "Check ComfyUI-Manager queue status",
        "actions": [{"type": "manager.queue_status", "payload": {}}],
    }


def _plan_manager_queue_control(text: str) -> dict | None:
    lowered = text.lower()
    mentions_manager = any(
        term in lowered or term in text
        for term in ("manager", "comfyui-manager", "节点管理器", "管理器")
    )
    mentions_queue = any(term in lowered or term in text for term in ("queue", "队列"))
    if not (mentions_manager and mentions_queue):
        return None
    if any(
        term in lowered or term in text
        for term in ("开始", "启动", "执行", "start", "run", "process")
    ):
        return {
            "summary": "Start ComfyUI-Manager queue",
            "actions": [{"type": "manager.queue_start", "payload": {}}],
        }
    if any(
        term in lowered or term in text
        for term in ("清空", "清除", "清掉", "重置", "取消", "reset", "clear")
    ):
        return {
            "summary": "Reset ComfyUI-Manager queue",
            "actions": [{"type": "manager.queue_reset", "payload": {}}],
        }
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
    match = re.search(
        r"(?:安装|禁用|启用|更新|升级|重装|重新安装|修复|卸载|移除|删除|切换|install|disable|enable|update|reinstall|fix|uninstall|remove|delete|switch)?\s*"
        r"([A-Za-z0-9_.:/-]+)\s*(?:custom\s+nodes?|自定义节点|节点管理器|manager(?:\s+node)?|插件|扩展|节点)",
        text,
        re.IGNORECASE,
    )
    if match:
        return match.group(1).rstrip(".,，。")
    return None


def _extract_custom_node_version(text: str) -> str | None:
    match = re.search(
        r"(?:版本|version|ver|tag)\s*([A-Za-z0-9_.:-]+)",
        text,
        re.IGNORECASE,
    )
    if match:
        return match.group(1).rstrip(".,，。")
    return None


def _mentions_custom_node(text: str) -> bool:
    lowered = text.lower()
    return any(marker in lowered or marker in text for marker in CUSTOM_NODE_MARKERS)


def _extract_custom_node_search_query(text: str) -> str | None:
    patterns = (
        r"(?:搜索|查找|找一下|search|find)\s*(?:custom\s+nodes?|自定义节点|节点管理器|manager(?:\s+node)?|插件|扩展|节点)?\s+(?P<query>.+)$",
        r"(?:custom\s+nodes?|自定义节点|节点管理器|manager(?:\s+node)?|插件|扩展|节点)\s*(?:搜索|查找|search|find)\s+(?P<query>.+)$",
    )
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if not match:
            continue
        query = _strip_value(match.group("query"))
        query = re.sub(r"\s*(?:custom\s+nodes?|自定义节点|节点管理器|manager(?:\s+node)?|插件|扩展|节点)\s*$", "", query, flags=re.IGNORECASE)
        query = _strip_value(query)
        if query:
            return query
    return None


def _plan_custom_node_read_action(text: str) -> dict | None:
    if not _mentions_custom_node(text):
        return None
    lowered = text.lower()
    mentions_search = any(term in lowered or term in text for term in ("搜索", "查找", "找一下", "search", "find"))
    if mentions_search:
        query = _extract_custom_node_search_query(text)
        if query:
            return {
                "summary": f"Search custom nodes for {query}",
                "actions": [{"type": "custom_node.search", "payload": {"query": query}}],
            }

    mentions_read = any(
        term in lowered or term in text
        for term in ("查看", "看看", "列出", "列表", "清单", "show", "list")
    )
    mentions_installed = any(term in lowered or term in text for term in ("已安装", "installed"))
    if mentions_read and mentions_installed:
        return {
            "summary": "List installed custom nodes",
            "actions": [{"type": "custom_node.list", "payload": {"scope": "installed"}}],
        }
    return None


def _mentions_missing_workflow_node_install(text: str) -> bool:
    lowered = text.lower()
    mentions_missing = any(
        term in lowered or term in text
        for term in ("missing", "not installed", "缺失", "未安装", "报红", "红色")
    )
    mentions_node = any(term in lowered or term in text for term in ("node", "节点"))
    mentions_fix = any(
        term in lowered or term in text
        for term in ("install", "fix", "repair", "resolve", "安装", "装上", "修复", "解决")
    )
    mentions_workflow = any(
        term in lowered or term in text
        for term in ("workflow", "graph", "当前工作流", "这个工作流", "当前图", "画布")
    )
    return mentions_missing and mentions_node and mentions_fix and mentions_workflow


def _manager_id_for_missing_node(node: dict) -> str | None:
    properties = node.get("properties")
    if isinstance(properties, dict):
        for key in ("cnr_id", "aux_id"):
            value = properties.get(key)
            if isinstance(value, str):
                cleaned = _strip_value(value)
                if cleaned and cleaned != "comfy-core":
                    return cleaned
    node_type = node.get("type")
    if isinstance(node_type, str):
        cleaned = _strip_value(node_type)
        if cleaned:
            return cleaned
    return None


def _missing_workflow_custom_node_ids(context: dict) -> list[str]:
    registered = _graph_registered_node_type_names(context)
    if not registered:
        return []
    node_ids = []
    seen = set()
    for node in _graph_nodes(context):
        node_type = node.get("type")
        if not isinstance(node_type, str) or not node_type or node_type in registered:
            continue
        node_id = _manager_id_for_missing_node(node)
        if not node_id or node_id in seen:
            continue
        seen.add(node_id)
        node_ids.append(node_id)
    return node_ids


def _plan_missing_workflow_custom_nodes(text: str, context: dict) -> dict | None:
    if not _mentions_missing_workflow_node_install(text):
        return None
    node_ids = _missing_workflow_custom_node_ids(context)
    if not node_ids:
        return None
    return {
        "summary": "Install missing custom nodes from current workflow through ComfyUI-Manager",
        "actions": [
            {
                "type": "custom_node.install",
                "payload": {"method": "manager_queue", "node": _manager_queue_node_payload(node_id)},
            }
            for node_id in node_ids
        ],
    }


def _plan_custom_node_manager_action(text: str) -> dict | None:
    if not _mentions_custom_node(text):
        return None
    lowered = text.lower()
    if any(term in lowered or term in text for term in ("全部", "所有", "已安装", "all", "installed")) and any(
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
    elif any(term in lowered or term in text for term in ("switch", "切换")):
        action_type = "custom_node.switch_version"
    elif any(term in lowered or term in text for term in ("uninstall", "remove", "卸载", "移除")):
        action_type = "custom_node.uninstall"
    elif any(term in lowered or term in text for term in ("update", "更新", "升级")):
        action_type = "custom_node.update"

    if action_type is None:
        return None
    node_id = _extract_custom_node_id(text)
    if not node_id:
        return None
    if action_type == "custom_node.switch_version":
        version = _extract_custom_node_version(text)
        if not version:
            return None
        return {
            "summary": f"Switch custom node {node_id} to version {version}",
            "actions": [
                {"type": action_type, "payload": {"id": node_id, "version": version}}
            ],
        }
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
    mentions_restart = "重启" in text or "restart" in lowered
    if not mentions_restart:
        return False
    return _mentions_custom_node(text) or any(
        term in lowered or term in text for term in ("comfyui", "容器", "container", "服务")
    )


def _with_restart_followup(plan: dict, text: str) -> dict:
    if not _mentions_service_restart(text):
        return plan
    return {
        "summary": f"{plan['summary']} and restart ComfyUI",
        "actions": [*plan["actions"], _restart_container_action()],
    }


def _plan_update_comfyui(text: str) -> dict | None:
    lowered = text.lower()
    mentions_comfyui = "comfyui" in lowered
    mentions_update = any(term in lowered or term in text for term in ("update", "更新", "升级"))
    mentions_core = any(
        term in lowered or term in text
        for term in ("comfyui 本体", "comfyui core", "comfyui itself", "comfyui 主程序")
    )
    if not (mentions_comfyui and mentions_update and mentions_core):
        return None
    return _with_restart_followup(
        {
            "summary": "Update ComfyUI through ComfyUI-Manager",
            "actions": [{"type": "service.update_comfyui", "payload": {}}],
        },
        text,
    )


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


def _plan_restore_original_container(text: str) -> dict | None:
    lowered = text.lower()
    mentions_restore = any(
        term in lowered or term in text
        for term in ("回滚", "恢复原始", "恢复原来的", "restore original", "rollback", "prevcfg")
    )
    mentions_container_config = any(
        term in lowered or term in text
        for term in ("comfyui", "容器", "container", "配置", "config", "prevcfg")
    )
    if not (mentions_restore and mentions_container_config):
        return None
    return {
        "summary": "Restore original ComfyUI container configuration",
        "actions": [{"type": "service.restore_original", "payload": {}}],
    }


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
    if any(term in lowered or term in text for term in ("disable", "禁用", "停用", "关闭", "关掉")):
        action_type = "custom_node.disable"
    elif any(term in lowered or term in text for term in ("enable", "启用", "开启", "打开", "恢复")):
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


def _plan_custom_node_action(text: str, context: dict) -> dict | None:
    missing_plan = _plan_missing_workflow_custom_nodes(text, context)
    if missing_plan is not None:
        return _with_restart_followup(missing_plan, text)
    read_plan = _plan_custom_node_read_action(text)
    if read_plan is not None:
        return read_plan
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
    if match:
        return match.group(0)
    lowered = text.lower()
    aliases = (
        (("bf16 vae", "bf16-vae", "bf16_vae"), "--bf16-vae"),
        (
            ("cuda malloc", "cudamalloc", "cuda-malloc", "cuda_malloc"),
            "--disable-cuda-malloc",
        ),
        (
            ("pinned memory", "pinned-memory", "pinned_memory", "pin memory"),
            "--disable-pinned-memory",
        ),
        (
            ("pytorch cross attention", "cross attention", "cross-attention", "sdpa"),
            "--use-pytorch-cross-attention",
        ),
        (("auto launch", "auto-launch", "自动打开浏览器"), "--disable-auto-launch"),
        (("reserve-vram", "reserve vram", "预留显存", "保留显存"), "--reserve-vram"),
    )
    for triggers, flag in aliases:
        if any(trigger in lowered or trigger in text for trigger in triggers):
            return flag
    return None


def _trim_command_value_tail(value: str) -> str:
    patterns = (
        r"\s*(?:并|然后|再)(?:应用|套用|重建|重启|restart|apply).*$",
        r"\s+and\s+(?:apply|restart|rebuild).*$",
    )
    cleaned = value
    for pattern in patterns:
        cleaned = re.sub(pattern, "", cleaned, flags=re.IGNORECASE)
    return _strip_value(cleaned)


def _extract_command_value(text: str) -> str | None:
    value = _extract_value_after_set(text)
    if value:
        value = _trim_command_value_tail(value)
        return value or None
    return None


def _plan_compose_command_value(text: str) -> dict | None:
    flag = _extract_command_flag(text)
    if not flag:
        return None
    lowered = text.lower()
    if not any(
        term in lowered or term in text
        for term in ("compose", "comfyui", "command", "flag", "启动参数", "参数")
    ):
        return None
    value = _extract_command_value(text)
    if not value:
        return None
    return {
        "summary": f"Set compose command value {flag} to {value}",
        "actions": [
            {"type": "compose.set_command_value", "payload": {"flag": flag, "value": value}}
        ],
    }


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
        for term in ("禁用", "关闭", "关掉", "移除", "删除", "去掉", "disable", "remove", "delete")
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


def _plan_service_logs(text: str) -> dict | None:
    lowered = text.lower()
    mentions_logs = any(term in lowered or term in text for term in ("log", "logs", "日志"))
    if not mentions_logs:
        return None
    mentions_service = any(
        term in lowered or term in text for term in ("comfyui", "容器", "container", "服务")
    )
    mentions_recent = any(
        term in lowered or term in text for term in ("recent", "latest", "tail", "最近", "最后")
    )
    if not (mentions_service or mentions_recent):
        return None
    return {
        "summary": "Read recent ComfyUI container logs",
        "actions": [
            {"type": "service.logs", "payload": {"container": "comfyui-gb10", "tail": 80}}
        ],
    }


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
        restore_original_plan = _plan_restore_original_container(text)
        if restore_original_plan is not None:
            return restore_original_plan
        graph_replace_plan = _plan_graph_replace_node(graph_text, context)
        if graph_replace_plan is not None:
            return _combine_with_followup_plans(graph_replace_plan, followup_plans, graph_text, text)
        graph_neighborhood_plan = _plan_graph_neighborhood_action(graph_text, context)
        if graph_neighborhood_plan is not None:
            return _combine_with_followup_plans(
                graph_neighborhood_plan, followup_plans, graph_text, text
            )
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
        graph_collapsed_plan = _plan_graph_set_collapsed(graph_text, context)
        if graph_collapsed_plan is not None:
            return _combine_with_followup_plans(
                graph_collapsed_plan, followup_plans, graph_text, text
            )
        graph_size_plan = _plan_graph_set_size(graph_text, context)
        if graph_size_plan is not None:
            return _combine_with_followup_plans(graph_size_plan, followup_plans, graph_text, text)
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
        graph_auto_layout_plan = _plan_graph_auto_layout(graph_text, context)
        if graph_auto_layout_plan is not None:
            return _combine_with_followup_plans(
                graph_auto_layout_plan, followup_plans, graph_text, text
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
        graph_insert_plan = _plan_graph_insert_node_between(graph_text, context)
        if graph_insert_plan is not None:
            return _combine_with_followup_plans(graph_insert_plan, followup_plans, graph_text, text)
        graph_adjacent_add_plan = _plan_graph_add_adjacent_node(graph_text, context)
        if graph_adjacent_add_plan is not None:
            return _combine_with_followup_plans(
                graph_adjacent_add_plan, followup_plans, graph_text, text
            )
        graph_add_connect_plan = _plan_graph_add_node_and_connect(graph_text, context)
        if graph_add_connect_plan is not None:
            return _combine_with_followup_plans(
                graph_add_connect_plan, followup_plans, graph_text, text
            )
        graph_input_reroute_plan = _plan_graph_reroute_input(graph_text, context)
        if graph_input_reroute_plan is not None:
            return _combine_with_followup_plans(
                graph_input_reroute_plan, followup_plans, graph_text, text
            )
        graph_reroute_plan = _plan_graph_reroute_connection(graph_text, context)
        if graph_reroute_plan is not None:
            return _combine_with_followup_plans(
                graph_reroute_plan, followup_plans, graph_text, text
            )
        graph_connect_plan = _plan_graph_connect(graph_text, context)
        if graph_connect_plan is not None:
            return _combine_with_followup_plans(graph_connect_plan, followup_plans, graph_text, text)
        graph_add_plan = _plan_graph_add_node(graph_text, context)
        if graph_add_plan is not None:
            return _combine_with_followup_plans(graph_add_plan, followup_plans, graph_text, text)
        prompt_role_plan = _plan_prompt_role_assignments(graph_text, context)
        if prompt_role_plan is not None:
            return _combine_with_followup_plans(prompt_role_plan, followup_plans, graph_text, text)
        image_generation_plan = _plan_image_generation_request(graph_text, context)
        if image_generation_plan is not None:
            return _combine_with_followup_plans(
                image_generation_plan, followup_plans, graph_text, text
            )
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
        manager_queue_control_plan = _plan_manager_queue_control(text)
        if manager_queue_control_plan is not None:
            return manager_queue_control_plan
        manager_queue_status_plan = _plan_manager_queue_status(text)
        if manager_queue_status_plan is not None:
            return manager_queue_status_plan
        model_install_plan = _plan_model_install(text)
        if model_install_plan is not None:
            return _with_restart_followup(model_install_plan, text)
        custom_node_plan = _plan_custom_node_action(text, context)
        if custom_node_plan is not None:
            return custom_node_plan
        update_comfyui_plan = _plan_update_comfyui(text)
        if update_comfyui_plan is not None:
            return update_comfyui_plan
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
                "actions": [
                    {
                        "type": "compose.set_command_value",
                        "payload": {"flag": "--reserve-vram", "value": value},
                    }
                ],
            }
        compose_value_plan = _plan_compose_command_value(text)
        if compose_value_plan is not None:
            return compose_value_plan
        compose_flag_plan = _plan_compose_command_flag(text)
        if compose_flag_plan is not None:
            return compose_flag_plan
        compose_up_plan = _plan_compose_up(text)
        if compose_up_plan is not None:
            return compose_up_plan
        prerender_free_memory_plan = _plan_prerender_free_memory(text)
        if prerender_free_memory_plan is not None:
            return prerender_free_memory_plan
        service_logs_plan = _plan_service_logs(text)
        if service_logs_plan is not None:
            return service_logs_plan
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
