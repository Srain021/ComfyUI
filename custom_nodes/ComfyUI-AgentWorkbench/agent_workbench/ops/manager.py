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


def manager_request_for_action(action: dict) -> dict:
    if not isinstance(action, dict):
        raise ManagerActionError("manager action must be an object")
    action_type = action.get("type")
    payload = _require_payload(action)
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
        return {"method": "POST", "path": "/manager/queue/install", "json": dict(node)}
    if action_type == "custom_node.disable":
        return {
            "method": "POST",
            "path": "/manager/queue/disable",
            "json": _manager_node_payload(payload),
        }
    if action_type == "custom_node.enable":
        node = _manager_node_payload(payload)
        node["skip_post_install"] = True
        return {"method": "POST", "path": "/manager/queue/install", "json": node}
    if action_type == "custom_node.switch_version":
        return {
            "method": "POST",
            "path": "/manager/queue/install",
            "json": _switch_version_payload(payload),
        }
    if action_type == "service.update_comfyui":
        return {"method": "POST", "path": "/manager/queue/update_comfyui"}
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
        return {"method": "POST", "path": path, "json": _manager_node_payload(payload)}
    if action_type == "custom_node.update_all":
        return {
            "method": "POST",
            "path": "/manager/queue/update_all",
            "json": {"mode": payload.get("mode", "default")},
        }
    raise ManagerActionError(f"unsupported manager action: {action_type}")
