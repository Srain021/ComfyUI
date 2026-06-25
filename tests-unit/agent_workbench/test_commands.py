import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
AGENT_ROOT = REPO_ROOT / "custom_nodes" / "ComfyUI-AgentWorkbench"
sys.path.insert(0, str(AGENT_ROOT))

from agent_workbench.ops.commands import CommandRejected, validate_command
from agent_workbench.ops.runtime import (
    build_free_memory_request,
    docker_restart_command,
    free_memory_command,
    stop_ollama_model_command,
)


def test_rejects_sudo_and_shell_operators():
    with pytest.raises(CommandRejected):
        validate_command(["sudo", "systemctl", "stop", "ollama"])
    with pytest.raises(CommandRejected):
        validate_command(["bash", "-lc", "docker ps"])
    with pytest.raises(CommandRejected):
        validate_command(["docker", "ps", "&&", "whoami"])


def test_rejects_unsupported_or_destructive_docker_commands():
    with pytest.raises(CommandRejected):
        validate_command(["docker", "rm", "-f", "comfyui-gb10"])
    with pytest.raises(CommandRejected):
        validate_command(["docker", "exec", "comfyui-gb10", "python3"])


def test_allows_known_non_sudo_commands():
    assert validate_command(["docker", "ps", "-a"]) == ["docker", "ps", "-a"]
    assert validate_command(docker_restart_command()) == ["docker", "restart", "comfyui-gb10"]
    assert validate_command(
        ["docker", "compose", "-f", "dgx_spark_ltx_setup/docker-compose.yml", "up", "-d"]
    ) == ["docker", "compose", "-f", "dgx_spark_ltx_setup/docker-compose.yml", "up", "-d"]
    assert stop_ollama_model_command("nemotron-3-nano:30b") == [
        "ollama",
        "stop",
        "nemotron-3-nano:30b",
    ]
    assert validate_command(stop_ollama_model_command("nemotron-3-nano:30b"))
    assert validate_command(free_memory_command()) == ["free", "-h"]
    assert build_free_memory_request() == {"unload_models": True, "free_memory": True}


def test_allows_only_fixed_prerender_free_memory_script():
    assert validate_command(["bash", "dgx_spark_ltx_setup/prerender_free_memory.sh"]) == [
        "bash",
        "dgx_spark_ltx_setup/prerender_free_memory.sh",
    ]
    with pytest.raises(CommandRejected):
        validate_command(["bash", "scripts/anything_else.sh"])
    with pytest.raises(CommandRejected):
        validate_command(["bash", "-lc", "dgx_spark_ltx_setup/prerender_free_memory.sh"])


def test_curl_is_limited_to_local_comfyui_urls():
    assert validate_command(["curl", "-sS", "--fail", "http://127.0.0.1:8188/free"])
    with pytest.raises(CommandRejected):
        validate_command(["curl", "https://example.com"])
