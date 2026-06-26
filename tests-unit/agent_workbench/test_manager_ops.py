import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
AGENT_ROOT = REPO_ROOT / "custom_nodes" / "ComfyUI-AgentWorkbench"
sys.path.insert(0, str(AGENT_ROOT))

from agent_workbench.ops.manager import ManagerActionError, manager_request_for_action


def test_manager_install_git_url_request():
    request = manager_request_for_action(
        {
            "type": "custom_node.install",
            "payload": {"method": "git_url", "url": "https://example.com/node.git"},
        }
    )

    assert request["path"] == "/customnode/install/git_url"
    assert request["method"] == "POST"
    assert request["body"] == "https://example.com/node.git"


def test_manager_disable_request_uses_queue_disable():
    request = manager_request_for_action(
        {
            "type": "custom_node.disable",
            "payload": {
                "id": "ComfyUI-TestNode",
                "version": "1.0.0",
                "ui_id": "ComfyUI-TestNode",
            },
        }
    )

    assert request["path"] == "/manager/queue/disable"
    assert request["json"]["id"] == "ComfyUI-TestNode"
    assert request["json"]["files"] == ["ComfyUI-TestNode"]


def test_manager_update_request_uses_queue_update():
    request = manager_request_for_action(
        {"type": "custom_node.update", "payload": {"id": "ComfyUI-TestNode"}}
    )

    assert request["path"] == "/manager/queue/update"
    assert request["json"] == {
        "id": "ComfyUI-TestNode",
        "version": "unknown",
        "ui_id": "ComfyUI-TestNode",
        "files": ["ComfyUI-TestNode"],
        "channel": "default",
        "mode": "cache",
    }


def test_manager_reinstall_request_uses_queue_reinstall():
    request = manager_request_for_action(
        {"type": "custom_node.reinstall", "payload": {"id": "ComfyUI-TestNode"}}
    )

    assert request["path"] == "/manager/queue/reinstall"
    assert request["json"]["id"] == "ComfyUI-TestNode"
    assert request["json"]["files"] == ["ComfyUI-TestNode"]


def test_manager_fix_request_uses_queue_fix():
    request = manager_request_for_action(
        {"type": "custom_node.fix", "payload": {"id": "ComfyUI-BrokenNode"}}
    )

    assert request["path"] == "/manager/queue/fix"
    assert request["json"]["id"] == "ComfyUI-BrokenNode"
    assert request["json"]["files"] == ["ComfyUI-BrokenNode"]


def test_manager_uninstall_request_uses_queue_uninstall():
    request = manager_request_for_action(
        {"type": "custom_node.uninstall", "payload": {"id": "ComfyUI-TestNode"}}
    )

    assert request["path"] == "/manager/queue/uninstall"
    assert request["json"]["id"] == "ComfyUI-TestNode"
    assert request["json"]["files"] == ["ComfyUI-TestNode"]


def test_manager_switch_version_request_uses_queue_install_with_selected_version():
    request = manager_request_for_action(
        {
            "type": "custom_node.switch_version",
            "payload": {"id": "ComfyUI-TestNode", "version": "1.2.3"},
        }
    )

    assert request["method"] == "POST"
    assert request["path"] == "/manager/queue/install"
    assert request["json"]["id"] == "ComfyUI-TestNode"
    assert request["json"]["version"] == "1.2.3"
    assert request["json"]["selected_version"] == "1.2.3"


def test_manager_update_comfyui_request_uses_queue_update_comfyui_without_body():
    request = manager_request_for_action({"type": "service.update_comfyui", "payload": {}})

    assert request == {
        "method": "POST",
        "path": "/manager/queue/update_comfyui",
        "start_queue": True,
    }


def test_manager_update_all_request_uses_default_mode():
    request = manager_request_for_action(
        {"type": "custom_node.update_all", "payload": {}}
    )

    assert request == {
        "method": "POST",
        "path": "/manager/queue/update_all",
        "start_queue": True,
        "json": {"mode": "default"},
    }


