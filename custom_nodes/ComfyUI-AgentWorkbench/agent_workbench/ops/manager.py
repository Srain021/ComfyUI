from urllib.parse import urlparse


class ManagerActionError(ValueError):
    pass


def _require_url(url: str) -> str:
    if not isinstance(url, str):
        raise ManagerActionError("custom node git_url must be a string")
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ManagerActionError("custom node git_url must be http or https")
    return url


def _require_payload(action: dict) -> dict:
    payload = action.get("payload", {})
    if not isinstance(payload, dict):
        raise ManagerActionError("custom node payload must be an object")
    return payload


def _require_node_id(payload: dict) -> str:
    node_id = payload.get("id")
    if not isinstance(node_id, str) or not node_id:
        raise ManagerActionError("custom node action requires id")
    return node_id


def _manager_node_payload(payload: dict) -> dict:
    node_id = _require_node_id(payload)
    files = payload.get("files")
    if not isinstance(files, list) or not files:
        files = [payload.get("path", node_id)]
    return {
        "id": node_id,
        "version": payload.get("version", "unknown"),
        "ui_id": payload.get("ui_id", node_id),
        "files": files,
        "channel": payload.get("channel", "default"),
        "mode": payload.get("mode", "cache"),
    }


def _switch_version_payload(payload: dict) -> dict:
    version = payload.get("version")
    if not isinstance(version, str) or not version:
        raise ManagerActionError("custom node switch_version requires version")
    node = _manager_node_payload({**payload, "version": version})
    node["selected_version"] = version
    return node


def _manager_model_payload(payload: dict) -> dict:
    model = payload.get("model")
    if not isinstance(model, dict):
        raise ManagerActionError("model install requires model object")
    result = {}
    for key in ("name", "type", "base", "save_path", "filename"):
        value = model.get(key)
        if not isinstance(value, str) or not value:
            raise ManagerActionError(f"model install requires {key}")
        result[key] = value
    result["url"] = _require_url(model.get("url"))
    ui_id = model.get("ui_id")
    result["ui_id"] = ui_id if isinstance(ui_id, str) and ui_id else result["filename"]
    return result


def _queue_request(path: str, json: dict | None = None) -> dict:
    request = {"method": "POST", "path": path, "start_queue": True}
    if json is not None:
        request["json"] = json
    return request


def _response_limit(payload: dict, default: int = 50) -> int:
    raw = payload.get("limit", default)
    if isinstance(raw, bool):
        return default
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return default
    return max(1, min(value, 200))


def _require_query(payload: dict) -> str:
    query = payload.get("query")
    if not isinstance(query, str) or not query.strip():
        raise ManagerActionError("custom node search requires query")
    return query.strip()


def manager_request_for_action(action: dict) -> dict:
    if not isinstance(action, dict):
        raise ManagerActionError("manager action must be an object")
    action_type = action.get("type")
    payload = _require_payload(action)
    if action_type == "manager.queue_status":
        return {"method": "GET", "path": "/manager/queue/status"}
    if action_type == "manager.queue_start":
        return {"method": "POST", "path": "/manager/queue/start"}
    if action_type == "manager.queue_reset":
        return {"method": "POST", "path": "/manager/queue/reset"}
    if action_type == "custom_node.list":
        scope = payload.get("scope", "installed")
        if scope != "installed":
            raise ManagerActionError("custom node list only supports installed scope")
        return {
            "method": "GET",
            "path": "/customnode/installed",
            "response_filter": {
                "type": "custom_node.list",
                "scope": "installed",
                "limit": _response_limit(payload),
            },
        }
    if action_type == "custom_node.search":
        return {
            "method": "GET",
            "path": "/customnode/getlist?mode=default&skip_update=true",
            "response_filter": {
                "type": "custom_node.search",
                "query": _require_query(payload),
                "limit": _response_limit(payload, default=20),
            },
        }
    if action_type == "model.install":
        return _queue_request("/manager/queue/install_model", _manager_model_payload(payload))
    if action_type == "custom_node.install" and payload.get("method") == "git_url":
        return {
            "method": "POST",
            "path": "/customnode/install/git_url",
            "body": _require_url(payload.get("url")),
        }
    if action_type == "custom_node.install" and payload.get("method") == "manager_queue":
        node = payload.get("node")
        if not isinstance(node, dict):
            raise ManagerActionError("manager_queue install requires node object")
        return _queue_request("/manager/queue/install", dict(node))
    if action_type == "custom_node.disable":
        return _queue_request("/manager/queue/disable", _manager_node_payload(payload))
    if action_type == "custom_node.enable":
        node = _manager_node_payload(payload)
        node["skip_post_install"] = True
        return _queue_request("/manager/queue/install", node)
    if action_type == "custom_node.switch_version":
        return _queue_request("/manager/queue/install", _switch_version_payload(payload))
    if action_type == "service.update_comfyui":
        return _queue_request("/manager/queue/update_comfyui")
    if action_type in {
        "custom_node.update",
        "custom_node.reinstall",
        "custom_node.fix",
        "custom_node.uninstall",
    }:
        path = {
            "custom_node.update": "/manager/queue/update",
            "custom_node.reinstall": "/manager/queue/reinstall",
            "custom_node.fix": "/manager/queue/fix",
            "custom_node.uninstall": "/manager/queue/uninstall",
        }[action_type]
        return _queue_request(path, _manager_node_payload(payload))
    if action_type == "custom_node.update_all":
        return _queue_request("/manager/queue/update_all", {"mode": payload.get("mode", "default")})
    raise ManagerActionError(f"unsupported manager action: {action_type}")
