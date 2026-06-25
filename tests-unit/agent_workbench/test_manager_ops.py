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
    assert request["json"]["files"] == []


def test_manager_enable_request_skips_post_install():
    request = manager_request_for_action(
        {"type": "custom_node.enable", "payload": {"id": "ComfyUI-TestNode"}}
    )

    assert request["path"] == "/manager/queue/install"
    assert request["json"]["id"] == "ComfyUI-TestNode"
    assert request["json"]["skip_post_install"] is True


def test_manager_rejects_invalid_git_url():
    with pytest.raises(ManagerActionError, match="http or https"):
        manager_request_for_action(
            {
                "type": "custom_node.install",
                "payload": {"method": "git_url", "url": "file:///tmp/node"},
            }
        )