def test_manager_enable_request_skips_post_install():
    request = manager_request_for_action(
        {"type": "custom_node.enable", "payload": {"id": "ComfyUI-TestNode"}}
    )

    assert request["path"] == "/manager/queue/install"
    assert request["json"]["id"] == "ComfyUI-TestNode"
    assert request["json"]["skip_post_install"] is True


def test_manager_queue_install_request_uses_node_payload():
    request = manager_request_for_action(
        {
            "type": "custom_node.install",
            "payload": {
                "method": "manager_queue",
                "node": {
                    "id": "ComfyUI-Impact-Pack",
                    "version": "unknown",
                    "ui_id": "ComfyUI-Impact-Pack",
                    "files": ["ComfyUI-Impact-Pack"],
                    "channel": "default",
                    "mode": "cache",
                },
            },
        }
    )

    assert request == {
        "method": "POST",
        "path": "/manager/queue/install",
        "start_queue": True,
        "json": {
            "id": "ComfyUI-Impact-Pack",
            "version": "unknown",
            "ui_id": "ComfyUI-Impact-Pack",
            "files": ["ComfyUI-Impact-Pack"],
            "channel": "default",
            "mode": "cache",
        },
    }


def test_manager_model_install_request_uses_queue_install_model():
    request = manager_request_for_action(
        {
            "type": "model.install",
            "payload": {
                "model": {
                    "name": "hero.safetensors",
                    "type": "checkpoints",
                    "base": "SDXL",
                    "save_path": "checkpoints",
                    "url": "https://example.com/models/hero.safetensors",
                    "filename": "hero.safetensors",
                    "ui_id": "hero.safetensors",
                }
            },
        }
    )

    assert request == {
        "method": "POST",
        "path": "/manager/queue/install_model",
        "start_queue": True,
        "json": {
            "name": "hero.safetensors",
            "type": "checkpoints",
            "base": "SDXL",
            "save_path": "checkpoints",
            "url": "https://example.com/models/hero.safetensors",
            "filename": "hero.safetensors",
            "ui_id": "hero.safetensors",
        },
    }


def test_manager_queue_status_request_does_not_start_queue():
    request = manager_request_for_action({"type": "manager.queue_status", "payload": {}})

    assert request == {"method": "GET", "path": "/manager/queue/status"}


def test_manager_custom_node_list_request_uses_installed_endpoint():
    request = manager_request_for_action(
        {"type": "custom_node.list", "payload": {"scope": "installed"}}
    )

    assert request == {
        "method": "GET",
        "path": "/customnode/installed",
        "response_filter": {"type": "custom_node.list", "scope": "installed", "limit": 50},
    }


def test_manager_custom_node_search_request_uses_cached_custom_node_list():
    request = manager_request_for_action(
        {"type": "custom_node.search", "payload": {"query": "Impact Pack", "limit": 12}}
    )

    assert request == {
        "method": "GET",
        "path": "/customnode/getlist?mode=default&skip_update=true",
        "response_filter": {"type": "custom_node.search", "query": "Impact Pack", "limit": 12},
    }


def test_manager_queue_start_request_uses_queue_start_endpoint():
    request = manager_request_for_action({"type": "manager.queue_start", "payload": {}})

    assert request == {"method": "POST", "path": "/manager/queue/start"}


def test_manager_queue_reset_request_uses_queue_reset_endpoint():
    request = manager_request_for_action({"type": "manager.queue_reset", "payload": {}})

    assert request == {"method": "POST", "path": "/manager/queue/reset"}


def test_manager_model_install_rejects_invalid_url():
    with pytest.raises(ManagerActionError, match="http or https"):
        manager_request_for_action(
            {
                "type": "model.install",
                "payload": {
                    "model": {
                        "name": "hero.safetensors",
                        "type": "checkpoints",
                        "base": "SDXL",
                        "save_path": "checkpoints",
                        "url": "file:///tmp/hero.safetensors",
                        "filename": "hero.safetensors",
                    }
                },
            }
        )


def test_manager_rejects_invalid_git_url():
    with pytest.raises(ManagerActionError, match="http or https"):
        manager_request_for_action(
            {
                "type": "custom_node.install",
                "payload": {"method": "git_url", "url": "file:///tmp/node"},
            }
        )
