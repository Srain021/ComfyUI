import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
AGENT_ROOT = REPO_ROOT / "custom_nodes" / "ComfyUI-AgentWorkbench"
sys.path.insert(0, str(AGENT_ROOT))

from agent_workbench import actions as agent_actions
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


def test_apply_dispatches_confirmed_compose_command_flag_change(tmp_path):
    compose_path = tmp_path / "dgx_spark_ltx_setup" / "docker-compose.yml"
    compose_path.parent.mkdir(parents=True)
    compose_path.write_text(COMPOSE_TEXT, encoding="utf-8")
    dry_run = dry_run_plan(
        {
            "summary": "Enable bf16 vae",
            "actions": [
                {
                    "type": "compose.set_command_flag",
                    "payload": {"flag": "--bf16-vae", "enabled": True},
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
    assert result["applied"][0]["type"] == "compose.set_command_flag"
    assert "- --bf16-vae" in compose_path.read_text(encoding="utf-8")
    assert executor.commands[-1] == [
        "docker",
        "compose",
        "-f",
        "dgx_spark_ltx_setup/docker-compose.yml",
        "up",
        "-d",
    ]


def test_apply_dispatches_confirmed_compose_up(tmp_path):
    dry_run = dry_run_plan(
        {
            "summary": "Apply compose config",
            "actions": [{"type": "service.compose_up", "payload": {}}],
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
    assert result["applied"][0]["type"] == "service.compose_up"
    assert executor.commands[-1] == [
        "docker",
        "compose",
        "-f",
        "dgx_spark_ltx_setup/docker-compose.yml",
        "up",
        "-d",
    ]


def test_apply_dispatches_confirmed_container_lifecycle_actions(tmp_path):
    dry_run = dry_run_plan(
        {
            "summary": "Stop and start ComfyUI",
            "actions": [
                {"type": "service.stop_container", "payload": {"container": "comfyui-gb10"}},
                {"type": "service.start_container", "payload": {"container": "comfyui-gb10"}},
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
    assert [row["type"] for row in result["applied"]] == [
        "service.stop_container",
        "service.start_container",
    ]
    assert executor.commands[-2:] == [
        ["docker", "stop", "comfyui-gb10"],
        ["docker", "start", "comfyui-gb10"],
    ]


def test_apply_dispatches_confirmed_prerender_free_memory_script(tmp_path):
    dry_run = dry_run_plan(
        {
            "summary": "Prepare memory before rendering",
            "actions": [{"type": "service.prerender_free_memory", "payload": {}}],
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
    assert result["applied"][0]["type"] == "service.prerender_free_memory"
    assert executor.commands[-1] == ["bash", "dgx_spark_ltx_setup/prerender_free_memory.sh"]


def test_apply_dispatches_confirmed_restore_original_script(tmp_path):
    dry_run = dry_run_plan(
        {
            "summary": "Restore original ComfyUI container config",
            "actions": [{"type": "service.restore_original", "payload": {}}],
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
    assert result["applied"][0]["type"] == "service.restore_original"
    assert executor.commands[-1] == ["bash", "dgx_spark_ltx_setup/restore_original.sh"]


def test_apply_dispatches_service_healthcheck_without_confirmation(tmp_path):
    dry_run = dry_run_plan(
        {
            "summary": "Check ComfyUI health",
            "actions": [{"type": "service.healthcheck", "payload": {}}],
        }
    )
    executor = RecordingExecutor()

    result = apply_plan(
        dry_run["plan"],
        approved_hash=dry_run["plan"]["plan_hash"],
        root=tmp_path,
        executor=executor,
    )

    assert result["ok"] is True
    assert result["applied"][0]["type"] == "service.healthcheck"
    assert executor.commands == [
        ["docker", "ps", "-a", "--filter", "name=comfyui-gb10"],
        ["docker", "logs", "--tail", "80", "comfyui-gb10"],
        ["curl", "-sS", "--fail", "http://127.0.0.1:8188/system_stats"],
        ["free", "-h"],
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


def test_service_restart_after_manager_request_is_deferred_until_frontend_completes(tmp_path):
    dry_run = dry_run_plan(
        {
            "summary": "Disable node and restart",
            "actions": [
                {"type": "custom_node.disable", "payload": {"id": "ComfyUI-TestNode"}},
                {
                    "type": "service.restart_container",
                    "payload": {"container": "comfyui-gb10"},
                },
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
    assert result["applied"][0]["manager_request"]["path"] == "/manager/queue/disable"
    assert result["applied"][1] == {
        "type": "service.restart_container",
        "deferred": True,
        "action_index": 1,
    }
    assert executor.commands == []

    assert hasattr(agent_actions, "apply_deferred_action")
    followup = agent_actions.apply_deferred_action(
        plan,
        approved_hash=dry_run["plan"]["plan_hash"],
        action_index=1,
        root=tmp_path,
        executor=executor,
    )

    assert followup["ok"] is True
    assert followup["applied"]["type"] == "service.restart_container"
    assert executor.commands[-1] == ["docker", "restart", "comfyui-gb10"]


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


def test_runtime_queue_prompt_returns_browser_required_action(tmp_path):
    dry_run = dry_run_plan(
        {
            "summary": "Queue current workflow",
            "actions": [{"type": "runtime.queue_prompt", "payload": {"front": True}}],
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

    assert result["applied"][0] == {
        "type": "runtime.queue_prompt",
        "browser_required": True,
        "payload": {"front": True},
    }


def test_runtime_clear_queue_returns_frontend_http_request(tmp_path):
    dry_run = dry_run_plan(
        {"summary": "Clear pending queue", "actions": [{"type": "runtime.clear_queue", "payload": {}}]}
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
        "type": "runtime.clear_queue",
        "http_request": {"path": "/queue", "json": {"clear": True}},
    }


def test_runtime_interrupt_returns_frontend_http_request(tmp_path):
    dry_run = dry_run_plan(
        {"summary": "Interrupt current generation", "actions": [{"type": "runtime.interrupt", "payload": {}}]}
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
        "type": "runtime.interrupt",
        "http_request": {"path": "/interrupt", "json": {}},
    }
