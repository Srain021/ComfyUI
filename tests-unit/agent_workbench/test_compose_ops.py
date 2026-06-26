import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
AGENT_ROOT = REPO_ROOT / "custom_nodes" / "ComfyUI-AgentWorkbench"
sys.path.insert(0, str(AGENT_ROOT))

from agent_workbench.ops.compose import (
    apply_command_flag,
    apply_command_value,
    apply_reserve_vram,
    patch_command_flag,
    patch_command_value,
    patch_reserve_vram,
    plan_command_flag,
    plan_command_value,
    plan_reserve_vram,
    validate_compose_text,
)


COMPOSE_TEXT = (
    "services:\n"
    "  comfyui-gb10:\n"
    "    command:\n"
    "      - main.py\n"
    "      - --reserve-vram\n"
    "      - \"8\"  # keep this comment\n"
)


def test_validate_compose_text_reads_service():
    data = validate_compose_text(COMPOSE_TEXT)

    assert "comfyui-gb10" in data["services"]


def test_runtime_compose_exposes_agent_ops_docker_channel():
    compose_path = REPO_ROOT / "dgx_spark_ltx_setup" / "docker-compose.yml"
    data = validate_compose_text(compose_path.read_text(encoding="utf-8"))
    service = data["services"]["comfyui-gb10"]

    volumes = service["volumes"]
    assert "/var/run/docker.sock:/var/run/docker.sock" in volumes
    assert "/usr/bin/docker:/usr/local/bin/docker:ro" in volumes
    assert (
        "/usr/libexec/docker/cli-plugins:/usr/local/lib/docker/cli-plugins:ro"
        in volumes
    )


def test_patch_reserve_vram_preserves_comment_line_shape():
    patched = patch_reserve_vram(COMPOSE_TEXT, "10")

    assert "- --reserve-vram" in patched
    assert "- \"10\"  # keep this comment" in patched


def test_patch_reserve_vram_rejects_missing_flag_or_bad_value():
    with pytest.raises(ValueError, match="reserve-vram flag not found"):
        patch_reserve_vram("services:\n  comfyui-gb10: {}\n", "10")
    with pytest.raises(ValueError, match="non-negative integer"):
        patch_reserve_vram(COMPOSE_TEXT, "10; rm -rf")


def test_plan_reserve_vram_reports_diff(tmp_path):
    compose_path = tmp_path / "docker-compose.yml"
    compose_path.write_text(COMPOSE_TEXT, encoding="utf-8")

    result = plan_reserve_vram(compose_path, "12")

    assert result["changed"] is True
    assert result["before"] == COMPOSE_TEXT
    assert "- \"12\"  # keep this comment" in result["after"]


def test_apply_reserve_vram_snapshots_before_write(tmp_path):
    compose_path = tmp_path / "docker-compose.yml"
    backup_dir = tmp_path / "backups"
    compose_path.write_text(COMPOSE_TEXT, encoding="utf-8")

    result = apply_reserve_vram(compose_path, " 9 ", backup_dir)

    assert Path(result["snapshot"]).read_text(encoding="utf-8") == COMPOSE_TEXT
    assert "- \"9\"  # keep this comment" in compose_path.read_text(encoding="utf-8")
    assert result["value"] == "9"


def test_patch_command_flag_adds_and_removes_boolean_flag():
    enabled = patch_command_flag(COMPOSE_TEXT, "--bf16-vae", enabled=True)

    assert "- --bf16-vae" in enabled
    assert enabled.index("- --reserve-vram") < enabled.index("- --bf16-vae")

    disabled = patch_command_flag(enabled, "--bf16-vae", enabled=False)

    assert disabled == COMPOSE_TEXT


def test_patch_command_flag_targets_comfyui_service_command():
    text = (
        "services:\n"
        "  helper:\n"
        "    command:\n"
        "      - helper.py\n"
        "  comfyui-gb10:\n"
        "    command:\n"
        "      - main.py\n"
    )

    patched = patch_command_flag(text, "--bf16-vae", enabled=True)

    assert "helper.py\n      - --bf16-vae" not in patched
    assert "main.py\n      - --bf16-vae" in patched


def test_patch_command_flag_rejects_bad_or_required_flags():
    with pytest.raises(ValueError, match="command flag must start"):
        patch_command_flag(COMPOSE_TEXT, "bf16-vae", enabled=True)
    with pytest.raises(ValueError, match="required GB10 flag"):
        patch_command_flag(COMPOSE_TEXT, "--reserve-vram", enabled=False)


def test_patch_command_value_updates_flag_value_preserving_comment():
    patched = patch_command_value(COMPOSE_TEXT, "--reserve-vram", "12")

    assert "- --reserve-vram" in patched
    assert "- \"12\"  # keep this comment" in patched


def test_patch_command_value_rejects_missing_or_bad_input():
    with pytest.raises(ValueError, match="command flag must start"):
        patch_command_value(COMPOSE_TEXT, "reserve-vram", "12")
    with pytest.raises(ValueError, match="command value must not be empty"):
        patch_command_value(COMPOSE_TEXT, "--reserve-vram", "")
    with pytest.raises(ValueError, match="flag value line is missing"):
        patch_command_value("services:\n  comfyui-gb10:\n    command:\n      - main.py\n", "--reserve-vram", "12")


def test_plan_and_apply_command_flag_report_diff_and_snapshot(tmp_path):
    compose_path = tmp_path / "docker-compose.yml"
    backup_dir = tmp_path / "backups"
    compose_path.write_text(COMPOSE_TEXT, encoding="utf-8")

    plan = plan_command_flag(compose_path, "--bf16-vae", enabled=True)
    result = apply_command_flag(compose_path, "--bf16-vae", True, backup_dir)

    assert plan["changed"] is True
    assert "- --bf16-vae" in plan["after"]
    assert Path(result["snapshot"]).read_text(encoding="utf-8") == COMPOSE_TEXT
    assert "- --bf16-vae" in compose_path.read_text(encoding="utf-8")
    assert result["flag"] == "--bf16-vae"
    assert result["enabled"] is True


def test_plan_and_apply_command_value_report_diff_and_snapshot(tmp_path):
    compose_path = tmp_path / "docker-compose.yml"
    backup_dir = tmp_path / "backups"
    compose_path.write_text(COMPOSE_TEXT, encoding="utf-8")

    plan = plan_command_value(compose_path, "--reserve-vram", "14")
    result = apply_command_value(compose_path, "--reserve-vram", "14", backup_dir)

    assert plan["changed"] is True
    assert "- \"14\"  # keep this comment" in plan["after"]
    assert Path(result["snapshot"]).read_text(encoding="utf-8") == COMPOSE_TEXT
    assert "- \"14\"  # keep this comment" in compose_path.read_text(encoding="utf-8")
    assert result["flag"] == "--reserve-vram"
    assert result["value"] == "14"
