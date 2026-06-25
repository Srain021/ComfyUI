import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
AGENT_ROOT = REPO_ROOT / "custom_nodes" / "ComfyUI-AgentWorkbench"
sys.path.insert(0, str(AGENT_ROOT))

from agent_workbench.ops.compose import (
    apply_reserve_vram,
    patch_reserve_vram,
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
