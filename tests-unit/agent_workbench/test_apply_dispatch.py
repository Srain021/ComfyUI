import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
AGENT_ROOT = REPO_ROOT / "custom_nodes" / "ComfyUI-AgentWorkbench"
sys.path.insert(0, str(AGENT_ROOT))

from agent_workbench.actions import apply_plan, dry_run_plan
from agent_workbench.executor import RecordingExecutor


COMPOSE_TEXT = (
    "services:\n"
    "  comfyui-gb10:\n"
    "    command:\n"
    "      - main.py\n"
    "      - --reserve-vram\n"
    "      - \"8\"  # keep this comment\n"
)


def test_apply_dispatches_confirmed_compose_change(tmp_path):
    compose_path = tmp_path / "dgx_spark_ltx_setup" / "docker-compose.yml"
    compose_path.parent.mkdir(parents=True)
    compose_path.write_text(COMPOSE_TEXT, encoding="utf-8")
    dry_run = dry_run_plan(
        {
            "summary": "Set reserve vram",
            "actions": [{"type": "compose.set_reserve_vram", "payload": {"value": "10"}}],
        }
    )
    plan = dict(dry_run["plan"])
    plan["confirmed"] = True
    executor = RecordingExecutor()

    result = apply_plan(
        plan,
        approved_hash=dry_run["plan"]["plan_hash"],
        root=tmp_path,
        executor=executor,
    )

    assert result["ok"] is True
    assert result["status"] == "applied"
    assert result["applied"][0]["type"] == "compose.set_reserve_vram"
    assert "- \"10\"  # keep this comment" in compose_path.read_text(encoding="utf-8")
    assert executor.commands[-1] == [
        "docker",
        "compose",
        "-f",
        "dgx_spark_ltx_setup/docker-compose.yml",
        "up",
        "-d",
    ]


def test_custom_node_apply_returns_manager_request_for_frontend_execution(tmp_path):
    dry_run = dry_run_plan(
        {
            "summary": "Install node",
            "actions": [
                {
                    "type": "custom_node.install",
                    "payload": {"method": "git_url", "url": "https://example.com/node.git"},
                }
            ],
        }
    )
    plan = dict(dry_run["plan"])
    plan["confirmed"] = True
    executor = RecordingExecutor()

    result = apply_plan(
        plan,
        approved_hash=dry_run["plan"]["plan_hash"],
        root=tmp_path,
        executor=executor,
    )

    assert result["ok"] is True
    assert result["applied"][0]["manager_request"]["path"] == "/customnode/install/git_url"
    assert executor.manager_requests[0]["body"] == "https://example.com/node.git"


def test_sudo_action_is_print_only(tmp_path):
    dry_run = dry_run_plan(
        {
            "summary": "Suggest swapoff",
            "actions": [
                {
                    "type": "sudo.print_command",
                    "payload": {"command": "sudo swapoff -a", "why": "avoid swap pressure"},
                }
            ],
        }
    )
    plan = dict(dry_run["plan"])
    plan["confirmed"] = True

    result = apply_plan(
        plan,
        approved_hash=dry_run["plan"]["plan_hash"],
        root=tmp_path,
        executor=RecordingExecutor(),
    )

    assert result["ok"] is True
    assert result["applied"][0] == {
        "type": "sudo.print_command",
        "command": "sudo swapoff -a",
        "executed": False,
    }


def test_runtime_free_memory_returns_frontend_http_request(tmp_path):
    dry_run = dry_run_plan(
        {"summary": "free", "actions": [{"type": "runtime.free_memory", "payload": {}}]}
    )
    plan = dict(dry_run["plan"])
    plan["confirmed"] = True

    result = apply_plan(
        plan,
        approved_hash=dry_run["plan"]["plan_hash"],
        root=tmp_path,
        executor=RecordingExecutor(),
    )

    assert result["applied"][0] == {
        "type": "runtime.free_memory",
        "http_request": {"path": "/free", "json": {}},
    }
